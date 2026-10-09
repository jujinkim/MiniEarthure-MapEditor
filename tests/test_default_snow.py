"""Alpine source reproduction, terrain seams, courses and structure safety."""
import io,json,os,sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Point,Polygon
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
class SnowWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('snow-mountain',KIT)
    def test_reproduction_and_routes(self):
        world,meta=build('snow-mountain',KIT)
        self.assertEqual(canonical(world.doc),canonical(self.world.doc));self.assertEqual(world.payloads,self.world.payloads);self.assertEqual(meta,self.meta)
        self.assertEqual(meta['size'],[1600,2080]);self.assertLessEqual(meta['validation']['max_road_grade'],.12)
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for r in meta['routes']:
            self.assertLessEqual(len(r['waypoints']),60);self.assertEqual(r['start']['x_cm'],35000);self.assertEqual(r['waypoints'][0]['x_cm'],39000)
    def test_all_seams_and_relief(self):
        grids={}
        for t in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[t['path']])) as im:grids[t['cell']['x'],t['cell']['y']]=np.asarray(im).copy()
        self.assertEqual(len(grids),3250)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        self.assertGreater(self.meta['relief'],200)
        for a in self.world.doc['surface_areas']:self.assertTrue(Polygon(a['polygon']).is_valid,a['id'])
    def test_frozen_tarn_and_gallery(self):
        lake=next(p for p in self.world.doc['placements'] if p['id']=='frozen-tarn')
        asset=next(a for a in self.world.doc['assets'] if a['id']==lake['asset_id'])
        self.assertLessEqual(len(asset['convex_collision'][0]['vertices']),32)
        self.assertEqual(max(v[1] for v in asset['convex_collision'][0]['vertices'])+lake['position'][1],9300)
        self.assertLess(float(self.world.height(946,1280)),92.8)
        gallery=next(p for p in self.world.doc['placements'] if p['id']=='summit-shelter')
        x,z,y=[v/100 for v in gallery['position']]
        self.assertGreater(self.world.routes['summit-ridge'].distance(Point(x,y)),20)
        self.assertAlmostEqual(z,float(self.world.height(x,y)),delta=.02)
    def test_altitude_zones_and_captures(self):
        trees=[p for p in self.world.doc['placements'] if p['asset_id'].startswith('authored-snow-fir')]
        self.assertGreater(len([p for p in trees if p['position'][2]>130000]),len([p for p in trees if p['position'][2]<80000])*3)
        for kind in ['alpine-lodge-0','alpine-lodge-1','alpine-crag-0','alpine-crag-1','snowbank','alpine-rail','snow-gallery']:
            self.assertGreater(self.meta['validation']['asset_instances'].get(kind,0),0,kind)
        self.assertEqual(len(self.meta['review_views']),5)
if __name__=='__main__':unittest.main()
