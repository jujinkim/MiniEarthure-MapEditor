"""City road rules on synthetic layouts only; no user geographic data is published."""
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import pyproj
from shapely.geometry import LineString, box, mapping, shape, Point
from shapely.ops import transform
import osm_roads
from osm_generalize import Generalizer
from geojson import convert


class Roads(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()
        self.options = dict(mode="wgs84-utm", origin=[9, 55], local_origin_m=[1000, 1000])
        projection = pyproj.Transformer.from_crs(4326, 32632, always_xy=True)
        x0, y0 = projection.transform(9, 55)
        self.inverse = lambda x, y, z=None: projection.transform(x + x0, y + y0, direction="INVERSE")
        self.features = []
        self.next_way = 1

    def add(self, geometry, refs=None, **properties):
        identity = self.next_way
        self.next_way += 1
        p = dict(osm_source_id=f"way/{identity}", **properties)
        if refs is not None:
            p["_city_refs"] = list(refs)
            p["_city_ends"] = [str(refs[0]), str(refs[-1])]
        self.features.append(dict(type="Feature", properties=p, geometry=json.loads(json.dumps(mapping(transform(self.inverse, geometry))))))
        return p["osm_source_id"]

    def road(self, points, refs, highway="primary", **tags):
        extra = {k: tags.pop(k) for k in list(tags) if k in ("width_m", "surface", "_city_level_structure", "_city_estimated_m", "_city_estimated_kind", "_city_crossings")}
        return self.add(LineString(points), refs, _city_road_tags=dict(highway=highway, **tags), **extra)

    def run_city(self, scale=3, gap=0):
        worker = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=scale)
        result, meta = worker.candidate(gap)
        roads = [(f["properties"], transform(worker.project, shape(f["geometry"]))) for f in result["features"] if f["geometry"]["type"] == "LineString"]
        return worker, result, meta, roads

    def layer(self, result):
        return convert(result, "synthetic", "ODbL-1.0", layer_id="c" * 32, coordinates=self.options, osm_graph=True, city=True)

    def ladder(self, crossings=(0, 100, 200), north=20, width="7", extra=lambda: None):
        """Carriageway A eastwards at y=0, B westwards at y=north, cross streets."""
        a = {x: 100 + i for i, x in enumerate(crossings)}
        b = {x: 200 + i for i, x in enumerate(crossings)}
        xs = list(crossings)
        for x0, x1 in zip(xs, xs[1:]):
            self.road([(x0, 0), (x1, 0)], [a[x0], a[x1]], oneway="yes", name="큰길", width_m=float(width))
            self.road([(x1, north), (x0, north)], [b[x1], b[x0]], oneway="yes", name="큰길", width_m=float(width))
        for i, x in enumerate(xs):
            self.road([(x, -60), (x, 0)], [300 + i, a[x]], highway="residential")
            self.road([(x, 0), (x, north)], [a[x], b[x]], highway="residential")
            self.road([(x, north), (x, north + 60)], [b[x], 400 + i], highway="residential")
        extra()
        return a, b

    def assert_connected(self, layer):
        nodes = {p["id"]: p["after"]["position"] for p in layer.patches if p["field"] == "nodes"}
        for p in layer.patches:
            if p["field"] != "roads": continue
            road = p["after"]
            self.assertEqual(nodes[road["from"]], road["points"][0])
            self.assertEqual(nodes[road["to"]], road["points"][-1])

    def test_class_profiles_set_vehicle_road_widths(self):
        self.road([(0, 0), (50, 0)], [1, 2], lanes="3")
        self.road([(50, 0), (100, 0)], [2, 3], highway="residential")
        self.road([(0, 10), (50, 10)], [4, 5], lanes="2", width_m=5.0)
        self.road([(0, 20), (50, 20)], [6, 7], lanes="6")
        self.road([(0, 30), (50, 30)], [8, 9], lanes="12")
        self.road([(0, 40), (50, 40)], [10, 11], highway="service", width_m=3.0)
        self.road([(0, 50), (50, 50)], [12, 13], highway="residential", oneway="yes")
        self.road([(0, 60), (50, 60)], [14, 15], highway="footway", width_m=2.0)
        for scale in (3, 8):
            with self.subTest(scale=scale):
                worker = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=scale)
                widths = {f["properties"]["osm_source_id"]: round(f["properties"]["width_m"] * 100 / scale) for f, g in worker.features if g.geom_type == "LineString"}
                self.assertEqual(widths["way/1"], 500, "three primary lanes: the class floor (map cm)")
                self.assertEqual(widths["way/2"], 300, "residential: two lanes, its floor")
                self.assertEqual(widths["way/3"], 500, "a tagged width does not set a vehicle road")
                self.assertEqual(widths["way/4"], 6 * osm_roads.LANE_CM + 60)
                self.assertEqual(widths["way/5"], 8 * osm_roads.LANE_CM + 60, "lanes capped per class")
                self.assertEqual(widths["way/6"], 200, "service: one lane, its floor")
                self.assertEqual(widths["way/7"], 175, "a one-way residential lane")
                self.assertEqual(widths["way/8"], round(200 / scale), "walking ways keep their source width")
                self.assertEqual(worker.road_rules["profile_tagged_width_ignored"], 2)
                self.assertEqual(worker.road_rules["lane_widths"], 3)

    def test_chains_join_across_width_lane_name_and_ref_changes_with_segment_widths(self):
        self.road([(0, 0), (40, 0)], [1, 2], lanes="2", name="가")
        self.road([(40, 0), (80, 0)], [2, 3], lanes="4", name="나", ref="7")
        self.road([(80, 0), (120, 0)], [3, 4], width_m=9.0)
        self.road([(120, 0), (160, 0)], [4, 5], surface="concrete")
        self.road([(160, 0), (200, 0)], [5, 6], highway="secondary", surface="concrete")
        worker, result, meta, roads = self.run_city(gap=0)
        self.assertEqual(meta["after"]["roads"], 3, "surface and class changes still break chains")
        first = next(p for p, g in roads if "way/1" in p["_city_sources"])
        self.assertEqual(first["_city_sources"], ["way/1", "way/2", "way/3"])
        self.assertEqual(first["_city_widths_m"], [15.0, 16.2, 16.2])
        self.assertEqual(first["_city_lanes"], 4, "lane counts vote by length; a tie takes the larger count")
        layer = self.layer(result)
        road = next(p["after"] for p in layer.patches if p["field"] == "roads" and len(p["after"]["points"]) == 4)
        self.assertEqual(road["widths_cm"], [1500, 1620, 1620], "per-segment profile widths, ÷D at adoption")

    def test_dual_carriageway_ladder_merges_into_one_two_way_road(self):
        a, b = self.ladder()
        before = {f["properties"]["osm_source_id"] for f in self.features}
        worker, result, meta, roads = self.run_city()
        rules = meta["road_rules"]
        self.assertEqual(rules["dual_merged_pairs"], 1)
        self.assertEqual(rules["dual_merged_ways"], 4)
        self.assertEqual(rules["dual_absorbed_links"], 3, "median rungs are absorbed")
        self.assertEqual(set(meta["source_ids"]), before, "no source is dropped")
        merged = [(p, g) for p, g in roads if p.get("_city_dual")]
        self.assertEqual(len(merged), 2, "one two-way road per block between the cross-street junctions")
        self.assertEqual(sum(len(p["_city_sources"]) for p, g in merged), 2 + 2 + 3, "both carriageways and the median rungs")
        for p, g in merged:
            self.assertTrue(all(abs(y - 10) < 0.05 for x, y in g.coords), "midline of both carriageways")
            self.assertNotIn("oneway", p["_city_road_tags"])
            self.assertTrue(all(abs(w - (20 - 7 + 2 * 9)) < 0.05 for w in p["_city_widths_m"]), "two 300 cm profile carriageways and the source median")
        # Every cross street now ends at the moved midline node.
        for x in (0, 100, 200):
            south = next(g for q, g in roads if g.coords[0] == (x, -60) or abs(g.coords[0][0] - x) < 0.05 and abs(g.coords[0][1] + 60) < 0.05)
            north = next(g for q, g in roads if abs(g.coords[-1][0] - x) < 0.05 and abs(g.coords[-1][1] - 80) < 0.05)
            self.assertAlmostEqual(south.coords[-1][1], 10, places=1)
            self.assertAlmostEqual(north.coords[0][1], 10, places=1)
        layer = self.layer(result)
        self.assert_connected(layer)
        road = next(q["after"] for q in layer.patches if q["field"] == "roads" and len(set(q["after"]["widths_cm"])) == 1 and q["after"]["widths_cm"][0] == 3100)
        self.assertEqual(road["markings"]["lanes"], 4)
        self.assertTrue(road["markings"]["center_line"], "two-way after merging")

    def test_one_sided_t_junction_gets_a_midline_node(self):
        def side():
            self.road([(150, 20), (150, 80)], [200 + 9, 500], highway="residential")
        # B's piece between x=200 and x=100 is split at the side street (node 209).
        a = {0: 100, 100: 101, 200: 102}
        b = {0: 200, 100: 201, 200: 202}
        for x0, x1 in ((0, 100), (100, 200)):
            self.road([(x0, 0), (x1, 0)], [a[x0], a[x1]], oneway="yes", width_m=7.0)
        self.road([(200, 20), (150, 20)], [202, 209], oneway="yes", width_m=7.0)
        self.road([(150, 20), (100, 20)], [209, 201], oneway="yes", width_m=7.0)
        self.road([(100, 20), (0, 20)], [201, 200], oneway="yes", width_m=7.0)
        for i, x in enumerate((0, 100, 200)):
            self.road([(x, 0), (x, 20)], [a[x], b[x]], highway="residential")
        side()
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1)
        street = next(g for p, g in roads if p["_city_sources"] == [self.features[-1]["properties"]["osm_source_id"]])
        self.assertAlmostEqual(street.coords[0][0], 150, places=1)
        self.assertAlmostEqual(street.coords[0][1], 10, places=1)
        ends = Counter(e for p, g in roads for e in p.get("_city_ends", []) if e)
        self.assertEqual(ends["209"], 3, "the side street meets the merged road at its own source node")
        self.assert_connected(self.layer(result))

    def test_converge_node_and_u_turn_link_bound_and_join_the_merge(self):
        # West rung at x=0; carriageways converge at node 9 (x=300) into a two-way road.
        self.road([(0, 0), (150, 0)], [100, 101], oneway="yes", width_m=7.0)
        self.road([(150, 0), (290, 0), (300, 10)], [101, 150, 9], oneway="yes", width_m=7.0)
        self.road([(300, 10), (290, 20), (150, 20)], [9, 151, 201], oneway="yes", width_m=7.0)
        self.road([(150, 20), (0, 20)], [201, 200], oneway="yes", width_m=7.0)
        self.road([(300, 10), (400, 10)], [9, 10], width_m=10.0)
        self.road([(0, 0), (0, 20)], [100, 200], highway="residential")
        # A curved U-turn link between the carriageways, longer than 1.5 × 20 m.
        u_turn = self.road([(150, 0), (160, 5), (165, 10), (160, 15), (150, 20)], [101, 160, 161, 162, 201], highway="primary_link", oneway="yes")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1)
        merged = [p for p, g in roads if p.get("_city_dual")]
        self.assertTrue(any(u_turn in p["_city_sources"] for p in merged), "the U-turn link is absorbed")
        self.assertFalse(any(p["_city_sources"] == [u_turn] for p, g in roads))
        ends = Counter(e for p, g in roads for e in p.get("_city_ends", []) if e)
        self.assertEqual(ends["9"], 0, "past the converge node the merged road continues as the two-way road")
        self.assertTrue(any(abs(g.coords[-1][0] - 400) < 0.05 for p, g in roads if p.get("_city_dual")))
        self.assert_connected(self.layer(result))

    def test_structure_pairs_never_merge_and_merging_stops_a_lead_before_anchors(self):
        # A pair of estimated bridges between x=100 and x=160, ground on both sides.
        xs = [-200, 0, 100, 160, 260, 460]
        a = [100 + i for i in range(len(xs))]
        b = [200 + i for i in range(len(xs))]
        for i in range(len(xs) - 1):
            props = dict(_city_estimated_m=[0.0, 0.0], _city_estimated_kind="bridge") if xs[i] == 100 else {}
            self.road([(xs[i], 0), (xs[i + 1], 0)], [a[i], a[i + 1]], oneway="yes", width_m=7.0, **props)
            self.road([(xs[i + 1], 20), (xs[i], 20)], [b[i + 1], b[i]], oneway="yes", width_m=7.0, **props)
        for i, x in enumerate(xs):
            self.road([(x, 0), (x, 20)], [a[i], b[i]], highway="residential")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 2, "only the ground blocks away from the bridges")
        bridges = [g for p, g in roads if "_city_estimated_m" in p]
        self.assertEqual(len(bridges), 2)
        self.assertEqual(sorted(round(g.coords[0][1]) for g in bridges), [0, 20], "structures keep their geometry")
        for p, g in roads:
            if p.get("_city_dual"):
                self.assertTrue(all(abs(x - 100) >= 8 and abs(x - 160) >= 8 for x, y in g.coords), "a lead length before the anchors")
                self.assertTrue(g.coords[-1][0] <= 0.01 or g.coords[0][0] >= 259.99)
        self.assert_connected(self.layer(result))

    def test_a_dead_end_deck_gives_the_outer_level_lead_to_a_ground_road(self):
        self.road([(-100, 0), (0, 0)], [9, 1], highway="residential")
        self.road([(75, 50), (75, -50)], [7, 8], highway="residential")  # A crossing road under the deck.
        self.road([(0, 0), (12, 0), (50, 0), (100, 0), (138, 0), (150, 0)], [1, 2, 3, 4, 5, 6], highway="residential",
                  _city_estimated_m=[0.0, 0.0, 6.0, 6.0, 0.0, 0.0], _city_estimated_kind="bridge")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["open_deck_ends"], 1)
        [lead] = [(p, g) for p, g in roads if p.get("_city_ground_lead")]
        [deck] = [(p, g) for p, g in roads if "_city_estimated_m" in p]
        synthetic = str(osm_roads.LEAD_REF_BASE + 6)
        self.assertEqual(lead[0]["_city_ends"], [synthetic, "6"], "the dead end's outer level lead")
        self.assertEqual(deck[0]["_city_ends"], ["1", synthetic], "the connected end keeps its deck lead")
        keep = 9.0 / 2 + 1.0  # Half the widest (residential 300 map cm = 9 m) road + 1 m.
        self.assertAlmostEqual(lead[1].coords[0][0], 138 + keep, delta=0.05, msg="the deck keeps a level mouth")
        self.assertEqual(deck[0]["_city_estimated_m"][-2:], [0.0, 0.0])
        layer = self.layer(result)
        self.assert_connected(layer)
        kinds = [p["after"]["kind"] for p in layer.patches if p["field"] == "roads"]
        self.assertEqual(kinds.count("bridge"), 1)

    def test_a_short_dead_end_lead_keeps_its_deck_cap(self):
        self.road([(-100, 0), (0, 0)], [9, 1], highway="residential")
        self.road([(75, 50), (75, -50)], [7, 8], highway="residential")
        self.road([(0, 0), (8, 0), (50, 0), (100, 0), (144, 0), (150, 0)], [1, 2, 3, 4, 5, 6], highway="residential",
                  _city_estimated_m=[0.0, 0.0, 6.0, 6.0, 0.0, 0.0], _city_estimated_kind="bridge")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"].get("open_deck_ends", 0), 0, "6 m < 5.5 m mouth + 1 m ground")
        self.assertFalse(any(p.get("_city_ground_lead") for p, g in roads))

    def test_a_structure_between_the_carriageways_blocks_the_merge(self):
        a, b = self.ladder(extra=lambda: self.road([(120, 10), (180, 10)], [900, 901], highway="tertiary",
                                                   _city_estimated_m=[-6.0, -6.0], _city_estimated_kind="tunnel"))
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"].get("dual_merged_pairs", 0), 1, "only the block without the underpass")
        tunnel = [g for p, g in roads if "_city_estimated_m" in p]
        self.assertEqual(len(tunnel), 1, "a structure is never absorbed")

    def pair_between_ramps(self, highway="trunk", rung=False, slip=False, north=20):
        """A eastwards at y=0 (ramp nodes at x=0 and 400), B westwards at y=north
        (ramp nodes at x=390 and 10): no median link unless `rung`."""
        self.road([(-100, 0), (0, 0)], [10, 11], highway=highway, oneway="yes", width_m=8.0)
        self.road([(0, 0), (400, 0)], [11, 12], highway=highway, oneway="yes", width_m=8.0)
        self.road([(400, 0), (500, 0)], [12, 13], highway=highway, oneway="yes", width_m=8.0)
        self.road([(500, north), (390, north)], [20, 21], highway=highway, oneway="yes", width_m=8.0)
        self.road([(390, north), (10, north)], [21, 22], highway=highway, oneway="yes", width_m=8.0)
        self.road([(10, north), (-100, north)], [22, 23], highway=highway, oneway="yes", width_m=8.0)
        ramps = [self.road([(0, 0), (40, -40)], [11, 30], highway=highway + "_link", oneway="yes"),
                 self.road([(360, -40), (400, 0)], [31, 12], highway=highway + "_link", oneway="yes"),
                 self.road([(390, north), (350, north + 40)], [21, 32], highway=highway + "_link", oneway="yes"),
                 self.road([(50, north + 40), (10, north)], [33, 22], highway=highway + "_link", oneway="yes")]
        if rung:
            self.road([(200, 0), (200, 20)], [40, 41], highway="tertiary")
        if slip:
            # A slip road beside A, in A's direction: never a partner.
            ramps.append(self.road([(0, 0), (60, -8), (340, -8), (400, 0)], [11, 50, 51, 12], highway=highway, oneway="yes", width_m=4.0))
        return ramps

    def test_trunk_sections_between_ramps_merge_without_a_median_rung(self):
        ramps = self.pair_between_ramps(slip=True)
        before = {f["properties"]["osm_source_id"] for f in self.features}
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1, "aligned ramp nodes bound the merge")
        self.assertEqual(set(meta["source_ids"]), before)
        merged = [(p, g) for p, g in roads if p.get("_city_dual")]
        self.assertTrue(merged and all(abs(y - 10) < 0.05 for p, g in merged for x, y in g.coords))
        slip = next(p for p, g in roads if p["_city_sources"] == [ramps[-1]])
        self.assertEqual(slip["_city_road_tags"].get("oneway"), "yes", "the parallel slip road stays its own one-way road")
        for ramp in ramps[:-1]:
            line = next(g for p, g in roads if p["_city_sources"] == [ramp])
            self.assertTrue(any(abs(y - 10) < 0.05 for x, y in (line.coords[0], line.coords[-1])), "ramps follow the merged node")
        self.assert_connected(self.layer(result))

    def test_one_real_rung_is_required_below_trunk(self):
        self.pair_between_ramps(highway="primary")
        self.assertEqual(self.run_city()[2]["road_rules"].get("dual_merged_pairs", 0), 0, "no rung: primary pairs stay apart")
        self.setUp()
        self.pair_between_ramps(highway="primary", rung=True)
        # The rung splits both carriageways at x=200.
        self.features = [f for f in self.features if f["properties"]["_city_refs"] not in ([11, 12], [21, 22])]
        self.road([(0, 0), (200, 0)], [11, 40], highway="primary", oneway="yes", width_m=8.0)
        self.road([(200, 0), (400, 0)], [40, 12], highway="primary", oneway="yes", width_m=8.0)
        self.road([(390, 20), (200, 20)], [21, 41], highway="primary", oneway="yes", width_m=8.0)
        self.road([(200, 20), (10, 20)], [41, 22], highway="primary", oneway="yes", width_m=8.0)
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1, "one real rung plus aligned ends")
        self.assert_connected(self.layer(result))

    def test_rungless_pairs_whose_profiles_overlap_merge(self):
        # 8.8 m apart: two 300 map cm one-way primary profiles (9 m at 1:3) would overlap.
        self.pair_between_ramps(highway="primary", north=8.8)
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1)
        self.assertEqual(meta["road_rules"]["dual_overlap_merged_pairs"], 1)
        self.assert_connected(self.layer(result))

    def test_a_diagonal_turn_link_up_to_three_separations_is_a_rung(self):
        a = {0: 100, 100: 101, 300: 102}
        b = {0: 200, 140: 201, 300: 202}
        self.road([(0, 0), (100, 0)], [100, 101], oneway="yes", width_m=7.0)
        self.road([(100, 0), (300, 0)], [101, 102], oneway="yes", width_m=7.0)
        self.road([(300, 20), (140, 20)], [202, 201], oneway="yes", width_m=7.0)
        self.road([(140, 20), (0, 20)], [201, 200], oneway="yes", width_m=7.0)
        # The turn link is the only real rung; the ends are aligned nodes.
        self.road([(0, 0), (0, -60)], [100, 300], highway="residential")
        self.road([(300, 20), (300, 80)], [202, 301], highway="residential")
        turn = self.road([(100, 0), (140, 20)], [101, 201], highway="primary_link", oneway="yes")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"]["dual_merged_pairs"], 1)
        self.assertNotIn([turn], [p["_city_sources"] for p, g in roads], "the 2.2 × separation turn link is an absorbed rung")
        self.assertTrue(any(turn in p["_city_sources"] for p, g in roads if p.get("_city_dual")))
        self.assert_connected(self.layer(result))

    def test_a_chain_trims_buildings_by_each_segment_width(self):
        self.road([(0, 0), (100, 0)], [1, 2], width_m=6.0)
        self.road([(100, 0), (200, 0)], [2, 3], lanes="6")
        building = self.add(box(20, 9, 60, 13), height_m=10)
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["after"]["roads"], 1, "one chain with 15 m and 23.4 m segments")
        self.assertNotIn(building, worker.excluded_sources, "the 23.4 m segment does not trim along the 15 m one")
        self.assertNotIn(building, meta["trimmed_building_sources"])
        self.assertIn(building, meta["source_ids"])

    def test_explicit_height_road_between_the_carriageways_blocks_the_merge(self):
        self.ladder(extra=lambda: self.add(LineString([(120, 10), (180, 10)]), None, osm_node_refs=[900, 901], osm_way_id=900, road_kind="ground",
                                            elevations_m=[0.0, -2.0], _city_road_tags=dict(highway="tertiary")))
        worker, result, meta, roads = self.run_city()
        self.assertEqual((meta["road_rules"]["dual_merged_pairs"], meta["road_rules"]["dual_merged_ways"]), (1, 2), "only the block a lead length away")
        explicit = next(g for p, g in roads if "osm_node_refs" in p)
        self.assertEqual([tuple(round(v) for v in c) for c in explicit.coords], [(120, 10), (180, 10)])

    def test_a_jughandle_u_turn_onto_one_merged_node_is_absorbed(self):
        self.ladder()
        u_turn = self.road([(100, 0), (115, -15), (130, -5), (130, 25), (115, 35), (100, 20)], [101, 600, 601, 602, 603, 201],
                           highway="primary_link", oneway="yes")
        worker, result, meta, roads = self.run_city()
        self.assertTrue(any(u_turn in p["_city_sources"] for p, g in roads if p.get("_city_dual")), "represented by the merged road")
        self.assertTrue(all(p.get("_city_ends") for p, g in roads), "no loop split into disconnected pieces")
        layer = self.layer(result)
        self.assertFalse([w for w in layer.warnings if "disconnected endpoints" in w])
        self.assert_connected(layer)

    def test_sidewalk_changes_break_chains(self):
        self.add(box(-50, -50, 300, 50), osm_region=True, landuse="residential")
        self.road([(0, 0), (100, 0)], [1, 2], highway="residential")
        self.road([(100, 0), (200, 0)], [2, 3], highway="residential", sidewalk="no")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(sorted(p["_city_sidewalk_m"] for p, g in roads), [0.0, 2.01], "one sidewalk per road record")

    def test_crossings_survive_absorbed_sidewalk_footways_and_are_counted_once(self):
        lon, lat = self.inverse(50, 6)
        self.road([(0, 0), (100, 0)], [1, 2], highway="residential", sidewalk="separate", width_m=6.0)
        footway = self.road([(0, 6), (100, 6)], [3, 4], highway="footway", footway="sidewalk", _city_crossings=[[lon, lat]])
        self.road([(0, 20), (100, 20)], [5, 6], highway="residential", _city_crossings=[[lon, lat]])
        worker = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=3)
        self.assertNotIn(footway, {f["properties"]["osm_source_id"] for f, g in worker.features})
        self.assertEqual(len(worker.crossing_points), 1, "kept from the absorbed footway, once")

    def test_service_ways_stay_roads_when_painting_would_strand_a_road_or_structure(self):
        self.road([(0, 0), (100, 0)], [1, 2], highway="residential")
        driveway = self.road([(100, 0), (110, 0)], [2, 3], highway="service", service="driveway")
        self.road([(110, 0), (200, 0)], [3, 4], highway="residential")
        aisle = self.road([(0, 0), (0, 30)], [1, 5], highway="service", service="parking_aisle")
        ramp = self.road([(200, 0), (210, 0)], [4, 6], highway="service", service="driveway")
        self.road([(210, 0), (300, 0)], [6, 7], highway="residential", _city_estimated_m=[0.0, 6.0], _city_estimated_kind="bridge")
        worker = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=3)
        painted = {f["properties"]["osm_source_id"]: f["properties"].get("_city_ground_paint") for f, g in worker.features if g.geom_type == "LineString"}
        self.assertIsNone(painted[driveway], "the only link between two roads")
        self.assertIsNone(painted[ramp], "a structure's only approach")
        self.assertEqual(painted[aisle], "service", "a dead-end aisle is still painted")

    def test_parallel_one_way_streets_a_block_apart_do_not_merge(self):
        # 20 m apart with buildings between them, and 45 m apart without.
        self.road([(0, 0), (200, 0)], [1, 2], highway="tertiary", oneway="yes", width_m=6.0)
        self.road([(200, 20), (0, 20)], [3, 4], highway="tertiary", oneway="yes", width_m=6.0)
        self.add(box(20, 6, 180, 14), height_m=10)
        self.road([(0, 100), (200, 100)], [5, 6], highway="tertiary", oneway="yes", width_m=6.0)
        self.road([(200, 145), (0, 145)], [7, 8], highway="tertiary", oneway="yes", width_m=6.0)
        self.road([(0, 0), (0, 20)], [1, 4], highway="residential")
        self.road([(200, 0), (200, 20)], [2, 3], highway="residential")
        self.road([(0, 100), (0, 145)], [5, 8], highway="residential")
        self.road([(200, 100), (200, 145)], [6, 7], highway="residential")
        worker, result, meta, roads = self.run_city()
        self.assertEqual(meta["road_rules"].get("dual_merged_pairs", 0), 0)
        self.assertEqual(sum(1 for p, g in roads if "oneway" in p["_city_road_tags"]), 4)

    def test_sidewalks_follow_tags_class_urban_land_and_parallel_footways(self):
        self.add(box(-50, -50, 400, 400), osm_region=True, landuse="residential")
        primary = self.road([(0, 0), (100, 0)], [1, 2])
        trunk = self.road([(0, 50), (100, 50)], [3, 4], highway="trunk", sidewalk="both")
        residential = self.road([(0, 100), (100, 100)], [5, 6], highway="residential")
        tagged_no = self.road([(0, 150), (100, 150)], [7, 8], highway="tertiary", sidewalk="no")
        service = self.road([(0, 200), (100, 200)], [9, 10], highway="service")
        separate = self.road([(0, 250), (100, 250)], [11, 12], highway="residential", sidewalk="separate", width_m=6.0)
        footway = self.road([(0, 256), (100, 256)], [13, 14], highway="footway", footway="sidewalk")
        worker = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=3)
        sidewalk = {f["properties"]["osm_source_id"]: f["properties"].get("_city_sidewalk_m") for f, g in worker.features if g.geom_type == "LineString"}
        self.assertEqual(sidewalk[primary], 3.0, "primary in urban land: 3 m (100 map cm at 1:3)")
        self.assertEqual(sidewalk[trunk], 0.0, "trunk: none, even when tagged")
        self.assertEqual(sidewalk[residential], 2.01, "2 m on the 1:3 lattice: 67 map cm")
        self.assertEqual(sidewalk[tagged_no], 0.0)
        self.assertEqual(sidewalk[service], 0.0, "service roads: no sidewalk")
        self.assertEqual(sidewalk[separate], 2.49, "to the footway's outer edge (6 - 4.5 + 0.8 m, in 0.25 m steps): 83 map cm")
        self.assertNotIn(footway, sidewalk, "the covered sidewalk footway is absorbed")
        owner = next(f for f, g in worker.features if f["properties"]["osm_source_id"] == separate)
        self.assertIn(footway, owner["properties"]["_city_sources"])
        result, meta = worker.candidate(0)
        layer = self.layer(result)
        sidewalks = Counter(p["after"]["sidewalk_cm"] for p in layer.patches if p["field"] == "roads")
        self.assertNotIn(None, sidewalks, "every ground road has an explicit sidewalk")
        self.assertTrue(all(v == 0 or v / 3 >= 20 for v in sidewalks), "0 or at least 20 map cm after the 1:3 adoption")
        self.assertIn(300, sidewalks, "3 m: 100 map cm, written as source centimetres")

    def test_sidewalks_quantize_to_zero_or_twenty_map_centimetres(self):
        self.assertEqual(osm_roads.quantized_sidewalk(2.0, 3), 67)
        self.assertEqual(osm_roads.quantized_sidewalk(1.5, 8), 20, "19 map cm rounds up to the 20 cm minimum")
        self.assertEqual(osm_roads.quantized_sidewalk(0.5, 8), 0, "6 map cm is no sidewalk")
        self.assertEqual(osm_roads.quantized_sidewalk(50, 3), 1000)

    def test_markings_lanes_center_line_and_junction_crosswalks(self):
        self.assertEqual(osm_roads.markings("primary", None, True, "asphalt")["lanes"], 4)
        self.assertEqual(osm_roads.markings("secondary", None, True, "asphalt")["lanes"], 2)
        self.assertIsNone(osm_roads.markings("residential", None, True, "asphalt"), "none below tertiary")
        self.assertEqual(osm_roads.markings("residential", 2, True, "asphalt")["lanes"], 2, "a tagged lane count")
        self.assertFalse(osm_roads.markings("primary", 3, True, "asphalt")["center_line"], "odd lane counts")
        self.assertFalse(osm_roads.markings("primary", 4, False, "asphalt")["center_line"], "one-way roads")
        self.assertIsNone(osm_roads.markings("primary", 4, True, "gravel"), "paint needs asphalt or concrete")
        self.assertFalse(osm_roads.markings("primary", 4, True, "concrete")["edge_lines"])
        lon, lat = self.inverse(90, 0)
        self.road([(0, 0), (100, 0)], [1, 2], _city_crossings=[[lon, lat]])
        self.road([(100, 0), (200, 0)], [2, 3], highway="secondary")
        self.road([(100, 0), (100, 80)], [2, 4], highway="residential")
        self.road([(0, 0), (0, 80)], [1, 5], highway="residential")
        self.road([(0, 0), (0, -80)], [1, 6], highway="residential")
        self.road([(150, -10), (150, 10)], [7, 8], highway="footway", footway="crossing")
        worker, result, meta, roads = self.run_city()
        marks = {p["_city_sources"][0]: p.get("_city_markings") for p, g in roads}
        self.assertEqual(marks["way/1"]["crosswalk_end"], True, "a crossing node within 15 m of the junction")
        self.assertEqual(marks["way/1"]["crosswalk_start"], False)
        self.assertEqual(marks["way/2"]["crosswalk_start"], False, "the footway crossing is 50 m from the junction")
        self.assertIsNone(marks["way/3"])

    def test_paint_estimate_bounds_records_and_splits_long_winding_roads(self):
        import math
        points = [(i * 12.0, 6.0 * math.sin(i)) for i in range(60)]
        refs = list(range(1, 61))
        self.road(points, refs, highway="primary")
        self.road([(points[-1][0], points[-1][1]), (points[-1][0], 100)], [60, 99], highway="residential")
        self.road([(points[-1][0], points[-1][1]), (points[-1][0], -100)], [60, 98], highway="residential")
        self.road([(0, 0), (0, 100)], [1, 97], highway="residential")
        self.road([(0, 0), (0, -100)], [1, 96], highway="residential")
        worker, result, meta, roads = self.run_city()
        marked = [(p, g) for p, g in roads if p.get("_city_markings")]
        self.assertGreater(len(marked), 1, "split at source nodes")
        self.assertEqual(meta["road_rules"]["paint_splits"], len(marked) - 1)
        self.assertLessEqual(meta["paint_segment_bound"], osm_roads.PAINT_SEGMENTS)
        pieces = [(dict(type="Feature", properties=p), g) for p, g in roads]
        graph = osm_roads.Graph(pieces, lambda f, g: True)
        for index, (f, g) in enumerate(pieces):
            if f["properties"].get("_city_markings"):
                self.assertLessEqual(osm_roads.record_segments(pieces, graph, index, 3), osm_roads.RECORD_SEGMENTS)
        self.assert_connected(self.layer(result))

    def test_paint_segments_count_like_mapkit(self):
        # Two free ends: one segment. A straight two-arm join adds MapKit's one
        # join point, plus one for adopted-vertex rounding (an upper bound).
        self.assertEqual(osm_roads.paint_segments([(0, 0), (100, 0)], [8], 3), 1)
        self.assertEqual(osm_roads.paint_segments([(0, 0), (100, 0)], [8], 3, after=((200, 0), 8)), 2)
        # A right-angle interior vertex: the full fillet (10-degree chords).
        arc = osm_roads.paint_segments([(0, 0), (100, 0), (100, 100)], [8, 8], 3)
        self.assertGreaterEqual(arc, 1 + 9)
        self.assertLessEqual(arc, 1 + 13)
        # Half of a right-angle join arc at a two-arm end.
        joined = osm_roads.paint_segments([(0, 0), (100, 0)], [8], 3, after=((100, 100), 8))
        self.assertLess(joined, arc)
        self.assertGreater(joined, 2)

    def test_service_aisles_driveways_stubs_and_tracks_become_paint(self):
        for x0, x1, r0, r1 in ((0, 50, 1, 3), (50, 100, 3, 5), (100, 150, 5, 7), (150, 200, 7, 2)):
            self.road([(x0, 0), (x1, 0)], [r0, r1], highway="residential")
        aisle = self.road([(50, 0), (50, 40)], [3, 4], highway="service", service="parking_aisle")
        stub = self.road([(100, 0), (100, 10)], [5, 6], highway="service")
        long_service = self.road([(150, 0), (150, 40)], [7, 8], highway="service")
        track = self.road([(0, 0), (0, -60)], [1, 9], highway="track")
        self.road([(0, 0), (-60, 0)], [1, 10], highway="residential")
        worker, result, meta, roads = self.run_city()
        painted = {f["properties"]["osm_source_id"]: f["properties"].get("_city_ground_paint") for f, g in worker.features if g.geom_type == "LineString"}
        self.assertEqual(painted[aisle], "service")
        self.assertEqual(painted[track], "track")
        self.assertEqual(painted[long_service], None)
        road_sources = {s for p, g in roads for s in p["_city_sources"]}
        self.assertNotIn(aisle, road_sources)
        paint = [f for f in result["features"] if "_city_paint" in f["properties"]]
        surfaces = {s: f["properties"]["_city_paint"] for f in paint for s in f["properties"]["_city_sources"]}
        self.assertEqual(surfaces[aisle], "asphalt")
        self.assertEqual(surfaces[track], "dirt")
        self.assertIn(stub, surfaces, "a dead-end service stub under 15 m is painted")
        self.assertIn(aisle, meta["source_ids"])


if __name__ == "__main__":
    unittest.main()
