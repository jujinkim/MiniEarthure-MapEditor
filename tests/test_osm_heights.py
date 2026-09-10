import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from osm_heights import Supplement, MAX_BYTES, MAX_NODES, read_source
from osm_heights_fixture import missing, supplement
from osm_extract import parse, LICENSE
from osm_stream import extract
from osm_area import crop
from vertical import Vertical
from vertical_fixture import xml, grid
from osm_fixture import pbf, connected_structures_xml, structural_junctions_xml


class HeightSupplementTests(unittest.TestCase):
    def test_missing_profiles_equal_explicit_source_without_mutation(self):
        for source in [xml(True),connected_structures_xml(),structural_junctions_xml(True)]:
            with self.subTest(source=source[:50]):
                text,entries=missing(source)
                raw=text.encode(); options=json.dumps(supplement(raw,entries),ensure_ascii=False)
                sup=Supplement(options)
                value,counts=parse(raw,"osm",sup)
                expected,expected_counts=parse(source.encode(),"osm")
                self.assertEqual(value,expected)
                self.assertEqual(counts["explicit_height_roads"],expected_counts["explicit_height_roads"])
                self.assertEqual(sup.metadata["source"],dict(json=options,bytes=len(options.encode()),sha256=hashlib.sha256(options.encode()).hexdigest()))
                self.assertEqual(sup.metadata["applied_nodes"],len(entries))
                tags={1:{"name":"kept"},2:{"ele":"0"}}; before=copy.deepcopy(tags)
                one=Supplement(json.dumps(supplement(raw,[dict(node_id="1",height_m=-0.125)])))
                result=one.apply({1:[0,0],2:[1,0]},tags,[(1,"road",[1,2],{"bridge":"yes"})],one.osm_sha256)
                self.assertEqual(tags,before);self.assertEqual(result[1]["name"],"kept")
                self.assertEqual(float(result[1]["ele"]),-0.125)

    def test_partial_missing_preserves_present_heights_and_requires_complete_approaches(self):
        source=xml(True);text,entries=missing(source,{"1","3","15"});raw=text.encode()
        value,_=parse(raw,"osm",Supplement(json.dumps(supplement(raw,entries))))
        self.assertEqual(value,parse(source.encode(),"osm")[0])
        for data in [None,supplement(raw,entries[:-1])]:
            with self.assertRaisesRegex(ValueError,"every road node"):
                parse(raw,"osm",None if data is None else Supplement(json.dumps(data)))
        for h in [100,101]:
            data=supplement(raw,entries+[dict(node_id="2",height_m=h)])
            with self.assertRaisesRegex(ValueError,"already has OSM ele"):
                parse(raw,"osm",Supplement(json.dumps(data)))

    def test_wrong_snapshot_unreferenced_and_nonstructural_ids_reject(self):
        text,entries=missing();raw=text.encode();data=supplement(raw,entries)
        wrong=dict(data,osm_sha256="0"*64)
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):parse(raw,"osm",Supplement(json.dumps(wrong)))
        for identity in ["999", "9007199254740993", "9223372036854775807"]:
            with self.assertRaisesRegex(ValueError,"unreferenced"):
                parse(raw,"osm",Supplement(json.dumps(dict(data,nodes=entries+[dict(node_id=identity,height_m=0)]))))
        root=ET.fromstring(text)
        for identity,x in [(90,9.5),(91,9.501)]:ET.SubElement(root,"node",id=str(identity),lon=str(x),lat="55.503")
        way=ET.SubElement(root,"way",id="90")
        for identity in [90,91]:ET.SubElement(way,"nd",ref=str(identity))
        ET.SubElement(way,"tag",k="highway",v="residential")
        raw=ET.tostring(root)
        with self.assertRaisesRegex(ValueError,"unreferenced"):
            parse(raw,"osm",Supplement(json.dumps(supplement(raw,entries+[dict(node_id="90",height_m=0)]))))

    def test_strict_contract_bounds_duplicates_and_datum(self):
        text,entries=missing();data=supplement(text.encode(),entries)
        for key,value in [("extra",0),("format","wrong"),("vertical_crs","EPSG:3855 / EGM2008 metres"),("osm_sha256","0"),("source",""),("license",""),("accuracy",""),("nodes",[]),("nodes",entries*MAX_NODES)]:
            with self.subTest(key=key),self.assertRaises(ValueError):Supplement(json.dumps(dict(data,**{key:value})))
        for value in [True,None,"0",float("nan"),float("inf"),10000.01,-10000.01]:
            with self.subTest(height=value),self.assertRaises(ValueError):Supplement(json.dumps(dict(data,nodes=[dict(node_id="1",height_m=value)])))
        for identity in [1,"0","01","-1","1.0","1e0","9223372036854775808"]:
            with self.subTest(id=identity),self.assertRaises(ValueError):Supplement(json.dumps(dict(data,nodes=[dict(node_id=identity,height_m=0)])))
        with self.assertRaisesRegex(ValueError,"duplicate.*node"):Supplement(json.dumps(dict(data,nodes=entries+[entries[0]])))
        with self.assertRaisesRegex(ValueError,"duplicate JSON"):Supplement(json.dumps(data).replace('"format":','"format":"ignored", "format":'))
        with self.assertRaises(ValueError):Supplement(" "*(MAX_BYTES+1))
        for height in [-10000,10000,0.00001]:Supplement(json.dumps(dict(data,nodes=[dict(node_id="1",height_m=height)])))

    def test_unsupported_tags_missing_nodes_and_clearance_not_repaired(self):
        text,entries=missing();raw=text.encode()
        node_semantics=ET.fromstring(text)
        ET.SubElement(node_semantics.find("node[@id='1']"),"tag",k="ele:datum",v="unknown")
        cases=[text.replace('k="bridge" v="yes"','k="bridge" v="viaduct"'),
               text.replace('k="maxheight:physical"','k="maxheight"'),
               text.replace('id="3"','id="300"',1), ET.tostring(node_semantics,encoding="unicode")]
        for changed in cases:
            with self.assertRaises(ValueError):parse(changed.encode(),"osm",Supplement(json.dumps(supplement(changed.encode(),entries))))

    def test_conversion_precedes_crop_and_grid_covers_outside_supplements(self):
        text,entries=missing();raw=text.encode();value,_=parse(raw,"osm",Supplement(json.dumps(supplement(raw,entries))))
        v=Vertical(dict(target="EGM2008",zero_m=102,grid=json.dumps(grid([1,5,7,13]))))
        converted=v.apply(value);clipped,meta=crop(converted,[9.5007,55.5,9.5017,55.502])
        expected,_=parse(xml(True).encode(),"osm")
        self.assertEqual(clipped,crop(v.apply(expected),[9.5007,55.5,9.5017,55.502])[0])
        self.assertEqual(meta["policy"],"geometry-intersection-v3")
        bad=grid();bad["bbox"][0]=9.5001
        with self.assertRaisesRegex(ValueError,"outside correction grid"):
            Vertical(dict(target="EGM2008",zero_m=102,grid=json.dumps(bad))).apply(value)

    def test_stream_closure_before_crop_complete_and_incomplete(self):
        text,entries=missing(connected_structures_xml())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"source.pbf";raw=pbf(source,text)
            bbox=[9.0009,55,9.0014,55.002]
            for values in [entries,entries[:-1]]:
                job=root/str(len(values));job.mkdir()
                sup=Supplement(json.dumps(supplement(raw,values)))
                if len(values)!=len(entries):
                    with self.assertRaisesRegex(ValueError,"every road node"):extract(source,bbox,job,supplement=sup)
                else:
                    selected,_,meta=extract(source,bbox,job,supplement=sup)
                    expected,_=parse(raw,"pbf",sup)
                    self.assertEqual(crop(selected,bbox)[0],crop(expected,bbox)[0])
                    self.assertEqual(meta["structure_closure"]["structures"],6)
                self.assertEqual(list(job.iterdir()),[])
            self.assertEqual(source.read_bytes(),raw)

    def test_stream_cancel_cleanup_with_captured_supplement(self):
        text,entries=missing(connected_structures_xml())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"source.pbf";raw=pbf(source,text);job=root/"job";job.mkdir()
            sup=Supplement(json.dumps(supplement(raw,entries)))
            def stop(stage,*args):
                if stage=="select":raise ValueError("synthetic cancellation")
            with self.assertRaisesRegex(ValueError,"cancellation"):extract(source,[9,55,9.002,55.002],job,stop,sup)
            self.assertEqual(list(job.iterdir()),[]);self.assertEqual(source.read_bytes(),raw)
            self.assertTrue(extract(source,[9,55,9.002,55.002],job,supplement=sup)[0])

    def test_cli_xml_pbf_stream_snapshot_read_bounds_and_exclusive_output(self):
        text,entries=missing()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"source.osm").write_text(text);pbf(root/"source.pbf",text)
            request=root/"vertical.json";request.write_text(json.dumps(dict(target="EGM2008",zero_m=102,grid=json.dumps(grid()))))
            outputs=[]
            for i,format in enumerate(["osm","pbf","pbf"]):
                source=root/("source."+format);raw=source.read_bytes();height=root/(str(i)+".json")
                height.write_text(json.dumps(supplement(raw,entries)),encoding="utf-8");original=height.read_bytes()
                job=root/("job"+str(i));job.mkdir();output=job/"layer.json"
                cmd=[sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(output),"--coordinates","wgs84-utm","--origin","9.5","55.5","--local-origin","512","512","--license",LICENSE,"--layer-id","a"*32,"--input-format",format,"--vertical-request",str(request),"--height-supplement",str(height),"--osm-bbox","9.5007","55.5","9.5017","55.502"]
                if i==2:cmd.append("--osm-stream")
                run=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(run.returncode,0,run.stderr)
                layer=json.loads(output.read_bytes());outputs.append(layer["patches"])
                self.assertEqual(layer["coordinates"]["osm_height_supplement"]["source"]["json"],original.decode())
                before=output.read_bytes();self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
                self.assertEqual(output.read_bytes(),before);self.assertEqual(source.read_bytes(),raw);self.assertEqual(height.read_bytes(),original)
            self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[0],outputs[2])
            height.write_bytes(b" "*(MAX_BYTES+1))
            with self.assertRaisesRegex(ValueError,"256 KiB"):read_source(height)
            height.write_bytes(b"\xff")
            with self.assertRaises(UnicodeError):read_source(height)

if __name__=="__main__":unittest.main()
