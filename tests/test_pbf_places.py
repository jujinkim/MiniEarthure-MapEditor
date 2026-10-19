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
    def run_lookup(self, query, xml=XML, event=lambda *args: None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.pbf"
            raw = pbf(source, xml)
            try:
                value = lookup(source, query, root, event)
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
        with patch("pbf_places.MAX_REFS", 1), self.assertRaisesRegex(ValueError, "reference budget"):
            self.run_lookup("가상")
        with self.assertRaisesRegex(ValueError,"name"):
            self.run_lookup("")


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
