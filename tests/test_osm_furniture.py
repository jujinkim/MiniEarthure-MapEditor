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
        mirrored = min((r for r in left if r["asset_id"].startswith("builtin:signal_")), key=lambda r: Point(r["position"][0], r["position"][2]).distance(Point(3000, 0)))
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
        kinds = [3 if r["asset_id"] in osm_furniture.LAMPS else 2 if r["asset_id"] in osm_furniture.PLANTING
                 else 1 if r["asset_id"] in osm_furniture.SIGN_POLE or r["asset_id"] == osm_furniture.GUIDE else 0 for r in records]
        self.assertTrue({0, 1, 2, 3} <= set(kinds), kinds)
        self.assertEqual(kinds, sorted(kinds), "signs follow the other furniture; street planting follows the signs; streetlights come last")
        self.assertEqual(osm_furniture.generate("l" * 32, patches, {"generation_regions": [park]}, SCALE, RIGHT), (records, counts), "fixed seeds")
        with patch.dict(osm_furniture.SIGN_CAPS, {"guide_signs": 1}):
            capped, capped_counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        self.assertEqual(capped_counts["guide_signs"], 1)
        self.assertEqual(capped_counts["skipped_guide_signs_limit"], 3)
        with patch.object(osm_furniture, "ROAD_SIGN_LIMIT", 2):
            limited, limited_counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT)
        self.assertEqual(len(signs(limited)) + len(signs(limited, "builtin:guide_sign")), 2)
        self.assertGreater(limited_counts["skipped_road_signs_limit"], 0)


AVENUE = dict(width=540 * SCALE, sidewalk=67 * SCALE)
PRIMARY = {"r": dict(highway="primary", name="Avenue", maxspeed=None)}


def trees(records):
    return [r for r in records if r["asset_id"] in osm_furniture.STREET_TREE_CROWN_CM]


def at(record):
    return Point(record["position"][0], record["position"][2])


def theta_deg(record):
    return record["quarter_turns"] * 90 + record.get("yaw_offset_mdeg", 0) / 1000


def named_species(species, prefix="Street"):
    """A street name whose seeded species is `species` on a wide sidewalk."""
    shape = osm_furniture.Furniture([], {}, SCALE, {})
    shape.road_info = {}
    for i in range(500):
        shape.road_info = {"r": dict(name=f"{prefix} {i}")}
        if shape._species(dict(id="r", sidewalk_cm=200 * SCALE)) == osm_furniture.SPECIES[species]: return f"{prefix} {i}"
    raise AssertionError(species)


class StreetPlanting(unittest.TestCase):
    def avenue(self, length=60000, angle=0.0, **options):
        """A straight avenue through the origin (source cm) at `angle` degrees."""
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        a, b = ("w", round(-length * c), round(-length * s)), ("e", round(length * c), round(length * s))
        return [node(*a), node(*b), street("r", a, b, **dict(AVENUE, **options))]

    def test_constants_mirror_the_mapkit_contract(self):
        # map-kit/spec/CURRENT_V1.md street planting builtins.
        self.assertEqual((osm_furniture.STREET_TREE_PIT_CM, osm_furniture.STREET_CANOPY_MIN_CM), (40, 120))
        self.assertEqual(osm_furniture.STREET_TREE_CROWN_CM, {"builtin:street_tree_ginkgo": 60, "builtin:street_tree_zelkova": 125,
                         "builtin:street_tree_plane": 115, "builtin:street_tree_cherry": 120, "builtin:street_tree_pine": 85})
        self.assertEqual({a: osm_furniture.SIZES[a] for a in osm_furniture.PLANTING if not a.startswith("builtin:street_tree_")},
                         {"builtin:planter": (40, 15), "builtin:planter_square": (30, 30), "builtin:median_bed": (150, 40), "builtin:median_bed_pine": (150, 40)})
        self.assertTrue(all(osm_furniture.SIZES[a] == (20, 20) for a in osm_furniture.STREET_TREE_CROWN_CM))
        self.assertEqual(osm_furniture.MAX_PLACEMENTS, 24000)

    def test_pits_line_both_curbs_turned_with_the_road(self):
        for angle in (0.0, 30.0, 45.0):
            with self.subTest(angle=angle):
                patches = self.avenue(angle=angle)
                records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, PRIMARY)
                found = trees(records)
                self.assertGreater(len(found), 250, counts)
                line = LineString([(q[0], q[2]) for q in patches[-1]["after"]["points"]])
                carriageway = line.buffer(AVENUE["width"] / 2)
                for r in found:
                    self.assertAlmostEqual(line.distance(at(r)), AVENUE["width"] / 2 + 28 * SCALE, delta=2)
                    self.assertAlmostEqual((theta_deg(r) - angle) % 180, 0, delta=0.01, msg="pit edges follow the curb")
                    pit = osm_furniture.Furniture([], {}, SCALE, {}).footprint(r["asset_id"], r["position"][0], r["position"][2], theta_deg(r))
                    self.assertFalse(pit.intersects(carriageway))
                    self.assertTrue(pit.within(line.buffer(AVENUE["width"] / 2 + AVENUE["sidewalk"])), "the pit stands on the sidewalk")
                left = sorted(line.project(at(r)) for r in found if (at(r).y * math.cos(math.radians(angle)) - at(r).x * math.sin(math.radians(angle))) > 0)
                pitch = 270 * SCALE
                gaps = [b - a for a, b in zip(left, left[1:])]
                self.assertTrue(all(abs(g - pitch * round(g / pitch)) <= 2 for g in gaps), "stations every 270 map cm (sign posts skip some)")
                self.assertGreater(sum(abs(g - pitch) <= 2 for g in gaps), len(gaps) * 0.9)
                self.assertEqual(len(left) * 2, len(found))
                self.assertAlmostEqual(left[0], osm_furniture.FREE_END_CM * SCALE, delta=1, msg="free ends keep 135 map cm")
                self.assertEqual(len({r["asset_id"] for r in found}), 1, "one species per street")

    def test_no_trees_without_sidewalk_on_bridges_minor_classes_links_or_short_records(self):
        for options, info in ((dict(sidewalk=0), PRIMARY), (dict(sidewalk=50 * SCALE), PRIMARY), (dict(kind="bridge"), PRIMARY),
                              ({}, {"r": dict(highway="residential")}), ({}, {"r": dict(highway="primary_link")}),
                              (dict(lanes=None), None), (dict(lanes=1), None)):
            with self.subTest(options=options, info=info):
                self.assertEqual(trees(osm_furniture.generate("l" * 32, self.avenue(**options), {}, SCALE, RIGHT, info)[0]), [])
        self.assertTrue(trees(osm_furniture.generate("l" * 32, self.avenue(), {}, SCALE, RIGHT, None)[0]), "painted lanes ≥ 2 without a class")
        self.assertEqual(trees(osm_furniture.generate("l" * 32, self.avenue(length=260 * SCALE), {}, SCALE, RIGHT, PRIMARY)[0]), [], "under two spacings")

    def test_junction_mouths_crosswalks_signals_signs_and_stops_keep_trees_away(self):
        arms = (("e", 30000, 0), ("w", -30000, 0), ("n", 0, 30000), ("s", 0, -30000))
        info = {f"road-{n}": dict(highway="primary", name="Cross") for n, *_ in arms}
        stops = {"osm_street_points": [dict(kind="bus_stop", category="bus_stop", source_id="node/1", position=[-15000, 1100])]}
        for crosswalk in (False, True):
            with self.subTest(crosswalk=crosswalk):
                patches = junction(arms, crosswalk_start=crosswalk, **AVENUE)
                records, counts = osm_furniture.generate("l" * 32, patches, stops, SCALE, RIGHT, info)
                found = trees(records)
                self.assertTrue(found, counts)
                mouth = math.sqrt(2) * (AVENUE["width"] / 2 + AVENUE["sidewalk"]) + (osm_furniture.CLEARANCE_CM + 60 + (250 if crosswalk else 0)) * SCALE
                nearest = min(max(abs(r["position"][0]), abs(r["position"][2])) for r in found)
                self.assertAlmostEqual(nearest, mouth, delta=2, msg="the first station keeps mouth + 60 (+ 250 before a crosswalk)")
                for r in records:
                    if r["asset_id"] in osm_furniture.TALL[:3]:
                        crown = max(osm_furniture.STREET_TREE_CROWN_CM[t["asset_id"]] for t in found)
                        self.assertTrue(all(at(t).distance(at(r)) >= (crown + 150) * SCALE for t in found), r["asset_id"])
                    if r["asset_id"] in osm_furniture.SIGN_POLE:
                        self.assertTrue(all(at(t).distance(at(r)) >= 150 * SCALE for t in found), r["asset_id"])
                shelters = [r for r in records if r["asset_id"] == "builtin:bus_shelter"]
                self.assertEqual(len(shelters), 1)
                self.assertTrue(all(at(t).distance(at(shelters[0])) >= 300 * SCALE for t in found))
                for reason in ("pole", "stop"):
                    self.assertGreater(counts.get(f"skipped_street_trees_{reason}", 0), 0, counts)

    def test_species_follow_the_street_name_with_a_ginkgo_fallback_beside_close_buildings(self):
        name = named_species("zelkova")
        half, side = AVENUE["width"] / 2, AVENUE["sidewalk"]
        two = [node("w", -60000, 0), node("m", 0, 0), node("e", 60000, 0),
               street("a", ("w", -60000, 0), ("m", 0, 0), **AVENUE), street("b", ("m", 0, 0), ("e", 60000, 0), **AVENUE)]
        info = {r: dict(highway="secondary", name=name) for r in "ab"}
        found = trees(osm_furniture.generate("l" * 32, two, {}, SCALE, RIGHT, info)[0])
        self.assertEqual({r["asset_id"] for r in found}, {"builtin:street_tree_zelkova"}, "one species along both records")
        xs = sorted(r["position"][0] for r in found if r["position"][2] > 0)
        across = min(x for x in xs if x > 0) - max(x for x in xs if x < 0)
        self.assertTrue(270 * SCALE <= across < 2 * 270 * SCALE, "stations continue across the two-arm join (free ends keep 135)")
        # A shop row 30 map cm beyond the sidewalk: only the ginkgo crown fits.
        def row(gap):
            y = half + side + gap * SCALE
            return [dict(field="buildings", id="shops", after=dict(id="shops", footprint=[[-50000, y], [50000, y], [50000, y + 3000], [-50000, y + 3000]]))]
        records, counts = osm_furniture.generate("l" * 32, self.avenue() + row(30), {}, SCALE, RIGHT, {"r": dict(highway="primary", name=name)})
        self.assertEqual({r["asset_id"] for r in trees(records)}, {"builtin:street_tree_ginkgo"}, counts)
        records, counts = osm_furniture.generate("l" * 32, self.avenue() + row(10), {}, SCALE, RIGHT, {"r": dict(highway="primary", name=name)})
        north = [r for r in trees(records) if r["position"][2] > 0 and abs(r["position"][0]) < 49000]
        self.assertEqual(north, [], "even the ginkgo crown misses the row")
        self.assertGreater(counts["skipped_street_trees_crown"], 0)
        self.assertTrue(any(r["position"][2] < 0 for r in trees(records)), "the open side keeps its trees")
        pine = named_species("pine")
        narrow = trees(osm_furniture.generate("l" * 32, self.avenue(), {}, SCALE, RIGHT, {"r": dict(highway="primary", name=pine)})[0])
        self.assertEqual({r["asset_id"] for r in narrow}, {"builtin:street_tree_ginkgo"}, "pines need a 1 map m sidewalk")
        wide = trees(osm_furniture.generate("l" * 32, self.avenue(sidewalk=120 * SCALE), {}, SCALE, RIGHT, {"r": dict(highway="primary", name=pine)})[0])
        self.assertEqual({r["asset_id"] for r in wide}, {"builtin:street_tree_pine"})

    def test_osm_trees_anchor_pits_and_suppress_their_neighbours(self):
        name = named_species("cherry")
        points = {"osm_street_points": [dict(kind="tree", category="ginkgo", source_id="node/3", position=[1000, 1200]),
                                        dict(kind="tree", category="tree", source_id="node/4", position=[-20000, -1100]),
                                        dict(kind="tree", category="pine", source_id="node/5", position=[0, 9000])]}
        records, counts = osm_furniture.generate("l" * 32, self.avenue(), points, SCALE, RIGHT, {"r": dict(highway="primary", name=name)})
        found = trees(records)
        self.assertEqual(counts["street_trees_osm"], 2, counts)
        self.assertEqual(counts["skipped_street_trees_osm_reach"], 1, "beyond the sidewalk + 3 map m")
        offset = AVENUE["width"] / 2 + 28 * SCALE
        anchored = [r for r in found if abs(r["position"][0] - 1000) < 2 and r["position"][2] == round(offset)]
        self.assertEqual([r["asset_id"] for r in anchored], ["builtin:street_tree_ginkgo"], "the species hint is kept")
        other = [r for r in found if abs(r["position"][0] + 20000) < 2 and r["position"][2] == -round(offset)]
        self.assertEqual([r["asset_id"] for r in other], ["builtin:street_tree_cherry"], "an unknown species takes the street's")
        for anchor in (anchored[0], other[0]):
            near = [r for r in found if r is not anchor and at(r).distance(at(anchor)) < 0.6 * 270 * SCALE]
            self.assertEqual(near, [], "procedural stations near an OSM tree are dropped")

    def test_median_side_of_one_way_pairs_gets_beds_not_trees(self):
        gap = 300 * SCALE  # Map cm between the carriageway edges of the pair.
        y = AVENUE["width"] + gap
        patches = [node("a", -60000, 0), node("b", 60000, 0), node("c", 60000, y), node("d", -60000, y),
                   street("east", ("a", -60000, 0), ("b", 60000, 0), one_way=1, **AVENUE),
                   street("west", ("c", 60000, y), ("d", -60000, y), one_way=1, **AVENUE)]
        info = {r: dict(highway="primary", name="Pair") for r in ("east", "west")}
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        found = trees(records)
        self.assertTrue(found and all(r["position"][2] < 0 or r["position"][2] > y for r in found), "only the outer curbs")
        self.assertGreater(counts["skipped_street_trees_median"], 0)
        beds = [r for r in records if r["asset_id"] in (osm_furniture.MEDIAN_BED, osm_furniture.MEDIAN_PINE)]
        self.assertTrue(beds, counts)
        self.assertTrue(all(0 < r["position"][2] < y for r in beds), "in the median")
        self.assertEqual(counts["median_beds"] + counts["median_beds_pine"], len(beds))
        xs = sorted(r["position"][0] for r in beds)
        self.assertTrue(all(b - a >= 300 * SCALE for a, b in zip(xs, xs[1:])), "a pair fills its median once")
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        lines = [LineString([(-60000, 0), (60000, 0)]), LineString([(-60000, y), (60000, y)])]
        for r in beds:
            box = shapes.footprint(r["asset_id"], r["position"][0], r["position"][2], theta_deg(r))
            self.assertTrue(all(line.distance(box) >= AVENUE["width"] / 2 + 15 * SCALE for line in lines), r)
        ordered = [r["asset_id"] for r in sorted(beds, key=lambda r: r["position"][0])]
        self.assertGreater(counts["median_beds_pine"], 0)
        self.assertTrue(all(a != b or a == osm_furniture.MEDIAN_BED for a, b in zip(ordered, ordered[1:])), "pines alternate")
        # Two-way roads and lone one-way roads have no median.
        single = [node("a", -60000, 0), node("b", 60000, 0), street("east", ("a", -60000, 0), ("b", 60000, 0), one_way=1, **AVENUE)]
        self.assertFalse([r for r in osm_furniture.generate("l" * 32, single, {}, SCALE, RIGHT)[0] if r["asset_id"] in (osm_furniture.MEDIAN_BED, osm_furniture.MEDIAN_PINE)])
        # A bed needs sidewalk + 18 + 80 + 15 map cm between the carriageways.
        close = AVENUE["width"] + 160 * SCALE
        narrow = patches[:2] + [node("c", 60000, close), node("d", -60000, close), patches[4],
                                street("west", ("c", 60000, close), ("d", -60000, close), one_way=1, **AVENUE)]
        records, counts = osm_furniture.generate("l" * 32, narrow, {}, SCALE, RIGHT, info)
        self.assertEqual(len([r for r in records if r["asset_id"] in (osm_furniture.MEDIAN_BED, osm_furniture.MEDIAN_PINE)]), 0, "too narrow a median")
        self.assertGreater(counts["skipped_median_beds"], 0)

    def test_median_beds_keep_off_the_partners_median_side_sidewalk(self):
        info = {r: dict(highway="primary", name="Pair") for r in ("east", "west")}
        beds_of = lambda records: [r for r in records if r["asset_id"] in (osm_furniture.MEDIAN_BED, osm_furniture.MEDIAN_PINE)]
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        for gap, expected in ((250 * SCALE, False), (400 * SCALE, True)):
            with self.subTest(gap=gap):
                y = AVENUE["width"] + gap
                patches = [node("a", -60000, 0), node("b", 60000, 0), node("c", 60000, y), node("d", -60000, y),
                           street("east", ("a", -60000, 0), ("b", 60000, 0), one_way=1, width=AVENUE["width"], sidewalk=0),
                           street("west", ("c", 60000, y), ("d", -60000, y), one_way=1, width=AVENUE["width"], sidewalk=175 * SCALE)]
                records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
                beds = beds_of(records)
                self.assertEqual(bool(beds), expected, counts)
                paving = LineString([(-60000, y), (60000, y)]).buffer(AVENUE["width"] / 2 + 175 * SCALE)
                for r in beds:
                    self.assertFalse(shapes.footprint(r["asset_id"], r["position"][0], r["position"][2], theta_deg(r)).intersects(paving), r)
                if not expected: self.assertGreater(counts["skipped_median_beds"], 0)

    def test_planting_follows_the_width_of_each_segment(self):
        wide, narrow, sidewalk = 540 * SCALE, 360 * SCALE, 67 * SCALE
        y = wide / 2 + sidewalk + 150 * SCALE
        record = street("r", ("w", -60000, 0), ("e", 60000, 0), width=wide, sidewalk=sidewalk)
        record["after"].update(points=[[-60000, 0, 0], [0, 0, 0], [60000, 0, 0]], widths_cm=[wide, narrow], surfaces=["asphalt"] * 2)
        shops = dict(field="buildings", id="shops", after=dict(id="shops", footprint=[[-55000, y], [55000, y], [55000, y + 3000], [-55000, y + 3000]]))
        records, counts = osm_furniture.generate("l" * 32, [node("w", -60000, 0), node("e", 60000, 0), record, shops], {}, SCALE, RIGHT, PRIMARY)
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        segments = {-1: (LineString([(-60000, 0), (0, 0)]), wide), 1: (LineString([(0, 0), (60000, 0)]), narrow)}
        found = [r for r in trees(records) if abs(r["position"][0]) > 1500]
        self.assertTrue(found and {math.copysign(1, r["position"][0]) for r in found} == {-1, 1}, counts)
        for r in found:
            line, width = segments[math.copysign(1, r["position"][0])]
            self.assertAlmostEqual(abs(r["position"][2]), width / 2 + 28 * SCALE, delta=2)
            pit = shapes.footprint(r["asset_id"], r["position"][0], r["position"][2], theta_deg(r))
            self.assertTrue(pit.within(line.buffer(width / 2 + sidewalk)), "the pit stands on its segment's sidewalk")
        planters = [r for r in records if r["asset_id"] == osm_furniture.PLANTER and abs(r["position"][0]) > 1500]
        self.assertTrue({math.copysign(1, r["position"][0]) for r in planters} == {-1, 1}, counts)
        for r in planters:
            width = segments[math.copysign(1, r["position"][0])][1]
            self.assertAlmostEqual(r["position"][2], width / 2 + sidewalk + (10 + 15) * SCALE, delta=1)

    def test_pits_keep_off_mapkit_joint_faces_where_widths_change(self):
        # Jongno road -86 (20261106): 8 lanes, 3645 → 3745 source cm at a 0.77° left
        # bend. MapKit's joint face joins the mouths 1872.5 cm either side of the
        # vertex (each as wide as its segment) with straight edges, so it reaches
        # beyond the narrow segment's band by about 14 map cm at the vertex (inner
        # side). The pit of place-04504, 28 map cm beyond the narrow curb 126 map cm
        # before the vertex, intersected it (an OSM tree there anchors that pit).
        points = [[256026, 0, -162549], [262170, 0, -162252], [269055, 0, -161826]]
        record = street("r", ("w", 256026, -162549), ("e", 269055, -161826), lanes=8, width=3645, sidewalk=300)
        record["after"].update(points=points, widths_cm=[3645, 3745], surfaces=["asphalt"] * 2)
        osm = dict(osm_street_points=[dict(kind="tree", source_id="node/1", position=[261700, -160366])])
        records, counts = osm_furniture.generate("l" * 32, [node("w", 256026, -162549), node("e", 269055, -161826), record], osm, SCALE, RIGHT, PRIMARY)
        (bx, by), (vx, vy), (ax, ay) = ((q[0], q[2]) for q in points)
        corners = []
        for (ox, oy), half in (((bx, by), 3645 / 2), ((ax, ay), 3745 / 2)):
            length = math.hypot(ox - vx, oy - vy)
            ux, uy = (ox - vx) / length, (oy - vy) / length
            cx, cy = vx + ux * 3745 / 2, vy + uy * 3745 / 2
            corners += [(cx - uy * half, cy + ux * half), (cx + uy * half, cy - ux * half)]
        face = Polygon(corners).convex_hull
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        found = trees(records)
        self.assertTrue([r for r in found if r["position"][0] < vx] and [r for r in found if r["position"][0] > vx], counts)
        for r in found:
            self.assertFalse(shapes.footprint(r["asset_id"], r["position"][0], r["position"][2], theta_deg(r)).intersects(face), r)
        self.assertNotIn("street_trees_osm", counts, "the anchored pit is skipped")
        self.assertNotIn([261700, 0, -160366], [r["position"] for r in found])

    def test_joint_faces_follow_the_inside_of_bends(self):
        shapes = osm_furniture.Furniture([], {}, SCALE, {})
        # A width step on a straight record: the trapezoid between the mouths.
        face = shapes._joint((0, 0), (-6000, 0), (6000, 0), 540, 810)
        self.assertAlmostEqual(face.symmetric_difference(Polygon([(-810, -540), (810, -810), (810, 810), (-810, 540)])).area, 0, delta=1)
        # An equal-width 25° bend: the edges meet on both sides (MapKit's inner
        # meeting gets a fillet), so the face stays on the mitred band, unlike
        # the hull of the mouths that cut across the inner sidewalk.
        after = (6000 * math.cos(math.radians(25)), 6000 * math.sin(math.radians(25)))
        face = shapes._joint((0, 0), (-6000, 0), after, 810, 810)
        band = LineString([(-6000, 0), (0, 0), after]).buffer(810, join_style="mitre", mitre_limit=10.0)
        self.assertLess(face.difference(band).area, 0.001 * face.area)
        self.assertGreater(face.convex_hull.difference(band).area, 0.01 * face.area)

    def test_corridors_keep_the_adoption_width_floor(self):
        # Adoption widens other roads under 150 map cm (a 53 cm tunnel to 150);
        # walking roads keep their width.
        narrow = street("tunnel", ("w", -6000, 0), ("e", 6000, 0), width=160, sidewalk=0, kind="tunnel")
        path = street("path", ("s", 0, -6000), ("n", 0, 6000), width=160, sidewalk=0)
        shapes = osm_furniture.Furniture([narrow, path], {"osm_pedestrian_roads": ["path"]}, SCALE, {})
        self.assertEqual({r["id"]: r["widths_cm"] for r in shapes.roads}, {"tunnel": [150 * SCALE], "path": [160]})
        self.assertEqual(narrow["after"]["widths_cm"], [160], "the layer record is unchanged")

    def test_street_trees_keep_their_crowns_apart_in_bends(self):
        name = named_species("zelkova")
        # Stations 135 map cm either side of the bend (free end 135, pitch 270):
        # 75-98 map cm apart on the inside of a 40-45° turn without the spacing rule.
        start = -270 * SCALE
        for turn in (40.0, 45.0):
            with self.subTest(turn=turn):
                bend = (round(60000 * math.cos(math.radians(turn))), round(60000 * math.sin(math.radians(turn))))
                record = street("r", ("w", start, 0), ("e", *bend), width=400 * SCALE, sidewalk=100 * SCALE)
                record["after"].update(points=[[start, 0, 0], [0, 0, 0], [bend[0], 0, bend[1]]], widths_cm=[400 * SCALE] * 2, surfaces=["asphalt"] * 2)
                patches = [node("w", start, 0), node("e", *bend), record]
                info = {"r": dict(highway="primary", name=name)}
                found = trees(osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)[0])
                self.assertGreater(len(found), 50)
                reach = max(osm_furniture.STREET_TREE_CROWN_CM[r["asset_id"]] for r in found) * SCALE
                closest = min(at(a).distance(at(b)) for i, a in enumerate(found) for b in found[i + 1:])
                self.assertGreaterEqual(closest, reach - 1, "no trunk under a neighbour's crown")
                with patch.object(osm_furniture.Furniture, "_crowded", lambda *_: False):
                    loose = trees(osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)[0])
                self.assertLess(min(at(a).distance(at(b)) for i, a in enumerate(loose) for b in loose[i + 1:]), reach, "the bend inside converges")

    def test_planters_stand_along_building_fronts(self):
        half = AVENUE["width"] / 2
        def shops(sidewalk):
            y = half + sidewalk + 150 * SCALE
            return [dict(field="buildings", id="shops", after=dict(id="shops", footprint=[[-55000, y], [55000, y], [55000, y + 3000], [-55000, y + 3000]]))]
        for sidewalk, inside in ((67 * SCALE, False), (120 * SCALE, True)):
            with self.subTest(sidewalk=sidewalk):
                records, counts = osm_furniture.generate("l" * 32, self.avenue(sidewalk=sidewalk) + shops(sidewalk), {}, SCALE, RIGHT, PRIMARY)
                planters = [r for r in records if r["asset_id"] == osm_furniture.PLANTER]
                self.assertTrue(planters, counts)
                self.assertTrue(all(r["position"][2] > 0 for r in planters), "only in front of the buildings")
                expected = half + sidewalk + ((-5 - 15) if inside else (10 + 15)) * SCALE
                self.assertTrue(all(abs(r["position"][2] - expected) <= 1 for r in planters), (expected, planters[:2]))
                self.assertTrue(all(abs(theta_deg(r)) % 180 < 0.01 for r in planters), "the long side along the road")
                xs = sorted(r["position"][0] for r in planters)
                self.assertTrue(all((b - a) % (4 * 270 * SCALE) == 0 for a, b in zip(xs, xs[1:])), "every fourth tree gap")
                self.assertTrue(all(min(abs(r["position"][0] - t["position"][0]) for t in trees(records)) >= 135 * SCALE - 1 for r in planters))
        self.assertFalse([r for r in osm_furniture.generate("l" * 32, self.avenue(), {}, SCALE, RIGHT, PRIMARY)[0] if r["asset_id"] == osm_furniture.PLANTER], "no front, no planter")

    def test_earlier_ids_stay_counts_sum_and_caps_apply(self):
        arms = (("e", 30000, 0), ("w", -30000, 0), ("n", 0, 30000), ("s", 0, -30000))
        park = dict(source_id="way/7", landuse="park", polygon=[[20000, 20000], [40000, 20000], [40000, 40000], [20000, 40000]], holes=[])
        patches = junction(arms, **AVENUE)
        inputs = {"generation_regions": [park]}
        records, counts = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT)
        self.assertEqual(sum(v for k, v in counts.items() if not k.startswith("skipped_") and k != "over_limit"), len(records))
        with patch.multiple(osm_furniture, STREET_TREE_LIMIT=0, MEDIAN_BED_LIMIT=0, PLANTER_LIMIT=0, STREETLIGHT_LIMIT=0):
            earlier, earlier_counts = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT)
        self.assertFalse(trees(earlier))
        self.assertGreater(earlier_counts["skipped_street_trees_limit"], 0)
        self.assertEqual(records[:len(earlier)], earlier, "planting appends after every earlier placement id")
        with patch.object(osm_furniture, "STREET_TREE_LIMIT", 3):
            capped, capped_counts = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT)
        self.assertEqual(len(trees(capped)), 3)
        with patch.object(osm_furniture, "STREETLIGHT_LIMIT", 0):
            planted, _ = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT)
        self.assertTrue(lamps(records) and not lamps(planted))
        self.assertEqual(records[:len(planted)], planted, "streetlights append after every earlier placement id")
        with patch.object(osm_furniture, "STREETLIGHT_LIMIT", 0), patch.object(osm_furniture, "MAX_PLACEMENTS", len(earlier) + 5):
            limited, limited_counts = osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT)
        self.assertEqual(len(limited), len(earlier) + 5)
        self.assertGreater(limited_counts["over_limit"], 0)
        self.assertEqual(osm_furniture.generate("l" * 32, patches, inputs, SCALE, RIGHT), (records, counts), "fixed seeds")

def lamps(records):
    return [r for r in records if r["asset_id"] in osm_furniture.LAMPS]


def lamp_reach(record):
    return {**osm_furniture.STREETLIGHT_REACH_CM, **osm_furniture.TWIN_REACH_CM}[record["asset_id"]]


def lamp_head(record, sign=1):
    """Map-plane head centre (source cm) of a lamp record."""
    t = math.radians(theta_deg(record))
    reach = lamp_reach(record) * SCALE * sign
    return Point(record["position"][0] + math.cos(t) * reach, record["position"][2] + math.sin(t) * reach)


class Streetlights(unittest.TestCase):
    def road(self, length=60000, angle=0.0, info=PRIMARY, **options):
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        a, b = ("w", round(-length * c), round(-length * s)), ("e", round(length * c), round(length * s))
        patches = [node(*a), node(*b), street("r", a, b, **dict(AVENUE, **options))]
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        return patches, records, counts

    def test_constants_mirror_the_mapkit_contract(self):
        # map-kit/spec/CURRENT_V1.md city streetlights (CITY_STREETLIGHTS, CITY_STREETLIGHT_*).
        self.assertEqual(osm_furniture.STREETLIGHT_REACH_CM, {"builtin:city_streetlight_75": 75, "builtin:city_streetlight_135": 135,
                         "builtin:city_streetlight_195": 195, "builtin:city_streetlight_255": 255,
                         "builtin:city_streetlight_315": 315, "builtin:city_streetlight_375": 375})
        self.assertEqual(osm_furniture.TWIN_REACH_CM, {"builtin:city_streetlight_twin_75": 75, "builtin:city_streetlight_twin_135": 135})
        self.assertEqual((osm_furniture.LAMP_POLE_CM, osm_furniture.LAMP_HEIGHT_CM, osm_furniture.LAMP_HEAD_CM), (12, 330, 310))
        self.assertEqual((osm_furniture.LAMP_BACK_CM, osm_furniture.LAMP_TIP_CM, osm_furniture.LAMP_SIDE_CM, osm_furniture.LAMP_TOP_CM), (25, 20, 8, 345))
        self.assertTrue(all(osm_furniture.SIZES[a] == (6, 6) for a in osm_furniture.LAMPS))

    def test_poles_stand_behind_the_sidewalk_with_the_head_over_the_lanes(self):
        for angle in (0.0, 30.0, 45.0):
            with self.subTest(angle=angle):
                patches, records, counts = self.road(angle=angle)
                found = lamps(records)
                self.assertGreater(len(found), 20, counts)
                self.assertEqual(records[-len(found):], found, "streetlights come last")
                line = LineString([(q[0], q[2]) for q in patches[-1]["after"]["points"]])
                half, sidewalk = AVENUE["width"] / 2, AVENUE["sidewalk"]
                for r in found:
                    self.assertEqual(r["asset_id"], "builtin:city_streetlight_135")
                    self.assertAlmostEqual(line.distance(at(r)), half + sidewalk + 38 * SCALE, delta=2, msg="road + sidewalk + 30 cm + the pole")
                    over = half - line.distance(lamp_head(r))
                    self.assertTrue(25 * SCALE - 2 <= over < 85 * SCALE, f"head {over / SCALE:.0f} map cm over the carriageway")
                    self.assertTrue(r["id"].startswith("import-" + "l" * 32 + "-place-"))
                # Staggered on both sides of a two-way 4-lane road: every 10 map m per side, half a spacing apart.
                sides = {1: [], -1: []}
                for r in found:
                    sides[1 if line.project(at(r)) and (at(r).y * math.cos(math.radians(angle)) - at(r).x * math.sin(math.radians(angle))) > 0 else -1].append(line.project(at(r)))
                self.assertTrue(sides[1] and sides[-1])
                for stations in sides.values():
                    stations.sort()
                    self.assertTrue(all(abs(b - a - 1000 * SCALE) <= 2 * 135 * SCALE for a, b in zip(stations, stations[1:])), stations)
                pairs = sorted(min(abs(a - b) for b in sides[-1]) for a in sides[1])
                self.assertAlmostEqual(pairs[len(pairs) // 2], 500 * SCALE, delta=135 * SCALE, msg="staggered by half a spacing")

    def test_arms_pass_between_street_tree_crowns(self):
        _, records, counts = self.road(info={"r": dict(highway="primary", name=named_species("zelkova"))})
        crowns = [(at(r), osm_furniture.STREET_TREE_CROWN_CM[r["asset_id"]] * SCALE) for r in trees(records)]
        self.assertTrue(crowns and lamps(records), counts)
        self.assertEqual({r["asset_id"] for r in trees(records)}, {"builtin:street_tree_zelkova"})
        shape = osm_furniture.Furniture([], {}, SCALE, {})
        for r in lamps(records):
            envelope = shape._envelope(r["position"][0], r["position"][2], theta_deg(r), lamp_reach(r), False)
            self.assertTrue(all(envelope.distance(p) >= reach for p, reach in crowns), r)

    def test_classes_arrangements_and_reach_by_sidewalk(self):
        for info in ({"r": dict(highway="residential")}, {"r": dict(highway="motorway")}, {"r": dict(highway="service")}):
            self.assertEqual(lamps(self.road(info=info)[1]), [], info)
        self.assertEqual(lamps(self.road(info=None, stop_lines=False)[1]), [], "no class, no stop lines")
        self.assertTrue(lamps(self.road(info=None)[1]), "no class, junction stop lines")
        for kind in ("bridge", "tunnel"):
            self.assertEqual(lamps(self.road(kind=kind, sidewalk=0)[1]), [], kind)
        # Reach steps follow the sidewalk: the head stays 25-85 map cm over the lanes.
        for sidewalk, asset in ((0, "builtin:city_streetlight_75"), (67, "builtin:city_streetlight_135"), (100, "builtin:city_streetlight_195"),
                                (167, "builtin:city_streetlight_255"), (230, "builtin:city_streetlight_315"),
                                (290, "builtin:city_streetlight_375"), (330, None)):
            with self.subTest(sidewalk=sidewalk):
                _, records, counts = self.road(sidewalk=sidewalk * SCALE, info={"r": dict(highway="primary_link")} if sidewalk == 100 else PRIMARY)
                self.assertEqual({r["asset_id"] for r in lamps(records)}, {asset} if asset else set(), counts)
                if asset is None: self.assertGreater(counts["skipped_streetlights_reach"], 0)
        # Opposite pairs on 6+ lanes, one side on 2 lanes and links.
        _, records, counts = self.road(lanes=6, width=900 * SCALE)
        xs = sorted(round(r["position"][0]) for r in lamps(records) if r["position"][2] > 0)
        self.assertEqual(xs, sorted(round(r["position"][0]) for r in lamps(records) if r["position"][2] < 0), "facing pairs")
        self.assertEqual(counts["streetlights_opposite"], len(lamps(records)))
        for lanes, info in ((2, PRIMARY), (4, {"r": dict(highway="secondary_link")})):
            _, records, counts = self.road(lanes=lanes, info=info)
            self.assertTrue(lamps(records) and len({r["position"][2] > 0 for r in lamps(records)}) == 1, (lanes, info))
            self.assertEqual(counts["streetlights_one_side"], len(lamps(records)))

    def test_one_way_roads_light_the_drivers_side(self):
        for driving, one_way, side in (("right", 1, -1), ("right", -1, 1), ("left", 1, 1)):
            with self.subTest(driving=driving, one_way=one_way):
                a, b = ("w", -60000, 0), ("e", 60000, 0)
                patches = [node(*a), node(*b), street("r", a, b, lanes=2, one_way=one_way, **AVENUE)]
                records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, dict(driving_side=driving, signal_style="horizontal"), PRIMARY)
                self.assertTrue(lamps(records), counts)
                self.assertTrue(all(math.copysign(1, r["position"][2]) == side for r in lamps(records)), "right of travel (+x), left in left-hand traffic")

    def pair(self, gap, lanes=3, sidewalk=0):
        y = 360 * SCALE + gap
        patches = [node("a", -60000, 0), node("b", 60000, 0), node("c", 60000, y), node("d", -60000, y),
                   street("east", ("a", -60000, 0), ("b", 60000, 0), lanes=lanes, one_way=1, width=360 * SCALE, sidewalk=sidewalk),
                   street("west", ("c", 60000, y), ("d", -60000, y), lanes=lanes, one_way=1, width=360 * SCALE, sidewalk=sidewalk)]
        info = {r: dict(highway="primary", name="Pair") for r in ("east", "west")}
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        return y, lamps(records), counts

    def test_narrow_medians_get_twins_and_wide_medians_lamps_at_both_edges(self):
        y, found, counts = self.pair(150 * SCALE)
        twins = [r for r in found if r["asset_id"] in osm_furniture.TWIN_REACH_CM]
        self.assertTrue(twins, counts)
        self.assertEqual(counts["streetlights_twin"], len(twins))
        for r in twins:
            self.assertEqual(r["asset_id"], "builtin:city_streetlight_twin_135")
            self.assertAlmostEqual(r["position"][2], y / 2, delta=2, msg="the median centre")
            for sign, edge in ((1, 180 * SCALE), (-1, y - 180 * SCALE)):
                over = abs(lamp_head(r, sign).y - y / 2) - (y / 2 - 180 * SCALE)
                self.assertTrue(25 * SCALE - 2 <= over < 85 * SCALE, "both heads over a carriageway")
        median = [r for r in found if 0 < r["position"][2] < y]
        self.assertEqual(median, twins, "no single lamps beside the twins")
        self.assertGreater(counts["skipped_streetlights_covered"], 0, "the partner's median row is covered")
        self.assertTrue([r for r in found if r["position"][2] < 0] and [r for r in found if r["position"][2] > y], "outer rows")
        self.assertEqual(counts["streetlights_twin"] + counts["streetlights_staggered"], len(found))
        # Too narrow for a pole: nothing in the median.
        y, found, counts = self.pair(60 * SCALE)
        self.assertFalse([r for r in found if 0 < r["position"][2] < y])
        self.assertGreater(counts["skipped_streetlights_median"], 0)
        # Both sidewalks count: a 130 cm median between 40 cm sidewalks is too
        # narrow (each band grows by its sidewalk + 30 cm), not "blocked".
        y, found, counts = self.pair(130 * SCALE, sidewalk=40 * SCALE)
        self.assertFalse([r for r in found if 0 < r["position"][2] < y])
        self.assertGreater(counts["skipped_streetlights_median"], 0)
        self.assertEqual(counts.get("skipped_streetlights_blocked", 0), 0, counts)
        # Wide medians: single lamps at both median edges, each facing its own road.
        y, found, counts = self.pair(500 * SCALE)
        inner = [r for r in found if 0 < r["position"][2] < y]
        self.assertFalse([r for r in found if r["asset_id"] in osm_furniture.TWIN_REACH_CM])
        self.assertTrue([r for r in inner if r["position"][2] < y / 2] and [r for r in inner if r["position"][2] > y / 2], counts)
        for r in inner:
            near = 180 * SCALE if r["position"][2] < y / 2 else y - 180 * SCALE
            self.assertLess(abs(lamp_head(r).y - near), abs(r["position"][2] - near), "the arm reaches over its own road")
        # Two-lane one-way pairs light only their outer sides.
        y, found, counts = self.pair(150 * SCALE, lanes=2)
        self.assertTrue(found and not [r for r in found if 0 < r["position"][2] < y], counts)

    def assert_heads_over_the_lanes(self, patches, found):
        """Each head over a carriageway, each pole beyond every road's
        sidewalk + 30 cm + the pole half."""
        roads = [p["after"] for p in patches if p["field"] == "roads"]
        lines = [(LineString([(q[0], q[2]) for q in r["points"]]), max(r["widths_cm"]) / 2, r["sidewalk_cm"] or 0) for r in roads]
        for r in found:
            heads = [lamp_head(r, 1), lamp_head(r, -1)] if r["asset_id"] in osm_furniture.TWIN_REACH_CM else [lamp_head(r)]
            for head in heads:
                self.assertTrue(any(line.distance(head) <= half for line, half, _ in lines), f"{r['id']}: head off the carriageway")
            for line, half, sidewalk in lines:
                self.assertGreaterEqual(line.distance(at(r)), half + sidewalk + 36 * SCALE - 2, f"{r['id']}: pole inside a road band")

    def polyline(self, identity, a, b, points, **options):
        record = street(identity, a, b, **dict(AVENUE, **options))
        record["after"]["points"] = [[x, 0, y] for x, y in points]
        record["after"]["widths_cm"] = record["after"]["widths_cm"] * (len(points) - 1)
        record["after"]["surfaces"] = record["after"]["surfaces"] * (len(points) - 1)
        return record

    def test_heads_point_over_the_carriageway_on_curves_and_corners(self):
        # Arcs of 120 and 40 map m radius (5° vertices), both sides lit.
        for radius in (12000 * SCALE, 4000 * SCALE):
            with self.subTest(radius=radius):
                points = [(round(radius * math.cos(math.radians(d))), round(radius * math.sin(math.radians(d)))) for d in range(0, 181, 5)]
                a, b = ("w", *points[0]), ("e", *points[-1])
                patches = [node(*a), node(*b), self.polyline("r", a, b, points)]
                records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, PRIMARY)
                found = lamps(records)
                self.assertGreater(len(found), 10, counts)
                self.assertTrue([r for r in found if math.hypot(r["position"][0], r["position"][2]) > radius]
                                and [r for r in found if math.hypot(r["position"][0], r["position"][2]) < radius], "outer and inner sides")
                self.assert_heads_over_the_lanes(patches, found)
        # An L-shaped two-arm chain: two-way, one-way, and a one-way pair with twins round the bend.
        a, m, b = ("w", -60000, 0), ("m", 0, 0), ("n", 0, 60000)
        info = {r: dict(highway="primary", name="Corner") for r in ("left", "up", "back", "down")}
        for one_way in (0, 1):
            with self.subTest(one_way=one_way):
                patches = [node(*a), node(*m), node(*b), street("left", a, m, one_way=one_way, **AVENUE), street("up", m, b, one_way=one_way, **AVENUE)]
                records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
                self.assertTrue(lamps(records), counts)
                self.assert_heads_over_the_lanes(patches, lamps(records))
        d = 360 * SCALE + 150 * SCALE  # The pair's centreline offset: a 150 cm median.
        c, k, e = ("c", -d, 60000), ("k", -d, d), ("f", -60000, d)
        lane = dict(lanes=3, one_way=1, width=360 * SCALE, sidewalk=0)
        patches = [node(*a), node(*m), node(*b), node(*c), node(*k), node(*e),
                   street("left", a, m, **lane), street("up", m, b, **lane), street("back", c, k, **lane), street("down", k, e, **lane)]
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        twins = [r for r in lamps(records) if r["asset_id"] in osm_furniture.TWIN_REACH_CM]
        self.assertTrue(twins, counts)
        self.assert_heads_over_the_lanes(patches, lamps(records))

    def test_painted_walking_ribbons_keep_poles_off(self):
        half, sidewalk = AVENUE["width"] / 2, AVENUE["sidewalk"]
        pole = half + sidewalk + 38 * SCALE
        ribbon = dict(field="surface_areas", id="walk", after=dict(id="walk", surface="paving",
                      polygon=[[-60000, pole - 25 * SCALE], [60000, pole - 25 * SCALE], [60000, pole + 25 * SCALE], [-60000, pole + 25 * SCALE]]))
        lawn = dict(ribbon, id="lawn", after=dict(ribbon["after"], id="lawn", surface="grass",
                    polygon=[[-60000, -pole - 25 * SCALE], [60000, -pole - 25 * SCALE], [60000, -pole + 25 * SCALE], [-60000, -pole + 25 * SCALE]]))
        a, b = ("w", -60000, 0), ("e", 60000, 0)
        records, counts = osm_furniture.generate("l" * 32, [node(*a), node(*b), street("r", a, b, **AVENUE), ribbon, lawn], {}, SCALE, RIGHT, PRIMARY)
        self.assertFalse([r for r in lamps(records) if r["position"][2] > 0], "the paved ribbon")
        self.assertTrue([r for r in lamps(records) if r["position"][2] < 0], "a lawn strip is no obstacle")
        self.assertGreater(counts["skipped_streetlights_blocked"], 0)

    def test_buildings_barriers_decks_signals_and_junction_mouths_keep_lamps_away(self):
        half, sidewalk = AVENUE["width"] / 2, AVENUE["sidewalk"]
        pole = half + sidewalk + 38 * SCALE
        _, plain, _ = self.road()
        base = len(lamps(plain))
        # A building front 20 map cm behind the pole axis on the north side (inside the 25 cm back reach).
        front = dict(field="buildings", id="shops", after=dict(id="shops", footprint=[[-60000, pole + 20 * SCALE], [0, pole + 20 * SCALE], [0, pole + 5000], [-60000, pole + 5000]]))
        fence = dict(field="barriers", id="fence", after=dict(id="fence", kind="fence", line=[[0, pole + 15 * SCALE], [60000, pole + 15 * SCALE]], thickness_cm=15, height_cm=120))
        a, b = ("w", -60000, 0), ("e", 60000, 0)
        patches = [node(*a), node(*b), street("r", a, b, **AVENUE), front, fence]
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, PRIMARY)
        north = [r for r in lamps(records) if r["position"][2] > 0]
        self.assertFalse([r for r in north if r["position"][0] < 0], "the building front")
        self.assertFalse([r for r in north if r["position"][0] > 0], "the fence")
        self.assertGreater(counts["skipped_streetlights_building"], 0)
        self.assertGreater(counts["skipped_streetlights_barrier"], 0)
        self.assertTrue([r for r in lamps(records) if r["position"][2] < 0], "the south side stays lit")
        # A bridge crossing overhead keeps the envelope 1 map m clear of its deck (+20 cm walls).
        bridge = street("deck", ("n", 0, 60000), ("s", 0, -60000), width=600 * SCALE, sidewalk=None, kind="bridge", lanes=2)
        records, counts = osm_furniture.generate("l" * 32, [node(*a), node(*b), node("n", 0, 60000), node("s", 0, -60000), street("r", a, b, **AVENUE), bridge],
                                                 {}, SCALE, RIGHT, PRIMARY)
        clear = 300 * SCALE + (20 + osm_furniture.LAMP_DECK_CLEAR_CM) * SCALE
        shape = osm_furniture.Furniture([], {}, SCALE, {})
        for r in lamps(records):
            envelope = shape._envelope(r["position"][0], r["position"][2], theta_deg(r), lamp_reach(r), False)
            self.assertGreaterEqual(envelope.distance(LineString([(0, 60000), (0, -60000)])), clear - 2)
        self.assertGreater(counts.get("skipped_streetlights_deck", 0) + counts.get("skipped_streetlights_blocked", 0), 0)
        self.assertLess(len(lamps(records)), base)
        # Junctions: poles keep 3 map m from signal poles and stay out of the mouth.
        arms = (("e", 30000, 0), ("w", -30000, 0), ("n", 0, 30000), ("s", 0, -30000))
        info = {f"road-{n}": dict(highway="primary", name="Cross") for n, *_ in arms}
        records, counts = osm_furniture.generate("l" * 32, junction(arms, **AVENUE), {}, SCALE, RIGHT, info)
        signals = [at(r) for r in records if r["asset_id"] == "builtin:signal_h"]
        self.assertTrue(signals and lamps(records), counts)
        mouth = math.sqrt(2) * (half + sidewalk) + osm_furniture.CLEARANCE_CM * SCALE
        for r in lamps(records):
            self.assertTrue(all(at(r).distance(p) >= 300 * SCALE for p in signals))
            self.assertGreater(max(abs(r["position"][0]), abs(r["position"][2])), mouth)

    def test_rows_continue_across_record_joins_and_spacing_widens_to_fit_the_budget(self):
        a, m, b = ("w", -60000, 0), ("m", 0, 0), ("e", 60000, 0)
        info = {r: dict(highway="secondary", name="Long") for r in ("left", "right")}
        patches = [node(*a), node(*m), node(*b), street("left", a, m, lanes=2, **AVENUE), street("right", m, b, lanes=2, **AVENUE)]
        records, counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        found = sorted(r["position"][0] for r in lamps(records))
        self.assertTrue(len({r["position"][2] > 0 for r in lamps(records)}) == 1, "one chain, one side")
        gaps = [b - a for a, b in zip(found, found[1:])]
        self.assertTrue(all(abs(g - 1170 * SCALE) <= 2 * 135 * SCALE for g in gaps), gaps)
        self.assertEqual(len(found), math.floor((120000 - 2 * 135 * SCALE) / (1170 * SCALE)) + 1 - counts.get("skipped_streetlights_crown", 0) - counts.get("skipped_streetlights_blocked", 0))
        # A budget below the rows widens the spacing instead of cutting rows short.
        with patch.object(osm_furniture, "STREETLIGHT_LIMIT", len(found) // 2):
            fewer, fewer_counts = osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info)
        spread = sorted(r["position"][0] for r in lamps(fewer))
        self.assertLessEqual(len(spread), len(found) // 2)
        self.assertGreater(fewer_counts["skipped_streetlights_spacing"], 0)
        self.assertLess(spread[0], -50000)
        self.assertGreater(spread[-1], 50000, "the whole road stays lit")
        self.assertEqual(sum(v for k, v in fewer_counts.items() if not k.startswith("skipped_") and k != "over_limit"), len(fewer))
        self.assertEqual(osm_furniture.generate("l" * 32, patches, {}, SCALE, RIGHT, info), (records, counts), "fixed seeds")


if __name__ == "__main__":
    unittest.main()
