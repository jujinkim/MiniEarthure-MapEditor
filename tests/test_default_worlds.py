"""Compact authored worlds: real scale, independent base routes and safe scenery."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image
from shapely.geometry import Point,Polygon
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from default_worlds import build,publish,THEMES,canonical
KIT=Path(os.environ.get('MAPKIT_ROOT',ROOT/'addons/mapkit'))

class CompactWorlds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.worlds={name:build(name,KIT) for name in THEMES}

    def test_dimensions_and_all_terrain_cell_seams(self):
        self.assertEqual(list(THEMES.values()),[(640,512),(960,768),(896,896),(1152,640),(832,1056),(768,768),(960,800)])
        for theme,(world,meta) in self.worlds.items():
            with self.subTest(theme=theme):
                self.assertEqual(world.doc['cell_size_cm'],3200)
                self.assertEqual(meta['size'],list(THEMES[theme]))
                self.assertNotIn(meta['name'],world.routes)
                tiles={}
                for tile in world.doc['heightmaps']:
                    with Image.open(io.BytesIO(world.payloads[tile['path']])) as image:
                        self.assertEqual(image.size,(17,17));tiles[tile['cell']['x'],tile['cell']['y']]=np.asarray(image).copy()
                self.assertEqual(len(tiles),THEMES[theme][0]*THEMES[theme][1]//1024)
                for (x,y),data in tiles.items():
                    if (x+1,y) in tiles:np.testing.assert_array_equal(data[:,-1],tiles[x+1,y][:,0])
                    if (x,y+1) in tiles:np.testing.assert_array_equal(data[-1,:],tiles[x,y+1][0,:])

    def test_connected_ordinary_routes_lengths_and_optional_progress(self):
        for theme,(world,meta) in self.worlds.items():
            roads={r['id']:r for r in world.doc['roads']}
            self.assertTrue(meta['validation']['road_graph_connected'],theme)
            self.assertLessEqual(meta['validation']['max_road_grade'],.12,theme)
            self.assertGreaterEqual(min(r['widths_cm'][0] for r in roads.values()),650)
            self.assertGreaterEqual(roads['arrival-road']['widths_cm'][0],1000)
            self.assertEqual(len(meta['routes']),3)
            self.assertEqual(len({json.dumps(r['waypoints']) for r in meta['routes']}),3)
            for route in meta['routes']:
                low,high={'intro':(600,900),'tour':(1400,2000),'technical':(1000,1500)}[route['id']]
                self.assertTrue(low<=route['length_m']<=high,(theme,route['id'],route['length_m']))
                self.assertTrue(3<=len(route['waypoints'])<=60)
                self.assertTrue(all(p['surface_id'] in roads for p in route['waypoints']))
                last=None
                for step in route['road_walk']:
                    r=roads[step.lstrip('-')];a,b=(r['to'],r['from']) if step.startswith('-') else (r['from'],r['to'])
                    if last is not None:self.assertEqual(last,a,(theme,route['id'],step))
                    last=b
                for branch in meta['optional_branches']:
                    self.assertFalse(set(branch['base_roads']) & {p['surface_id'] for p in route['waypoints']},'branch-only gate would force the bypass')
            self.assertEqual({a['surface']['surface_id'] for a in world.attachments},
                {'arrival-road'} if theme in ('neon-harbor','machine-factory') else {'arrival-road','track:scenic-shortcut'})
            self.assertGreaterEqual(meta['optional_branches'][0]['landing_runway_m'],6)
            self.assertTrue(world.track_source['road_connections'])

    def test_water_clearance_and_near_far_assets(self):
        for theme,(world,meta) in self.worlds.items():
            with self.subTest(theme=theme):
                for water in world.water:
                    for road in world.doc['roads']:
                        if road['kind']=='ground':self.assertTrue(water.disjoint(world.routes[road['id']].buffer(road['widths_cm'][0]/200+.5)),road['id'])
                self.assertGreaterEqual(len(meta['districts']),3)
                self.assertGreaterEqual(len(meta['landmarks']),2)
                self.assertTrue({'entry','landmark','special-branch','distant','overview'}<=set(v['name'] for v in meta['review_views']))
                self.assertTrue(set(meta['menu_views'].values())<=set(v['name'] for v in meta['review_views']))
                overview=next(v for v in meta['review_views'] if v['name']=='overview')
                self.assertGreater(overview['view_distance_m'],max(world.size))
                for asset in world.doc['assets']:
                    for field in ('path','distant_path'):self.assertEqual(world.payloads[asset[field]][:4],b'glTF')
                for placement in world.doc['placements']:
                    if placement['id'].startswith(('bridge-support-','bridge-pier-','forest-pier-')):
                        x,z,y=[v/100 for v in placement['position']]
                        self.assertLessEqual(z,float(world.base(x,y)),(theme,placement['id'],'pier base above terrain'))
                self.assertTrue(meta['habitats'])
        snow=self.worlds['snow-mountain'][1]
        self.assertTrue(any(v.get('weather')=='snow' and v.get('snow')==1 for v in snow['review_views']))
        harbor=self.worlds['neon-harbor'][1]
        self.assertTrue(any(v.get('time_minutes',0)>=1080 for v in harbor['review_views']))

    def test_reproducibility_and_no_overwrite(self):
        world,meta=build('village',KIT)
        self.assertEqual(canonical(world.doc),canonical(self.worlds['village'][0].doc))
        self.assertEqual(meta,self.worlds['village'][1])
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'village').mkdir();marker=root/'village/user.txt';marker.write_text('preserve')
            with self.assertRaises(FileExistsError):publish(root,'village',KIT,Path('unused'))
            self.assertEqual(marker.read_text(),'preserve')

    def test_facility_props_meet_their_finished_ground(self):
        groups={'village':('market-stall-','market-planter-','farm-tractor'),
            'machine-factory':('shipping-truck-','service-compressor-'),
            'sky-park':('queue-','flower-border-','shade-arcade-')}
        for theme,prefixes in groups.items():
            world,_=self.worlds[theme]
            for placement in world.doc['placements']:
                if placement['id'].startswith(prefixes):
                    x,z,y=[v/100 for v in placement['position']]
                    self.assertLess(abs(z-float(world.height(x,y))),.025,(theme,placement['id']))

class RailWorlds(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.worlds={name:build(name,KIT) for name in ('neon-harbor','machine-factory')}

    def test_curve_shortcuts_and_clear_corridor(self):
        for theme,(world,meta) in self.worlds.items():
            branch=world.shortcuts[0];line=world.track_source['grind_lines'][0]
            self.assertLessEqual(branch['shortcut_length_m'],branch['main_length_m']*.8)
            self.assertGreaterEqual(branch['main_length_m']-branch['shortcut_length_m'],5)
            self.assertGreaterEqual(branch['landing_runway_m'],18)
            for r in meta['routes']:
                low,high={'intro':(600,900),'tour':(1400,2000),'technical':(1000,1500)}[r['id']]
                self.assertTrue(low<=r['length_m']<=high,(theme,r['id'],r['length_m']))
                self.assertFalse(set(branch['base_roads']) & {p['surface_id'] for p in r['waypoints']})
            for a,b in zip(line['control_points'],line['control_points'][1:]):
                for t in np.linspace(0,1,100):
                    p=np.array(a)+(np.array(b)-a)*t
                    self.assertLessEqual(world.height(p[0]/100,p[2]/100),p[1]/100-.4+.01)
            for name,shape in world.obstacles:
                self.assertFalse(shape.intersects(branch['clearance']),(theme,name))
            again,_=build(theme,KIT)
            self.assertEqual(canonical(world.track_source),canonical(again.track_source))
            self.assertEqual(canonical(world.doc),canonical(again.doc))

if __name__=='__main__':unittest.main()
