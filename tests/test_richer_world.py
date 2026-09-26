"""Focused authoring regressions; no driving, completion or release acceptance."""
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
KIT=ROOT.parent/'map-kit'
sys.path[:0]=[str(ROOT/'scripts'),str(KIT/'scripts')]
from richer_world import build, SPECS, Region

def hashes(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and p.suffix!='.import' and p.name!='.DS_Store'}

class RicherWorld(unittest.TestCase):
    def test_reproduction_and_original_preservation(self):
        source=ROOT/'examples/richer-world'
        before=hashes(ROOT/'examples/special-driving')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new';build(target,KIT)
            for ident in SPECS:
                self.assertEqual(hashes(source/ident),hashes(target/ident),ident)
            with self.assertRaises(FileExistsError):build(target,KIT)
        self.assertEqual(before,hashes(ROOT/'examples/special-driving'))

    def test_routes_terrain_and_parcels(self):
        for ident,spec in SPECS.items():
            with self.subTest(map=ident):
                folder=ROOT/'examples/richer-world'/ident
                doc=json.loads((folder/'document.json').read_text());meta=json.loads((folder/'region.json').read_text())
                self.assertEqual(doc['bounds']['max'],[v*100 for v in spec['size']])
                self.assertEqual(doc['recipe_version'],1)
                self.assertEqual(doc['courses'],[])
                self.assertEqual(len(meta['routes']),3)
                roads={r['id']:r for r in doc['roads']};nodes={n['id'] for n in doc['nodes']}
                neighbours={n:set() for n in nodes}
                for r in roads.values():
                    neighbours[r['from']].add(r['to']);neighbours[r['to']].add(r['from'])
                    self.assertGreaterEqual(min(r['widths_cm']),280)
                visited=set();todo=[next(iter(nodes))]
                while todo:
                    n=todo.pop()
                    if n in visited:continue
                    visited.add(n);todo.extend(neighbours[n]-visited)
                self.assertEqual(visited,nodes,'every exploration branch connects')
                for route,limits in zip(meta['routes'],[(175,300),(250,450),(300,500)]):
                    self.assertTrue(limits[0]<=route['length_m']<=limits[1],route)
                    self.assertEqual(route['start']['surface_id'],'main-0')
                    for a,b in zip(route['road_path'],route['road_path'][1:]):
                        self.assertEqual(roads[a]['to'],roads[b]['from'],(route['id'],a,b))
                for g in meta['challenges']:self.assertGreaterEqual(g['bypass_width_cm'],140)
                heights={}
                for h in doc['heightmaps']:
                    self.assertEqual(h['spacing_cm'],200)
                    with Image.open(folder/h['path']) as image:
                        self.assertEqual(image.size,(9,9));pixels=list(image.getdata())
                    heights[h['cell']['x'],h['cell']['y']]=[v*h['step_cm']+h['offset_cm'] for v in pixels]
                for (x,z),h in heights.items():
                    if (x+1,z) in heights:self.assertEqual(h[8::9],heights[x+1,z][0::9])
                    if (x,z+1) in heights:self.assertEqual(h[-9:],heights[x,z+1][:9])
                authored=Region(ident,KIT)
                x,z,rx,rz=spec['pond'];self.assertLess(authored.natural(x,z),authored.water_level(x,z)-.8)
                self.assertGreater(len(meta['parcels']),20)
                self.assertGreater(len({round(p['rx'],1) for p in meta['parcels']}),3)
                for p in meta['parcels']:self.assertIn(p['road'],roads)
                for path,expected in meta['source_files'].items():self.assertEqual(hashlib.sha256((folder/path).read_bytes()).hexdigest(),expected)

if __name__=='__main__':unittest.main()
