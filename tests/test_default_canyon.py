"""Canyon authoring safety and deterministic source contracts, not art scoring."""
import io,json,os,sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
class CanyonWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('red-canyon',KIT)
    def test_reproduction_routes_and_grid(self):
        world,meta=build('red-canyon',KIT)
        self.assertEqual(canonical(world.doc),canonical(self.world.doc));self.assertEqual(world.payloads,self.world.payloads);self.assertEqual(meta,self.meta)
        self.assertEqual(meta['size'],[2400,1200]);self.assertLessEqual(meta['validation']['max_road_grade'],.12)
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for r in meta['routes']:
            self.assertLessEqual(len(r['waypoints']),60);self.assertEqual(r['start']['x_cm'],24000);self.assertEqual(r['waypoints'][0]['x_cm'],28000)
    def test_all_cell_seams_and_geological_relief(self):
        grids={}
        for tile in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[tile['path']])) as im:grids[tile['cell']['x'],tile['cell']['y']]=np.asarray(im).copy()
        self.assertEqual(len(grids),2850)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        self.assertGreater(self.meta['relief'],90);self.assertFalse(self.world.water)
        for a in self.world.doc['surface_areas']:
            self.assertTrue(Polygon(a['polygon']).is_valid,a['id'])
            self.assertTrue(all(0<=x<=240000 and 0<=y<=120000 for x,y in a['polygon']),a['id'])
    def test_bridge_grounding_and_aprons(self):
        roads={r['id']:r for r in self.world.doc['roads']}
        for name in ['west-bridge-apron','north-bridge-apron','east-bridge-apron','south-bridge-apron']:
            self.assertTrue(all(p[1]==6000 for p in roads[name]['points']),name)
        for name in ['west-canyon-bridge','east-canyon-bridge']:
            line=self.world.routes[name]
            for distance in np.arange(24,line.length-24,8):
                p=line.interpolate(distance)
                self.assertLess(float(self.world.height(p.x,p.y)),58,name)
        piers=[p for p in self.world.doc['placements'] if p['asset_id']=='authored-canyon-pier'];self.assertEqual(len(piers),8)
        for p in piers:
            x,z,y=[v/100 for v in p['position']];self.assertAlmostEqual(z+44.8,59.8);self.assertLessEqual(z,float(self.world.height(x,y))+1)
    def test_distinct_scenery_and_capture_coverage(self):
        for kind in ['sandstone-0','sandstone-1','sandstone-2','canyon-rubble','desert-scrub','cactus','quarry-crusher','quarry-loader','quarry-office','quarry-conveyor']:
            self.assertGreater(self.meta['validation']['asset_instances'].get(kind,0),0,kind)
        self.assertEqual(len(self.meta['review_views']),5)
        self.assertTrue(set(self.meta['menu_views'].values())<=set(v['name'] for v in self.meta['review_views']))
if __name__=='__main__':unittest.main()
