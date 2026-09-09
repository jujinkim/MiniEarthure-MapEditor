"""Frozen synthetic profile, terrain seams and safe fixture publication."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("reference_maps",ROOT/"scripts/reference_maps.py")
reference=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)

class ReferenceMapsTests(unittest.TestCase):
    def test_frozen_sources_and_metrics(self):
        expected=json.loads((ROOT/"tests/reference_maps.lock.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            result=reference.create(Path(tmp)/"maps")
            for name,entry in result.items():
                self.assertEqual(entry,{k:v for k,v in expected[name].items() if k not in ("inspection","capacity","generated_cells")})
                for path,digest in entry["source_files"].items():
                    self.assertEqual(hashlib.sha256((Path(tmp)/"maps"/name/path).read_bytes()).hexdigest(),digest)
            self.assertEqual(result["baseline"]["counts"]["buildings"],700)
            self.assertEqual(result["baseline"]["road_centerline_planar_m"],420000)
            self.assertEqual(result["baseline"]["cell_count"],400)

    def test_refuse_existing_output_and_preserve_every_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"maps"
            reference.create(out)
            before={str(p.relative_to(out)):p.read_bytes() for p in out.rglob("*") if p.is_file()}
            with self.assertRaises(FileExistsError): reference.create(out)
            self.assertEqual(before,{str(p.relative_to(out)):p.read_bytes() for p in out.rglob("*") if p.is_file()})

    def test_full_png16_edges_and_known_peak(self):
        for hill in (False,True):
            png=reference.terrain_png(hill)
            offset=8
            data=b""
            while offset<len(png):
                length=struct.unpack(">I",png[offset:offset+4])[0]
                kind=png[offset+4:offset+8]
                payload=png[offset+8:offset+8+length]
                self.assertEqual(zlib.crc32(kind+payload),struct.unpack(">I",png[offset+8+length:offset+12+length])[0])
                if kind==b"IHDR": self.assertEqual(struct.unpack(">IIBBBBB",payload),(257,257,16,0,0,0,0))
                if kind==b"IDAT": data+=payload
                offset+=12+length
            raw=zlib.decompress(data)
            self.assertEqual(len(raw),257*515)
            rows=[]
            for y in range(257):
                self.assertEqual(raw[y*515],0)
                rows.append(struct.unpack(">257H",raw[y*515+1:(y+1)*515]))
            self.assertTrue(all(v==0 for v in rows[0]+rows[-1]))
            self.assertTrue(all(row[0]==row[-1]==0 for row in rows))
            self.assertEqual(rows[128][128],1280 if hill else 0)

    def test_routes_and_distinct_grade_graph(self):
        doc,_,_=reference.baseline()
        nodes={n["id"]:n["position"] for n in doc["nodes"]}
        self.assertEqual(len(nodes),441)
        for road in doc["roads"]:
            self.assertEqual(nodes[road["from"]],road["points"][0])
            self.assertEqual(nodes[road["to"]],road["points"][-1])
        structure,_,_=reference.structures()
        self.assertEqual({r["kind"] for r in structure["roads"]},{"ground","bridge","elevated","underpass","tunnel"})
        self.assertEqual(len({n["id"] for n in structure["nodes"]}),len(structure["nodes"]))

if __name__=="__main__": unittest.main()
