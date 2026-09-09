"""Synthetic vertical families: real Arrow reader boundary and strict normalization."""
import copy
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import overture_area as a
from geojson import convert
from overture_fixture import vertical_snapshot

class VerticalTests(unittest.TestCase):
    def layer(self, value):
        raw = json.dumps(value).encode()
        normalized, meta = a.parse(raw)
        return a.finish(convert(normalized, "synthetic", a.LICENSE, layer_id="a"*32, source_bytes=raw,
            coordinates={"mode":"wgs84-utm", "origin":[9,55], "local_origin_m":[512,512]}), meta)

    def test_dimensions_parent_mapping_and_order(self):
        value = vertical_snapshot(); original = copy.deepcopy(value)
        layer = self.layer(value)
        self.assertEqual(value, original)
        self.assertEqual([(p["after"]["base_cm"], p["after"]["height_cm"]) for p in layer.patches], [(200,400),(1000,300)])
        self.assertNotIn("base_m", layer.estimates)
        self.assertNotIn("height_m", layer.estimates)
        meta = layer.coordinates["overture"]
        self.assertEqual(meta["parent_sources"][0]["part_ids"], ["lower","upper"])
        self.assertEqual(meta["parent_sources"][0]["sources"], value["features"][0]["properties"]["sources"])
        self.assertEqual(meta["feature_sources"][0]["parent_id"], value["features"][0]["id"])
        self.assertEqual([f["building_ids"][0] for f in meta["feature_sources"]], [p["id"] for p in layer.patches])
        value["features"].reverse()
        self.assertEqual(self.layer(value).patches, layer.patches)
        self.assertEqual(self.layer(value).coordinates, layer.coordinates)

    def test_whole_source_rejections(self):
        for mode in ["orphan", "missing", "flag", "duplicate", "nested", "type", "height", "base", "negative", "bool", "underground", "level", "outside", "remainder", "part_outside", "sources", "ground"]:
            value = vertical_snapshot(); parent, lower, upper = value["features"]
            props = upper["properties"]
            if mode == "orphan": props["building_id"] = "missing"
            elif mode == "missing": value["features"] = [parent]
            elif mode == "flag": parent["properties"]["has_parts"] = False
            elif mode == "duplicate": value["features"].append(copy.deepcopy(upper))
            elif mode == "nested": props["has_parts"] = True
            elif mode == "type": props["type"] = "place"
            elif mode == "height": props.pop("height")
            elif mode == "base": props.pop("min_height"); props["min_floor"] = 2
            elif mode == "negative": props["min_height"] = -1
            elif mode == "bool": props["min_height"] = True
            elif mode == "underground": props["is_underground"] = True
            elif mode == "level": props["level"] = 1
            elif mode == "outside": value["bbox"][0] = 9.00015
            elif mode == "remainder":
                for f in [lower,upper]:
                    for pos in f["geometry"]["coordinates"][0][0]:
                        if pos[0] == 9.0002: pos[0] = 9.00018
            elif mode == "part_outside": upper["geometry"]["coordinates"][0][0][1][0] = 9.0003
            elif mode == "sources": parent["properties"]["sources"] = []
            elif mode == "ground": value["ground_m"] = float("inf")
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.layer(value)

    def test_profile_budgets_and_elevated_standalone(self):
        with patch.object(a, "MAX_VERTICAL_FEATURES", 2), self.assertRaisesRegex(ValueError,"256"):
            self.layer(vertical_snapshot())
        with patch.object(a, "MAX_VERTICAL_POINTS", 10), self.assertRaisesRegex(ValueError,"point budget"):
            self.layer(vertical_snapshot())
        value = vertical_snapshot(); value["features"] = [value["features"][2]]
        p = value["features"][0]["properties"]; p.pop("building_id"); p["type"] = "building"
        self.assertEqual(self.layer(value).patches[0]["after"]["base_cm"], 1000)
        value.pop("include_parts"); value.pop("ground_m")
        with self.assertRaises(ValueError): self.layer(value)

    def test_both_arrow_queries_and_exclusive_capture(self):
        import pyarrow as pa
        import overturemaps.core as core
        from shapely.geometry import shape
        value = vertical_snapshot(); query = a.checked_plan(value); calls = []
        def reader(kind, **kwargs):
            calls.append((kind,kwargs))
            rows = []
            for f in value["features"]:
                if f["properties"]["type"] == kind:
                    rows.append(dict(f["properties"], geometry=shape(f["geometry"]).wkb))
            table = pa.Table.from_pylist(rows)
            return pa.RecordBatchReader.from_batches(table.schema, table.to_batches())
        with tempfile.TemporaryDirectory() as directory, patch.object(core,"record_batch_reader", reader):
            root = Path(directory); events = []
            result = a.acquire(query, root/"partial", root/"source", lambda *args: events.append(args))
            raw = (root/"source").read_bytes()
            self.assertEqual(len(self.layer(json.loads(raw)).patches), 2)
            self.assertEqual(result["actual_bytes"], len(raw))
            self.assertEqual([c[0] for c in calls], ["building","building_part"])
            self.assertTrue(all(c[1]["bbox"] == query["bbox"] and c[1]["release"] == query["release"] for c in calls))
            self.assertEqual(events[-1], (len(raw), a.MAX_INPUT))
            with self.assertRaises(FileExistsError): a.acquire(query, root/"again", root/"source", lambda *args:None)
            self.assertEqual((root/"source").read_bytes(),raw)

    def test_second_reader_failure_never_publishes(self):
        value = vertical_snapshot(); query = a.checked_plan(value)
        def failed(query):
            yield value["features"][0]
            raise OSError("parts interrupted")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(OSError): a.acquire(query,root/"partial",root/"source",lambda *args:None,failed)
            self.assertFalse((root/"source").exists())

if __name__ == "__main__": unittest.main()
