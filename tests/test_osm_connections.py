import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_osm_importer import osm, convert, OPTIONS
from osm_fixture import connected_structures_xml, pbf
from osm_area import crop
import osm_stream as stream
from vertical import Vertical

BOX = [9.001, 54.9999, 9.0012, 55.001]
JOIN_BOX = [9.00075, 54.9999, 9.0015, 55.001]


class Connections(unittest.TestCase):
    def parse(self, root=None):
        raw = connected_structures_xml().encode() if root is None else ET.tostring(root)
        return osm.parse(raw, "osm")

    def test_same_kind_endpoints_profiles_parity_reversal_and_source_identity(self):
        raw = connected_structures_xml().encode()
        value, counts = self.parse()
        self.assertEqual(counts["structure_continuations"], 4)
        self.assertEqual([j["ref"] for j in value["osm_connections"]], ["3", "4", "9", "10"])
        layer = convert(value, "synthetic", osm.LICENSE, source_bytes=raw, layer_id="c"*32, coordinates=OPTIONS, osm_graph=True)
        roads = [p["after"] for p in layer.patches if p["field"] == "roads"]
        for offset in [0, 5]:
            for i in range(offset, offset+4): self.assertEqual(roads[i]["to"], roads[i+1]["from"])
        self.assertEqual(layer.source.sha256, hashlib.sha256(raw).hexdigest())
        self.assertTrue(all(len(j["retained"]) == 2 for j in layer.coordinates["osm_connections"]["joins"]))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(osm.parse(pbf(Path(directory)/"original.pbf",raw.decode()), "pbf"), (value, counts))
        root = ET.fromstring(raw)
        for way in root.findall("way"):
            refs = way.findall("nd")
            for ref in refs: way.remove(ref)
            for ref in reversed(refs): way.append(ref)
        reversed_value, _ = self.parse(root)
        self.assertEqual(reversed_value["osm_connections"], value["osm_connections"])
        root = ET.fromstring(raw)
        duplicate = copy.deepcopy(root.find("node[@id='3']")); duplicate.set("id", "100"); root.insert(0, duplicate)
        root.find("way[@id='3']/nd").set("ref", "100")
        with self.assertRaisesRegex(ValueError, "ground connections"): self.parse(root)

    def test_missing_mixed_branch_interior_untagged_and_clearance_reject_before_crop(self):
        def branch(root, explicit=True, interior=False):
            way = ET.SubElement(root, "way", id="100")
            for ref in ([1,3,6] if interior else [3,6]): ET.SubElement(way,"nd",ref=str(ref))
            ET.SubElement(way,"tag",k="highway",v="service")
            if explicit: ET.SubElement(way,"tag",k="bridge",v="yes")
            else:
                # No elevations: this approach must not disappear from incidence.
                for node in root.findall("node"): node.remove(node.find("tag"))
        changes = {
            "missing": lambda r: r.remove(r.find("way[@id='1']")),
            "mixed": lambda r: (r.find("way[@id='3']/tag[@k='bridge']").set("k","tunnel"), ET.SubElement(r.find("way[@id='3']"),"tag",k="maxheight:physical",v="4.5")),
            "branch": lambda r: branch(r), "interior": lambda r: branch(r,interior=True),
            "clearance": lambda r: r.find("way[@id='8']/tag[@k='maxheight:physical']").set("v","4.51"),
            "height": lambda r: r.find("node[@id='2']").remove(r.find("node[@id='2']/tag")),
            "unsupported": lambda r: ET.SubElement(r.find("way[@id='2']"),"tag",k="incline",v="2%"),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                root = ET.fromstring(connected_structures_xml()); change(root)
                with self.assertRaises(ValueError): self.parse(root)
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory)/"original.pbf"; raw = pbf(source,ET.tostring(root,encoding="unicode"))
                    with self.assertRaises(ValueError): stream.extract(source,BOX,directory)
                    self.assertEqual(source.read_bytes(),raw)
                    self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
        # A highway sharing the new join but with no complete explicit profile
        # cannot be silently treated as a disconnected approach.
        root = ET.fromstring(connected_structures_xml())
        way = ET.SubElement(root,"way",id="100")
        for ref in [3,6]: ET.SubElement(way,"nd",ref=str(ref))
        ET.SubElement(way,"tag",k="highway",v="construction")
        with self.assertRaisesRegex(ValueError,"highway"): self.parse(root)

    def test_unanchored_cycles_reject(self):
        root = ET.fromstring(connected_structures_xml())
        for identity in [1,5]: root.remove(root.find(f"way[@id='{identity}']"))
        way = ET.SubElement(root,"way",id="100")
        for ref in [5,2]: ET.SubElement(way,"nd",ref=str(ref))
        for key, value in dict(highway="service",bridge="yes").items(): ET.SubElement(way,"tag",k=key,v=value)
        with self.assertRaisesRegex(ValueError,"cycles"): self.parse(root)

    def test_join_keeps_per_way_width_surface_and_quantized_clearance(self):
        root = ET.fromstring(connected_structures_xml())
        root.find("way[@id='3']/tag[@k='width']").set("v","6")
        ET.SubElement(root.find("way[@id='3']"),"tag",k="surface",v="gravel")
        root.find("way[@id='8']/tag[@k='maxheight:physical']").set("v","4.504")
        value,_ = self.parse(root)
        roads = [p["after"] for p in convert(value,"source",osm.LICENSE,coordinates=OPTIONS,osm_graph=True).patches if p["field"] == "roads"]
        self.assertEqual(roads[2]["widths_cm"],[600])
        self.assertEqual(roads[2]["surfaces"],["gravel"])
        self.assertTrue(all(roads[i]["clearance_cm"] == 450 for i in [6,7,8]))
        self.assertEqual(roads[1]["to"],roads[2]["from"])

    def test_dense_incidence_budget_precedes_normalization(self):
        root = ET.fromstring(connected_structures_xml())
        for identity in range(100,115):
            way = ET.SubElement(root,"way",id=str(identity))
            for ref in [3,6]: ET.SubElement(way,"nd",ref=str(ref))
            ET.SubElement(way,"tag",k="highway",v="service")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf"; raw = pbf(source,ET.tostring(root,encoding="unicode"))
            with patch.object(stream,"MAX_REFS",20), self.assertRaisesRegex(ValueError,"incidence budget"):
                stream.extract(source,BOX,directory)
            self.assertEqual(source.read_bytes(),raw)
            self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))

    def test_crop_across_original_way_join_has_open_section_not_missing_ramp(self):
        value,_ = self.parse(); original = copy.deepcopy(value)
        output, meta = crop(value, JOIN_BOX)
        self.assertEqual(value, original)
        self.assertEqual(meta["policy"],"geometry-intersection-v4")
        self.assertEqual(meta["vertical"]["partial_structure_ways"],0)
        self.assertEqual(meta["vertical"]["section_endpoints"],4)
        self.assertEqual(set(meta["vertical"]["connection_sections"]), {"3","4","9","10"})
        self.assertTrue(all(not e["partial"] for e in meta["vertical"]["structures"]))
        layer = convert(output,"source",osm.LICENSE,coordinates=OPTIONS,osm_graph=True)
        self.assertTrue(all(len(j["retained"]) == 1 for j in layer.coordinates["osm_connections"]["joins"]))
        # Keeping both original arms retains one graph join; synthetic cuts remain separate.
        output, meta = crop(value,[9.0006,54.9999,9.0012,55.001])
        self.assertEqual(meta["policy"],"geometry-intersection-v3")
        self.assertEqual(output["features"][0]["properties"]["osm_node_refs"][-1], 3)
        self.assertEqual(output["features"][1]["properties"]["osm_node_refs"][0], 3)

    def test_closure_transits_multiple_structures_includes_ground_but_stops_there(self):
        root = ET.fromstring(connected_structures_xml())
        # Beyond the collected ground approach: unsupported semantics not selected.
        way = ET.SubElement(root,"way",id="100")
        for ref in [1,7]: ET.SubElement(way,"nd",ref=str(ref))
        for key,value in dict(highway="service",incline="1%").items(): ET.SubElement(way,"tag",k=key,v=value)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf"; pbf(source,ET.tostring(root,encoding="unicode"))
            value,counts,meta = stream.extract(source,BOX,directory)
            self.assertEqual(meta["selected"]["ways"],10)
            self.assertEqual(meta["structure_closure"]["structures"],6)
            self.assertEqual(meta["structure_closure"]["ways"],10)
            self.assertEqual(crop(value,BOX),crop(self.parse()[0],BOX))
            self.assertEqual(counts["structure_continuations"],4)

    def test_off_window_incident_ground_semantics_cannot_hide_at_interior_vertex(self):
        root = ET.fromstring(connected_structures_xml())
        # Way 2's original interior node, outside BOX, has a malformed approach.
        root.find("way[@id='2']").insert(1,ET.Element("nd",ref="1"))
        ET.SubElement(root.find("way[@id='1']"),"tag",k="incline",v="1%")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf";pbf(source,ET.tostring(root,encoding="unicode"))
            with self.assertRaisesRegex(ValueError,"vertical semantics"): stream.extract(source,BOX,directory)

    def test_closure_limits_cancel_retry_and_no_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf"; raw = pbf(source,connected_structures_xml())
            for name,value in [("MAX_FEATURES",3),("MAX_REFS",5),("MAX_INPUT",20)]:
                with self.subTest(name=name),patch.object(stream,name,value),self.assertRaisesRegex(ValueError,"budget"):
                    stream.extract(source,BOX,directory)
                self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
            events = 0
            def cancel(stage,c,t,*unit):
                nonlocal events
                if stage == "index_relations" and c == t:
                    events += 1
                    if events == 5: raise InterruptedError("chain closure cancelled")
            with self.assertRaisesRegex(InterruptedError,"chain closure cancelled"): stream.extract(source,BOX,directory,cancel)
            self.assertEqual(source.read_bytes(),raw)
            self.assertTrue(all(not (Path(directory)/n).exists() for n in stream.OWNED_FILES))
            self.assertEqual(stream.extract(source,BOX,directory)[1]["structure_continuations"],4)

    def test_cli_vertical_crop_provenance_hash_and_exclusive_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"original.pbf";raw = pbf(source,connected_structures_xml())
            output = Path(directory)/"layer.json"
            command = [sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(output),
                "--input-format","pbf","--osm-stream","--osm-bbox",*map(str,JOIN_BOX),"--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",osm.LICENSE,"--layer-id","c"*32]
            result = subprocess.run(command,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            saved = output.read_bytes(); layer = json.loads(saved)
            self.assertEqual(layer["source"]["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual(layer["coordinates"]["osm_crop"]["policy"],"geometry-intersection-v4")
            self.assertEqual(layer["coordinates"]["vertical"]["explicit_roads"],10)
            self.assertIn("two explicit ground ends"," ".join(layer["warnings"]))
            self.assertTrue(all(len(w)<=512 for w in layer["warnings"]))
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=20).returncode,0)
            self.assertEqual(output.read_bytes(),saved);self.assertEqual(source.read_bytes(),raw)
        value,_ = self.parse()
        transformed = Vertical(dict(target="EGM96",zero_m=2,grid=None)).apply(value)
        self.assertEqual(transformed["osm_connections"],value["osm_connections"])
        output,_ = crop(transformed,JOIN_BOX)
        self.assertEqual([f["properties"]["elevations_m"] for f in output["features"]], [[4,4],[-8,-8]])


if __name__ == "__main__": unittest.main()
