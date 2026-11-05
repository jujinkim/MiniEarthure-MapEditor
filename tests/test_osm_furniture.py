"""Generated city street furniture on synthetic layer patches (source cm, 1:3)."""
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from shapely.geometry import LineString, Point, Polygon
import osm_furniture

SCALE = 3


def road(identity, a, b, marked=True, width=1500, sidewalk=300):
    return dict(field="roads", id=identity, after=dict(id=identity, **{"from": a[0], "to": b[0]}, points=[[a[1], 0, a[2]], [b[1], 0, b[2]]],
                widths_cm=[width], surfaces=["asphalt"], kind="ground", sidewalk_cm=sidewalk, markings=dict(lanes=4, stop_lines=True) if marked else None))


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
        streets = crossroad()
        for patch in streets:
            if patch["field"] == "roads": patch["after"]["markings"]["stop_lines"] = False
        residential = [r for r in osm_furniture.generate("l" * 32, streets, {}, SCALE, {})[0] if r["asset_id"].startswith("builtin:signal_")]
        self.assertEqual(residential, [], "residential center lines alone bring no signals (stop signs instead)")
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

    def test_shelters_keep_clear_of_the_outer_corner_of_a_bend(self):
        # A 110-degree bend: a round-join corridor would let the shelter touch
        # MapKit's mitred outer corner.
        bend = [node("a", 3843, 9591), node("v", 0, 0), node("b", 3213, -1734),
                dict(field="roads", id="r", after=dict(id="r", **{"from": "a", "to": "b"}, points=[[3843, 0, 9591], [0, 0, 0], [3213, 0, -1734]],
                     widths_cm=[900, 900], surfaces=["asphalt"] * 2, kind="ground", sidewalk_cm=0, markings=None))]
        stops = {"osm_street_points": [dict(kind="bus_stop", category="bus_stop", source_id="node/1", position=[-560, -260])]}
        records, counts = osm_furniture.generate("l" * 32, bend, stops, SCALE, {})
        mitred = LineString([(3843, 9591), (0, 0), (3213, -1734)]).buffer(450, join_style="mitre", mitre_limit=10.0)
        for r in records:
            footprint = osm_furniture.Furniture([], {}, SCALE, {}).footprint(r["asset_id"], r["position"][0], r["position"][2], r["quarter_turns"] * 90 + r.get("yaw_offset_mdeg", 0) / 1000)
            self.assertFalse(footprint.intersects(mitred), counts)

    def test_parks_scatter_seeded_details_inside_their_area(self):
        park = dict(source_id="way/7", landuse="park", polygon=[[20000, 20000], [40000, 20000], [40000, 40000], [20000, 40000]], holes=[])
        records, counts = osm_furniture.generate("l" * 32, [], {"generation_regions": [park, dict(park, source_id="way/8", landuse="industrial")]}, SCALE, {})
        kinds = {r["asset_id"] for r in records}
        self.assertEqual(kinds, {"builtin:bench", "builtin:shrub"}, "park trees are vegetation zones, not placements")
        area = Polygon(park["polygon"])
        self.assertTrue(all(area.contains(Point(r["position"][0], r["position"][2])) for r in records))
        self.assertTrue(all(r["id"].startswith("import-" + "l" * 32 + "-place-") for r in records))



def street(identity, a, b, *, lanes=4, stop_lines=True, width=1500, sidewalk=300, kind="ground", **markings):
    """A straight road record between named nodes a and b = (id, x, y)."""
    marks = None if lanes is None else dict(lanes=lanes, stop_lines=stop_lines, **markings)
    return dict(field="roads", id=identity, after=dict(id=identity, **{"from": a[0], "to": b[0]}, points=[[a[1], 0, a[2]], [b[1], 0, b[2]]],
                widths_cm=[width], surfaces=["asphalt"], kind=kind, sidewalk_cm=sidewalk, markings=marks))


def junction(arms, **options):
    """Arms from a centre node c at (0, 0): (name, x, y) each."""
    centre = ("c", 0, 0)
    patches = [node("c", 0, 0)]
    for name, x, y in arms:
        patches += [node(name, x, y), street("road-" + name, centre, (name, x, y), **options)]
    return patches


RIGHT = dict(driving_side="right", signal_style="horizontal")


def signs(records, prefix="builtin:sign_"):
    return [r for r in records if r["asset_id"].startswith(prefix)]


def theta(record):
    return math.radians(record["quarter_turns"] * 90 + record.get("yaw_offset_mdeg", 0) / 1000)


def facing(record):
    """Map-plane direction of a sign's printed face (local +y)."""
    t = theta(record)
    return -math.sin(t), math.cos(t)


class RoadSigns(unittest.TestCase):
    def corridors(self, patches):
        return [LineString([(q[0], q[2]) for q in p["after"]["points"]]).buffer(p["after"]["widths_cm"][0] / 2 + p["after"]["sidewalk_cm"])
                for p in patches if p["field"] == "roads"]

    def assert_beside(self, patches, records):
        corridors = self.corridors(patches)
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        for r in records:
            footprint = shapes.footprint(r["asset_id"], r["position"][0], r["position"][2], math.degrees(theta(r)))
            self.assertFalse(any(c.intersects(footprint) for c in corridors), r)

    def long_road(self, **options):
        return [node("w", -100000, 0), node("e", 100000, 0), street("r", ("w", -100000, 0), ("e", 100000, 0), **options)]

    def test_speed_signs_repeat_face_the_traffic_and_stand_on_the_drivers_right(self):
        patches = self.long_road()
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        speed = signs(records)
        self.assertTrue(speed and all(r["asset_id"] == "builtin:sign_speed_50" for r in speed), counts)
        self.assert_beside(patches, speed)
        for heading in (1, -1):
            group = sorted((r for r in speed if facing(r)[0] * heading < -0.99), key=lambda r: r["position"][0] * heading)
            self.assertEqual(len(group), 3, "a sign 10 m after the start and every 250 map m")
            for r in group:
                # Eastbound traffic (heading +x) keeps right: the south side (-y).
                self.assertLess(r["position"][2] * heading, 0)
            gaps = [abs(b["position"][0] - a["position"][0]) for a, b in zip(group, group[1:])]
            self.assertTrue(all(g >= osm_furniture.SPEED_REPEAT_CM * SCALE - 1 for g in gaps), gaps)
        info = lambda **v: {"r": dict(dict(highway="primary", maxspeed=None), **v)}
        for road_info, expected in ((info(maxspeed=60), "builtin:sign_speed_60"), (info(maxspeed=70), "builtin:sign_speed_60"),
                                    (info(maxspeed=110), "builtin:sign_speed_100"), (info(highway="trunk"), "builtin:sign_speed_80"),
                                    (info(maxspeed=25), None), (info(highway="residential"), None)):
            with self.subTest(road_info=road_info):
                found = {r["asset_id"] for r in signs(osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, road_info)[0])}
                self.assertEqual(found, {expected} if expected else set())
        wide = self.long_road(lanes=6, edge_lines=True)
        self.assertEqual({r["asset_id"] for r in signs(osm_furniture.generate("l" * 32, wide, {}, SCALE, RIGHT)[0])}, {"builtin:sign_speed_60"})
        self.assertEqual(signs(osm_furniture.generate("l" * 32, self.long_road(kind="bridge"), {}, SCALE, RIGHT)[0]), [], "never beside a bridge")
        self.assertEqual(signs(osm_furniture.generate("l" * 32, self.long_road(stop_lines=False), {}, SCALE, RIGHT)[0]), [], "residential streets")
        one_way = signs(osm_furniture.generate("l" * 32, self.long_road(one_way=1), {}, SCALE, RIGHT)[0])
        self.assertTrue(one_way and all(facing(r)[0] < -0.99 for r in one_way), "one direction only")

    def test_guide_signs_hang_over_wide_signalled_approaches_in_right_hand_traffic(self):
        arms = (("e", 12000, 0), ("w", -12000, 0), ("n", 0, 12000), ("s", 0, -12000))
        patches = junction(arms)
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        guides = signs(records, "builtin:guide_sign")
        self.assertEqual(len(guides), 4, counts)
        self.assert_beside(patches, guides)
        for r in guides:
            x, y = r["position"][0], r["position"][2]
            t = theta(r)
            # Local +x reaches over the carriageway (toward the arm's centreline).
            toward = (-x, 0) if abs(y) > abs(x) else (0, -y)
            self.assertGreater(math.cos(t) * toward[0] + math.sin(t) * toward[1], 0, r)
            self.assertAlmostEqual(max(abs(x), abs(y)), osm_furniture.GUIDE_SETBACK_CM * SCALE, delta=20 * SCALE * 6)
        self.assertEqual(signs(osm_furniture.generate("l" * 32, patches, {}, SCALE, dict(driving_side="left"))[0], "builtin:guide_sign"), [])
        self.assertEqual(signs(osm_furniture.generate("l" * 32, junction(arms, sidewalk=400), {}, SCALE, RIGHT)[0], "builtin:guide_sign"), [])
        short = junction(tuple((n, x // 2, y // 2) for n, x, y in arms))
        self.assertEqual(signs(osm_furniture.generate("l" * 32, short, {}, SCALE, RIGHT)[0], "builtin:guide_sign"), [], "approaches under 30 m")

    def test_crossing_signs_only_before_unsignalled_crosswalks(self):
        arms = (("e", 9000, 0), ("w", -9000, 0), ("n", 0, 9000))
        patches = junction(arms, stop_lines=False, crosswalk_start=True)
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        crossing = [r for r in records if r["asset_id"] == "builtin:sign_crossing"]
        self.assertEqual(len(crossing), 3, counts)
        self.assert_beside(patches, crossing)
        for r in crossing:
            x, y = r["position"][0], r["position"][2]
            outward = (1, 0) if x > 1500 else (-1, 0) if x < -1500 else (0, 1)
            self.assertGreater(facing(r)[0] * outward[0] + facing(r)[1] * outward[1], 0.99, "faces the arriving traffic")
        signalled = junction(arms, crosswalk_start=True)
        self.assertEqual([r for r in osm_furniture.generate("l" * 32, signalled, {}, SCALE, RIGHT)[0] if r["asset_id"] == "builtin:sign_crossing"], [])

    def test_stop_and_yield_signs_on_minor_arms(self):
        tee = junction((("e", 9000, 0), ("w", -9000, 0), ("s", 0, -9000)), stop_lines=False)
        records, counts = osm_furniture.generate("l" * 32, tee, {}, SCALE, RIGHT)
        self.assertEqual([r["asset_id"] for r in signs(records)], ["builtin:sign_stop"], counts)
        stop = signs(records)[0]
        self.assertLess(stop["position"][2], -1500, "on the south arm")
        self.assertLess(facing(stop)[1], -0.99, "facing the arriving northbound traffic")
        self.assert_beside(tee, signs(records))
        oblique = junction((("e", 9000, 0), ("w", -9000, 0), ("s", -6400, -6400)), stop_lines=False)
        self.assertEqual([r["asset_id"] for r in signs(osm_furniture.generate("l" * 32, oblique, {}, SCALE, RIGHT)[0])], ["builtin:sign_yield"])
        tagged = {"osm_street_points": [dict(kind="give_way", category="give_way", source_id="node/5", position=[200, -3000])]}
        records, counts = osm_furniture.generate("l" * 32, tee, tagged, SCALE, RIGHT)
        self.assertEqual([r["asset_id"] for r in signs(records)], ["builtin:sign_yield"], counts)
        self.assertLess(signs(records)[0]["position"][2], -2900, "at the tagged node, beyond the mouth")
        wye = junction((("a", 0, 9000), ("b", 7794, -4500), ("d", -7794, -4500)), stop_lines=False)
        self.assertEqual(signs(osm_furniture.generate("l" * 32, wye, {}, SCALE, RIGHT)[0]), [], "a Y junction has no through road")

    def test_children_signs_and_a_30_sign_where_roads_enter_a_school_zone(self):
        patches = self.long_road()
        school = [[-6000, 3000], [6000, 3000], [6000, 15000], [-6000, 15000]]
        regions = [dict(source_id="way/3", landuse="school", polygon=school, holes=[], tags=dict(amenity="school"))]
        for inputs, areas in (({"generation_regions": regions}, None), ({}, [school])):
            with self.subTest(areas=areas):
                records, counts = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT, None, areas)
                children = [r for r in records if r["asset_id"] == "builtin:sign_children"]
                self.assertEqual(len(children), 2, counts)
                self.assert_beside(patches, children)
                zone = Polygon(school).buffer(osm_furniture.SCHOOL_ZONE_CM * SCALE)
                for r in children:
                    self.assertFalse(zone.contains(Point(r["position"][0], 0)), "at the entry, outside")
                    self.assertGreater(facing(r)[0] * r["position"][0], 0, "faces the entering traffic")
                thirty = [r for r in records if r["asset_id"] == "builtin:sign_speed_30"]
                self.assertTrue(thirty and all(zone.contains(Point(r["position"][0], 0)) for r in thirty), counts)
                self.assertFalse(any(r["asset_id"] == "builtin:sign_speed_50" and zone.contains(Point(r["position"][0], 0)) for r in records))

    def bent(self, identity, points, a, b, **options):
        """A road record along `points` (map-plane (x, y) pairs) from node a to b."""
        p = street(identity, (a, *points[0]), (b, *points[-1]), **options)
        p["after"]["points"] = [[x, 0, y] for x, y in points]
        p["after"]["widths_cm"] = [p["after"]["widths_cm"][0]] * (len(points) - 1)
        p["after"]["surfaces"] = ["asphalt"] * (len(points) - 1)
        return p

    def test_signs_stand_along_bent_approaches_and_tagged_nodes_near_their_junction(self):
        # The east arm runs 30 m east, then turns 45 degrees north: its guide
        # sign 60 m along stands beside the bent road, facing the traffic
        # arriving along it.
        east = [(0, 0), (3000, 0), (11485, 8485)]
        patches = [node("c", 0, 0), node("e", 11485, 8485), self.bent("road-e", east, "c", "e")]
        for name, x, y in (("w", -12000, 0), ("n", 0, 12000), ("s", 0, -12000)):
            patches += [node(name, x, y), street("road-" + name, ("c", 0, 0), (name, x, y))]
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        guides = signs(records, "builtin:guide_sign")
        self.assertEqual(len(guides), 4, counts)
        self.assert_beside(patches, guides)
        offset = 1500 / 2 + 300 + (osm_furniture.CLEARANCE_CM + osm_furniture.SIZES[osm_furniture.GUIDE][0] + 2) * SCALE
        bend = LineString(east)
        lines = [LineString([(q[0], q[2]) for q in p["after"]["points"]]) for p in patches if p["field"] == "roads"]
        for r in guides:
            spot = Point(r["position"][0], r["position"][2])
            self.assertAlmostEqual(min(line.distance(spot) for line in lines), offset, delta=2, msg=r)
        on_bend = [r for r in guides if bend.distance(Point(r["position"][0], r["position"][2])) < offset + 2]
        self.assertEqual(len(on_bend), 1)
        # South-westbound traffic on the diagonal leg: the face looks north-east.
        self.assertGreater(facing(on_bend[0])[0] + facing(on_bend[0])[1], 1.41, on_bend[0])
        self.assertGreater(on_bend[0]["position"][2], 2000, on_bend[0])
        # A tagged give-way far along a long record before its junction gets no sign.
        tee = junction((("e", 9000, 0), ("w", -9000, 0), ("s", 0, -60000)), stop_lines=False)
        far = {"osm_street_points": [dict(kind="give_way", category="give_way", source_id="node/5", position=[200, -45000])]}
        records, counts = osm_furniture.generate("l" * 32, tee, far, SCALE, RIGHT)
        self.assertEqual(counts.get("skipped_tagged_signs"), 1, counts)
        self.assertEqual([r["asset_id"] for r in signs(records)], ["builtin:sign_stop"], "the generated sign stands at the junction")
        self.assertGreater(signs(records)[0]["position"][2], -6000)

    def test_signal_clearance_is_kept_from_the_sign_pole_on_wide_roads(self):
        for width in (1500, 2400, 3000):
            with self.subTest(width=width):
                arms = (("e", 7500, 0), ("w", -7500, 0), ("n", 0, 7500), ("s", 0, -7500))
                records, counts = osm_furniture.generate("l" * 32, junction(arms, width=width), {}, SCALE, RIGHT)
                poles = [r for r in records if r["asset_id"] == "builtin:signal_h"]
                placed = [r for r in records if r["asset_id"] == osm_furniture.GUIDE or r["asset_id"].startswith("builtin:sign_speed")
                          or r["asset_id"] == "builtin:sign_children"]
                self.assertTrue(poles and placed, counts)
                closest = min(math.hypot(a["position"][0] - b["position"][0], a["position"][2] - b["position"][2]) for a in placed for b in poles)
                self.assertGreaterEqual(closest, osm_furniture.SIGNAL_CLEAR_CM * SCALE, counts)

    def test_motorways_and_trunks_get_no_school_zone(self):
        patches = self.long_road(lanes=6, edge_lines=True)
        school = [[-6000, 3000], [6000, 3000], [6000, 15000], [-6000, 15000]]
        for highway, speed in (("motorway", 100), ("trunk", 80), ("primary", None)):
            with self.subTest(highway=highway):
                road_info = {"r": dict(highway=highway, maxspeed=speed)}
                found = {r["asset_id"] for r in signs(osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, road_info, [school])[0])}
                if highway == "primary":
                    self.assertTrue({"builtin:sign_children", "builtin:sign_speed_30"} <= found, found)
                else:
                    self.assertEqual(found, {f"builtin:sign_speed_{speed}"})

    def test_signs_follow_every_other_placement_with_caps_and_fixed_seeds(self):
        arms = (("e", 30000, 0), ("w", -30000, 0), ("n", 0, 30000), ("s", 0, -30000))
        park = dict(source_id="way/7", landuse="park", polygon=[[20000, 20000], [40000, 20000], [40000, 40000], [20000, 40000]], holes=[])
        patches = junction(arms)
        records, counts = osm_furniture.generate("l" * 32, patches, {"generation_regions": [park]}, SCALE, RIGHT)
        kinds = [r["asset_id"] in osm_furniture.SIGN_POLE or r["asset_id"] == osm_furniture.GUIDE for r in records]
        self.assertIn(True, kinds)
        self.assertEqual(kinds, sorted(kinds), "every sign record follows every other record")
        self.assertEqual(osm_furniture.generate("l" * 32, patches, {"generation_regions": [park]}, SCALE, RIGHT), (records, counts), "fixed seeds")
        with patch.dict(osm_furniture.SIGN_CAPS, {"guide_signs": 1}):
            capped, capped_counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        self.assertEqual(capped_counts["guide_signs"], 1)
        self.assertEqual(capped_counts["skipped_guide_signs_limit"], 3)
        with patch.object(osm_furniture, "ROAD_SIGN_LIMIT", 2):
            limited, limited_counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        self.assertEqual(len(signs(limited)) + len(signs(limited, "builtin:guide_sign")), 2)
        self.assertGreater(limited_counts["skipped_road_signs_limit"], 0)


if __name__ == "__main__":
    unittest.main()
