import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from geojson import convert, _collapses


class CitySlivers(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()

    def building(self):
        square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        sliver = [[20, 20], [20, 20.02], [22.62, 19.99], [20, 20]]  # 2 cm wide (source)
        return dict(type="FeatureCollection", features=[dict(type="Feature", properties={"building": "yes", "height": "6"},
                    geometry=dict(type="MultiPolygon", coordinates=[[square], [sliver]]))])

    def buildings(self, **options):
        layer = convert(self.building(), "synthetic", "MIT", layer_id="d" * 32, coordinates=dict(mode="local-metres"), **options)
        return [p["after"]["id"] for p in layer.patches if p["field"] == "buildings"], layer.warnings

    def test_a_piece_the_map_lattice_erases_is_left_out(self):
        self.assertTrue(_collapses([[2000, 2000], [2000, 2002], [2262, 1999]], 3))
        self.assertFalse(_collapses([[2000, 2000], [2000, 2002], [2262, 1999]], 1))
        ids, warnings = self.buildings(city=True, denominator=3)
        self.assertEqual(len(ids), 1)
        self.assertTrue(ids[0].endswith("-part-0"))
        self.assertTrue(any("thinner than one map centimetre" in w for w in warnings))
        # At 1:1 the sliver keeps its own whole centimetres; outside the city profile nothing changes.
        self.assertEqual(len(self.buildings(city=True, denominator=1)[0]), 2)
        self.assertEqual(len(self.buildings()[0]), 2)


if __name__ == "__main__":
    unittest.main()
