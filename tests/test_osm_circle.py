import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from osm_area import circle_region, crop, extent_region, play_area, square_region
from projection import Coordinates
from pyproj import Geod
from shapely.geometry import LineString, mapping, shape


class CircleTests(unittest.TestCase):
    def test_geodesic_boundary_and_stored_polygon_error(self):
        geod = Geod(ellps="WGS84")
        for center in [[127.052074, 37.257705], [8.45, 60.42], [-118.17, 34.07]]:
            for radius in [0.1, 1.5, 20]:
                region = circle_region(center, radius)
                options = dict(mode="wgs84-utm", origin=center, local_origin_m=[0, 0])
                # Projection limit is independently enforced by Coordinates.
                if radius == 20:
                    points = list(region.exterior.coords)[:-1]
                else:
                    rings = play_area(list(region.bounds), region, options, 3, exact=True)
                    self.assertLessEqual(len(rings[0]), 512)
                    frame = Coordinates(options)
                    points = [frame.transformer.transform(x / 100 + frame.origin_xy[0], y / 100 + frame.origin_xy[1], direction="INVERSE") for x, y in rings[0]]
                for a, b in zip(points, points[1:] + points[:1]):
                    _, _, edge = geod.inv(*a, *b)
                    self.assertLess(radius * 1000 - (radius * radius * 1e6 - edge * edge / 4) ** .5, 0.5)
                    _, _, distance = geod.inv(*center, *a)
                    self.assertLess(abs(distance - radius * 1000), .1)

    def test_circle_clips_road_and_corners(self):
        region = circle_region([9., 55.], 1.5)
        w, s, e, n = region.bounds
        line = LineString([(w - .001, 55), (e + .001, 55)])
        value, meta = crop(dict(type="FeatureCollection", features=[dict(type="Feature", properties={}, geometry=mapping(line))]), [w, s, e, n], region=region)
        self.assertTrue(region.buffer(1e-12).covers(shape(value["features"][0]["geometry"])))
        self.assertFalse(region.covers(__import__("shapely").Point(w, s)))

    def test_invalid_circle_never_changes_radius(self):
        for center, radius in [([9, 55], 0), ([9, 55], 21), ([180, 55], 1.5), ([9, 84], 1.5), ([float("nan"), 55], 1.5)]:
            with self.assertRaises(ValueError):
                circle_region(center, radius)


class SquareTests(unittest.TestCase):
    def test_square_is_axis_aligned_in_map_frame_with_four_corners(self):
        for center in [[127.052074, 37.257705], [8.45, 60.42], [-118.17, 34.07], [151.2, -33.86]]:
            for half in [0.5, 2.5]:
                region = square_region(center, half)
                options = dict(mode="wgs84-utm", origin=center, local_origin_m=[0, 0])
                rings = play_area(list(region.bounds), region, options, 3)
                self.assertEqual(len(rings), 1)
                xs = sorted({x for x, _ in rings[0]}); ys = sorted({y for _, y in rings[0]})
                self.assertEqual((len(rings[0]), len(xs), len(ys)), (4, 2, 2), rings[0])
                for values in (xs, ys):
                    self.assertAlmostEqual(values[0], -half * 100000, delta=6)
                    self.assertAlmostEqual(values[1], half * 100000, delta=6)

    def test_extent_region_selects_shape_and_refuses_others(self):
        self.assertEqual(extent_region([9., 55.], 1.0).geom_type, "Polygon")
        self.assertGreater(extent_region([9., 55.], 1.0, "square").area, extent_region([9., 55.], 1.0).area)
        for center, half, shape in [([9, 55], 0, "square"), ([9, 55], 21, "square"), ([9, 55], 1, "hexagon"), ([5.999, 55], 1, "square")]:
            with self.assertRaises(ValueError):
                extent_region(center, half, shape)


if __name__ == "__main__":
    unittest.main()
