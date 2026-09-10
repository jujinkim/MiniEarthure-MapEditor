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
from osm_loops_fixture import xml
from osm_fixture import pbf
from osm_area import crop
import osm_stream as stream
from vertical import Vertical

BOX = [9,55,9+100/64000,55+100/111000]


class Loops(unittest.TestCase):
    def layer(self, value, counts):
        return osm.finish(convert(value,"synthetic",osm.LICENSE,coordinates=OPTIONS,osm_graph=True,layer_id="a"*32),counts)

    def test_segments_shared_nodes_direction_and_estimates(self):
        value,counts = osm.parse(xml().encode(),"osm")
        self.assertEqual(counts["closed_ground_ways"],1)
        self.assertEqual(counts["explicit_height_roads"],0)
        layer = self.layer(value,counts)
        meta = layer.coordinates["osm_ground_loops"]
        self.assertEqual([s["way"] for s in meta["sources"]],["1","2","3"])
        self.assertEqual([f["properties"]["osm_node_refs"] for f in value["features"][:4]],[[1,2],[2,3],[3,4],[4,1]])
        self.assertEqual([e["source_range"] for e in meta["retained"]],[[0,1],[1,2],[2,3],[3,4],[0,1],[1,2],[0,2]])
        roads = [p["after"] for p in layer.patches if p["field"] == "roads"]
        self.assertEqual(roads[0]["from"],roads[3]["to"])
        self.assertEqual(roads[0]["from"],roads[4]["to"])
        self.assertEqual(roads[0]["from"],roads[5]["from"])
        self.assertNotEqual(roads[0]["to"],roads[-1]["from"])
        self.assertEqual(roads[0]["points"][-1],roads[-1]["points"][0])
        self.assertEqual(layer.estimates["elevation_m"],8)
        self.assertTrue(all(p[1] == 20 for r in roads for p in r["points"]))
        self.assertIn("No routing/access/oneway", " ".join(layer.warnings))

    def test_xml_pbf_order_reversal_and_isolated_loop(self):
        raw = xml().encode();expected = osm.parse(raw,"osm")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(osm.parse(pbf(Path(d)/"fixture.pbf",raw.decode()),"pbf"),expected)
        root = ET.fromstring(raw);root[:] = root[::-1]
        self.assertEqual(osm.parse(ET.tostring(root),"osm"),expected)
        for way in root.findall("way"):
            refs=way.findall("nd")
            for ref in refs: way.remove(ref)
            for ref in refs[::-1]: way.append(ref)
        value,_ = osm.parse(ET.tostring(root),"osm")
        self.assertEqual([f["properties"]["osm_node_refs"] for f in value["features"][:4]],[[1,4],[4,3],[3,2],[2,1]])
        for way in root.findall("way"):
            if way.get("id") != "1": root.remove(way)
        self.assertEqual(len(osm.parse(ET.tostring(root),"osm")[0]["features"]),4)

    def test_crop_original_junction_and_independent_cut_identity(self):
        value,counts = osm.parse(xml().encode(),"osm");original=copy.deepcopy(value)
        selected,meta = crop(value,BOX)
        self.assertEqual(meta["policy"],"geometry-intersection-v1")
        layer=self.layer(selected,counts)
        entries=layer.coordinates["osm_ground_loops"]["retained"]
        self.assertEqual(len(entries),4)
        self.assertEqual(entries[0]["refs"][0],"1")
        self.assertTrue(entries[0]["refs"][-1].startswith("crop-"))
        self.assertEqual(entries[1]["refs"][-1],"1")
        self.assertGreater(entries[1]["source_range"][0],3)
        self.assertEqual(entries[2]["refs"][-1],entries[3]["refs"][0])
        self.assertEqual(value,original)
        # Whole-ring crop keeps exact traversal, without shapely canonicalization.
        self.assertEqual(crop(value,[9,55,9.005,55.005])[0],value)

    def test_height_conversion_before_crop_and_no_estimated_conversion(self):
        value,counts=osm.parse(xml("height").encode(),"osm")
        vertical=Vertical(dict(target="EGM96",zero_m=2,grid=None));value=vertical.apply(value)
        selected,meta=crop(value,BOX)
        self.assertEqual(meta["policy"],"geometry-intersection-v2")
        layer=self.layer(selected,counts)
        self.assertTrue(all(e["explicit_height"] for e in layer.coordinates["osm_ground_loops"]["retained"]))
        self.assertTrue(all(p[1]==100 for r in layer.patches if r["field"]=="roads" for p in r["after"]["points"]))
        plain,_=osm.parse(xml().encode(),"osm")
        with self.assertRaisesRegex(ValueError,"requires explicit"): vertical.apply(plain)

    def test_streaming_collects_outside_approaches_before_crop(self):
        complete,_=osm.parse(xml().encode(),"osm")
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"original.pbf";raw=pbf(source,xml())
            value,counts,meta=stream.extract(source,BOX,d)
            self.assertEqual(meta["structure_closure"],dict(profile="loop-structural-incidence-v1",ways=3,structures=0,loops=1,nodes=4,visits=6))
            self.assertEqual(crop(value,BOX)[0],crop(complete,BOX)[0])
            self.assertEqual(source.read_bytes(),raw)
            self.assertTrue(all(not (Path(d)/n).exists() for n in stream.OWNED_FILES))
            root=ET.fromstring(xml())
            ET.SubElement(root.find("way[@id='3']"),"tag",k="incline",v="1%")
            bad=Path(d)/"bad.pbf";pbf(bad,ET.tostring(root,encoding="unicode"))
            with self.assertRaisesRegex(ValueError,"vertical semantics"): stream.extract(bad,BOX,d)

    def test_streaming_cancel_caps_and_retry(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"original.pbf";raw=pbf(source,xml())
            def stop(stage,current,total,*unit):
                if stage=="index_relations" and current==total: raise InterruptedError("loop cancelled")
            with self.assertRaises(InterruptedError): stream.extract(source,BOX,d,stop)
            with patch.object(stream,"MAX_FEATURES",1),self.assertRaisesRegex(ValueError,"budget"): stream.extract(source,BOX,d)
            self.assertTrue(all(not (Path(d)/n).exists() for n in stream.OWNED_FILES))
            self.assertEqual(stream.extract(source,BOX,d)[1]["closed_ground_ways"],1)
            self.assertEqual(source.read_bytes(),raw)

    def test_malformed_loops_and_incident_semantics_reject_whole_input(self):
        changes={
            "short":lambda r:r.find("way").remove(r.find("way/nd[@ref='3']")),
            "repeat":lambda r:r.find("way/nd[@ref='3']").set("ref","2"),
            "cross":lambda r:r.find("way/nd[@ref='2']").set("ref","3"),
            "area":lambda r:ET.SubElement(r.find("way"),"tag",k="area",v="yes"),
            "missing":lambda r:r.remove(r.find("node[@id='2']")),
            "structural":lambda r:ET.SubElement(r.find("way"),"tag",k="bridge",v="yes"),
            "approach":lambda r:ET.SubElement(r.find("way[@id='3']"),"tag",k="bridge",v="yes"),
        }
        for name,action in changes.items():
            root=ET.fromstring(xml("height"));action(root)
            if name=="short": root.find("way").remove(root.find("way/nd[@ref='4']"))
            with self.subTest(name=name),self.assertRaises(ValueError):osm.parse(ET.tostring(root),"osm")
        root=ET.fromstring(xml());root.find("way/nd[@ref='2']").set("ref","4");root.find("way/nd[@ref='4']").set("ref","2")
        # Explicit order 1,3,2,4,1 crosses the ring.
        refs=root.find("way").findall("nd")
        for n,ref in zip(refs,[1,3,2,4,1]):n.set("ref",str(ref))
        with self.assertRaisesRegex(ValueError,"self-intersects"):osm.parse(ET.tostring(root),"osm")

    def test_source_topology_split_output_and_native_arm_budgets(self):
        import polygon_geometry as geometry
        import import_layer
        with patch.object(geometry,"MAX_TOPOLOGY_CHECKS",1),self.assertRaisesRegex(ValueError,"topology budget"):osm.parse(xml().encode(),"osm")
        with patch.object(osm,"MAX_FEATURES",5),self.assertRaisesRegex(ValueError,"split feature budget"):osm.parse(xml().encode(),"osm")
        value,counts=osm.parse(xml().encode(),"osm")
        with patch.object(import_layer,"MAX_RECORDS",3),self.assertRaisesRegex(ValueError,"record budget"):self.layer(value,counts)
        root=ET.fromstring(xml());way=root.find("way[@id='2']")
        for i in range(30):
            peer=copy.deepcopy(way);peer.set("id",str(100+i));root.append(peer)
        with self.assertRaisesRegex(ValueError,"32 native arms"):osm.parse(ET.tostring(root),"osm")

    def test_cli_metadata_source_hash_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"original.osm";source.write_text(xml());out=Path(d)/"result.json"
            cmd=[sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(out),"--input-format","osm","--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",osm.LICENSE,"--layer-id","b"*32]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            raw=out.read_bytes();meta=json.loads(raw)
            self.assertEqual(meta["coordinates"]["vertical"]["explicit_points"],0)
            self.assertEqual(meta["source"]["sha256"],hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotEqual(subprocess.run(cmd,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(out.read_bytes(),raw)
            self.assertEqual(source.read_text(),xml())


if __name__ == "__main__":unittest.main()
