"""Real-city source acquisition with recorded responses; tests never use the network."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acquire_city_sources as acquire

XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="Overpass API 0.7.62">
<meta osm_base="2026-11-12T00:00:00Z"/>
  <node id="1" lat="55.0" lon="9.0" version="2" timestamp="2020-01-01T00:00:00Z" changeset="1" uid="1" user="a"/>
  <node id="2" lat="55.001" lon="9.001" version="1" timestamp="2020-01-01T00:00:00Z" changeset="1" uid="1" user="a"/>
  <way id="10" version="3" timestamp="2020-01-01T00:00:00Z" changeset="1" uid="1" user="a"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
</osm>
"""
COUNTRY = {"elements": [{"type": "relation", "tags": {"admin_level": "2", "ISO3166-1:alpha2": "DK", "boundary": "administrative"}}]}


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()


def fake(routes):
    """request() stand-in: the first route whose key occurs in the URL or body answers."""
    calls = []

    def call(url, data=None, timeout=60):
        text = url + (data.decode() if data else "")
        calls.append(text)
        for key, answer in routes:
            if key in text:
                if isinstance(answer, Exception): raise answer
                return Response(answer if isinstance(answer, bytes) else json.dumps(answer).encode())
        raise AssertionError("unexpected request " + url)
    return call, calls


class AcquireTests(unittest.TestCase):
    def test_search_is_cached_identified_and_parsed(self):
        rows = [{"lat": "37.57", "lon": "126.98", "name": "종로구", "display_name": "종로구, 서울", "category": "boundary", "type": "administrative",
                 "osm_type": "relation", "osm_id": 2419946, "boundingbox": ["37.56", "37.63", "126.94", "127.02"], "address": {"country_code": "kr"}},
                {"lat": "nan", "lon": "x"}]
        call, calls = fake([("nominatim", rows)])
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call):
            first = acquire.search("  종로구 ", Path(folder), "ko")
            second = acquire.search("종로구", Path(folder), "ko")
        self.assertEqual(len(calls), 1)
        self.assertIn("accept-language=ko", calls[0])
        self.assertFalse(first["cached"]); self.assertTrue(second["cached"])
        self.assertEqual(first["results"], [{"name": "종로구", "display_name": "종로구, 서울", "point": [126.98, 37.57], "kind": "boundary/administrative",
                                              "source_id": "relation/2419946", "bbox": [126.94, 37.56, 127.02, 37.63], "country": "KR", "supported": True}])
        for bad in ("", "x" * 257):
            with self.assertRaises(ValueError): acquire.search(bad, Path("/nonexistent"))

    def test_user_agent_is_fixed_client_name(self):
        seen = {}
        def opener(req, timeout):
            seen.update(dict(req.header_items()))
            return Response(b"[]")
        with patch.object(acquire, "urlopen", opener):
            acquire.request("https://example.invalid/")
        self.assertEqual(seen["User-agent"], acquire.USER_AGENT)

    def test_overpass_query_reads_box_relations_and_members(self):
        query = acquire.overpass_query([9.0, 55.0, 9.1, 55.1])
        self.assertIn("[bbox:55.0000000,9.0000000,55.1000000,9.1000000]", query)
        for part in ("rel[type=multipolygon]", "boundary=protected_area", "rel[type=site]", "(._;>;)", "out meta"):
            self.assertIn(part, query)
        self.assertNotIn("route", query)

    def test_osm_snapshot_pbf_header_manifest_and_reuse(self):
        import osmium
        call, calls = fake([("is_in", COUNTRY), ("out+meta", XML.encode())])
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call):
            cache = Path(folder)
            value = acquire.osm([9.0, 55.0], 1.0, "square", cache)
            again = acquire.osm([9.0, 55.0], 1.0, "square", cache)
            reader = osmium.io.Reader(value["path"], osmium.osm.NOTHING)
            box = reader.header().box(); reader.close()
            self.assertTrue(box.valid())
            self.assertTrue(acquire.covers([box.bottom_left.lon, box.bottom_left.lat, box.top_right.lon, box.top_right.lat], value["extent_bounds"]))
            self.assertEqual(value["counts"], {"nodes": 2, "ways": 1, "relations": 0})
            self.assertEqual(value["country"], {"code": "DK", "driving_side": "", "basis": "boundary"})
            self.assertEqual(value["sha256"], acquire.file_identity(Path(value["path"]))["sha256"])
            self.assertTrue(again["cached"]); self.assertEqual(again["path"], value["path"])
            self.assertEqual(len(calls), 2)
            self.assertEqual([p.name for p in (cache / "osm").iterdir() if p.name.startswith(".")], [])
            check = acquire.preflight(dict(center=[9.0, 55.0], radius_km=1.0, shape="square"), value["path"])
            self.assertTrue(check["ok"], check)
            self.assertEqual(check["pbf"]["basis"], "header")

    def test_overpass_runtime_error_publishes_nothing(self):
        broken = XML.replace("</osm>", "<remark> runtime error: Query timed out </remark>\n</osm>").encode()
        for answer, message in ((broken, "did not finish"), (b"<html>busy</html>", "no OSM data"), (XML[:-8].encode(), "truncated"),
                                (HTTPError("u", 400, "Bad Request", {}, None), "HTTP 400")):
            call, _ = fake([("is_in", COUNTRY), ("out+meta", answer)])
            with self.subTest(message=message), tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call):
                with self.assertRaisesRegex(ValueError, message):
                    acquire.osm([9.0, 55.0], 1.0, "circle", Path(folder))
                self.assertEqual(list((Path(folder) / "osm").iterdir()), [])

    def test_busy_overpass_is_retried_then_succeeds(self):
        answers = [HTTPError("u", 504, "Gateway Timeout", {}, None), HTTPError("u", 502, "Bad Gateway", {}, None), XML.encode()]
        def call(url, data=None, timeout=60):
            if "is_in" in data.decode(): return Response(json.dumps(COUNTRY).encode())
            answer = answers.pop(0)
            if isinstance(answer, Exception): raise answer
            return Response(answer)
        waits = []
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call), patch.object(acquire.time, "sleep", waits.append):
            value = acquire.osm([9.0, 55.0], 0.5, "circle", Path(folder))
        self.assertEqual(waits, list(acquire.RETRY_WAITS_S))
        self.assertEqual(value["counts"]["ways"], 1)

    def test_radius_cap_and_shape(self):
        for extent in (dict(center=[9, 55], radius_km=2.6), dict(center=[9, 55], radius_km=0), dict(center=[9, 55], radius_km=1, shape="hex")):
            with self.assertRaises(ValueError): acquire.extent_value(extent)
        self.assertGreater(acquire.extent_value(dict(center=[9, 55], radius_km=1, shape="square"))[0].area,
                           acquire.extent_value(dict(center=[9, 55], radius_km=1))[0].area)

    def test_dem_records_absent_sea_tiles_and_preflight_reports_missing(self):
        from copernicus_dem import tile_filename
        call, _ = fake([("Copernicus_DSM", HTTPError("u", 404, "Not Found", {}, None))])
        extent = dict(center=[9.5, 55.5], radius_km=1.0)
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call):
            tiles = Path(folder) / "tiles"
            missing = acquire.preflight(extent, dem_folder=tiles)
            self.assertFalse(missing["ok"])
            self.assertIn(tile_filename([9, 55]), missing["errors"][0])
            value = acquire.dem(acquire.extent_value(extent)[1], tiles)
            self.assertEqual(value["tiles"], []); self.assertEqual(value["absent"], [tile_filename([9, 55])])
            after = acquire.preflight(extent, dem_folder=tiles)
            self.assertTrue(after["ok"]); self.assertEqual(after["dem"]["absent"], [tile_filename([9, 55])])

    def test_dem_refuses_unrecorded_existing_tile(self):
        from copernicus_dem import tile_filename
        with tempfile.TemporaryDirectory() as folder:
            tiles = Path(folder)
            (tiles / tile_filename([9, 55])).write_bytes(b"user file")
            with self.assertRaisesRegex(ValueError, "without its acquisition record"):
                acquire.dem([9.4, 55.4, 9.6, 55.6], tiles)
            self.assertEqual((tiles / tile_filename([9, 55])).read_bytes(), b"user file")

    def test_preflight_pbf_outside_extent_and_missing_file(self):
        call, _ = fake([("is_in", COUNTRY), ("out+meta", XML.encode())])
        with tempfile.TemporaryDirectory() as folder, patch.object(acquire, "request", call):
            value = acquire.osm([9.0, 55.0], 0.5, "circle", Path(folder), margin_m=0)
            far = acquire.preflight(dict(center=[9.5, 55.0], radius_km=0.5), value["path"])
            self.assertFalse(far["ok"]); self.assertIn("does not cover", far["errors"][0])
            gone = acquire.preflight(dict(bbox=[9, 55, 9.01, 55.01]), Path(folder) / "none.pbf")
            self.assertFalse(gone["ok"])


if __name__ == "__main__":
    unittest.main()
