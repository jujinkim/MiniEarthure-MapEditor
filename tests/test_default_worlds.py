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

    def test_existing_projects_and_unimplemented_themes_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'village').mkdir();marker=root/'village/user.txt';marker.write_text('retained')
            with self.assertRaises(FileExistsError):publish(root,'village',KIT,Path('unused'))
            self.assertEqual(marker.read_text(),'retained')
        with self.assertRaisesRegex(ValueError,'not yet been authored'):build('not-a-theme',KIT)

class HarborWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.world,cls.meta=build('neon-harbor',KIT)

    def test_reproducibility_and_distinct_connected_courses(self):
        other,meta=build('neon-harbor',KIT)
        self.assertEqual(canonical(self.world.doc),canonical(other.doc))
        self.assertEqual(self.world.payloads,other.payloads)
        self.assertEqual(self.meta,meta)
        self.assertEqual(self.meta['size'],[1920,1280])
        self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
        for route in meta['routes']:
            self.assertLessEqual(len(route['waypoints']),60)
            self.assertEqual(route['start']['x_cm'],26000)
            self.assertGreaterEqual(route['waypoints'][0]['x_cm']-route['start']['x_cm'],4000)
        self.assertLessEqual(meta['validation']['max_road_grade'],.12)

    def test_terrain_seams_and_water_crossing(self):
        paints=[]
        for paint in self.world.doc['surface_areas']:
            shape=Polygon(paint['polygon'])
            self.assertTrue(shape.is_valid,paint['id'])
            self.assertEqual(len(paint['polygon']),len(set(tuple(p) for p in paint['polygon'])),paint['id'])
            for other in paints:self.assertEqual(shape.intersection(other).area,0,paint['id'])
            paints.append(shape)
        grids={}
        for tile in self.world.doc['heightmaps']:
            with Image.open(io.BytesIO(self.world.payloads[tile['path']])) as image:
                grids[(tile['cell']['x'],tile['cell']['y'])]=np.asarray(image).copy()
        self.assertEqual(len(grids),2400)
        for (x,y),grid in grids.items():
            if (x+1,y) in grids:np.testing.assert_array_equal(grid[:,-1],grids[x+1,y][:,0])
            if (x,y+1) in grids:np.testing.assert_array_equal(grid[-1,:],grids[x,y+1][0,:])
        for water in self.world.water:
            for road in self.world.doc['roads']:
                if road['kind']=='ground':
                    self.assertTrue(water.disjoint(self.world.routes[road['id']].buffer(road['widths_cm'][0]/200+.5)),road['id'])

    def test_piers_and_container_stacks_have_real_support(self):
        roads={r['id']:r for r in self.world.doc['roads']}
        for name,end in [('west-pier-road',0),('east-pier-road',-1),('port-service-south',-1)]:
            points=roads[name]['points'];approach=points[:2] if end==0 else points[-2:]
            self.assertEqual([p[1] for p in approach],[1000,1000],name)
        piers=[p for p in self.world.doc['placements'] if p['asset_id']=='authored-harbor-pier']
        self.assertEqual(len(piers),2)
        asset=next(a for a in self.world.doc['assets'] if a['id']=='authored-harbor-pier')
        top=max(c['center'][1]+c['size_cm'][1]/2 for c in asset['collision'])
        self.assertTrue(all(p['position'][1]+top==980 for p in piers))
        stacks=[p for p in self.world.doc['placements'] if 'container-stack' in p['asset_id']]
        self.assertGreater(len(stacks),40)
        for p in stacks:
            x,z,y=[v/100 for v in p['position']]
            self.assertAlmostEqual(float(self.world.height(x,y)),z,delta=.08,msg=p['id'])

    def test_neon_bindings_and_review_views(self):
        self.assertEqual(len(self.meta['review_views']),6)
        self.assertTrue(set(self.meta['menu_views'].values())<=set(v['name'] for v in self.meta['review_views']))
        assets={a['id']:a for a in self.world.doc['assets']}
        self.assertEqual(len(self.world.doc['environment']['lights']),7)
        for binding in self.world.doc['environment']['lights']:
            self.assertTrue(binding['bulb_materials'])
            materials=[]
            for field in ('path','distant_path'):
                data=self.world.payloads[assets[binding['asset_id']][field]]
                doc=json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
                materials.append([m['pbrMetallicRoughness']['baseColorFactor'] for m in doc['materials']])
            self.assertEqual(materials[0],materials[1])

if __name__=='__main__':unittest.main()
