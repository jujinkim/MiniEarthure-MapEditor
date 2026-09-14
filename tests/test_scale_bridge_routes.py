import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import scale_bridge_routes as bridge
import scale_hill_routes as hill
import scale_maps
import scale_routes


class BridgeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, _, cls.metadata = scale_maps.make('mixed', 288)

    def source(self):
        return copy.deepcopy((self.doc, self.metadata))

    def route(self):
        return bridge.source_routes(*self.source())[0][0]

    def reference(self, route):
        # Explicit test planes, not production generation or packaged geometry.
        triangles = []
        points = route['source_graph']['points_cm']
        for a, b in zip(points, points[1:]):
            p, q = [a[0],a[1],500], [a[0],a[1],1100]
            r, s = [b[0],b[1],500], [b[0],b[1],1100]
            triangles.extend(dict(road_id='speed-bridge',vertices_cm=t) for t in [[p,q,r],[q,s,r]])
        return dict(floor_triangles_cm=triangles)

    def test_new_routes_preserve_original_graph_source_and_forward_only_profile(self):
        doc, metadata = self.source()
        before = copy.deepcopy((doc,metadata))
        old = scale_routes.routes(doc,metadata)
        results = bridge.source_routes(doc,metadata)
        self.assertEqual((doc,metadata),before)
        self.assertEqual(scale_routes.routes(doc,metadata),old)
        self.assertNotIn('shuttle',next(r for r in old if r['id']=='bridge-grades'))
        self.assertEqual([(r['id'],r['distance_m']) for r,_ in results],
                         [('bridge-full-shuttle',256),('bridge-east-ramp-shuttle',160)])
        full, east = [r for r,_ in results]
        self.assertEqual(full['start_cm'],[1600,0,800])
        self.assertEqual(full['end_cm'],[27200,0,800])
        self.assertEqual(east['start_cm'],[11200,300,800])
        self.assertEqual(east['segments'][-1]['end_cm'],east['end_cm'])
        self.assertEqual(full['shuttle']['braking']['end_cm'],[26000,112.5,800])
        self.assertEqual(full['shuttle']['bounds_cm'],[290,690,28510,910])

    def test_large_route_is_named_complete_ramp_not_full_bridge_prefix(self):
        doc, _, metadata = scale_maps.make('mixed', 2000)
        results = bridge.source_routes(doc,metadata)
        self.assertEqual(len(results),1)
        route = results[0][0]
        self.assertEqual(route['id'],'bridge-east-ramp-shuttle')
        self.assertEqual(route['distance_m'],160)
        self.assertEqual(route['start_cm'],[182400,300,800])
        self.assertEqual(route['end_cm'],[198400,0,800])
        self.assertEqual(len(route['segments']),2)
        self.assertEqual(route['segments'][0]['end_cm'],route['segments'][1]['start_cm'])

    def test_changed_graph_material_geometry_or_invalid_size_reject(self):
        for mutation in ['node','duplicate','grade','width','surface','kind','size','bounds']:
            doc, metadata = self.source()
            road = next(r for r in doc['roads'] if r['id']=='speed-bridge')
            if mutation=='node': next(n for n in doc['nodes'] if n['id']==road['from'])['position'][0] += 1
            if mutation=='duplicate': doc['roads'].append(copy.deepcopy(road))
            if mutation=='grade': road['points'][2][1] = 0
            if mutation=='width': road['widths_cm'][0] = 400
            if mutation=='surface': road['surfaces'][2] = 'grass'
            if mutation=='kind': road['kind'] = 'ground'
            if mutation=='size': metadata['size_m'] = '288'
            if mutation=='bounds': doc['bounds']['max'][0] -= 100
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                bridge.source_routes(doc,metadata)

    def test_world_edge_halo_excludes_only_outside_cells_and_keeps_sweep(self):
        _,source = bridge.source_routes(*self.source())[0]
        box,cells,excluded = hill.reference_cells(source)
        self.assertEqual(len(cells),36)
        self.assertEqual(excluded,24)
        self.assertEqual({z for x,z in cells},{0,1})
        self.assertEqual({x for x,z in cells},set(range(18)))
        source['sweep'][0][0] = -1
        with self.assertRaisesRegex(ValueError,'outside source world'):
            hill.reference_cells(source)

    def test_obstacles_in_both_stopping_ends_and_vehicle_width_reject(self):
        for x,z in [(400,800),(28400,800),(10000,905)]:
            doc,metadata = self.source()
            doc['zones'].append(dict(id='blocked',polygon=[[x-2,z-2],[x+2,z-2],[x+2,z+2],[x-2,z+2]]))
            with self.subTest(x=x,z=z), self.assertRaisesRegex(ValueError,'obstacle'):
                bridge.source_routes(doc,metadata)

    def test_native_probes_require_support_relief_normals_and_downhill_runway(self):
        route = self.route()
        native = self.reference(route)
        result = bridge.probe_reference(route,native)
        self.assertLessEqual(result['samples'],4096)
        self.assertEqual(result['maximum_height_cm'],300)
        self.assertEqual(result['minimum_height_cm'],0)
        self.assertAlmostEqual(result['maximum_height_error_cm'],0)
        self.assertEqual(result['downhill_grade_range'],[-.09375,-.09375])
        for mutation in ['gap','height','normal','flat-stop']:
            changed = copy.deepcopy(native)
            if mutation=='gap': changed['floor_triangles_cm'] = changed['floor_triangles_cm'][2:]
            if mutation in ['height','normal']:
                for t in changed['floor_triangles_cm']:
                    for v in t['vertices_cm']: v[1] += 20 if mutation=='height' else (v[2]-800)*2
            selected = copy.deepcopy(route)
            if mutation=='flat-stop':
                selected['shuttle']['braking']['start_cm'][0] = 10000
                selected['shuttle']['braking']['end_cm'][0] = 11200
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError,'native bridge'):
                bridge.probe_reference(selected,changed)

    def test_native_failure_keeps_logs_without_sidecar_and_source_changes_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base/'source'
            scale_maps.create(source,'mixed',288)
            before = {p:p.read_bytes() for p in source.rglob('*') if p.is_file()}
            package = base/'fixture.mkregions'
            package.write_bytes(b'explicit unit fixture, not a native package')
            kwargs = dict(source=source,package=package,output=base/'routes.json',restored=source,
                          profile='bridge-shuttle',mapkit=sys.executable,native_output=base/'native')
            with patch.object(scale_routes,'package_identity',return_value={'index_version':2}), \
                 patch.object(hill.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','intentional failure')):
                with self.assertRaisesRegex(ValueError,'native bridge audit failed'):
                    scale_routes.create(**kwargs)
            self.assertFalse(kwargs['output'].exists())
            commands = json.loads((base/'native/bridge-full-shuttle/commands.json').read_text())
            self.assertEqual(commands[0]['exit_code'],1)
            self.assertEqual({p:p.read_bytes() for p in before},before)
            with patch.object(scale_routes,'package_identity',return_value={'index_version':1}):
                with self.assertRaisesRegex(ValueError,'index v2'):
                    scale_routes.create(**dict(kwargs,native_output=base/'stale-native'))
            self.assertFalse((base/'stale-native').exists())
            with self.assertRaisesRegex(ValueError,'--mapkit'):
                scale_routes.create(**dict(kwargs,mapkit=None))
            (source/'terrain/hill.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source identity'):
                scale_routes.create(**dict(kwargs,native_output=base/'changed-native'))
            self.assertFalse((base/'changed-native').exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'routes.json'
            output.write_text('keep me')
            with self.assertRaises(FileExistsError):
                scale_routes.create('missing','missing',output,'missing','bridge-shuttle','missing','missing')
            self.assertEqual(output.read_text(),'keep me')
            with self.assertRaises(FileExistsError):
                bridge.bridge_routes(*self.source(),'missing','missing',Path(folder))


if __name__ == '__main__': unittest.main()
