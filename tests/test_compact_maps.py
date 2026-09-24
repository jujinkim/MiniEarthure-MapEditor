"""Focused compact content acceptance, using preserved sources and public MapKit."""
import collections,hashlib,importlib.util,json,math,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import compact_maps
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT.parent/'map-kit'))
SIZES={'haeon':[512,512],'belmont':[640,448],'nord':[704,320],'safra':[448,448],'red-wadi':[704,384],'kanupi':[640,448],'bansai':[576,384]}

class CompactMaps(unittest.TestCase):
 def test_preserved_source_topology_density_and_routes(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)
   for ident,size in SIZES.items():
    with self.subTest(map=ident):
     # These artifacts are historical. Current public ramp/tree authoring
     # intentionally changed; preserve the old bytes instead of re-authoring
     # them through a historical algorithm or overwriting the originals.
     folder=ROOT/'examples/compact-driving'/ident
     meta=json.loads((folder/'region.json').read_text())
     doc=json.loads((folder/'document.json').read_text())
     self.assertEqual(meta['size'],size)
     self.assertGreaterEqual(len(meta['challenges']),12)
     self.assertEqual(len({c['district'] for c in meta['challenges']}),4)
     self.assertGreaterEqual(len({c['kind'] for c in meta['challenges']}),3)
     self.assertGreaterEqual(sum(g['motion']['kind']!='static' for g in doc['gimmicks']),2)
     self.assertTrue(all(c['bypass_width_cm']>=140 for c in meta['challenges']))
     # Junctions terminate each straight. Only explicitly authored acceleration
     # sections may exceed 80m between a challenge and the next road decision.
     main={ident for route in meta['routes'] for ident in route['road_path']}
     exceptions={item['road_id'] for item in meta['acceleration_sections']}
     for road in doc['roads']:
      if road['id'] not in main:continue
      a,b=road['points'][0],road['points'][-1];length=math.dist(a,b)
      marks=sorted(sum((c['position_cm'][i]-a[i])*(b[i]-a[i]) for i in range(3))/length/100 for c in meta['challenges'] if c['road_id']==road['id'])
      distances=[0]+marks+[length/100]
      for start,end in zip(distances,distances[1:]):
       self.assertTrue(end-start<=80 or road['id'] in exceptions,(ident,road['id'],end-start))
     for r,limits in zip(meta['routes'],[(350,600),(500,900),(600,1000)]):
      self.assertTrue(limits[0]<=r['length_m']<=limits[1])
      self.assertGreater(len(r['waypoints']),5)
     graph=collections.defaultdict(set)
     for r in doc['roads']:graph[r['from']].add(r['to']);graph[r['to']].add(r['from'])
     seen=set();stack=[next(iter(graph))]
     while stack:
      n=stack.pop()
      if n not in seen:seen.add(n);stack.extend(graph[n]-seen)
     self.assertEqual(set(graph),seen)
     grids={ (h['cell']['x'],h['cell']['y']):Image.open(folder/h['path']).copy() for h in doc['heightmaps']}
     for (x,y),grid in grids.items():
      if (x+1,y) in grids:self.assertEqual([grid.getpixel((8,i)) for i in range(9)],[grids[x+1,y].getpixel((0,i)) for i in range(9)])
      if (x,y+1) in grids:self.assertEqual([grid.getpixel((i,8)) for i in range(9)],[grids[x,y+1].getpixel((i,0)) for i in range(9)])
     for path,hash in meta['source_files'].items():self.assertEqual(hashlib.sha256((folder/path).read_bytes()).hexdigest(),hash)
     result=subprocess.run([str(KIT/'target/debug/mapkit'),'pack',str(folder),str(out/(ident+'.memap'))],capture_output=True,text=True)
     self.assertEqual(result.returncode,0,result.stderr)
     self.assertEqual((out/(ident+'.memap')).read_bytes(),(ROOT/'examples/compact-driving'/(ident+'.memap')).read_bytes())

if __name__=='__main__':unittest.main()
