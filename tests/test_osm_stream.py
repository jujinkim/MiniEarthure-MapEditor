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
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.
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

    def test_city_block_pointers_keep_off_window_members_and_approaches(self):
        def without_city(value):
            result=json.loads(json.dumps(value))
            for feature in result["features"]:
                feature["properties"]={k:v for k,v in feature["properties"].items() if not k.startswith("_city")}
            return result
        for xml,selected in [(multipolygon_xml(),[9.0031,55.0011,9.0049,55.0029]),
                             (structural_xml(),[9.0004,54.9999,9.0016,55.0001])]:
            self.source.unlink(missing_ok=True)
            original=pbf(self.source,xml)
            exact=stream.extract(self.source,selected,self.directory)
            city=stream.extract(self.source,selected,self.directory,city=True)
            self.assertEqual(without_city(city[0]),without_city(exact[0]))
            self.assertEqual(city[2]["index_policy"],"source-block-pointers-v1")
            self.assertGreater(city[2]["resolved_way_blocks"],0)
            self.assertEqual(self.source.read_bytes(),original)
            self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))

    def test_enclosing_relation_holes_island_and_crossing_no_inside_vertices(self):
        for xml,box in [(XML,[9.00051,54.9999,9.0006,55.0001]),
                        (XML,[9.00005,55.00005,9.00015,55.00015]),
                        (multipolygon_xml(),[9.0031,55.0011,9.0049,55.0029])]:
            value,_,meta=self.extract(xml,box)
            actual=crop(value,box)[0]
            self.assertEqual(actual,crop(parse(self.source.read_bytes(),"pbf")[0],box)[0])
            self.assertLess(meta["selected"]["nodes"],meta["scan"]["nodes"])

    def test_source_coordinate_precision_in_both_hemispheres(self):
        for dx,dy in [(117.1234567,-18.7654321),(-80.1234567,-88.7654321)]:
            root=ET.fromstring(XML)
            for node in root.findall("node"):
                node.set("lon",f"{float(node.get('lon'))+dx:.7f}")
                node.set("lat",f"{float(node.get('lat'))+dy:.7f}")
            selected=[BOX[0]+dx,BOX[1]+dy,BOX[2]+dx,BOX[3]+dy]
            value,_,_=self.extract(ET.tostring(root,encoding="unicode"),selected)
            original=parse(self.source.read_bytes(),"pbf")[0]
            self.assertEqual(crop(value,selected)[0],crop(original,selected)[0])

    def test_sorted_and_unsorted_node_batches_preserve_selection(self):
        root=ET.fromstring(XML)
        nodes=root.findall("node")
        nodes.extend(ET.Element("node",id=str(i),lon="20.1234567",lat="60.7654321") for i in range(100,4300))
        remainder=[item for item in root if item.tag!="node"]
        expected=None
        for ordered in [nodes,list(reversed(nodes))]:
            snapshot=ET.Element("osm",root.attrib);snapshot.extend(ordered+remainder)
            value,_,_=self.extract(ET.tostring(snapshot,encoding="unicode"))
            if expected is None: expected=value
            else: self.assertEqual(value,expected)
        with patch.object(stream,"MAX_INDEX",65536),self.assertRaisesRegex(ValueError,"index exceeds its disk quota"):
            self.extract(ET.tostring(snapshot,encoding="unicode"))
        self.assertTrue(all(not (self.directory/name).exists() for name in stream.OWNED_FILES))
        # A duplicate far from its earlier occurrence cannot disappear in a
        # file index, even when it is outside the selected geographic area.
        snapshot.insert(0,ET.Element("node",id="100",lon="20.1234567",lat="60.7654321"))
        with self.assertRaisesRegex(ValueError,"UNIQUE|duplicate"):
            self.extract(ET.tostring(snapshot,encoding="unicode"))

    def test_plain_node_blocks_and_unsorted_closure_match_the_decoded_index(self):
        import osmium
        box=[9.0004,54.9999,9.0016,55.0001]
        expected=self.extract(structural_xml(),box)
        self.assertGreater(expected[2]["structure_closure"]["visits"],0)
        # Plain (non-dense) node blocks stay on the per-entity path.
        self.source.unlink()
        with osmium.SimpleWriter(osmium.io.File(str(self.source),"pbf,pbf_dense_nodes=false")) as writer:
            for entity in osmium.FileProcessor(osmium.io.FileBuffer(structural_xml().encode(),"osm")): writer.add(entity)
        plain=stream.extract(self.source,box,self.directory)
        self.assertEqual(plain[:2],expected[:2])
        self.assertEqual({k:v for k,v in plain[2].items() if k not in ("source_bytes","source_sha256")},
                         {k:v for k,v in expected[2].items() if k not in ("source_bytes","source_sha256")})
        # Unsorted nodes keep every highway incidence in SQLite; the shared-node
        # index must give the same closure, visit count included.
        root=ET.fromstring(structural_xml())
        nodes=root.findall("node")
        remainder=[item for item in root if item.tag!="node"]
        snapshot=ET.Element("osm",root.attrib);snapshot.extend(list(reversed(nodes))+remainder)
        unsorted=self.extract(ET.tostring(snapshot,encoding="unicode"),box)
        self.assertEqual(unsorted[:2],expected[:2])
        self.assertEqual(unsorted[2]["structure_closure"],expected[2]["structure_closure"])

    def test_decoded_blocks_follow_libosmium_granularity_offsets_and_refs(self):
        import numpy as np
        import osmium
        def field(number,payload): return stream._varint(number<<3|2)+stream._varint(len(payload))+payload
        def scalar(number,value): return stream._varint(number<<3)+stream._varint(value%2**64)
        def packed(values):
            previous,out=0,b""
            for value in values:
                delta,previous=value-previous,value
                out+=stream._varint((delta<<1)^(delta>>63))
            return out
        ids=[5,9,10,4000000000]
        lat=[-5,7,123456,-900000]
        lon=[-123,99,-1,1800000]
        dense=field(1,packed(ids))+field(8,packed(lat))+field(9,packed(lon))
        ways=field(3,scalar(1,7)+field(8,packed([10,5,9,4000000000,5])))+field(3,scalar(1,8))
        block=field(1,field(1,b""))+field(2,field(2,dense))+field(2,ways)+scalar(17,1000)+scalar(19,-123456789)+scalar(20,987654321)
        pbf(self.source)
        header=next(stream._blocks(self.source,"x",lambda *a:None,self.source.stat().st_size))
        source=stream._frame(*header)+stream._frame(b"OSMData",block)
        nodes,(way_ids,counts,refs)=stream._decode_block(np,block,nodes=True,ways=True)
        located,decoded_ways=[],[]
        for entity in osmium.FileProcessor(osmium.io.FileBuffer(source,"pbf")):
            if entity.is_node(): located.append([entity.id,entity.location.x,entity.location.y])
            else: decoded_ways.append((entity.id,[n.ref for n in entity.nodes]))
        self.assertEqual(len(nodes),1)
        self.assertIsNone(nodes[0][2])
        self.assertEqual(np.column_stack((nodes[0][0],nodes[0][1])).tolist(),located)
        self.assertEqual(list(zip(way_ids,[refs[sum(counts[:i]):sum(counts[:i+1])].tolist() for i in range(len(counts))])),decoded_ways)
        self.assertEqual(decoded_ways[1],(8,[]))
        # Anything but the canonical encoding stays on libosmium's per-entity path:
        # truncation, unknown wire types, unterminated packed values, repeated or
        # mismatched dense arrays, a repeated way ID, oversized blocks.
        for broken in [block[:-1],block+b"\x0b",field(2,field(2,field(1,b"\x80"))),
                       field(2,field(2,field(1,packed([1,2]))+field(8,packed([1]))+field(9,packed([1,2])))),
                       field(2,field(2,field(1,packed([1]))+field(1,packed([2])))),
                       field(2,field(3,scalar(1,7)+scalar(1,8))),
                       field(2,field(2,field(1,packed([1]))+field(8,packed([1]))+field(9,packed([1]))+field(5,field(6,stream._varint(2**32))))),
                       block+field(1,b"x"*stream.MAX_DECODED_BLOCK)]:
            self.assertIsNone(stream._decode_block(np,broken,nodes=True,ways=True))
        # libosmium's int64/int32 arithmetic: IDs beyond 2**52, wrapped coordinates,
        # a granularity truncated to int32.
        dense=field(1,packed([2**62+1]))+field(8,packed([550000000+2**32]))+field(9,packed([90000000]))
        wrapped=field(1,field(1,b""))+field(2,field(2,dense))+field(2,field(3,scalar(1,2**62)+field(8,packed([2**62+1]))))+scalar(17,2**32+100)
        nodes,(way_ids,counts,refs)=stream._decode_block(np,wrapped,nodes=True,ways=True)
        located=[]
        for entity in osmium.FileProcessor(osmium.io.FileBuffer(stream._frame(*header)+stream._frame(b"OSMData",wrapped),"pbf")):
            located.append([entity.id,entity.location.x,entity.location.y] if entity.is_node() else [entity.id,[n.ref for n in entity.nodes]])
        self.assertEqual([[int(nodes[0][0][0]),*nodes[0][1][0].tolist()],[way_ids[0],refs.tolist()]],located)

    def test_shared_road_nodes_keep_only_nodes_two_ways_share(self):
        import sqlite3
        from osm_disk_nodes import DiskNodes, SharedRoadNodes
        db=sqlite3.connect(":memory:")
        db.execute("CREATE TABLE nodes(id INTEGER PRIMARY KEY, x INTEGER, y INTEGER)")
        nodes=DiskNodes(self.directory,db,1024**2)
        import numpy as np
        nodes.add_many(np.arange(1,9,dtype=np.int64),np.zeros((8,2),dtype=np.int32))
        nodes.seal()
        shared=SharedRoadNodes(nodes,self.directory)
        try:
            shared.add([(20,[1,2,3,1]),(21,[3,4])])
            shared.add([(22,[4,5,6]),(23,[])])
            shared.add([(24,[7,8,7])])
            shared.add([(100+way,[1]) for way in range(255)])  # One batch sharing a node never wraps.
            self.assertEqual(sorted(shared.rows()),[(1,20)]+[(1,100+way) for way in range(255)]+[(3,20),(3,21),(4,21),(4,22)])
        finally:
            shared.close()
            nodes.close()
        self.assertFalse(any((self.directory/name).exists() for name in stream.NODE_FILES[2:]))
        self.assertEqual(nodes.written,8*16)

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

    def test_way_batches_keep_envelopes_empty_ways_and_failures_separate(self):
        root=ET.fromstring(multipolygon_xml())
        # Empty/nonfeature ways and disjoint source geometry must not pollute
        # a neighbouring way's envelope when bounds are reduced together.
        for identity in range(1000,1260):
            way=ET.SubElement(root,"way",id=str(identity))
            if identity%3: ET.SubElement(way,"nd",ref="1")
        xml=ET.tostring(root,encoding="unicode")
        expected=None
        for batch in [1,2,128]:
            with patch.object(stream,"WAY_BATCH_ROWS",batch):
                actual=self.extract(xml)
            if expected is None: expected=actual
            else: self.assertEqual(actual,expected)
        import import_layer
        with patch.object(stream,"WAY_BATCH_BYTES",1): self.assertEqual(self.extract(xml),expected)
        self.assertIn("stream_way_bytes",{e["code"] for e in import_layer.limit_entries()})
        with patch.object(stream,"WAY_PAYLOAD_CEILING",1),self.assertRaisesRegex(ValueError,"buffer byte ceiling"):
            self.extract(xml)
        root.find("way[@id='1259']/nd").set("ref","999999")
        with self.assertRaisesRegex(ValueError,"missing referenced node"):
            self.extract(ET.tostring(root,encoding="unicode"))
        self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))

    def test_ignored_area_ownership_and_partial_structure_source_closure(self):
        xml=XML.replace('</osm>','<relation id="3"><member type="way" ref="1" role="outer"/><tag k="type" v="boundary"/></relation></osm>')
        with self.assertRaisesRegex(ValueError,"area relation"): self.extract(xml)
        box=[9.0004,54.9999,9.0016,55.0001]
        value,_,meta=self.extract(structural_xml(),box)
        clipped,crop_meta=crop(value,box)
        self.assertEqual(len(clipped["features"]),1)
        self.assertEqual(meta["selected"]["ways"],3)  # Both off-window source approaches.
        self.assertEqual(crop_meta["vertical"]["section_endpoints"],2)
        self.assertEqual(clipped,crop(parse(self.source.read_bytes(),"pbf")[0],box)[0])
        # Missing original source approaches remain invalid even outside the box.
        root=ET.fromstring(structural_xml());root.remove(root.find("way[@id='1']"))
        with self.assertRaisesRegex(ValueError,"ground connections"):
            self.extract(ET.tostring(root,encoding="unicode"),box)
        root=ET.fromstring(structural_xml());ET.SubElement(root.find("way[@id='1']"),"tag",k="incline",v="1%")
        with self.assertRaisesRegex(ValueError,"vertical semantics"):
            self.extract(ET.tostring(root,encoding="unicode"),box)

    def test_partial_approach_closure_budget_and_cancellation(self):
        box=[9.0004,54.9999,9.0016,55.0001]
        import import_layer
        with patch.object(stream,"MAX_FEATURES",1): self.extract(structural_xml(),box)
        self.assertIn("stream_closure_features",{e["code"] for e in import_layer.limit_entries()})
        completed_relations=0
        def interrupt(stage,c,t,*unit):
            nonlocal completed_relations
            if stage=="index_relations" and c==t:
                completed_relations+=1
                # End of scan, start of closure, then its first admitted approach.
                if completed_relations==3: raise InterruptedError("closure cancelled")
        with self.assertRaisesRegex(InterruptedError,"closure cancelled"):
            self.extract(structural_xml(),box,interrupt)
        self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
        self.extract(structural_xml(),box)  # A fresh retry preserves the source.

    def test_limits_workspace_and_capture_mutation(self):
        import import_layer
        def codes(): return {e["code"] for e in import_layer.limit_entries()}
        expected=self.extract()[0]
        # Source-work budgets warn and keep the whole selection.
        for name,value,code in [("MAX_SOURCE",1,"stream_source_bytes"),("MAX_SCAN_ENTITIES",1,"stream_scan_entities"),
                                ("MAX_SCAN_REFS",1,"stream_scan_references"),("MAX_ENTITY_REFS",1,"stream_entity_references"),
                                ("MAX_INPUT",1,"stream_selected_bytes"),("MAX_POINTS",1,"osm_nodes"),
                                ("MAX_ENTITIES",1,"stream_selected_entities"),("MAX_FEATURES",1,"osm_features"),
                                ("MAX_REFS",1,"stream_selected_references")]:
            import_layer.reset_limits()
            with self.subTest(name=name),patch.object(stream,name,value):
                self.assertEqual(self.extract()[0],expected)
                self.assertIn(code,codes())
            self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
        # Memory/disk guards still refuse.
        for name,value in [("SOURCE_CEILING",1),("MAX_INDEX",4096),("ENTITY_REFS_CEILING",1)]:
            with self.subTest(name=name),patch.object(stream,name,value),self.assertRaises(ValueError): self.extract()
            self.assertTrue(all(not (self.directory/n).exists() for n in stream.OWNED_FILES))
        import_layer.reset_limits()
        with patch.object(stream.shutil,"disk_usage",return_value=type("Usage",(),{"free":0})()):
            self.extract()  # Low free disk warns; a real out-of-space error fails.
        self.assertIn("stream_free_disk",codes())
        def mutate(stage,c,t,*unit):
            if stage=="read" and c==t:
                with self.source.open("ab") as writer: writer.write(b"changed")
        pbf(self.directory/"untouched.pbf")
        with self.assertRaisesRegex(ValueError,"changed during capture"): self.extract(event=mutate)
        for name in stream.NODE_FILES:
            reserved=self.directory/name;reserved.write_bytes(b"not-owned")
            with self.assertRaisesRegex(ValueError,"workspace"): stream.extract(self.source,BOX,self.directory)
            self.assertEqual(reserved.read_bytes(),b"not-owned")
            reserved.unlink()  # This test owns the reservation fixture.
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
        # A nonreferenced POI's metadata is outside the selected geometry.
        self.extract(XML.replace('v="bench"','v="'+'x'*513+'"'))
        with self.assertRaisesRegex(ValueError,"tag"):
            self.extract(XML.replace('v="residential"','v="'+'x'*513+'"'))
        # An oversized member role marks its relation as tags do; an unselected
        # relation no longer refuses the whole import. Invalid references still do.
        route='<relation id="7"><member type="way" ref="1" role="'+'r'*513+'"/><tag k="type" v="route"/></relation></osm>'
        baseline=self.extract()[0]
        self.assertEqual(self.extract(XML.replace('</osm>',route))[0],baseline)

    def test_explicit_review_excludes_objects_without_flattening_or_guessing(self):
        from osm_review import Review
        root=ET.fromstring(XML)
        ET.SubElement(root.find("way[@id='2']"), "tag", k="bridge", v="yes")
        # Many translated labels on an unreferenced source node are harmless.
        node=root.find("node[@id='11']")
        for index in range(140): ET.SubElement(node,"tag",k=f"name:lang{index}",v="label")
        pbf(self.source,ET.tostring(root,encoding="unicode"))
        with self.assertRaisesRegex(ValueError,"way/2.*ele on every"):
            stream.extract(self.source,BOX,self.directory)
        review=Review(True)
        result,_,_=stream.extract(self.source,BOX,self.directory,review=review)
        self.assertEqual([r["source_id"] for r in review.metadata()["excluded"]],["way/2"])
        self.assertFalse(any(f["geometry"]["type"]=="LineString" for f in result["features"]))
        self.assertEqual(len(result["features"]),2)
        # A typed budget failure stays fatal under review; a plain reason is excluded.
        from import_layer import BudgetExceeded
        with self.assertRaisesRegex(BudgetExceeded,"budget"):
            review.reject("way/3",BudgetExceeded("aggregate reference budget exceeded"))
        review.reject("way/4","unsupported budget-like wording")
        self.assertIn("way/4",[r["source_id"] for r in review.metadata()["excluded"]])

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
