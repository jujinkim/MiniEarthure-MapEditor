"""Bounded synthetic multipart road sources; no datasets or network access."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from geojson import convert
from projection import Coordinates


def fixture():
    return {"type": "FeatureCollection", "features": [{"type": "Feature",
        "properties": {"width_m": 6, "surface": "gravel", "elevation_m": 0.2, "level": 0},
        "geometry": {"type": "MultiLineString", "coordinates": [
            [[40, 40], [100, 40], [150, 60]], [[150, 60], [200, 60]],
            [[240, 100], [180, 100]]]}}]}


class MultiLineTests(unittest.TestCase):
    def test_part_identity_order_properties_and_source(self):
        value = fixture()
        original = copy.deepcopy(value)
        raw = json.dumps(value).encode()
        a = convert(value, "synthetic roads", "MIT", layer_id="a" * 32, source_bytes=raw)
        self.assertEqual(a.encode(), convert(value, "synthetic roads", "MIT", layer_id="a" * 32, source_bytes=raw).encode())
        self.assertEqual(value, original)
        self.assertEqual(a.feature_count, 1)
        self.assertEqual(a.point_count, 7)
        self.assertEqual(len(a.patches), 9)
        self.assertEqual(a.source.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(a.source.bytes, len(raw))
        self.assertEqual(a.source.accuracy, "unknown")
        roads = [p["after"] for p in a.patches if p["field"] == "roads"]
        ids = [f"import-{'a' * 32}-0-part-{i}" for i in range(3)]
        self.assertEqual([r["id"] for r in roads], ids)
        self.assertEqual(a.coordinates["geojson_multilines"], {
            "profile": "disconnected-parts-v1", "features": [dict(feature=0, road_ids=ids, point_counts=[3, 2, 2])]})
        self.assertEqual(roads[0]["points"][-1], roads[1]["points"][0])
        self.assertNotEqual(roads[0]["to"], roads[1]["from"])
        self.assertEqual(roads[2]["points"], [[24000, 20, 10000], [18000, 20, 10000]])
        for road in roads:
            self.assertEqual(road["widths_cm"], [600] * (len(road["points"]) - 1))
            self.assertEqual(road["surfaces"], ["gravel"] * (len(road["points"]) - 1))
            self.assertEqual(road["kind"], "ground")

    def test_mixed_features_single_part_and_fresh_namespace(self):
        value = fixture()
        single = copy.deepcopy(value["features"][0])
        single["geometry"] = dict(type="LineString", coordinates=[[40, 200], [80, 200]])
        value["features"].insert(0, single)
        value["features"][1]["geometry"]["coordinates"] = [[[150, 60], [200, 60]]]
        progress = []
        a = convert(value, "mixed", "MIT", progress=lambda c, t: progress.append((c, t)))
        b = convert(value, "mixed", "MIT")
        self.assertEqual(a.feature_count, 2)
        self.assertEqual(a.point_count, 4)
        self.assertTrue(a.patches[2]["id"].endswith("-0"))
        self.assertTrue(a.patches[5]["id"].endswith("-1-part-0"))
        self.assertEqual(a.coordinates["geojson_multilines"]["features"][0]["feature"], 1)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertTrue(set(p["id"] for p in a.patches).isdisjoint(p["id"] for p in b.patches))

    def test_estimates_and_warning_samples_count_output_parts(self):
        value = fixture()
        value["features"][0]["properties"] = {}
        value["features"][0]["geometry"]["coordinates"] = [[[10, 10], [50, 10]]] * 60
        result = convert(value, "many", "MIT")
        self.assertEqual(result.estimates, dict(elevation_m=60, level=60, width_m=60, surface=60))
        self.assertEqual((result.warning_count, len(result.warnings)), (60, 50))
        self.assertIn("0 part 49", result.warnings[-1])

    def test_invalid_last_part_rejects_entire_candidate(self):
        for bad in [None, {}, [], [1, 2], [[1, 2]], [[1, 2], [True, 2]],
                    [[1, 2], [float("inf"), 2]], [[1, 2], [2, 3, 4]], [[1, 2], [100001, 3]]]:
            with self.subTest(bad=bad):
                value = fixture()
                value["features"][0]["geometry"]["coordinates"].append(bad)
                with self.assertRaises(ValueError): convert(value, "bad", "MIT", source_bytes=b"synthetic")
        for coordinates in [[], None, {}]:
            value = fixture()
            value["features"][0]["geometry"]["coordinates"] = coordinates
            with self.assertRaises(ValueError): convert(value, "bad", "MIT")

    def test_reserved_structural_input_not_flattened(self):
        for key in ["osm_node_refs", "elevations_m", "road_kind", "clearance_m"]:
            value = fixture()
            value["features"][0]["properties"][key] = None
            with self.assertRaisesRegex(ValueError, "structural/OSM"):
                convert(value, "bad", "MIT")
        with self.assertRaisesRegex(ValueError, "structural/OSM"):
            convert(fixture(), "bad", "MIT", osm_graph=True)

    def test_existing_aggregate_budgets_include_all_parts(self):
        # Record admission occurs before any projection or part allocation.
        value = fixture()
        value["features"][0]["geometry"]["coordinates"] = [None] * 20001
        with patch.object(Coordinates, "point", side_effect=AssertionError("projected before admission")):
            with self.assertRaisesRegex(ValueError, "record budget"):
                convert(value, "budget", "MIT", source_bytes=b"synthetic")
        with patch("import_layer.MAX_POINTS", 6):
            with self.assertRaisesRegex(ValueError, "coordinate budget"):
                convert(fixture(), "budget", "MIT")
        with patch("import_layer.MAX_OUTPUT", 32):
            with self.assertRaisesRegex(ValueError, "12 MiB"):
                convert(fixture(), "budget", "MIT")

    def test_wgs84_matches_explicit_projected_parts(self):
        value = fixture()
        value["features"][0]["geometry"]["coordinates"] = [
            [[9, 55], [9.0002, 55]], [[9.0002, 55.0002], [9, 55.0002]]]
        options = dict(mode="wgs84-utm", origin=[9, 55], local_origin_m=[512, 512])
        geo = convert(value, "geo", "MIT", layer_id="a" * 32, coordinates=options)
        local = fixture()
        local["features"][0]["geometry"]["coordinates"] = [
            [[512, 512], [524.79, 512]], [[524.79, 534.26], [512, 534.26]]]
        self.assertEqual(geo.patches, convert(local, "local", "MIT", layer_id="a" * 32).patches)
        value["features"][0]["geometry"]["coordinates"][-1][-1] = [13, 55]
        with self.assertRaises(ValueError): convert(value, "geo", "MIT", coordinates=options)

    def test_cli_atomic_output_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "roads with spaces.geojson"
            output = Path(directory) / "candidate.json"
            value = fixture()
            source.write_text(json.dumps(value))
            original = source.read_bytes()
            command = [sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "scripts/importers/geojson.py"),
                       str(source), str(output), "--coordinates", "local-metres", "--license", "MIT", "--layer-id", "a" * 32]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            accepted = output.read_bytes()
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(len(json.loads(accepted)["patches"]), 9)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), accepted)
            value["features"][0]["geometry"]["coordinates"].append([])
            source.write_text(json.dumps(value))
            command[4] = str(Path(directory) / "must-not-exist.json")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse(Path(command[4]).exists())


if __name__ == "__main__":
    unittest.main()
