import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_osm_importer import osm, convert, OPTIONS
from osm_fixture import structural_junctions_xml, pbf
from osm_area import crop
import osm_stream as stream
from vertical import Vertical

# Exact first source junction; retain the west arm, or the two eastern arms.
WEST = [9, 55, 9.0015, 55.0015]
EAST = [9.0015, 55, 9.0025, 55.0015]


class Junctions(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def parse(self, interior=True):
        return osm.parse(structural_junctions_xml(interior).encode(), "osm")

    def test_explicit_branch_interior_mixed_and_direct_transition(self):
        value, counts = self.parse()
        self.assertEqual(counts["structure_continuations"],4)
        joins = value["osm_connections"]
        self.assertEqual([j["kind"] for j in joins],["bridge","tunnel","mixed","mixed"])
        self.assertEqual([len(j["source_arms"]) for j in joins],[3,3,3,2])
        self.assertEqual(joins[0]["source_ways"],["1","5"])
        self.assertEqual([(a["source_way"],a["end"]) for a in joins[0]["source_arms"]],[("1","from"),("1","to"),("5","from")])
        layer = convert(value,"synthetic",osm.LICENSE,coordinates=OPTIONS,osm_graph=True)
        self.assertEqual(layer.coordinates["osm_connections"]["profile"],"explicit-structural-junctions-v1")
        roads = {p["id"]:p["after"] for p in layer.patches if p["field"] == "roads"}
        for join in layer.coordinates["osm_connections"]["joins"]:
            for arm in join["retained"]:
                road = roads[f"import-{layer.layer_id}-{arm['feature']}"]
                self.assertEqual(road[arm["end"]],f"import-{layer.layer_id}-osm-node-{join['ref']}")
                source = next(a for a in join["source_arms"] if (a["source_way"],a["end"]) == (arm["source_way"],arm["end"]))
                self.assertEqual((road["kind"],road["clearance_cm"]),(source["kind"],source["clearance_cm"]))

    def test_xml_pbf_parity_source_order_and_reversal(self):
        raw = structural_junctions_xml().encode()
        expected = osm.parse(raw,"osm")
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(osm.parse(pbf(Path(directory)/"original.pbf",raw.decode()),"pbf"),expected)
        root = ET.fromstring(raw)
        root[:] = list(reversed(root[:]))
        self.assertEqual(osm.parse(ET.tostring(root),"osm"),expected)
        for way in root.findall("way"):
            refs = way.findall("nd")
            for ref in refs: way.remove(ref)
            for ref in reversed(refs): way.append(ref)
        reversed_joins = osm.parse(ET.tostring(root),"osm")[0]["osm_connections"]
        for before,after in zip(expected[0]["osm_connections"],reversed_joins):
            self.assertEqual(before["ref"],after["ref"])
            self.assertEqual(before["source_ways"],after["source_ways"])
            self.assertEqual([a["end"] for a in after["source_arms"]],["to"]*len(after["source_arms"]))

    def test_partial_junction_records_one_or_two_remaining_arms(self):
        value,_ = self.parse(); original = copy.deepcopy(value)
        for box,remaining in [(WEST,1),(EAST,2)]:
            with self.subTest(remaining=remaining):
                output,meta = crop(value,box)
                self.assertEqual(meta["policy"],"geometry-intersection-v1")
                self.assertIn("1",meta["vertical"]["connection_sections"])
                layer = convert(output,"source",osm.LICENSE,coordinates=OPTIONS,osm_graph=True)
                join = layer.coordinates["osm_connections"]["joins"][0]
                self.assertEqual(len(join["source_arms"]),3)
                self.assertEqual(len(join["retained"]),remaining)
                self.assertEqual(len({a["source_way"] for a in join["retained"]}),remaining)
                ends = [e for s in meta["vertical"]["structures"] for e in s["endpoints"] if e["ref"] == "1"]
                self.assertEqual(len(ends),remaining)
                self.assertTrue(all(e["role"] == "boundary-section" for e in ends))
        self.assertEqual(value,original)

    def test_streaming_closure_includes_all_branches_and_original_height_conversion(self):
        value,_ = self.parse()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf";raw = pbf(source,structural_junctions_xml(True))
            selected,counts,meta = stream.extract(source,EAST,directory)
            self.assertEqual(meta["structure_closure"]["structures"],2)
            self.assertEqual(meta["structure_closure"]["ways"],5)
            output,_ = crop(selected,EAST)
            expected,_ = crop(value,EAST)
            self.assertEqual(output["features"],expected["features"])
            self.assertEqual(counts["structure_continuations"],1)
            self.assertEqual(source.read_bytes(),raw)
            self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
        transformed = Vertical(dict(target="EGM96",zero_m=2,grid=None)).apply(value)
        self.assertEqual(transformed["osm_connections"],value["osm_connections"])
        transformed,_ = crop(transformed,EAST)
        for feature in transformed["features"]:
            if feature["properties"].get("road_kind") == "bridge":
                self.assertIn(4,feature["properties"]["elevations_m"])

    def test_unsupported_outside_branch_missing_profile_and_clearance_reject(self):
        changes = {
            "outside": lambda r: ET.SubElement(r.find("way[@id='1']"),"tag",k="incline",v="1%"),
            "missing": lambda r: r.find("node[@id='2']").remove(r.find("node[@id='2']/tag")),
            "clearance": lambda r: r.find("way[@id='202']/tag[@k='maxheight:physical']").set("v","4.51"),
        }
        for name,change in changes.items():
            root = ET.fromstring(structural_junctions_xml());change(root)
            with self.subTest(name=name),self.assertRaises(ValueError): osm.parse(ET.tostring(root),"osm")
            if name == "outside":
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory)/"original.pbf";raw = pbf(source,ET.tostring(root,encoding="unicode"))
                    with self.assertRaisesRegex(ValueError,"vertical semantics"): stream.extract(source,EAST,directory)
                    self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),hashlib.sha256(raw).digest())
        root = ET.fromstring(structural_junctions_xml())
        root.find("way[@id='202']/tag[@k='maxheight:physical']").set("v","4.504")
        joins = osm.parse(ET.tostring(root),"osm")[0]["osm_connections"]
        self.assertTrue(all(a["clearance_cm"] == 450 for a in joins[2]["source_arms"] if a["kind"] == "tunnel"))

    def test_arm_cap_counts_interior_twice_and_precedes_crop(self):
        value,_ = self.parse()
        # Exercise original graph admission directly, with source refs distinct
        # except the explicit central ID; native geometry is tested separately.
        roads = []
        for i in range(17):
            roads.append(dict(properties=dict(road_kind="bridge",osm_way_id=i+1,osm_node_refs=[100+i,1,200+i])))
        from collections import Counter
        uses = Counter(ref for f in roads for ref in f["properties"]["osm_node_refs"])
        with self.assertRaisesRegex(ValueError,"32 native arms"): osm.structure_connections(roads,uses)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf";pbf(source,structural_junctions_xml(True))
            import import_layer
            with patch.object(stream,"MAX_FEATURES",2):
                self.assertEqual(stream.extract(source,EAST,directory)[1]["structure_continuations"],1)
            self.assertIn("stream_closure_features",{e["code"] for e in import_layer.limit_entries()})
            self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
            self.assertEqual(stream.extract(source,EAST,directory)[1]["structure_continuations"],1)

    def test_distinct_ground_anchors_and_identity_not_positions(self):
        root = ET.fromstring(structural_junctions_xml())
        # Each branch leaf must still connect, even though two other anchors exist.
        root.remove(root.find("way[@id='2']"))
        with self.assertRaisesRegex(ValueError,"missing approaches"): osm.parse(ET.tostring(root),"osm")
        root = ET.fromstring(structural_junctions_xml())
        node = copy.deepcopy(root.find("node[@id='1']"));node.set("id","999");root.insert(0,node)
        root.find("way[@id='1']/nd").set("ref","999")
        with self.assertRaisesRegex(ValueError,"missing approaches"): osm.parse(ET.tostring(root),"osm")

    def test_anchored_cycle_needs_two_distinct_ground_nodes(self):
        from collections import Counter
        roads = [dict(properties=dict(road_kind="bridge",osm_way_id=i+1,osm_node_refs=refs))
                 for i,refs in enumerate([[1,2],[2,3],[3,1]])]
        roads.append(dict(properties=dict(road_kind="ground",osm_node_refs=[1,10],elevations_m=[0,0])))
        uses = Counter(ref for f in roads for ref in f["properties"]["osm_node_refs"])
        with self.assertRaisesRegex(ValueError,"two distinct"): osm.structure_connections(roads,uses)
        roads.append(dict(properties=dict(road_kind="ground",osm_node_refs=[2,11],elevations_m=[0,0])))
        uses.update([2,11])
        self.assertEqual(len(osm.structure_connections(roads,uses)),1)

    def test_source_incidence_bound_and_closure_cancellation_retry(self):
        from collections import Counter
        value,_ = self.parse(False)
        uses = Counter(ref for f in value["features"] for ref in f["properties"]["osm_node_refs"])
        import import_layer
        expected = osm.structure_connections(value["features"],uses)
        with patch.object(osm,"MAX_REFS",2):
            self.assertEqual(osm.structure_connections(value["features"],uses),expected)
        self.assertIn("osm_structure_arms",{e["code"] for e in import_layer.limit_entries()})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf";raw = pbf(source,structural_junctions_xml(True))
            events = 0
            def cancel(stage,current,total,*unit):
                nonlocal events
                if stage == "index_relations" and current == total:
                    events += 1
                    if events == 3: raise InterruptedError("junction closure cancelled")
            with self.assertRaisesRegex(InterruptedError,"junction closure cancelled"):
                stream.extract(source,EAST,directory,cancel)
            self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
            self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(stream.extract(source,EAST,directory)[1]["structure_continuations"],1)


if __name__ == "__main__": unittest.main()

class PedestrianWays(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def test_footways_keep_independent_ends_and_never_split_vehicle_junctions(self):
        xml = """<osm version="0.6">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.001" lat="55"/><node id="3" lon="9.002" lat="55"/>
<node id="4" lon="9.001" lat="55.001"/><node id="6" lon="9.001" lat="54.999"/><node id="7" lon="9.0005" lat="55.0005"/>
<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/></way>
<way id="2"><nd ref="2"/><nd ref="4"/><tag k="highway" v="residential"/></way>
<way id="3"><nd ref="6"/><nd ref="2"/><nd ref="7"/><tag k="highway" v="footway"/></way>
</osm>"""
        value, _ = osm.parse(xml.encode(), "osm")
        footways = [f for f in value["features"] if f["properties"].get("_city_road_tags", {}).get("highway") == "footway"]
        self.assertEqual(len(footways), 1, "a footway is not split at a shared node")
        residential = [f for f in value["features"] if f["properties"].get("_city_road_tags", {}).get("highway") == "residential"]
        self.assertEqual(len(residential), 3, "vehicle roads split at their shared node")
        layer = convert(value, "synthetic", osm.LICENSE, coordinates=OPTIONS, osm_graph=True)
        roads = {p["id"]: p["after"] for p in layer.patches if p["field"] == "roads"}
        walking = layer.coordinates["osm_pedestrian_roads"]
        self.assertEqual(len(walking), 1)
        self.assertNotIn("osm-ground-node", roads[walking[0]]["from"] + roads[walking[0]]["to"])
        shared = [r for r in roads.values() if any(n.endswith("-osm-ground-node-2") for n in (r["from"], r["to"]))]
        self.assertEqual(len(shared), 3, "vehicle roads meet at one source junction")


class LevelStructures(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def osm(self, crossing):
        cross = """<node id="7" lon="9.0015" lat="54.999"/><node id="8" lon="9.0015" lat="55.001"/>
<way id="4"><nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/></way>""" if crossing else ""
        return f"""<osm version="0.6">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.001" lat="55"/><node id="3" lon="9.002" lat="55"/><node id="4" lon="9.003" lat="55"/>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
<way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="bridge" v="yes"/><tag k="layer" v="1"/></way>
<way id="3"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/></way>{cross}
</osm>""".encode()

    def test_city_draws_a_bridge_crossing_no_road_at_ground_level(self):
        with self.assertRaisesRegex(ValueError, "explicit vertical geometry"):
            osm.parse(self.osm(False), "osm")
        value, _ = osm.parse(self.osm(False), "osm", city=True)
        bridge = next(f for f in value["features"] if f["properties"]["osm_source_id"] == "way/2")
        self.assertTrue(bridge["properties"]["_city_level_structure"])
        self.assertNotIn("road_kind", bridge["properties"])
        self.assertEqual([f["properties"].get("_city_level_structure", False) for f in value["features"] if f["properties"]["osm_source_id"] != "way/2"], [False, False])

    def test_city_estimates_rather_than_levels_a_bridge_over_a_road(self):
        value, _ = osm.parse(self.osm(True), "osm", city=True)
        bridge = next(f for f in value["features"] if f["properties"]["osm_source_id"] == "way/2")
        self.assertNotIn("_city_level_structure", bridge["properties"])
        self.assertEqual(bridge["properties"]["_city_estimated_kind"], "bridge")

class EstimatedStructures(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def osm(self, approach=0.002):
        # West ground approach, a layer-1 bridge over a north-south road, east approach.
        x = [0, approach, approach+0.002, 2*approach+0.002]
        return f"""<osm version="0.6">
<node id="1" lon="{9+x[0]}" lat="55"/><node id="2" lon="{9+x[1]}" lat="55"/><node id="3" lon="{9+x[2]}" lat="55"/><node id="4" lon="{9+x[3]}" lat="55"/>
<node id="5" lon="{9+x[0]}" lat="55.001"/><node id="6" lon="{9+x[3]}" lat="55.001"/>
<node id="7" lon="{9+approach+0.001}" lat="54.999"/><node id="8" lon="{9+approach+0.001}" lat="55.001"/>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
<way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="bridge" v="yes"/><tag k="layer" v="1"/></way>
<way id="3"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/></way>
<way id="4"><nd ref="5"/><nd ref="1"/><tag k="highway" v="residential"/></way>
<way id="5"><nd ref="4"/><nd ref="6"/><tag k="highway" v="residential"/></way>
<way id="6"><nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/></way>
<node id="9" lon="{9+x[0]}" lat="54.999"/><node id="10" lon="{9+x[3]}" lat="54.999"/>
<way id="7"><nd ref="1"/><nd ref="9"/><tag k="highway" v="residential"/></way>
<way id="8"><nd ref="4"/><nd ref="10"/><tag k="highway" v="residential"/></way>
</osm>""".encode()

    def test_overpass_gets_a_six_metre_deck_and_ramps_on_its_approaches(self):
        value, _ = osm.parse(self.osm(), "osm", city=True)
        by_way = {f["properties"]["osm_source_id"]: f["properties"] for f in value["features"]}
        for way in ("way/1", "way/2", "way/3"):
            self.assertEqual(by_way[way]["_city_estimated_kind"], "bridge")
        self.assertNotIn("_city_estimated_m", by_way["way/6"])
        self.assertEqual(by_way["way/2"]["_city_estimated_m"], [6.0, 6.0])
        self.assertEqual(by_way["way/1"]["_city_estimated_m"][0], 0.0, "the junction anchor stays on the ground")
        layer = convert(value, "synthetic", osm.LICENSE, coordinates=OPTIONS, osm_graph=True, city=True)
        roads = {p["id"]: p["after"] for p in layer.patches if p["field"] == "roads"}
        estimated = layer.coordinates["osm_estimated_structures"]
        self.assertEqual(sorted(roads[r]["kind"] for r in estimated), ["bridge"]*3)
        deck = max(p[1] for r in estimated for p in roads[r]["points"])
        self.assertEqual(deck, 600)
        nodes = {p["id"] for p in layer.patches if p["field"] == "nodes"}
        anchors = [roads[r]["from"] for r in estimated] + [roads[r]["to"] for r in estimated]
        self.assertTrue(all("-osm-ground-node-" in n and n in nodes for n in anchors), "structures share ordinary ground nodes")

    def test_short_approaches_keep_requiring_source_heights(self):
        with self.assertRaisesRegex(ValueError, "way/2: OSM explicit vertical geometry requires ele"):
            osm.parse(self.osm(0.0001), "osm", city=True)

    def test_a_chain_crossing_only_excluded_structures_is_leveled(self):
        value = self.osm()
        root = ET.fromstring(value)
        crossed = root.find("way[@id='6']")
        ET.SubElement(crossed, "tag", k="tunnel", v="yes")
        ET.SubElement(root.find("node[@id='7']"), "tag", k="ele", v="10")  # Partial heights: excluded.
        ways, nodes, node_tags = [], {}, {}
        for node in root.iter("node"):
            nodes[int(node.get("id"))] = [float(node.get("lon")), float(node.get("lat"))]
            node_tags[int(node.get("id"))] = {t.get("k"): t.get("v") for t in node.iter("tag")}
        for way in root.iter("way"):
            ways.append((int(way.get("id")), "road", [int(n.get("ref")) for n in way.iter("nd")], {t.get("k"): t.get("v") for t in way.iter("tag")}))
        estimated, leveled = osm.estimate_structures(ways, nodes, node_tags, set())
        self.assertEqual((estimated, leveled), ({}, {2}))

    def test_a_chain_that_cannot_be_estimated_over_paint_only_is_leveled(self):
        # Approaches too short for a deck, crossing only a footway (ground
        # paint): the bridge lies on the ground instead of being excluded.
        root = ET.fromstring(self.osm(0.0001))
        root.find("way[@id='6']/tag[@k='highway']").set("v", "footway")
        value, _ = osm.parse(ET.tostring(root), "osm", city=True)
        bridge = next(f for f in value["features"] if f["properties"]["osm_source_id"] == "way/2")["properties"]
        self.assertTrue(bridge["_city_level_structure"])
        self.assertNotIn("_city_estimated_m", bridge)
        for change in ("closed", "touches a closed way", "ele", "structure"):
            with self.subTest(change=change):
                root = ET.fromstring(self.osm(0.0001))
                crossed = root.find("way[@id='6']")
                crossed.find("tag[@k='highway']").set("v", "footway")
                if change == "ele":
                    ET.SubElement(root.find("node[@id='7']"), "tag", k="ele", v="10")
                    ET.SubElement(root.find("node[@id='8']"), "tag", k="ele", v="10")
                elif change == "structure":
                    ET.SubElement(crossed, "tag", k="bridge", v="yes"); ET.SubElement(crossed, "tag", k="layer", v="1")
                elif change == "closed":
                    ET.SubElement(root, "node", id="20", lon="9.0003", lat="54.999")
                    crossed.insert(2, ET.Element("nd", ref="20")); crossed.insert(3, ET.Element("nd", ref="7"))  # Nodes before tags.
                else:
                    ET.SubElement(root, "node", id="21", lon="9.0012", lat="55.0012"); ET.SubElement(root, "node", id="22", lon="9.0010", lat="55.0012")
                    loop = ET.SubElement(root, "way", id="30")
                    for ref in ("8", "21", "22", "8"): ET.SubElement(loop, "nd", ref=ref)
                    ET.SubElement(loop, "tag", k="highway", v="footway")
                with self.assertRaisesRegex(ValueError, "way/2: OSM explicit vertical geometry requires ele"):
                    osm.parse(ET.tostring(root), "osm", city=True)

    def test_a_ramp_of_an_estimated_chain_is_not_paint(self):
        # Chain 5 (footway 4 absorbed as its west ramp) is estimated over road 7.
        # Short bridge 2 crosses only that raised footway ramp: it stays excluded.
        nodes = {1: [9.0, 55], 2: [9.0015, 55], 3: [9.003, 55], 4: [9.006, 55], 7: [9.0017, 54.999], 8: [9.0017, 55.001],
                 10: [9.0005, 54.9999], 11: [9.0005, 55.0001]}
        ways = [(4, "road", [1, 2], {"highway": "footway"}),
                (5, "road", [2, 3], {"highway": "residential", "bridge": "yes", "layer": "1"}),
                (6, "road", [3, 4], {"highway": "residential"}),
                (7, "road", [7, 8], {"highway": "residential"}),
                (2, "road", [10, 11], {"highway": "footway", "bridge": "yes", "layer": "1"})]
        estimated, leveled = osm.estimate_structures(ways, nodes, {}, set())
        self.assertEqual(set(estimated), {4, 5, 6})
        self.assertNotIn(2, leveled)

    def test_estimated_ways_carry_their_chain(self):
        value, _ = osm.parse(self.osm(), "osm", city=True)
        chains = {f["properties"]["osm_source_id"]: f["properties"].get("_city_estimated_chain") for f in value["features"] if "_city_estimated_m" in f["properties"]}
        self.assertEqual(set(chains), {"way/1", "way/2", "way/3"})
        self.assertEqual(set(chains.values()), {1}, "keyed by the first way of the extended chain")

    def test_an_excluded_continuation_cuts_the_chain_instead_of_leaving_a_raised_end(self):
        # A long bridge passes separation over way 6, but the way continuing it
        # east is excluded anyway (level tag): the bridge is cut, not ramped
        # over a dropped way or left ending in the air.
        root = ET.fromstring(self.long_bridge(east_tags={"level": "1"}))
        with self.assertRaisesRegex(ValueError, "way/2: OSM city structure ends where an excluded way continued it"):
            osm.parse(ET.tostring(root), "osm", city=True)
        value, _ = osm.parse(self.long_bridge(), "osm", city=True)
        by_way = {f["properties"]["osm_source_id"]: f["properties"] for f in value["features"]}
        self.assertEqual(by_way["way/2"]["_city_estimated_kind"], "bridge", "the same bridge is estimated when its continuation is kept")

    def test_a_cut_chain_crossing_only_excluded_structures_is_still_leveled(self):
        root = ET.fromstring(self.long_bridge(east_tags={"level": "1"}))
        ET.SubElement(root.find("way[@id='6']"), "tag", k="tunnel", v="yes")
        ET.SubElement(root.find("node[@id='7']"), "tag", k="ele", v="10")  # Partial heights: excluded.
        with self.assertRaisesRegex(ValueError, "way/3: OSM unsupported vertical semantics on road"):
            osm.parse(ET.tostring(root), "osm", city=True)
        ways, nodes, node_tags = self.selection(root)
        present = [w for w in ways if w[0] != 3]
        cut = set()
        self.assertEqual(osm.estimate_structures(present, nodes, node_tags, set(), {3, 4}, cut), ({}, {2}))
        self.assertEqual(cut, set())

    def test_a_ground_road_excluded_anyway_is_no_crossing(self):
        # maxheight:physical on a ground road is rejected, so the bridge crosses
        # nothing drawn and lies on the ground.
        root = ET.fromstring(self.long_bridge())
        ET.SubElement(root.find("way[@id='6']"), "tag", k="maxheight:physical", v="3.5")
        with self.assertRaisesRegex(ValueError, "way/6: OSM physical clearance requires an explicit supported tunnel"):
            osm.parse(ET.tostring(root), "osm", city=True)
        ways, nodes, node_tags = self.selection(root)
        self.assertEqual(osm.estimate_structures([w for w in ways if w[0] != 6], nodes, node_tags, set()), ({}, {2}))

    def long_bridge(self, east_tags={}):
        # Ground way 1, a 300 m layer-1 bridge (way 2) over way 6 at its middle,
        # ground way 3 east of it ending in a dead end.
        east = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in east_tags.items())
        return f"""<osm version="0.6">
<node id="1" lon="8.997" lat="55"/><node id="2" lon="9" lat="55"/><node id="3" lon="9.0047" lat="55"/><node id="4" lon="9.0077" lat="55"/>
<node id="5" lon="8.997" lat="55.001"/><node id="9" lon="8.997" lat="54.999"/>
<node id="7" lon="9.00235" lat="54.999"/><node id="8" lon="9.00235" lat="55.001"/>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
<way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="bridge" v="yes"/><tag k="layer" v="1"/></way>
<way id="3"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/>{east}</way>
<way id="4"><nd ref="5"/><nd ref="1"/><tag k="highway" v="residential"/></way>
<way id="7"><nd ref="1"/><nd ref="9"/><tag k="highway" v="residential"/></way>
<way id="6"><nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/></way>
</osm>""".encode()

    def selection(self, root):
        ways, nodes, node_tags = [], {}, {}
        for node in root.iter("node"):
            nodes[int(node.get("id"))] = [float(node.get("lon")), float(node.get("lat"))]
            node_tags[int(node.get("id"))] = {t.get("k"): t.get("v") for t in node.iter("tag")}
        for way in root.iter("way"):
            ways.append((int(way.get("id")), "road", [int(n.get("ref")) for n in way.iter("nd")], {t.get("k"): t.get("v") for t in way.iter("tag")}))
        return ways, nodes, node_tags


class CitySteps(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def osm(self, *steps_tags):
        tags = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in steps_tags)
        return f"""<osm version="0.6">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.001" lat="55"/><node id="3" lon="9.001" lat="55.0005"/><node id="4" lon="9.002" lat="55.0005"/>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
<way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="steps"/><tag k="incline" v="up"/>{tags}</way>
<way id="3"><nd ref="3"/><nd ref="4"/><tag k="highway" v="footway"/><tag k="incline" v="12%"/></way>
</osm>""".encode()

    def test_ground_steps_are_city_walking_ways_and_keep_their_class(self):
        with self.assertRaisesRegex(ValueError, "unsupported highway/area profile"):
            osm.parse(self.osm(), "osm")
        value, _ = osm.parse(self.osm(), "osm", city=True)
        by_way = {f["properties"]["osm_source_id"]: f["properties"] for f in value["features"]}
        self.assertEqual(by_way["way/2"]["_city_road_tags"]["highway"], "steps")
        self.assertEqual(by_way["way/3"]["_city_road_tags"]["highway"], "footway", "a ground walking way's incline is only its slope")
        self.assertNotIn("road_kind", by_way["way/2"])

    def test_structural_and_conveying_steps_stay_excluded(self):
        for tags in ((("bridge", "yes"), ("layer", "1")), (("layer", "-1"),), (("conveying", "yes"),)):
            with self.subTest(tags=tags), self.assertRaisesRegex(ValueError, "way/2: OSM city steps are ground paint"):
                osm.parse(self.osm(*tags), "osm", city=True)
        value, _ = osm.parse(self.osm(("conveying", "no")), "osm", city=True)
        self.assertIn("way/2", {f["properties"]["osm_source_id"] for f in value["features"]}, "conveying=no is ordinary stairs")

    def test_vehicle_road_incline_still_rejects(self):
        root = ET.fromstring(self.osm())
        ET.SubElement(root.find("way[@id='1']"), "tag", k="incline", v="5%")
        with self.assertRaisesRegex(ValueError, "way/1: OSM unsupported vertical semantics on road"):
            osm.parse(ET.tostring(root), "osm", city=True)


class CityLayersAndEntrances(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def osm(self, building_tags=(), entrance_tags=(("entrance", "yes"), ("level", "1")), building="yes"):
        kind, tags = building, "".join(f'<tag k="{k}" v="{v}"/>' for k, v in building_tags)
        entrance = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in entrance_tags)
        return f"""<osm version="0.6">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.0002" lat="55"/><node id="3" lon="9.0002" lat="55.0002"/><node id="4" lon="9" lat="55.0002"/>
<node id="5" lon="9.0001" lat="54.9995"/><node id="6" lon="9.0001" lat="54.9999">{entrance}</node>
<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="{kind}"/>{tags}</way>
<way id="2"><nd ref="5"/><nd ref="6"/><tag k="highway" v="footway"/></way>
</osm>""".encode()

    def features(self, raw):
        value, _ = osm.parse(raw, "osm", city=True)
        return {f["properties"]["osm_source_id"]: f["properties"] for f in value["features"]}

    def test_positive_layer_buildings_stand_on_the_city_ground(self):
        raw = self.osm((("layer", "1"),))
        with self.assertRaisesRegex(ValueError, "nonzero layer requires explicit vertical geometry"):
            osm.parse(raw, "osm")
        self.assertTrue(self.features(raw)["way/1"]["_city_layer_building"])
        self.assertNotIn("_city_layer_building", self.features(self.osm())["way/1"])
        for kind, tags in (("yes", (("layer", "-1"),)), ("roof", (("layer", "1"),)), ("yes", (("layer", "1"), ("barrier", "toll_booth"))), ("yes", (("layer", "1"), ("bridge", "yes")))):
            with self.subTest(kind=kind, tags=tags), self.assertRaisesRegex(ValueError, "way/1: OSM bridge/tunnel/nonzero layer requires explicit vertical geometry"):
                osm.parse(self.osm(tags, building=kind), "osm", city=True)

    def test_layered_building_relations_and_their_outlines_are_lifted(self):
        root = ET.fromstring(self.osm())
        outer = root.find("way[@id='1']")
        outer.remove(outer.find("tag[@k='building']"))
        relation = ET.SubElement(root, "relation", id="7")
        ET.SubElement(relation, "member", type="way", ref="1", role="outer")
        for k, v in (("type", "multipolygon"), ("building", "yes")): ET.SubElement(relation, "tag", k=k, v=v)
        for place in ("relation", "outline"):
            with self.subTest(place=place):
                variant = copy.deepcopy(root)
                ET.SubElement(variant.find("relation[@id='7']" if place == "relation" else "way[@id='1']"), "tag", k="layer", v="1")
                with self.assertRaisesRegex(ValueError, "nonzero layer requires explicit vertical geometry"):
                    osm.parse(ET.tostring(variant), "osm")
                self.assertTrue(self.features(ET.tostring(variant))["relation/7"]["_city_layer_building"])

    def test_an_entrance_level_is_not_road_height(self):
        with self.assertRaisesRegex(ValueError, "way/2: OSM unsupported road-node vertical semantics"):
            osm.parse(self.osm(), "osm")
        self.assertIn("way/2", self.features(self.osm()))
        with self.assertRaisesRegex(ValueError, "way/2: OSM unsupported road-node vertical semantics"):
            osm.parse(self.osm(entrance_tags=(("level", "1"),)), "osm", city=True)

