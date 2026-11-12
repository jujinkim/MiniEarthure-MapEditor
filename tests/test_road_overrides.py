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


class SegmentOverrides(unittest.TestCase):
    """Author re-routing between adjacent source nodes (Osaka-shaped synthetic data)."""
    def setUp(self):
        self.road = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[135.500, 34.68], [135.501, 34.68], [135.502, 34.68]]},
                     "properties": {"osm_source_id": "way/9", "_city_road_tags": {"highway": "primary", "lanes": "5"}, "width_m": 16.75, "_city_refs": [11, 12, 13]}}
        self.other = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[135.501, 34.68], [135.501, 34.681]]},
                      "properties": {"osm_source_id": "way/10", "_city_road_tags": {"highway": "residential"}, "_city_refs": [12, 14]}}
        self.source = {"type": "FeatureCollection", "features": [self.road, self.other]}
        south = 34.68 - 2.5 / 111195  # 2.5 m south
        self.segment = {"from_node": 12, "to_node": 13, "max_displacement_m": 3, "points": [[135.5013, south], [135.5017, south]]}
        self.request = {"osm_sha256": "a" * 64, "ways": [{"source_id": "way/9", "segments": [self.segment]}]}

    def test_inserts_points_and_keeps_nodes(self):
        before = copy.deepcopy(self.source)
        result, receipt = road_overrides.apply(self.source, self.request, "a" * 64)
        self.assertEqual(self.source, before)
        road = result["features"][0]
        refs = road["properties"]["_city_refs"]
        self.assertEqual([refs[0], refs[1], refs[-1]], [11, 12, 13])
        base = road_overrides.OVERRIDE_REF_BASE + 9 * 10000
        self.assertEqual(refs[2:4], [base + 1, base + 2])
        self.assertEqual(road["geometry"]["coordinates"][2:4], self.segment["points"])
        self.assertTrue(road["properties"]["_city_author_geometry"])
        self.assertNotIn("_city_author_override", road["properties"])
        self.assertEqual(result["features"][1], self.other)
        applied = receipt["applied"][0]
        self.assertEqual(applied["original_width_m"], 16.75)
        self.assertNotIn("width_m", applied)
        segment = applied["segments"][0]
        self.assertEqual(segment["original_wgs84"], [[135.501, 34.68], [135.502, 34.68]])
        self.assertAlmostEqual(segment["max_offset_m"], 2.5, delta=0.02)  # UTM metres
        self.assertEqual((result, receipt), road_overrides.apply(self.source, self.request, "a" * 64))

    def test_reversed_way_order_and_heights(self):
        self.road["geometry"]["coordinates"] = [[135.502, 34.68, 4.0], [135.501, 34.68, 2.0], [135.500, 34.68, 0.0]]
        self.road["properties"]["_city_refs"] = [13, 12, 11]
        result, receipt = road_overrides.apply(self.source, self.request, "a" * 64)
        coords = result["features"][0]["geometry"]["coordinates"]
        self.assertEqual([c[:2] for c in coords[1:3]], list(reversed(self.segment["points"])))
        self.assertTrue(all(2.0 < c[2] < 4.0 for c in coords[1:3]))
        self.assertEqual(receipt["applied"][0]["segments"][0]["from_node"], 12)

    def test_refusals_are_atomic(self):
        far = copy.deepcopy(self.segment); far["points"][0][1] -= 2 / 111195
        backwards = copy.deepcopy(self.segment); backwards["points"].reverse()
        outside = copy.deepcopy(self.segment); outside["points"][1][0] = 135.5021
        absent = copy.deepcopy(self.segment); absent["from_node"] = 11
        for bad, message in [(far, "max_displacement"), (backwards, "advance"), (outside, "between"), (absent, "one adjacent")]:
            request = copy.deepcopy(self.request); request["ways"][0]["segments"] = [bad]
            before = copy.deepcopy(self.source)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                road_overrides.apply(self.source, request, "a" * 64)
            self.assertEqual(self.source, before)
        self.road["properties"]["_city_estimated_m"] = [0, 0, 0]
        with self.assertRaisesRegex(ValueError, "ordinary ground road"):
            road_overrides.apply(self.source, self.request, "a" * 64)

    def test_schema(self):
        for change in [{"width_m": 10}, {"segments": []}, {"segments": [dict(self.segment, max_displacement_m=6)]},
                       {"segments": [dict(self.segment, to_node=12)]}, {"segments": [self.segment, dict(self.segment, from_node=13, to_node=12)]},
                       {"segments": [dict(self.segment, points=[[200, 0]])]}, {"segments": [dict(self.segment, extra=1)]}]:
            bad = copy.deepcopy(self.request); bad["ways"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): road_overrides.validate(bad)
        both = copy.deepcopy(self.request); both["ways"][0].update(width_m=18, lanes=5)
        result, receipt = road_overrides.apply(self.source, both, "a" * 64)
        self.assertEqual(receipt["applied"][0]["width_m"], 18)
        self.assertTrue(result["features"][0]["properties"]["_city_author_override"])
        with self.assertRaises(ValueError): road_overrides.validate({"osm_sha256": "a" * 64, "ways": [{"source_id": "way/9"}]})


if __name__ == "__main__":
    unittest.main()
