"""Authored-world contracts, using original synthetic assets and isolated data."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,publish,THEMES,canonical

KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))

class DefaultWorlds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('village',KIT)

    def test_reproducible_fresh_layout_and_preserved_dimensions(self):
        other,meta=build('village',KIT)
        self.assertEqual(canonical(self.world.doc),canonical(other.doc))
        self.assertEqual(self.world.payloads,other.payloads)
        self.assertEqual(self.meta,meta)
        self.assertEqual(list(THEMES.values()),[(1120,960),(1920,1280),(1760,1760),(2400,1200),(1600,2080),(1440,1440),(1920,1600)])
        self.assertTrue(self.world.doc['map_id'].startswith('default-village-authored-'))
        self.assertEqual(self.world.doc['cell_size_cm'],3200)
        self.assertTrue(self.meta['validation']['road_graph_connected'])
        self.assertLessEqual(self.meta['validation']['max_road_grade'],.12)
        self.assertEqual(len({p['id'] for p in self.world.doc['placements']}),len(self.world.doc['placements']))

    def test_all_terrain_borders_share_integer_samples(self):
        grids={}
        for tile in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[tile['path']])) as image:
                self.assertEqual(image.size,(17,17))
                grids[(tile['cell']['x'],tile['cell']['y'])]=np.asarray(image).copy()
        self.assertEqual(len(grids),1050)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])

    def test_water_stays_clear_of_ground_roads_and_bridge_is_supported(self):
        for body in self.world.doc['water_bodies']:
            water=Polygon([(x/100,y/100) for x,y in body['polygon']])
            for road in self.world.doc['roads']:
                if road['kind']!='ground':continue
                travelled=self.world.routes[road['id']].buffer(road['widths_cm'][0]/200+.5)
                self.assertTrue(water.disjoint(travelled),(body['id'],road['id']))
        supports=[p for p in self.world.doc['placements'] if p['asset_id']=='authored-bridge-support']
        self.assertEqual(len(supports),4)
        bridge=next(r for r in self.world.doc['roads'] if r['id']=='river-bridge')
        self.assertTrue(all(p[1]==1100 for p in bridge['points']))
        asset=next(a for a in self.world.doc['assets'] if a['id']=='authored-bridge-support')
        top=max(c['center'][1]+c['size_cm'][1]/2 for c in asset['collision'])
        self.assertTrue(all(p['position'][1]+top==1080 for p in supports))

    def test_routes_views_and_paired_assets_are_complete(self):
        routes=self.meta['routes'];self.assertEqual(len(routes),3)
        self.assertEqual(len({json.dumps(r['waypoints'],sort_keys=True) for r in routes}),3)
        roads={r['id'] for r in self.world.doc['roads']}
        for route in routes:
            self.assertLessEqual(len(route['waypoints']),60)
            self.assertGreaterEqual(len(route['waypoints']),3)
            self.assertTrue(all(p['surface_id'] in roads for p in route['waypoints']))
            self.assertEqual(route['start']['x_cm'],22000)
            self.assertEqual(route['waypoints'][0]['x_cm'],26000)
        self.assertEqual({v['name'] for v in self.meta['review_views']},{'main-street','farm-road','nature-road','distant','overview'})
        self.assertTrue(all(v['quality']==2 and v['view_distance_m']==384 for v in self.meta['review_views']))
        for asset in self.world.doc['assets']:
            for key in ('path','distant_path'):
                data=self.world.payloads[asset[key]]
                self.assertEqual(data[:4],b'glTF')
                doc=json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
                self.assertFalse(doc.get('images')) # Common tiles are quality-owned, <=512px.
            self.assertTrue(asset['collision'] or asset['convex_collision'])

    def test_existing_projects_and_unapproved_themes_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'village').mkdir();marker=root/'village/user.txt';marker.write_text('retained')
            with self.assertRaises(FileExistsError):publish(root,'village',KIT,Path('unused'))
            self.assertEqual(marker.read_text(),'retained')
        with self.assertRaisesRegex(ValueError,'art review'):build('neon-harbor',KIT)

if __name__=='__main__':unittest.main()
