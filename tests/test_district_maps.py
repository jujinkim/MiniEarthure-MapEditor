import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from district_maps import BUILDERS
MAPKIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
SOURCES=ROOT/'examples/regional-districts'

class DistrictMaps(unittest.TestCase):
    def test_sources_seams_connections_and_district_density(self):
        layouts=set()
        with tempfile.TemporaryDirectory() as work:
            for ident,build in BUILDERS.items():
                with self.subTest(region=ident):
                    region=build(MAPKIT/'examples/district-library');meta=region.finish(work)
                    source=SOURCES/ident;rebuilt=Path(work)/ident
                    expected={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
                    actual={str(p.relative_to(rebuilt)):p.read_bytes() for p in rebuilt.rglob('*') if p.is_file()}
                    self.assertEqual(expected.keys(),actual.keys())
                    for key in expected:self.assertEqual(hashlib.sha256(expected[key]).digest(),hashlib.sha256(actual[key]).digest(),key)
                    doc=region.doc
                    self.assertEqual(doc['cell_size_cm'],1600)
                    self.assertEqual(len(meta['districts']),4);self.assertEqual(len(meta['landmarks']),3)
                    self.assertEqual([r['laps'] for r in meta['routes']],[2,2,1])
                    self.assertEqual(len({tuple(r['road_path']) for r in meta['routes']}),3)
                    # Preserved historical sources; current default course ranges are
                    # validated by test_compact_maps, separately per course kind.
                    self.assertTrue(all(r['length_m']>0 for r in meta['routes']))
                    # Connectivity checks include true elevated node identities.
                    links={n['id']:set() for n in doc['nodes']}
                    for road in doc['roads']:links[road['from']].add(road['to']);links[road['to']].add(road['from'])
                    seen=set();todo=[next(iter(links))]
                    while todo:
                        p=todo.pop()
                        if p in seen:continue
                        seen.add(p);todo.extend(links[p]-seen)
                    self.assertEqual(seen,set(links))
                    layouts.add(json.dumps([r['points'] for r in doc['roads']]))
                    grids={}
                    for hm in doc['heightmaps']:
                        with Image.open(source/hm['path']) as image:grids[hm['cell']['x'],hm['cell']['y']]=list(image.getdata())
                    for (x,y),values in grids.items():
                        if (x+1,y) in grids:self.assertEqual(values[8::9],grids[x+1,y][0::9])
                        if (x,y+1) in grids:self.assertEqual(values[-9:],grids[x,y+1][:9])
                    if ident=='haeon':
                        counts=Counter(p['asset_id'].rsplit('-',1)[0] for p in doc['placements'])
                        self.assertGreaterEqual(counts['district-civic-tower'],20)
                        self.assertGreaterEqual(counts['district-streetwall'],90)
                        self.assertGreaterEqual(counts['district-apartment'],20)
                        self.assertGreaterEqual(sum(r['sidewalk_cm']>=120 for r in doc['roads']),60)
                        self.assertGreaterEqual(sum(p['asset_id']=='district-street-lamp' for p in doc['placements']),15)
                    package=Path(work)/(ident+'.memap')
                    result=subprocess.run([str(MAPKIT/'target/debug/mapkit'),'pack',str(rebuilt),str(package)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(package.read_bytes(),source.with_suffix('.memap').read_bytes())
        self.assertEqual(len(layouts),7)

if __name__=='__main__':unittest.main()
