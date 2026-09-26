"""Authored design checks, independent of the road construction helper."""
import json
import math
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'examples/arcade-world'
SIZES = {'village': (224,192), 'neon-harbor': (384,256), 'deep-forest': (352,352),
         'red-canyon': (480,240), 'snow-mountain': (320,416),
         'machine-factory': (288,288), 'sky-park': (384,320)}

class ArcadeWorld(unittest.TestCase):
    def test_connected_networks_and_ordered_recommendations(self):
        manifest=json.loads((SOURCE/'arcade-world.json').read_text())
        self.assertEqual(manifest['maps'],list(SIZES))
        signatures=set()
        for ident,size in SIZES.items():
            with self.subTest(map=ident):
                d=json.loads((SOURCE/ident/'document.json').read_text())
                meta=json.loads((SOURCE/ident/'region.json').read_text())
                self.assertEqual(d['bounds']['max'],[n*100 for n in size])
                roads={r['id']:r for r in d['roads']};graph={}
                for r in roads.values():
                    graph.setdefault(r['from'],set()).add(r['to'])
                    graph.setdefault(r['to'],set()).add(r['from'])
                pending=[next(iter(graph))];seen=set()
                while pending:
                    node=pending.pop()
                    if node in seen:continue
                    seen.add(node);pending.extend(graph[node]-seen)
                self.assertEqual(seen,set(graph))
                signatures.add(tuple(sorted(len(v) for v in graph.values())))
                self.assertEqual(len(meta['routes']),3)
                self.assertEqual(meta['routes'][0]['required'],[])
                for route in meta['routes']:
                    self.assertTrue(120<=route['length_m']<=900)
                    self.assertLessEqual(len(route['waypoints']),64)
                    last=None
                    for name in route['road_path']:
                        points=roads[name.lstrip('-')]['points']
                        if name.startswith('-'):points=points[::-1]
                        if last is not None:self.assertEqual(last,points[0])
                        last=points[-1]
                    self.assertEqual({p['gimmick'] for p in route['required']},
                                     {p['gimmick'] for p in route['waypoints'] if 'gimmick' in p})
                    gates=[p for p in route['waypoints'] if 'choice_gate' in p]
                    self.assertEqual(len(gates),2*len(route['choices']))
                    self.assertGreater(math.dist(roads[route['road_path'][0]]['points'][0],roads[route['road_path'][0]]['points'][1]),5800)
                for exit in meta['water_exits']:
                    self.assertGreaterEqual(exit['width_m'],7)
                    self.assertEqual(exit['land_m'][2],1)
                    self.assertLessEqual(exit['max_slope'],.18)
                    self.assertTrue(any([exit['land_m'][0]*100,100,exit['land_m'][1]*100]==n['position'] for n in d['nodes']))
                self.assertEqual(meta['validation_status'],'unverified')
        self.assertEqual(len(signatures),7)

    def test_non_solid_water_and_clear_authored_shores(self):
        for ident in ['neon-harbor','deep-forest']:
            d=json.loads((SOURCE/ident/'document.json').read_text())
            self.assertEqual(len(d['water_bodies']),1)
            self.assertEqual(d['water_bodies'][0]['surface_cm'],0)
            self.assertFalse(any(a['id'].startswith('water-') for a in d['assets']))
            shores=[r for r in d['roads'] if r['id'].startswith(('boat-entry','boat-exit','lake-entry','lake-exit'))]
            self.assertGreaterEqual(len(shores),4)
            for r in shores:
                self.assertEqual(r['kind'],'ground')
                a,b=r['points']
                grade=abs(b[1]-a[1])/math.hypot(b[0]-a[0],b[2]-a[2])
                self.assertLessEqual(grade,.18)
                self.assertGreaterEqual(r['widths_cm'][0],700)

    def test_elevated_crossings_have_separate_driving_levels(self):
        crossings={}
        for ident in SIZES:
            document=json.loads((SOURCE/ident/'document.json').read_text())
            segments=[(r['id'],a,b) for r in document['roads']
                      for a,b in zip(r['points'],r['points'][1:])]
            levels=[]
            for i,(_,a,b) in enumerate(segments):
                for _,c,d in segments[i+1:]:
                    u=(b[0]-a[0],b[2]-a[2]);v=(d[0]-c[0],d[2]-c[2])
                    det=u[0]*v[1]-u[1]*v[0]
                    if abs(det)<1:continue
                    w=(c[0]-a[0],c[2]-a[2])
                    t=(w[0]*v[1]-w[1]*v[0])/det
                    s=(w[0]*u[1]-w[1]*u[0])/det
                    if not (1e-7<t<1-1e-7 and 1e-7<s<1-1e-7):continue
                    gap=abs(a[1]+t*(b[1]-a[1])-c[1]-s*(d[1]-c[1]))
                    if gap>200:
                        self.assertGreaterEqual(gap,400,(ident,a,b,c,d))
                        levels.append(round(gap/100,2))
            if levels:crossings[ident]=levels
        self.assertEqual(set(crossings),{'neon-harbor','red-canyon','snow-mountain','machine-factory','sky-park'})

if __name__ == '__main__':unittest.main()
