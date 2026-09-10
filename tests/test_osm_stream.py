import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import osm_stream as stream
from osm_fixture import XML, pbf, multipolygon_xml, structural_xml
from osm_stream_fixture import large_pbf
from osm_extract import parse, LICENSE
from osm_area import crop

BOX = [8.9999,54.9999,9.006,55.006]


class Streaming(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "original.pbf"

    def extract(self, xml=XML, box=BOX, event=lambda *a: None):
        self.source.unlink(missing_ok=True)  # Test-owned fixture only.
        raw = pbf(self.source, xml)
        result = stream.extract(self.source, box, self.directory, event)
        self.assertEqual(self.source.read_bytes(),raw)
        self.assertEqual(result[2]["source_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertTrue(all(not (self.directory/name).exists() for name in stream.OWNED_FILES))
        return result

    def test_small_multipart_vertical_parity_and_progress(self):
        for xml in [XML,multipolygon_xml(),structural_xml()]:
            with self.subTest(xml=xml[:30]):
                events=[]
                value, counts, meta=self.extract(xml,event=lambda *a:events.append(a))
                expected=parse(self.source.read_bytes(),"pbf")[0]
                self.assertEqual(crop(value,BOX)[0],crop(expected,BOX)[0])
                self.assertEqual(meta["passes"],3)
                for stage in ["read","index_nodes","index_ways","index_relations"]:
                    steps=[x for x in events if x[0]==stage]
                    self.assertEqual(steps[0][1],0)
                    self.assertEqual(steps[-1][1:3],(meta["source_bytes"],meta["source_bytes"]))
                    self.assertEqual([e[1] for e in steps],sorted(e[1] for e in steps))

    def test_enclosing_relation_holes_island_and_crossing_no_inside_vertices(self):
        for xml,box in [(XML,[9.00051,54.9999,9.0006,55.0001]),
                        (XML,[9.00005,55.00005,9.00015,55.00015]),
                        (multipolygon_xml(),[9.0031,55.0011,9.0049,55.0029])]:
            value,_,meta=self.extract(xml,box)
            actual=crop(value,box)[0]
            self.assertEqual(actual,crop(parse(self.source.read_bytes(),"pbf")[0],box)[0])
            self.assertLess(meta["selected"]["nodes"],meta["scan"]["nodes"])

    def test_selected_outside_semantics_and_complete_references(self):
        # Unsupported geometry outside candidate envelopes is a disclosed omission.
        root=ET.fromstring(XML)
        ET.SubElement(root.find("way[@id='3']"),"tag",k="layer",v="5")
        xml=ET.tostring(root,encoding="unicode")
        self.extract(xml,[9,54.9999,9.0003,55.0003])
        with self.assertRaisesRegex(ValueError,"vertical"): self.extract(xml)
        root.remove(root.find("node[@id='10']"))
        with self.assertRaisesRegex(ValueError,"missing referenced node"):
            self.extract(ET.tostring(root,encoding="unicode"),[9,54.9999,9.0003,55.0003])
        for xml in [multipolygon_xml().replace('ref="114"','ref="999"'),
                    multipolygon_xml().replace('type="way" ref="114"','type="relation" ref="114"'),
                    XML.replace('</osm>','<node id="1" lon="9" lat="55"/></osm>'),
                    structural_xml().replace('<tag k="ele" v="6" />', '',1)]:
            with self.assertRaises(ValueError): self.extract(xml)

    def test_ignored_area_ownership_and_partial_structure_reject(self):
        xml=XML.replace('</osm>','<relation id="3"><member type="way" ref="1" role="outer"/><tag k="type" v="boundary"/></relation></osm>')
        with self.assertRaisesRegex(ValueError,"area relation"): self.extract(xml)
        box=[9.0004,54.9999,9.0016,55.0001]
        with self.assertRaisesRegex(ValueError,"ground connections|complete explicit"):
            value,_,_=self.extract(structural_xml(),box)
            crop(value,box)

    def test_limits_workspace_and_capture_mutation(self):
        for name,value in [("MAX_SOURCE",1),("MAX_INDEX",4096),("MAX_SCAN_ENTITIES",1),
                           ("MAX_SCAN_REFS",1),("MAX_ENTITY_REFS",1),("MAX_INPUT",1),
                           ("MAX_POINTS",1),("MAX_ENTITIES",1),("MAX_FEATURES",1),("MAX_REFS",1)]:
            with self.subTest(name=name),patch.object(stream,name,value),self.assertRaises(ValueError): self.extract()
            self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
        with patch.object(stream.shutil,"disk_usage",return_value=type("Usage",(),{"free":0})()),self.assertRaisesRegex(ValueError,"free workspace"):
            self.extract()
        def mutate(stage,c,t,*unit):
            if stage=="read" and c==t:
                with self.source.open("ab") as writer: writer.write(b"changed")
        pbf(self.directory/"untouched.pbf")
        with self.assertRaisesRegex(ValueError,"changed during capture"): self.extract(event=mutate)
        occupied=self.directory/"source.pbf"
        occupied.write_bytes(b"not-owned")
        with self.assertRaisesRegex(ValueError,"workspace"): stream.extract(self.source,BOX,self.directory)
        self.assertEqual(occupied.read_bytes(),b"not-owned")

    def test_malformed_frames_and_expansion_budget(self):
        raw=pbf(self.source)
        for altered in [raw[:-1],b"\xff"*4+raw,raw+raw]:
            self.source.write_bytes(altered)
            with self.assertRaises(ValueError): stream.extract(self.source,BOX,self.directory)
            self.assertEqual(self.source.read_bytes(),altered)
        # A truthful raw_size exceeding the admission limit must fail before inflate.
        payload=zlib.compress(b"x"*4097)
        blob=b"\x10"+stream._varint(4097)+b"\x1a"+stream._varint(len(payload))+payload
        header=b"\x0a\x07OSMData\x18"+stream._varint(len(blob))
        self.source.write_bytes(struct.pack(">I",len(header))+header+blob)
        with patch.object(stream,"MAX_BLOB",4096),self.assertRaisesRegex(ValueError,"bounded raw_size"):
            list(stream._blocks(self.source,"parse",lambda *a:None,self.source.stat().st_size))
        # A false size must not turn a compressed bomb into an unbounded allocation.
        self.source.write_bytes(self.source.read_bytes().replace(stream._varint(4097),stream._varint(4096),1))
        with patch.object(stream,"MAX_BLOB",4096),self.assertRaisesRegex(ValueError,"size/budget"):
            list(stream._blocks(self.source,"parse",lambda *a:None,self.source.stat().st_size))

    def test_capture_is_frozen_and_interruption_closes_owned_index(self):
        raw=pbf(self.source)
        def replace_original(stage,c,t,*unit):
            if stage=="index_nodes" and c==0: self.source.write_bytes(b"user changed source after capture")
        value,_,meta=stream.extract(self.source,BOX,self.directory,replace_original)
        self.assertEqual(meta["source_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(value,parse(raw,"pbf")[0])
        self.assertEqual(self.source.read_bytes(),b"user changed source after capture")
        self.source.write_bytes(raw)
        for stop in ["read","index_nodes","index_ways","index_relations","select","parse"]:
            def interrupt(stage,c,t,*unit):
                if stage==stop: raise InterruptedError("synthetic interruption")
            with self.assertRaises(InterruptedError): stream.extract(self.source,BOX,self.directory,interrupt)
            self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
            self.assertEqual(self.source.read_bytes(),raw)

    def test_history_and_long_tag_reject(self):
        import osmium
        history=osmium.io.File(str(self.source),"pbf")
        history.has_multiple_object_versions=True
        with osmium.SimpleWriter(history) as writer:
            writer.add_node(osmium.osm.mutable.Node(id=1,location=(9,55)))
        with self.assertRaisesRegex(ValueError,"history"): stream.extract(self.source,BOX,self.directory)
        with self.assertRaisesRegex(ValueError,"tag"):
            self.extract(XML.replace('v="bench"','v="'+'x'*513+'"'))

    def test_index_growth_cap_and_parent_eof(self):
        root=ET.fromstring(XML)
        for identity in range(100,110):
            node=ET.SubElement(root,"node",id=str(identity),lon="20",lat="60")
            for k in range(64): ET.SubElement(node,"tag",k=f"test_{k}",v="x"*500)
        with patch.object(stream,"MAX_INDEX",65536),self.assertRaisesRegex(ValueError,"full"):
            self.extract(ET.tostring(root,encoding="unicode"))
        self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
        module_path=str(Path(__file__).resolve().parents[1]/"scripts/importers")
        code="import sys,threading; sys.path.insert(0,sys.argv[1]); from geojson import watch_parent_lifetime; watch_parent_lifetime(900); print('ready',flush=True); threading.Event().wait()"
        with subprocess.Popen([sys.executable,"-B","-c",code,module_path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
            self.assertEqual(child.stdout.readline(),b"ready\n")
            child.stdin.close()
            self.assertEqual(child.wait(timeout=5),3)

    def test_actual_large_cli_hash_progress_exclusive_publication(self):
        size=large_pbf(self.source)
        self.assertGreater(size,32*1024**2)
        with self.source.open("rb") as file: digest=hashlib.file_digest(file,"sha256").hexdigest()
        script=Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"
        output=self.directory/"layer.json"
        command=[sys.executable,"-B",str(script),str(self.source),str(output),"--input-format","pbf","--osm-stream","--osm-bbox",*map(str,BOX),"--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",LICENSE,"--layer-id","a"*32]
        result=subprocess.run(command,capture_output=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        data=json.loads(output.read_bytes())
        self.assertEqual(data["source"]["sha256"],digest)
        self.assertEqual(data["source"]["bytes"],size)
        self.assertLess(data["coordinates"]["osm_stream"]["selected"]["bytes"],32*1024**2)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(list(dict.fromkeys(e["stage"] for e in events)),["read","index_nodes","index_ways","index_relations","select","parse","convert","write","complete"])
        self.assertLess(len(result.stdout),1024**2)
        saved=output.read_bytes()
        self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=90).returncode,0)
        self.assertEqual(output.read_bytes(),saved)
        with self.source.open("rb") as file: self.assertEqual(hashlib.file_digest(file,"sha256").hexdigest(),digest)
        self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))


if __name__=="__main__": unittest.main()
