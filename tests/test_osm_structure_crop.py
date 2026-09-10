import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_osm_ground_crop import road, run
from test_osm_importer import osm, convert, OPTIONS
from osm_fixture import structural_xml, pbf
from osm_area import crop
from osm_stream import extract

BOX = [9.0005, 54.9999, 9.0016, 55.001]


class StructureCrop(unittest.TestCase):
    def test_both_cut_grades_heights_clearance_source_ranges_and_determinism(self):
        value,_=osm.parse(structural_xml().encode(), "osm")
        original=copy.deepcopy(value)
        output,meta=crop(value,BOX)
        self.assertEqual(value,original)
        self.assertEqual(crop(value,BOX),(output,meta))
        self.assertEqual(meta["policy"],"geometry-intersection-v3")
        v=meta["vertical"]
        self.assertEqual(v["partial_structure_ways"],2)
        self.assertEqual(v["section_endpoints"],4)
        self.assertEqual(v["retained_structure_features"],2)
        self.assertEqual([f["properties"]["road_kind"] for f in output["features"]],["bridge","tunnel"])
        for entry,feature,source in zip(v["structures"], output["features"], [value["features"][1],value["features"][4]]):
            lo,hi=entry["source_range"]
            self.assertTrue(0<lo<1 and 2<hi<3)
            points=feature["geometry"]["coordinates"]
            self.assertEqual([points[0][0],points[-1][0]], [BOX[0],BOX[2]])
            h=source["properties"]["elevations_m"]
            self.assertAlmostEqual(feature["properties"]["elevations_m"][0],h[0]+lo*(h[1]-h[0]))
            self.assertAlmostEqual(feature["properties"]["elevations_m"][-1],h[2]+(hi-2)*(h[3]-h[2]))
            self.assertTrue(all(e["role"]=="boundary-section" for e in entry["endpoints"]))
        self.assertEqual(output["features"][1]["properties"]["clearance_m"],4.5)

    def test_one_cut_retains_original_approach_and_native_input_graph(self):
        value,_=osm.parse(structural_xml().encode(),"osm")
        output,meta=crop(value,[*BOX[:2],9.0021,BOX[3]])
        layer=convert(output,"source",osm.LICENSE,coordinates=OPTIONS,osm_graph=True,layer_id="c"*32)
        roads=[p["after"] for p in layer.patches if p["field"]=="roads"]
        self.assertEqual([r["kind"] for r in roads],["bridge","ground","tunnel","ground"])
        for i in [0,2]: self.assertEqual(roads[i]["to"],roads[i+1]["from"])
        self.assertEqual(meta["vertical"]["section_endpoints"],2)
        self.assertEqual([e["role"] for e in meta["vertical"]["structures"][0]["endpoints"]],["boundary-section","source-node"])

    def test_xml_pbf_stream_geometry_and_provenance_parity(self):
        raw=structural_xml().encode()
        xml=crop(osm.parse(raw,"osm")[0],BOX)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"original.pbf";data=pbf(source,raw.decode())
            whole=crop(osm.parse(data,"pbf")[0],BOX)
            streamed=crop(extract(source,BOX,directory)[0],BOX)
            self.assertEqual(xml,whole)
            self.assertEqual(whole,streamed)
            self.assertEqual(source.read_bytes(),data)

    def test_reentry_reversal_distinct_cuts_and_output_budget(self):
        f=road([[-.005,.002],[.015,.002],[.015,.008],[-.005,.008]],[-10,10,30,50])
        f["properties"].update(road_kind="tunnel",clearance_m=4)
        twin=copy.deepcopy(f);twin["properties"]["osm_way_id"]=2
        with patch("shapely.geometry.base.BaseGeometry.intersection",side_effect=AssertionError("overlay")):
            output,meta=run([f,twin])
        self.assertEqual(len(output["features"]),4)
        self.assertEqual(meta["vertical"]["section_endpoints"],8)
        self.assertNotEqual(output["features"][0]["properties"]["osm_node_refs"],output["features"][2]["properties"]["osm_node_refs"])
        rev=copy.deepcopy(f)
        rev["geometry"]["coordinates"].reverse()
        for key in ["osm_node_refs","elevations_m"]: rev["properties"][key].reverse()
        backwards=run([rev])[0]["features"]
        for a,b in zip(backwards,reversed(output["features"][:2])):
            self.assertEqual(a["geometry"]["coordinates"],list(reversed(b["geometry"]["coordinates"])))
            for actual,expected in zip(a["properties"]["elevations_m"],reversed(b["properties"]["elevations_m"])): self.assertAlmostEqual(actual,expected)
        with patch("osm_area.MAX_POINTS",3),self.assertRaisesRegex(ValueError,"budget"): run([f])

    def test_existing_vertex_cut_and_retained_shared_junction(self):
        first=road([[-.005,.002],[0,.002],[.005,.002]],[0,5,5],[1,2,3])
        first["properties"].update(road_kind="bridge")
        second=road([[.005,.002],[.015,.002]],[5,0],[3,4])
        second["properties"].update(road_kind="bridge")
        output,meta=run([first,second])
        entries=meta["vertical"]["structures"]
        self.assertEqual(entries[0]["endpoints"],[dict(ref="2",role="boundary-section"),dict(ref="3",role="source-node")])
        self.assertEqual(entries[1]["endpoints"][0],dict(ref="3",role="source-node"))
        self.assertEqual(output["features"][0]["properties"]["osm_node_refs"][-1],output["features"][1]["properties"]["osm_node_refs"][0])

    def test_partial_cli_warning_bounds_hash_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.osm";output=Path(directory)/"layer.json"
            raw=structural_xml().encode();source.write_bytes(raw)
            command=[sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(output),
                "--input-format","osm","--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512",
                "--license",osm.LICENSE,"--layer-id","c"*32,"--osm-bbox",*map(str,BOX)]
            result=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            saved=output.read_bytes();layer=json.loads(saved)
            self.assertTrue(all(len(w)<=512 for w in layer["warnings"]))
            self.assertGreaterEqual(layer["warning_count"],len(layer["warnings"]))
            self.assertIn("not surveyed entrances"," ".join(layer["warnings"]))
            self.assertEqual(layer["source"]["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual(layer["coordinates"]["osm_crop"]["vertical"]["section_endpoints"],4)
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(output.read_bytes(),saved)
            self.assertEqual(source.read_bytes(),raw)


if __name__=="__main__": unittest.main()
