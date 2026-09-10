import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from vertical import Vertical, CRS, MAX_GRID_BYTES
from osm_extract import parse, LICENSE
from osm_area import crop
from geojson import convert
from vertical_fixture import grid, xml
from osm_fixture import XML, pbf


class VerticalTests(unittest.TestCase):
    def options(self, values=None, zero=102):
        return dict(target="EGM2008",zero_m=zero,grid=json.dumps(grid(values),ensure_ascii=False))

    def test_bilinear_axes_sign_nodes_and_boundaries(self):
        v=Vertical(self.options([1,3,5,11],zero=0))
        for p,expected in [([9.5,55.5],1),([9.504,55.5],3),([9.5,55.504],5),([9.504,55.504],11),([9.502,55.502],5),([9.501,55.503],5.25)]:
            self.assertAlmostEqual(v.delta(p),expected,places=8)
        self.assertAlmostEqual(Vertical(self.options([-2]*4)).delta([9.502,55.502]),-2)

    def test_preserve_original_graph_clearance_and_snapshot(self):
        value,_=parse(xml().encode(),"osm"); original=copy.deepcopy(value)
        options=self.options(); v=Vertical(options); output=v.apply(value)
        self.assertEqual(value,original)
        self.assertEqual(output["features"][1]["properties"]["elevations_m"],[0,6,6,0])
        self.assertEqual(output["features"][4]["properties"]["elevations_m"],[0,-6,-6,0])
        self.assertEqual(output["features"][4]["properties"]["clearance_m"],4.5)
        for a,b in zip(value["features"],output["features"]):
            self.assertEqual(a["geometry"],b["geometry"])
            self.assertEqual(a["properties"]["osm_node_refs"],b["properties"]["osm_node_refs"])
        s=v.metadata["grid_source"]
        self.assertEqual(s["json"],options["grid"])
        self.assertEqual(s["sha256"],hashlib.sha256(options["grid"].encode()).hexdigest())
        self.assertEqual(s["bytes"],len(options["grid"].encode()))
        self.assertEqual(v.metadata["explicit_roads"],6)
        self.assertEqual(v.metadata["explicit_points"],16)

    def test_same_datum_offset_negative_zero_and_range(self):
        value,_=parse(xml().encode(),"osm")
        v=Vertical(dict(target="EGM96",zero_m=100,grid=None))
        self.assertEqual(v.apply(value)["features"][1]["properties"]["elevations_m"],[0,6,6,0])
        v=Vertical(dict(target="EGM96",zero_m=-100,grid=None))
        self.assertEqual(v.apply(value)["features"][0]["properties"]["elevations_m"],[200,200])
        with self.assertRaisesRegex(ValueError,"converted local elevation"):
            Vertical(dict(target="EGM96",zero_m=-10000,grid=None)).apply(value)

    def test_conversion_precedes_crop_and_once_cm_quantization(self):
        value,_=parse(xml().encode(),"osm")
        v=Vertical(self.options([1,5,7,13],zero=100))
        converted=v.apply(value)
        clipped,meta=crop(converted,[9.5007,55.5,9.5017,55.502])
        self.assertEqual(meta["policy"],"geometry-intersection-v3")
        original=converted["features"][1]
        result=clipped["features"][0]
        x=result["geometry"]["coordinates"][0][0]
        a,b=original["geometry"]["coordinates"][:2]
        t=(x-a[0])/(b[0]-a[0])
        ah,bh=original["properties"]["elevations_m"][:2]
        expected=ah+(bh-ah)*t
        self.assertAlmostEqual(result["properties"]["elevations_m"][0],expected)
        layer=convert(clipped,"synthetic",LICENSE,coordinates=dict(mode="wgs84-utm",origin=[9.5,55.5],local_origin_m=[512,512]),osm_graph=True)
        road=next(p["after"] for p in layer.patches if p["field"]=="roads")
        self.assertEqual(road["points"][0][1],round(expected*100))

    def test_missing_unknown_invalid_budget_no_fallback(self):
        for change in [dict(target="ellipsoid"),dict(zero_m=True),dict(zero_m=float("nan")),dict(zero_m=0.001),dict(grid=None),dict(grid="x"*(MAX_GRID_BYTES+1)),dict(extra=1)]:
            with self.subTest(change=list(change)),self.assertRaises(ValueError): Vertical(dict(self.options(),**change))
        with self.assertRaises(ValueError): Vertical(dict(target="EGM96",zero_m=0,grid="{}"))
        for key,val in [("source_crs",CRS["EGM2008"]),("quantity","N_EGM2008-minus-N_EGM96"),("accuracy",""),("license",""),("columns",True),("rows",34),("values_m",[1,2,None,4]),("values_m",[1,2,3]),("values_m",[1,2,3,201]),("bbox",[9.5,55.5,11,56]),("bbox",[9.5,55.5,9,56]),("horizontal_crs","EPSG:3857")]:
            g=grid();g[key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError): Vertical(dict(self.options(),grid=json.dumps(g)))
        with self.assertRaisesRegex(ValueError,"duplicate JSON"):
            Vertical(dict(self.options(),grid=self.options()["grid"].replace('"columns": 2','"columns": 2, "columns": 2')))
        value,_=parse(xml().encode(),"osm")
        with patch("vertical.MAX_POINTS",2),self.assertRaisesRegex(ValueError,"point budget"): Vertical(self.options()).apply(value)

    def test_full_source_coverage_and_missing_height_rejection(self):
        value,_=parse(xml().encode(),"osm")
        g=grid();g["bbox"][0]=9.5001
        with self.assertRaisesRegex(ValueError,"outside correction grid"):
            Vertical(dict(self.options(),grid=json.dumps(g))).apply(value)
        with self.assertRaisesRegex(ValueError,"every road node"):
            parse(xml().replace('<tag k="ele" v="100.0" />','',1).encode(),"osm")
        ordinary,_=parse(XML.encode(),"osm")
        with self.assertRaisesRegex(ValueError,"requires explicit"): Vertical(self.options()).apply(ordinary)
        self.assertEqual(Vertical(dict(target="EGM96",zero_m=0,grid=None)).apply(ordinary),ordinary)

    def test_xml_pbf_stream_cli_snapshot_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"source.osm"; source.write_text(xml())
            pbf(root/"source.pbf",xml()); request=root/"request.json"; request.write_text(json.dumps(self.options()))
            original=source.read_bytes(); outputs=[]
            for i,format in enumerate(["osm","pbf","pbf"]):
                job=root/str(i);job.mkdir();output=job/"layer.json"
                cmd=[sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source if format=="osm" else root/"source.pbf"),str(output),"--coordinates","wgs84-utm","--origin","9.5","55.5","--local-origin","512","512","--license",LICENSE,"--layer-id","a"*32,"--input-format",format,"--vertical-request",str(request),"--osm-bbox","9.5007","55.5","9.5017","55.502"]
                if i==2:cmd.append("--osm-stream")
                run=subprocess.run(cmd,capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stderr)
                layer=json.loads(output.read_bytes());outputs.append(layer)
                self.assertEqual(layer["coordinates"]["vertical"]["grid_source"]["json"],self.options()["grid"])
                self.assertTrue(all(len(w)<=512 for w in layer["warnings"]))
                before=output.read_bytes()
                self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
                self.assertEqual(output.read_bytes(),before)
            self.assertEqual(outputs[0]["patches"],outputs[1]["patches"])
            self.assertEqual(outputs[0]["patches"],outputs[2]["patches"])
            self.assertEqual(source.read_bytes(),original)


if __name__=="__main__": unittest.main()
