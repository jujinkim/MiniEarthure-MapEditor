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
        self.assertEqual(layer.coordinates["osm_connections"]["profile"],"explicit-structural-junctions-v2")
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
                self.assertEqual(meta["policy"],"geometry-intersection-v4")
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
            with patch.object(stream,"MAX_FEATURES",2),self.assertRaisesRegex(ValueError,"budget"):
                stream.extract(source,EAST,directory)
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
        with patch.object(osm,"MAX_REFS",2),self.assertRaisesRegex(ValueError,"source incidence budget"):
            osm.structure_connections(value["features"],uses)
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
