import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from geojson import convert
from polygon_geometry import Budget, group_rings


def square(x, y, size):
    return [[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]


def convert_polygons(polygons, properties=None):
    return convert({"type":"FeatureCollection", "features":[{"type":"Feature", "properties":properties or {"landuse":"forest"}, "geometry":{"type":"MultiPolygon", "coordinates":polygons}}]}, "synthetic", "CC0", layer_id="d"*32)


class PolygonTests(unittest.TestCase):
    def test_exclusions_island_and_multiple_parts(self):
        outer, hole, island = square(0,0,100), square(20,20,60), square(40,40,20)
        self.assertEqual(group_rings([outer,island],[hole],Budget()), [[outer,hole],[island]])
        result = convert_polygons([[outer,hole],[island]])
        self.assertEqual(len(result.patches),2)
        self.assertEqual(result.point_count,12)
        self.assertEqual(result.patches[0]["after"]["exclusions"], [[[2000,2000],[8000,2000],[8000,8000],[2000,8000]]])
        self.assertNotEqual(result.patches[0]["id"],result.patches[1]["id"])
        self.assertEqual(len(convert_polygons([[outer],[square(200,0,20)]], {"height_m":5}).patches),2)

    def test_topology_rejects_without_repair(self):
        outer = square(0,0,100)
        cases = [
            ([outer,square(10,10,20)], []), # overlapping filled outers
            ([outer,square(100,0,20)], []), # touching boundary
            ([outer,square(90,90,20)], []), # crossing boundary
            ([outer], [square(200,0,20)]), # outside hole
            ([outer], [square(0,10,20)]), # touching hole
            ([outer], [square(10,10,80),square(20,20,20)]), # nested holes
            ([[[0,0],[10,10],[0,10],[10,0],[0,0]]], []),
            ([[[0,0],[10,0],[5,0],[10,10],[0,10],[0,0]]], []),
            ([[[0,0],[5,0],[10,0],[0,0]]], []),
            ([[[0,0],[10,0],[10,10],[0,0],[0,10],[0,0]]], []),
            ([], [outer]),
        ]
        for outers, holes in cases:
            with self.subTest(outers=outers, holes=holes), self.assertRaises(ValueError):
                group_rings(outers,holes,Budget())
        courtyard = convert_polygons([[outer,square(20,20,10)]], {"height_m":5})
        self.assertEqual(courtyard.patches[0]["after"]["holes"], [[[2000,2000],[3000,2000],[3000,3000],[2000,3000]]])
        with self.assertRaisesRegex(ValueError,"declared outer"):
            convert_polygons([[outer], [square(200,0,100),square(20,20,10)]])

    def test_projection_quantization_and_total_budget(self):
        # Source boundaries are disjoint, but centimetre quantization joins them.
        with self.assertRaisesRegex(ValueError,"touch"):
            convert_polygons([[square(0,0,10)], [square(10.004,0,5)]])
        with self.assertRaisesRegex(ValueError,"repeated positions"):
            convert_polygons([[square(0,0,0.001)]])
        with patch("polygon_geometry.MAX_TOPOLOGY_CHECKS", 1), self.assertRaisesRegex(ValueError,"budget"):
            convert_polygons([[square(0,0,10)]])
        # A continued collinear boundary is valid; backtracking was rejected above.
        ring = [[0,0],[5,0],[10,0],[10,10],[0,10],[0,0]]
        self.assertEqual(group_rings([ring],[],Budget()),[[ring]])


if __name__ == "__main__": unittest.main()
