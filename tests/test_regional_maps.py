import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from regional_maps import PLANS,build,canonical,sha
MAPKIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
LIBRARY=MAPKIT/'examples/regional-library'
CLI=MAPKIT/'target/debug/mapkit'
SOURCES=ROOT/'examples/regional-miniatures'

class RegionalMaps(unittest.TestCase):
    def test_sources_packages_and_terrain_seams(self):
        fingerprints=set()
        for plan in PLANS:
            with self.subTest(region=plan['id']):
                doc,payloads,meta=build(plan,LIBRARY)
                folder=SOURCES/plan['id']
                self.assertEqual((folder/'document.json').read_bytes(),canonical(doc))
                self.assertEqual((folder/'region.json').read_bytes(),canonical(meta))
                self.assertEqual(doc['cell_size_cm'],1600)
                w,h=plan['size'];self.assertTrue(110_000<=w*h<=115_000)
                self.assertGreaterEqual(len(meta['districts']),4)
                self.assertGreaterEqual(len(meta['landmarks']),3)
                self.assertEqual([r['laps'] for r in meta['routes']],[2,2,1])
                self.assertEqual(len({tuple((p['x_cm'],p['y_cm']) for p in r['waypoints']) for r in meta['routes']}),3)
                fingerprints.add(sha(canonical([r['points'] for r in doc['roads']])))
                # Every declared road belongs to one connected authored graph.
                links={n['id']:set() for n in doc['nodes']}
                for r in doc['roads']:links[r['from']].add(r['to']);links[r['to']].add(r['from'])
                seen=set();todo=[next(iter(links))]
                while todo:
                    n=todo.pop()
                    if n in seen:continue
                    seen.add(n);todo.extend(links[n]-seen)
                self.assertEqual(seen,set(links))
                grids={}
                for hm in doc['heightmaps']:
                    cell=(hm['cell']['x'],hm['cell']['y'])
                    with Image.open(folder/hm['path']) as image:grids[cell]=list(image.getdata())
                for (x,y),values in grids.items():
                    if (x+1,y) in grids:self.assertEqual(values[8::9],grids[x+1,y][0::9])
                    if (x,y+1) in grids:self.assertEqual(values[-9:],grids[x,y+1][:9])
                for path,data in payloads.items():self.assertEqual((folder/path).read_bytes(),data,path)
                with tempfile.TemporaryDirectory() as temp:
                    package=Path(temp)/'map.memap'
                    run=subprocess.run([str(CLI),'pack',str(folder),str(package)],capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stderr)
                    self.assertEqual(package.read_bytes(),folder.with_suffix('.memap').read_bytes())
                    result=subprocess.run([str(CLI),'validate-cells',str(package)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(fingerprints),7)

if __name__=='__main__':unittest.main()
