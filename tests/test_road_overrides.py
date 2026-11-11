"""Snapshot-bound author corrections; synthetic sources only."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import road_overrides
from osm_roads import dimensions

class Overrides(unittest.TestCase):
    def setUp(self):
        self.request = {"osm_sha256": "a" * 64, "ways": [{"source_id": "way/1", "width_m": 20, "lanes": 6}]}
        self.source = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0,0], [1,0]]}, "properties": {"osm_source_id": "way/1", "_city_road_tags": {"highway": "primary"}}}]}

    def test_atomic_deterministic_correction_and_receipt(self):
        before = copy.deepcopy(self.source)
        result, receipt = road_overrides.apply(self.source, self.request, "a"*64)
        self.assertEqual(self.source, before)
        self.assertEqual((result, receipt), road_overrides.apply(self.source, self.request, "a"*64))
        self.assertEqual(dimensions(result["features"][0]), (20,6,3.25,"author"))
        self.assertEqual(receipt["applied"][0]["original_width_m"], None)
        self.assertEqual(receipt["request"], self.request)
        for bad in ["b"*64, ""]:
            with self.assertRaisesRegex(ValueError, "mismatch"): road_overrides.apply(self.source, self.request, bad)
        self.request["ways"].append({"source_id":"way/2","width_m":20,"lanes":6})
        with self.assertRaisesRegex(ValueError, "way/2"): road_overrides.apply(self.source,self.request,"a"*64)
        self.assertEqual(self.source,before)

    def test_schema_and_non_road_duplicates(self):
        for key, value in [("lanes",17),("lanes",True),("lanes",1.5),("width_m",float("nan")),("source_id","relation/1")]:
            bad=copy.deepcopy(self.request); bad["ways"][0][key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): road_overrides.validate(bad)
        bad=copy.deepcopy(self.request);bad["ways"]*=2
        with self.assertRaises(ValueError): road_overrides.validate(bad)
        polygon={"properties":{"osm_source_id":"way/1"},"geometry":{"type":"Polygon","coordinates":[]}}
        self.source["features"].append(polygon)
        result,_=road_overrides.apply(self.source,self.request,"a"*64)
        self.assertEqual(result["features"][1],polygon)
