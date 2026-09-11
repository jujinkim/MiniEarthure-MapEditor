"""L02 quality retention, spatial density, terrain and safe authoring regressions."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import scale_maps as maps


class ScaleMapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town=maps.reference_town()

    def test_quality_geometry_and_assets_are_exact_translations(self):
        doc,payloads,report=maps.make("dense",288,self.town)
        original,roads,assets=maps.quality_template(self.town)
        self.assertEqual(len(original),25)
        self.assertEqual(len(roads),7)
        self.assertEqual(report["building_instances"],96)
        for lot in report["lots"]:
            prefix=lot["id"]+"-"
            dx,dz=lot["bounds_cm"][0]+1600-23800,lot["bounds_cm"][1]+1600-4800
            actual=[]
            for p in doc["placements"]:
                if p["id"].startswith(prefix):
                    q=copy.deepcopy(p)
                    q["id"]=q["id"][len(prefix):]
                    q["position"][0]-=dx;q["position"][2]-=dz
                    actual.append(q)
            self.assertEqual(actual,original)
            translated_roads={r["id"][len(prefix):]:r for r in doc["roads"] if r["id"].startswith(prefix)}
            for road in roads:
                translated=translated_roads[road["id"]]
                self.assertEqual([[p[0]-dx,p[1],p[2]-dz] for p in translated["points"]],road["points"])
                for key in set(road)-{"id","from","to","points"}:
                    self.assertEqual(translated[key],road[key])
        for asset in assets:
            self.assertIn(asset,doc["assets"])
            self.assertEqual(payloads[asset["path"]],self.town.payloads[asset["path"]])
        self.assertEqual(report["transfer"]["preinstalled_common_asset_credit_bytes"],0)

    def test_constant_lot_density_at_two_sizes_and_both_conditions(self):
        lock=json.loads((Path(__file__).parent/"scale_maps.lock.json").read_text())
        for size in [288,1056,2000]:
            for profile in (["dense"] if size==1056 else ["mixed","dense"]):
                doc,payloads,report=maps.make(profile,size,self.town)
                n=report["tiles_per_side"]
                self.assertEqual(report["execution_cells"],(size//16)**2)
                self.assertEqual(report["occupied_lot_area_m2"]+report["outer_margin_area_m2"],size**2)
                expected={"urban":n*n} if profile=="dense" else {k:n*n//4 for k in ["urban","residential","rural","forest"]}
                self.assertEqual(report["lot_counts"],expected)
                self.assertEqual(report["counts"]["placements"],25*n*n if profile=="dense" else 32*n*n//4)
                self.assertLess(report["source_document_bytes"],32*1024*1024)
                self.assertEqual(set(payloads),{a["path"] for a in doc["assets"]}|{h["path"] for h in doc["heightmaps"]})
                self.assertEqual({k:report[k] for k in lock[f"{profile}-{size}"]},lock[f"{profile}-{size}"])

    def test_connected_graph_structure_and_bounded_source(self):
        doc,_,report=maps.make("mixed",288,self.town)
        nodes={n["id"]:n["position"] for n in doc["nodes"]}
        self.assertEqual(len(nodes),len(doc["nodes"]))
        for r in doc["roads"]:
            self.assertEqual(nodes[r["from"]],r["points"][0])
            self.assertEqual(nodes[r["to"]],r["points"][-1])
            for x,h,z in r["points"]:self.assertTrue(0<=x<=28800 and 0<=z<=28800)
        adjacency={key:set() for key in nodes}
        for r in doc["roads"]:
            adjacency[r["from"]].add(r["to"]);adjacency[r["to"]].add(r["from"])
        start=next(r["from"] for r in doc["roads"] if r["id"].startswith("grid-"))
        seen=set();todo=[start]
        while todo:
            current=todo.pop()
            if current not in seen:seen.add(current);todo.extend(adjacency[current]-seen)
        for r in doc["roads"]:
            if r["id"]!="speed-bridge":self.assertIn(r["from"],seen);self.assertIn(r["to"],seen)
        bridge=next(r for r in doc["roads"] if r["id"]=="speed-bridge")
        self.assertEqual(max(p[1] for p in bridge["points"]),300)
        self.assertEqual(bridge["kind"],"bridge")
        self.assertEqual(report["terrain"]["spacing_m"],4)

    def test_terrain_crc_full_grid_and_implicit_flat_seams(self):
        png=maps.hill_png();pos=8;compressed=b""
        while pos<len(png):
            size=struct.unpack(">I",png[pos:pos+4])[0]
            kind=png[pos+4:pos+8];data=png[pos+8:pos+8+size]
            self.assertEqual(zlib.crc32(kind+data),struct.unpack(">I",png[pos+8+size:pos+12+size])[0])
            if kind==b"IDAT":compressed+=data
            pos+=12+size
        raw=zlib.decompress(compressed)
        rows=[struct.unpack(">5H",raw[i*11+1:i*11+11]) for i in range(5)]
        self.assertEqual(rows[2][2],200)
        self.assertTrue(all(v==0 for v in rows[0]+rows[-1]))
        self.assertTrue(all(row[0]==row[-1]==0 for row in rows))

    def test_new_destination_only_and_invalid_arguments(self):
        for size in [0,128,2001,10016]:
            with self.assertRaises(ValueError):maps.make("mixed",size,self.town)
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"source"
            report=maps.create(dest,"mixed",288)
            original={str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob("*") if p.is_file()}
            with self.assertRaises(FileExistsError):maps.create(dest,"dense",2000)
            self.assertEqual(original,{str(p.relative_to(dest)):p.read_bytes() for p in dest.rglob("*") if p.is_file()})
            self.assertEqual(json.loads(original["scale.json"]),report)
            for name,digest in report["source_hashes"].items():self.assertEqual(maps.sha(original[name]),digest)


if __name__=="__main__":unittest.main()
