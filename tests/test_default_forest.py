"""Synthetic forest authoring contracts; art acceptance remains a render review."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image
from shapely.geometry import Polygon,Point

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))

class ForestWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('deep-forest',KIT)

    def test_reproducible_graph_and_courses(self):
        other,meta=build('deep-forest',KIT)
        self.assertEqual(canonical(self.world.doc),canonical(other.doc))
        self.assertEqual(self.world.payloads,other.payloads);self.assertEqual(self.meta,meta)
        self.assertEqual(meta['size'],[1760,1760]);self.assertTrue(meta['validation']['road_graph_connected'])
        self.assertLessEqual(meta['validation']['max_road_grade'],.12)
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for route in meta['routes']:
            self.assertLessEqual(len(route['waypoints']),60)
            self.assertEqual(route['start']['x_cm'],31000)
            self.assertEqual(route['waypoints'][0]['x_cm'],35000)

    def test_all_seams_and_water_road_clearance(self):
        grids={}
        for tile in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[tile['path']])) as bitmap:
                grids[(tile['cell']['x'],tile['cell']['y'])]=np.asarray(bitmap).copy()
        self.assertEqual(len(grids),3025)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        for water in self.world.water:
            for road in self.world.doc['roads']:
                if road['kind']=='ground':self.assertTrue(water.disjoint(self.world.routes[road['id']].buffer(road['widths_cm'][0]/200+.5)),road['id'])
        self.assertGreater(self.meta['relief'],75)

    def test_bridge_support_and_flat_aprons(self):
        roads={r['id']:r for r in self.world.doc['roads']}
        for name,end,z in [('south-gorge-approach',-1,3600),('east-gorge-approach',0,3600),('north-gorge-approach',-1,4000),('beech-crest',0,4000)]:
            points=roads[name]['points'];segment=points[:2] if end==0 else points[-2:]
            self.assertEqual([p[1] for p in segment],[z,z],name)
        piers=[p for p in self.world.doc['placements'] if p['asset_id']=='authored-forest-pier']
        self.assertEqual(len(piers),8)
        for pier in piers:
            deck=3600 if pier['id'].startswith('south') else 4000
            self.assertEqual(pier['position'][1]+2480,deck-20)
            x,z,y=[v/100 for v in pier['position']]
            self.assertLessEqual(z,float(self.world.height(x,y))+1)

    def test_landscape_layers_and_review_coverage(self):
        counts=self.meta['validation']['asset_instances']
        for kind in ['cedar-0','cedar-1','cedar-2','beech','sapling-0','sapling-1','fern-patch','shrub','fallen-cedar','ranger-lodge','camp-tent','picnic-shelter']:
            self.assertGreater(counts.get(kind,0),0,kind)
        self.assertEqual(len(self.meta['review_views']),5)
        self.assertTrue(set(self.meta['menu_views'].values())<=set(v['name'] for v in self.meta['review_views']))
        for area in self.world.doc['surface_areas']:self.assertTrue(Polygon(area['polygon']).is_valid,area['id'])
        self.assertGreater(self.meta['display_height_range_m'][1],100)
        for placement in self.world.doc['placements']:
            if any(name in placement['asset_id'] for name in ['cedar-','beech','sapling','shrub']):
                p=placement['position']
                for water in self.world.water:
                    self.assertFalse(water.contains(Point(p[0]/100,p[2]/100)),placement['id'])

if __name__=='__main__':unittest.main()
