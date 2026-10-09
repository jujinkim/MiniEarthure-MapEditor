"""Industrial source, shared terrain edges and connected service assemblies."""
import io,json,os,sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon,Point
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))
class FactoryWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('machine-factory',KIT)
    def test_reproduction_and_three_connected_courses(self):
        world,meta=build('machine-factory',KIT)
        self.assertEqual(canonical(world.doc),canonical(self.world.doc));self.assertEqual(world.payloads,self.world.payloads);self.assertEqual(meta,self.meta)
        self.assertEqual(meta['size'],[1440,1440]);self.assertEqual(meta['validation']['max_road_grade'],0)
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for r in meta['routes']:
            self.assertLessEqual(len(r['waypoints']),60);self.assertEqual(r['start']['x_cm'],26000);self.assertEqual(r['waypoints'][0]['x_cm'],30000)
    def test_seams_water_and_surface_rings(self):
        grids={}
        for t in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[t['path']])) as im:grids[t['cell']['x'],t['cell']['y']]=np.asarray(im).copy()
        self.assertEqual(len(grids),2025)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        for water in self.world.water:self.assertTrue(water.disjoint(self.world.road_area(1)))
        for a in self.world.doc['surface_areas']:self.assertTrue(Polygon(a['polygon']).is_valid,a['id'])
    def test_pipe_connections_grounding_and_tall_display(self):
        for label in ['production','process','maintenance']:
            pipes=sorted([p for p in self.world.doc['placements'] if p['id'].startswith(label+'-rack-')],key=lambda p:p['position'][0])
            self.assertGreater(len(pipes),8)
            for a,b in zip(pipes,pipes[1:]):self.assertEqual(b['position'][0]-a['position'][0],2400)
            for p in pipes:self.assertEqual(p['position'][1],1200)
        for gate in ['production-gate','production-north-gate','process-gate','power-gate','maintenance-gate','shipping-gate']:
            self.assertTrue(any(a['id'].startswith(gate) for a in self.world.doc['surface_areas']),gate)
        self.assertGreaterEqual(self.meta['display_height_range_m'][1],79)
    def test_functional_groups_and_views(self):
        counts=self.meta['validation']['asset_instances']
        for kind in ['production-0','production-1','production-2','process-tank-0','boiler-bank','factory-stack','pipe-rack','transformer','factory-admin','dock-crane','parked-truck','warehouse-0','port-fence','tank-link','process-feed','electrical-busbar']:
            self.assertGreater(counts.get(kind,0),0,kind)
        self.assertEqual(len(self.meta['review_views']),5)
if __name__=='__main__':unittest.main()
