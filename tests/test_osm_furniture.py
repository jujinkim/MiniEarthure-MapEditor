"""Generated city street furniture on synthetic layer patches (source cm, 1:3)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from shapely.geometry import LineString, Point, Polygon
import osm_furniture

SCALE = 3


def road(identity, a, b, marked=True, width=1500, sidewalk=300):
    return dict(field="roads", id=identity, after=dict(id=identity, **{"from": a[0], "to": b[0]}, points=[[a[1], 0, a[2]], [b[1], 0, b[2]]],
                widths_cm=[width], surfaces=["asphalt"], kind="ground", sidewalk_cm=sidewalk, markings=dict(lanes=4) if marked else None))


def node(identity, x, y):
    return dict(field="nodes", id=identity, after=dict(id=identity, position=[x, 0, y], level=0))


def crossroad(marked=True):
    centre = ("c", 0, 0)
    patches = [node("c", 0, 0)]
    for name, x, y in (("e", 6000, 0), ("w", -6000, 0), ("n", 0, 6000), ("s", 0, -6000)):
        patches += [node(name, x, y), road("road-" + name, centre, (name, x, y), marked)]
    return patches


class Furniture(unittest.TestCase):
    def corridors(self, patches):
        return [LineString([(q[0], q[2]) for q in p["after"]["points"]]).buffer(p["after"]["widths_cm"][0] / 2 + p["after"]["sidewalk_cm"])
                for p in patches if p["field"] == "roads"]

    def test_marked_crossroads_get_one_signal_per_inbound_arm_beside_the_road(self):
        patches = crossroad()
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, dict(driving_side="right", signal_style="horizontal"))
        signals = [r for r in records if r["asset_id"] == "builtin:signal_h"]
        self.assertEqual(len(signals), 4, counts)
        corridors = self.corridors(patches)
        for r in signals:
            at = Point(r["position"][0], r["position"][2])
            self.assertFalse(any(c.contains(at) for c in corridors), "poles stand beside the carriageway and sidewalk")
        self.assertEqual(sorted(r["quarter_turns"] % 2 for r in signals), [0, 0, 1, 1], "cross approaches alternate lamp phase")
        # The east arm's pole stands on the driver's right of westbound traffic (north side).
        east = min(signals, key=lambda r: Point(r["position"][0], r["position"][2]).distance(Point(3000, 0)))
        self.assertGreater(east["position"][2], 0)
        left, _ = osm_furniture.generate("l" * 32, patches, {}, SCALE, dict(driving_side="left", signal_style="vertical"))
        mirrored = min(left, key=lambda r: Point(r["position"][0], r["position"][2]).distance(Point(3000, 0)))
        self.assertEqual(mirrored["asset_id"], "builtin:signal_v")
        self.assertLess(mirrored["position"][2], 0, "left-hand traffic mirrors the corner")
        again, _ = osm_furniture.generate("l" * 32, patches, {}, SCALE, dict(driving_side="right", signal_style="horizontal"))
        self.assertEqual(again, records, "fixed seeds")

    def test_unmarked_junctions_get_signals_only_from_osm_signal_nodes(self):
        patches = crossroad(marked=False)
        records, _ = osm_furniture.generate("l" * 32, patches, {}, SCALE, {})
        self.assertEqual(records, [])
        tagged = {"osm_street_points": [dict(kind="traffic_signals", category="traffic_signals", source_id="node/9", position=[300, 200])]}
        records, _ = osm_furniture.generate("l" * 32, patches, tagged, SCALE, {})
        self.assertEqual(len(records), 4)

    def test_bus_shelters_face_the_road_and_skip_blocked_spots(self):
        patches = crossroad(marked=False) + [dict(field="buildings", id="b", after=dict(id="b", footprint=[[-3000, 1250], [-1000, 1250], [-1000, 4000], [-3000, 4000]]))]
        stops = {"osm_street_points": [dict(kind="bus_stop", category="bus_stop", source_id="node/1", position=[4000, 900]),
                                       dict(kind="bus_stop", category="bus_stop", source_id="node/2", position=[-2000, 1300])]}
        records, counts = osm_furniture.generate("l" * 32, patches, stops, SCALE, {})
        shelters = [r for r in records if r["asset_id"] == "builtin:bus_shelter"]
        self.assertEqual(len(shelters), 1, counts)
        self.assertEqual(counts.get("skipped_bus_stop"), 1, "a building occupies the second stop's roadside")
        shelter = shelters[0]
        self.assertGreater(shelter["position"][2], 750 + 300, "beyond the road edge and sidewalk")
        self.assertEqual((shelter["quarter_turns"], shelter.get("yaw_offset_mdeg", 0)), (2, 0), "the open front (local +y) faces the road to the south")

    def test_parks_scatter_seeded_details_inside_their_area(self):
        park = dict(source_id="way/7", landuse="park", polygon=[[20000, 20000], [40000, 20000], [40000, 40000], [20000, 40000]], holes=[])
        records, counts = osm_furniture.generate("l" * 32, [], {"generation_regions": [park, dict(park, source_id="way/8", landuse="industrial")]}, SCALE, {})
        kinds = {r["asset_id"] for r in records}
        self.assertTrue({"builtin:tree", "builtin:bench", "builtin:shrub"} <= kinds, counts)
        area = Polygon(park["polygon"])
        self.assertTrue(all(area.contains(Point(r["position"][0], r["position"][2])) for r in records))
        self.assertTrue(all(r["id"].startswith("import-" + "l" * 32 + "-place-") for r in records))


if __name__ == "__main__":
    unittest.main()
