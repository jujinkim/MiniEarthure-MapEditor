"""New authoring is deterministic; historical sources are never rewritten."""
import collections, hashlib, json, math, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from miniature_streets import build, IDS
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
SIZES=[[256,256],[320,224],[352,160],[224,224],[352,192],[320,224],[288,192]]

class MiniatureStreets(unittest.TestCase):
 def test_sources_packages_and_driving_geometry(self):
  with tempfile.TemporaryDirectory() as temp:
   destination=Path(temp)
   for ident,size in zip(IDS,SIZES):
    with self.subTest(map=ident):
     original=ROOT/'examples/compact-driving'/ident
     before={str(p.relative_to(original)):hashlib.sha256(p.read_bytes()).hexdigest() for p in original.rglob('*') if p.is_file() and not p.name.endswith('.import')}
     meta=build(original,destination,KIT)
     folder=destination/ident;stored=ROOT/'examples/miniature-streets'/ident
     self.assertEqual(meta,json.loads((stored/'region.json').read_text()))
     doc=json.loads((folder/'document.json').read_text())
     self.assertEqual(doc,json.loads((stored/'document.json').read_text()))
     self.assertEqual(meta['size'],size);self.assertEqual(len(meta['district_records']),4)
     self.assertGreaterEqual(meta['street_infill_count'],30)
     for relative,sha in meta['source_files'].items():
      self.assertEqual(hashlib.sha256((folder/relative).read_bytes()).hexdigest(),sha)
      self.assertEqual((folder/relative).read_bytes(),(stored/relative).read_bytes())
     roads={r['id']:r for r in doc['roads']};nodes={n['id']:n for n in doc['nodes']}
     graph=collections.defaultdict(set)
     for r in roads.values():
      self.assertGreaterEqual(min(r['widths_cm']),280)
      self.assertEqual(r['points'][0],nodes[r['from']]['position'])
      self.assertEqual(r['points'][-1],nodes[r['to']]['position'])
      graph[r['from']].add(r['to']);graph[r['to']].add(r['from'])
     seen=set();pending=[next(iter(graph))]
     while pending:
      node=pending.pop()
      if node not in seen:seen.add(node);pending.extend(graph[node]-seen)
     self.assertEqual(seen,set(graph))
     for route,limits in zip(meta['routes'],[(175,300),(250,450),(300,500)]):
      self.assertTrue(limits[0]<=route['length_m']<=limits[1])
      self.assertEqual(route['checkpoint_radius_cm'],300)
      for first,last in zip(route['road_path'],route['road_path'][1:]):
       self.assertTrue({roads[first]['from'],roads[first]['to']} & {roads[last]['from'],roads[last]['to']},(ident,first,last))
     self.assertGreaterEqual(len(meta['bridges']),2)
     for bridge in meta['bridges']:
      self.assertGreaterEqual(bridge['clearance_cm'],260)
      self.assertLess(bridge['approach_grade'],math.tan(math.radians(20)))
      r=roads[bridge['road_id']]
      self.assertEqual(r['points'][0][1],r['points'][1][1])
      self.assertEqual(r['points'][-1][1],r['points'][-2][1])
     under=meta['underpass'];self.assertGreaterEqual(under['clearance_cm'],240)
     self.assertEqual(roads[under['road_id']]['kind'],'underpass')
     public=set(meta['routes'][0]['road_path'])|set(meta['routes'][2]['road_path'])
     for challenge in meta['challenges']:
      self.assertGreaterEqual(challenge['bypass_width_cm'],140)
      self.assertNotIn(challenge['road_id'],public)
     grids={}
     for h in doc['heightmaps']:
      im=Image.open(folder/h['path']);grids[h['cell']['x'],h['cell']['y']]=[[im.getpixel((x,y))*h['step_cm']+h['offset_cm'] for x in range(9)] for y in range(9)]
     for (x,y),grid in grids.items():
      if (x+1,y) in grids:self.assertEqual([row[8] for row in grid],[row[0] for row in grids[x+1,y]])
      if (x,y+1) in grids:self.assertEqual(grid[8],grids[x,y+1][0])
     result=subprocess.run([str(KIT/'target/debug/mapkit'),'pack',str(folder),str(destination/(ident+'.memap'))],capture_output=True,text=True)
     self.assertEqual(result.returncode,0,result.stderr)
     self.assertEqual((destination/(ident+'.memap')).read_bytes(),(ROOT/'examples/miniature-streets'/(ident+'.memap')).read_bytes())
     self.assertEqual(before,{str(p.relative_to(original)):hashlib.sha256(p.read_bytes()).hexdigest() for p in original.rglob('*') if p.is_file() and not p.name.endswith('.import')})

if __name__=='__main__':unittest.main()
