import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from pbf_places import lookup
from pbf_places_fixture import XML, pbf


class PlaceLookup(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def run_lookup(self, query, xml=XML, event=lambda *args: None, point=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.pbf"
            raw = pbf(source, xml)
            try:
                value = lookup(source, query, root, event, point)
                self.assertEqual(value["source_sha256"], hashlib.sha256(raw).hexdigest())
                return value
            finally:
                self.assertEqual(source.read_bytes(), raw)
                self.assertEqual(sorted(p.name for p in root.iterdir()), ["original.pbf"])

    def test_korean_english_exact_extent_and_byte_progress(self):
        for query in ("가상시", "synthetic"):
            events = []
            value = self.run_lookup(query, event=lambda *args: events.append(args))
            place = value["places"][0]
            self.assertEqual(place["bbox"], [9,55,9.0002,55.0002])
            self.assertEqual(place["name"], "가상시")
            self.assertEqual(place["source_id"], "relation/10")
            self.assertFalse(place["issue"])
            for stage in ("read", "index_relations", "index_ways", "index_nodes"):
                steps = [x for x in events if x[0] == stage]
                self.assertEqual(steps[0][1], 0)
                self.assertEqual(steps[-1][1:3], (value["source_bytes"],)*2)
        self.assertFalse(self.run_lookup("unknown")["places"])

    def test_missing_and_nested_outer_never_guess(self):
        for xml in (XML.replace('type="way" ref="1" role="outer"', 'type="way" ref="999" role="outer"'),
                    XML.replace('ref="11" role="subarea"', 'ref="11" role="outer"')):
            place = self.run_lookup("가상", xml)["places"][0]
            self.assertTrue(place["issue"])
            self.assertEqual(place["bbox"], [])
            self.assertEqual(place["outlines"], [])

    def test_cancel_and_budget_clean_owned_capture(self):
        def cancel(stage, completed, total):
            if stage == "index_ways": raise ValueError("controlled cancellation")
        with self.assertRaisesRegex(ValueError, "controlled cancellation"):
            self.run_lookup("가상", event=cancel)
        expected = self.run_lookup("가상")
        self.assertEqual(expected["limit_warnings"], [])
        with patch("pbf_places.MAX_REFS", 1):
            warned = self.run_lookup("가상")
        self.assertEqual(warned["places"], expected["places"])
        self.assertTrue(any(w.startswith("Limit warning: PBF boundary reference budget exceeded") for w in warned["limit_warnings"]))
        with patch("pbf_places.REFS_CEILING", 1), self.assertRaisesRegex(ValueError, "references exceed"):
            self.run_lookup("가상")
        with self.assertRaisesRegex(ValueError,"name"):
            self.run_lookup("")


    def test_named_places_with_containing_areas_and_country(self):
        xml = XML.replace("</osm>", '''<node id="50" lon="9.0001" lat="55.0001"><tag k="place" v="village"/><tag k="name" v="가상마을"/></node>
<node id="51" lon="9.0001" lat="55.0001"><tag k="amenity" v="school"/><tag k="name:ko" v="가상마을"/></node>
<relation id="12"><member type="way" ref="1" role="outer"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="2"/>
<tag k="name" v="가상국"/><tag k="ISO3166-1:alpha2" v="ZZ"/><tag k="driving_side" v="left"/></relation></osm>''').replace(
            '<tag k="highway" v="residential"/>', '<tag k="highway" v="residential"/><tag k="name" v="가상마을"/>')
        value = self.run_lookup("가상마을", xml)
        self.assertEqual(value["places"], [])
        anchors = value["anchors"]
        self.assertEqual([a["source_id"] for a in anchors], ["node/50", "node/51", "way/2"])
        self.assertEqual([a["kind"] for a in anchors], ["place=village", "amenity=school", "highway=residential"])
        self.assertLess(anchors[0]["tier"], anchors[1]["tier"])
        self.assertEqual(anchors[0]["point"], [9.0001, 55.0001])
        self.assertEqual(anchors[2]["point"], [9.00075, 55.0])  # a way's bbox centre
        areas = anchors[0]["context"]["areas"]
        self.assertEqual([a["source_id"] for a in areas], ["relation/10", "relation/12"])
        self.assertEqual(areas[0]["bbox"], [9, 55, 9.0002, 55.0002])
        self.assertGreater(areas[0]["km2"], 0)
        self.assertEqual(anchors[0]["context"]["country"], dict(code="ZZ", name="가상국", driving_side="left", basis="boundary"))
        # Outside every boundary: no areas, the extract's only country.
        self.assertEqual(anchors[2]["context"], dict(areas=[], country=dict(code="ZZ", name="가상국", driving_side="left", basis="extract")))
        # A matched administrative area carries the context of its centre.
        place = self.run_lookup("가상시", xml)["places"][0]
        self.assertEqual(place["context"]["country"]["basis"], "boundary")
        point = self.run_lookup("", xml, point=[9.0001, 55.0001])
        self.assertEqual((point["places"], point["anchors"]), ([], []))
        self.assertEqual([a["source_id"] for a in point["point_context"]["areas"]], ["relation/10", "relation/12"])
        with self.assertRaisesRegex(ValueError, "Point"):
            self.run_lookup("", xml, point=[200, 0])

    def test_subdivision_code_names_the_country_of_an_incomplete_country_boundary(self):
        xml = XML.replace('<tag k="name:en" v="Synthetic City"/>', '<tag k="name:en" v="Synthetic City"/><tag k="ISO3166-2" v="JP-27"/>').replace("</osm>", '''
<node id="50" lon="9.0001" lat="55.0001"><tag k="place" v="town"/><tag k="name" v="가상"/></node>
<relation id="12"><member type="way" ref="999" role="outer"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="2"/>
<tag k="name" v="日本"/><tag k="ISO3166-1" v="JP"/></relation></osm>''')
        anchor = self.run_lookup("가상", xml)["anchors"][0]
        self.assertEqual([a["source_id"] for a in anchor["context"]["areas"]], ["relation/10"])
        self.assertEqual(anchor["context"]["country"], dict(code="JP", name="日本", driving_side="", basis="subdivision"))

    def test_cut_boundaries_spanning_the_place_name_its_country(self):
        # A regional extract: the state boundary keeps only a far way around the place.
        xml = XML.replace("</osm>", '''
<node id="50" lon="9.0001" lat="55.0001"><tag k="place" v="town"/><tag k="name" v="가상"/></node>
<node id="60" lon="8" lat="54"/><node id="61" lon="10" lat="56"/>
<way id="60"><nd ref="60"/><nd ref="61"/></way>
<relation id="12"><member type="way" ref="60" role="outer"/><member type="way" ref="999" role="outer"/><tag k="boundary" v="administrative"/>
<tag k="admin_level" v="4"/><tag k="name" v="가상주"/><tag k="ISO3166-2" v="US-CA"/></relation>
<relation id="13"><member type="way" ref="998" role="outer"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="2"/>
<tag k="name" v="Mexico"/><tag k="ISO3166-1" v="MX"/></relation></osm>''')
        anchor = self.run_lookup("가상", xml)["anchors"][0]
        self.assertEqual(anchor["context"]["country"], dict(code="US", name="", driving_side="", basis="partial"))

    def test_region_is_the_exact_boundary_union_and_never_guesses(self):
        from pbf_places import region
        from osm_extract import dependency
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pbf"
            pbf(path, XML)
            geometry, areas = region(path, [10], dependency())
            self.assertEqual(areas, [dict(source_id="relation/10", name="가상시")])
            self.assertEqual(geometry.bounds, (9, 55, 9.0002, 55.0002))
            self.assertAlmostEqual(geometry.area, 0.0002 * 0.0002)
            for ids, message in (([99], "missing"), ([], "Choose"), ([10, 10], "Choose")):
                with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, message): region(path, ids, dependency())
            missing = Path(directory) / "missing.pbf"
            pbf(missing, XML.replace('type="way" ref="1" role="outer"', 'type="way" ref="999" role="outer"'))
            with self.assertRaisesRegex(ValueError, "incomplete boundary"): region(missing, [10], dependency())


    def test_streaming_cli_clips_to_selected_areas(self):
        import json, subprocess, sys
        from osm_extract import LICENSE
        script = Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf"
            # A separate boundary way, as in real extracts, around part of the fixture.
            from osm_fixture import XML as BASE
            boundary = BASE.replace("</osm>", '''<node id="101" lon="8.99995" lat="54.99995"/><node id="102" lon="9.0012" lat="54.99995"/>
<node id="103" lon="9.0012" lat="55.0003"/><node id="104" lon="8.99995" lat="55.0003"/>
<way id="101"><nd ref="101"/><nd ref="102"/><nd ref="103"/><nd ref="104"/><nd ref="101"/></way>
<relation id="20"><member type="way" ref="101" role="outer"/><tag k="type" v="boundary"/><tag k="boundary" v="administrative"/>
<tag k="admin_level" v="8"/><tag k="name" v="서쪽구"/></relation></osm>''')
            raw = pbf(source, boundary)
            def run(box, name):
                output = Path(directory)/name
                command = [sys.executable,"-B",str(script),str(source),str(output),"--input-format","pbf","--osm-stream","--osm-bbox",*map(str,box),
                    "--osm-areas","20","--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",LICENSE,"--layer-id","a"*32]
                return subprocess.run(command,capture_output=True,timeout=60,text=True), output
            result, output = run([8.9999,54.9999,9.006,55.006], "layer.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            crop = json.loads(output.read_bytes())["coordinates"]["osm_crop"]
            self.assertEqual((crop["region"], crop["areas"]), ("administrative-union-v1", [dict(source_id="relation/20", name="서쪽구")]))
            self.assertGreater(crop["counts"]["outside_features"], 0)
            result, _ = run([9,55,9.0001,55.0001], "small.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("beyond the crop rectangle", result.stderr)
            self.assertEqual(source.read_bytes(), raw)


if __name__ == "__main__": unittest.main()
