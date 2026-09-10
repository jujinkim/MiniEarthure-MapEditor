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

from test_osm_importer import OPTIONS, osm, convert
from osm_area import crop
from osm_fixture import structural_xml, pbf
from osm_stream import extract

BOX = [9.0001, 54.9999, 9.0021, 55.001]


def road(coordinates, heights, refs=None):
    return dict(type="Feature", properties=dict(road_kind="ground", osm_way_id=1,
        osm_node_refs=refs or list(range(1,len(coordinates)+1)), elevations_m=heights),
        geometry=dict(type="LineString", coordinates=coordinates))


def run(features, box=None):
    return crop(dict(type="FeatureCollection", features=features), box or [0,0,.01,.01])


class GroundCrop(unittest.TestCase):
    def test_complete_structures_clipped_approaches_and_source_parity(self):
        raw=structural_xml().encode()
        value,_=osm.parse(raw,"osm")
        original=copy.deepcopy(value)
        clipped,meta=crop(value,BOX)
        self.assertEqual(value,original)
        self.assertEqual(meta["policy"],"geometry-intersection-v2")
        self.assertEqual(meta["vertical"],dict(profile="explicit-ground-crop-v1",
            clipped_ground_features=4,outside_explicit_features=0,retained_structure_features=2))
        for index in [1,4]: self.assertEqual(clipped["features"][index],value["features"][index])
        result=convert(clipped,"synthetic.osm",osm.LICENSE,source_bytes=raw,layer_id="c"*32,coordinates=OPTIONS,osm_graph=True)
        roads=[p["after"] for p in result.patches if p["field"]=="roads"]
        self.assertEqual(roads[0]["to"],roads[1]["from"])
        self.assertEqual(roads[1]["to"],roads[2]["from"])
        self.assertIn("crop-",roads[0]["from"])
        self.assertEqual(result.source.sha256,hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"original.pbf"; captured=pbf(source,raw.decode())
            snapshot=osm.parse(captured,"pbf")[0]
            streamed,_,_=extract(source,BOX,Path(directory),lambda *a:None)
            self.assertEqual(crop(snapshot,BOX),crop(streamed,BOX))
            self.assertEqual(source.read_bytes(),captured)

    def test_order_multiple_visits_heights_and_no_boundary_welding(self):
        f=road([[-.005,.002],[.015,.002],[.015,.008],[-.005,.008]],[-10,10,30,50])
        clipped,meta=run([f])
        parts=clipped["features"]
        self.assertEqual(len(parts),2)
        self.assertEqual(parts[0]["geometry"]["coordinates"],[[0,.002],[.01,.002]])
        self.assertEqual(parts[1]["geometry"]["coordinates"],[[.01,.008],[0,.008]])
        for actual,expected in zip(parts[0]["properties"]["elevations_m"],[-5,5]): self.assertAlmostEqual(actual,expected)
        for actual,expected in zip(parts[1]["properties"]["elevations_m"],[35,45]): self.assertAlmostEqual(actual,expected)
        twin=copy.deepcopy(f);twin["properties"]["osm_way_id"]=2
        two,_=run([f,twin])
        self.assertNotEqual(two["features"][0]["properties"]["osm_node_refs"][0],two["features"][2]["properties"]["osm_node_refs"][0])
        self.assertEqual(run([f]),(clipped,meta))

    def test_original_boundary_node_identity_bends_and_reversed_traversal(self):
        f=road([[-.005,.002],[0,.002],[.005,.005],[.015,.005]],[0,2,4,8])
        clipped,_=run([f]); part=clipped["features"][0]
        self.assertEqual(part["properties"]["osm_node_refs"][:2],[2,3])
        self.assertEqual(part["properties"]["elevations_m"],[2,4,6])
        rev=copy.deepcopy(f)
        rev["geometry"]["coordinates"].reverse()
        for key in ["osm_node_refs","elevations_m"]: rev["properties"][key].reverse()
        backwards=run([rev])[0]["features"][0]
        self.assertEqual(backwards["geometry"]["coordinates"],list(reversed(part["geometry"]["coordinates"])))
        self.assertEqual(backwards["properties"]["elevations_m"],list(reversed(part["properties"]["elevations_m"])))

    def test_tangent_excursion_does_not_shortcut_or_drop_boundary_line(self):
        f=road([[.002,.002],[0,.002],[-.005,.005],[0,.008],[.002,.008]],[0,1,2,3,4])
        parts=run([f])[0]["features"]
        self.assertEqual(len(parts),2)
        self.assertEqual([p["properties"]["osm_node_refs"] for p in parts],[[1,2],[4,5]])
        tangent=road([[-.001,.001],[0,0],[-.001,-.001]],[0,1,2])
        boundary=road([[0,-.001],[0,.011]],[0,12])
        output,meta=run([tangent,boundary])
        self.assertEqual(len(output["features"]),1)
        self.assertEqual(meta["counts"]["outside_features"],1)
        self.assertEqual(meta["counts"]["boundary_contacts"],1)
        self.assertEqual(output["features"][0]["geometry"]["coordinates"],[[0,0],[0,.01]])

    def test_outside_supported_structures_omitted_but_invalid_source_rejects(self):
        value,_=osm.parse(structural_xml().encode(),"osm")
        output,meta=crop(value,[9.0001,54.9999,9.0021,55.0001])
        self.assertEqual(len(output["features"]),3)
        self.assertEqual(meta["vertical"]["outside_explicit_features"],3)
        self.assertEqual(meta["vertical"]["retained_structure_features"],1)
        root=ET.fromstring(structural_xml());root.find("way/tag[@k='tunnel']").set("v","invalid")
        with self.assertRaisesRegex(ValueError,"unsupported"):
            crop(osm.parse(ET.tostring(root),"osm")[0],[9.0001,54.9999,9.0021,55.0001])

    def test_partial_span_lost_approach_and_split_way_reject(self):
        value,_=osm.parse(structural_xml().encode(),"osm")
        for box,message in [([9.0005,*BOX[1:]],"complete bridge/tunnel"),
                            ([9+20/64000,*BOX[1:]],"nonzero explicit-height ground approach")]:
            with self.assertRaisesRegex(ValueError,message): crop(value,box)
        # Clipping at an existing shared interior node must not retain half a way.
        root=ET.fromstring(structural_xml())
        node=ET.SubElement(root,"node",id="99",lon=str(9+50/64000),lat="55.0001")
        ET.SubElement(node,"tag",k="ele",v="6")
        way=ET.SubElement(root,"way",id="99")
        for ref in ["3","99"]: ET.SubElement(way,"nd",ref=ref)
        ET.SubElement(way,"tag",k="highway",v="residential")
        value,_=osm.parse(ET.tostring(root),"osm")
        cut=next(f["geometry"]["coordinates"][-1][0] for f in value["features"]
                 if f["properties"]["road_kind"]=="bridge" and f["properties"]["osm_node_refs"][-1]==3)
        with self.assertRaisesRegex(ValueError,"split source-way"):
            crop(value,[cut,54.9999,9.0021,55.0002])

    def test_caps_and_zero_source_segment_reject(self):
        f=road([[-.001,.002],[.011,.002]],[0,1])
        with patch("osm_area.MAX_POINTS",1),self.assertRaisesRegex(ValueError,"budget"): run([f])
        f=road([[-.001,.002],[-.001,.002],[.011,.002]],[0,1,2])
        with self.assertRaisesRegex(ValueError,"zero-length"): run([f])

    def test_crossing_road_keeps_traversal_without_overlay_noding(self):
        f=road([[-.01,.002],[.008,.008],[.002,.008],[.012,.002]],[0,10,20,30])
        # Explicit line clipping must not build GEOS pairwise-intersection output.
        with patch("shapely.geometry.base.BaseGeometry.intersection",side_effect=AssertionError("overlay")):
            clipped,_=run([f])
        self.assertEqual(len(clipped["features"]),1)
        part=clipped["features"][0]
        self.assertEqual(len(part["geometry"]["coordinates"]),4)
        self.assertEqual(part["properties"]["osm_node_refs"][1:3],[2,3])

    def test_cli_review_hash_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.osm";output=Path(directory)/"layer.json"
            raw=structural_xml().encode();source.write_bytes(raw)
            script=Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"
            command=[sys.executable,"-B",str(script),str(source),str(output),"--input-format","osm",
                "--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512",
                "--license",osm.LICENSE,"--layer-id","c"*32,"--osm-bbox",*map(str,BOX)]
            result=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            saved=output.read_bytes();layer=json.loads(saved)
            self.assertEqual(layer["source"]["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertIn("ground still follows map terrain"," ".join(layer["warnings"]))
            self.assertTrue(all(len(w)<=512 for w in layer["warnings"]))
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(output.read_bytes(),saved)
            self.assertEqual(source.read_bytes(),raw)


if __name__=="__main__": unittest.main()
