"""Park source reproduction, terrain seams and supported skyway clearance."""
import io,json,os,sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
class ParkWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('sky-park',KIT)
    def test_reproduction_and_connected_routes(self):
        world,meta=build('sky-park',KIT)
        self.assertEqual(canonical(world.doc),canonical(self.world.doc));self.assertEqual(world.payloads,self.world.payloads);self.assertEqual(meta,self.meta)
        self.assertEqual(meta['size'],[1920,1600]);self.assertLessEqual(meta['validation']['max_road_grade'],.12)
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for r in meta['routes']:
            self.assertLessEqual(len(r['waypoints']),60);self.assertEqual(r['start']['x_cm'],31000);self.assertEqual(r['waypoints'][0]['x_cm'],35000)
    def test_all_cell_seams_and_surface_rings(self):
        grids={}
        for t in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[t['path']])) as im:grids[t['cell']['x'],t['cell']['y']]=np.asarray(im).copy()
        self.assertEqual(len(grids),3000)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        self.assertGreater(self.meta['relief'],70)
        for a in self.world.doc['surface_areas']:self.assertTrue(Polygon(a['polygon']).is_valid,a['id'])
    def test_bridge_grounding_and_level_aprons(self):
        roads={r['id']:r for r in self.world.doc['roads']}
        for name,z in [('central-skyway',70),('northern-skyway',88)]:
            line=self.world.routes[name]
            self.assertTrue(all(p[1]==z*100 for p in roads[name]['points']))
            for s in np.arange(24,line.length-24,8):
                p=line.interpolate(s);self.assertLess(float(self.world.height(p.x,p.y)),z-2,name)
        for name,end,z in [('west-sky-approach',-1,70),('wheel-promenade',0,70),('west-garden-descent',0,88)]:
            ps=roads[name]['points'];section=ps[-3:] if end==-1 else ps[:3]
            self.assertTrue(all(p[1]==z*100 for p in section),name)
        piers=[p for p in self.world.doc['placements'] if p['asset_id'].startswith('authored-sky-pier-')];self.assertEqual(len(piers),10)
        for p in piers:
            x,z,y=[v/100 for v in p['position']];height=59.8 if p['asset_id'].endswith('low') else 77.8
            self.assertAlmostEqual(z+height,(70 if y==800 else 88)-.2)
            self.assertLessEqual(z,float(self.world.height(x,y)))
    def test_facility_groups_and_high_silhouette_coverage(self):
        for name in ['observation-wheel','carousel','decorative-coaster','park-kiosk-0','park-kiosk-1','park-kiosk-2','queue-rail','flowerbed']:
            self.assertGreater(self.meta['validation']['asset_instances'].get(name,0),0,name)
        self.assertGreaterEqual(self.meta['display_height_range_m'][1],130)
        self.assertEqual(len(self.meta['review_views']),6)
        self.assertTrue(set(self.meta['menu_views'].values())<=set(v['name'] for v in self.meta['review_views']))
if __name__=='__main__':unittest.main()
