import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import scale_hill_maps as hills
import scale_hill_routes as routes
import scale_maps
import scale_routes


class HillRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.payloads, cls.metadata = scale_maps.make('mixed', 288)

    def fixture(self):
        return hills.derive(self.original, self.metadata)

    def test_preserves_quality_terrain_and_only_one_explicit_exclusion(self):
        original = copy.deepcopy((self.original, self.metadata))
        doc, metadata = self.fixture()
        for key in ['assets', 'placements', 'heightmaps', 'buildings', 'repetitions', 'surface_areas', 'seed']:
            self.assertEqual(doc[key], self.original[key], key)
        for key in ['lots', 'lot_counts', 'quality', 'terrain', 'building_instances_per_km2', 'payload_bytes']:
            self.assertEqual(metadata[key], self.metadata[key], key)
        changed = [z for z, old in zip(doc['zones'], self.original['zones']) if z != old]
        self.assertEqual(len(changed), 1)
        changed[0]['exclusions'] = []
        self.assertEqual(doc['zones'], self.original['zones'])
        self.assertEqual(metadata['road_centerline_spatial_m'], self.metadata['road_centerline_spatial_m']+64)
        self.assertEqual((self.original, self.metadata), original)

    def test_explicit_graph_hill_and_stopping_room(self):
        doc, metadata = self.fixture()
        route = routes.source_route(doc, metadata)
        self.assertEqual(len(route['connections']), 2)
        self.assertEqual(len(route['supports']), 5)
        self.assertEqual(len(route['points']), 9)
        self.assertEqual(route['terrain']['path'], 'terrain/hill.png')
        self.assertEqual(metadata['forest_hill']['excluded_area_m2'], 288)
        self.assertEqual(route['points'][-1][2]-route['points'][0][2], 5200)

    def test_graph_identity_not_coordinate_overlap(self):
        doc, metadata = self.fixture()
        road = next(r for r in doc['roads'] if r['id'] == hills.ROAD)
        node = next(n for n in doc['nodes'] if n['id'] == road['from'])
        doc['nodes'].append(dict(node, id='disconnected-copy'))
        road['from'] = 'disconnected-copy'
        with self.assertRaisesRegex(ValueError, 'disconnected'):
            routes.source_route(doc, metadata)

    def test_missing_hill_exclusion_and_swept_obstacles_reject(self):
        for mutation in ['hill', 'exclusion', 'surface', 'obstacle', 'stop', 'other-terrain']:
            doc, metadata = self.fixture()
            spec = metadata['forest_hill']
            road = next(r for r in doc['roads'] if r['id'] == hills.ROAD)
            x, _, z = road['points'][0]
            if mutation == 'hill': doc['heightmaps'] = []
            if mutation == 'exclusion':
                next(zone for zone in doc['zones'] if zone['id'] == spec['zone_id'])['exclusions'] = []
            if mutation == 'surface': road['kind'] = 'bridge'
            if mutation == 'other-terrain':
                doc['heightmaps'].append(dict(cell=dict(x=x//1600, y=z//1600), path='unexpected.png'))
            if mutation in ['obstacle', 'stop']:
                at = z+(4000 if mutation == 'obstacle' else 6200)
                doc['zones'].append(dict(id='blocked', polygon=[[x-10, at-10], [x+10, at-10], [x+10, at+10], [x-10, at+10]]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                routes.source_route(doc, metadata)

    def test_new_destination_identity_and_native_failure_are_not_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)/'original'
            scale_maps.create(base, 'mixed', 288)
            expected = {p: p.read_bytes() for p in base.rglob('*') if p.is_file()}
            destination = Path(folder)/'hill'
            hills.create(base, destination)
            self.assertEqual({p: p.read_bytes() for p in expected}, expected)
            with self.assertRaises(FileExistsError): hills.create(base, destination)
            (base/'terrain/hill.png').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'identity'): hills.create(base, Path(folder)/'bad')
            self.assertFalse((Path(folder)/'bad').exists())
            doc, metadata = self.fixture()
            with patch.object(routes.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'deliberate native failure')):
                with self.assertRaisesRegex(ValueError, 'native hill audit failed'):
                    routes.native_reference(destination/'document.json', sys.executable, Path(folder)/'native', routes.source_route(doc, metadata))
            self.assertNotEqual(json.loads((Path(folder)/'native/commands.json').read_text())[0]['exit_code'], 0)
            with patch.object(scale_routes, 'package_identity', return_value={'index_version': 1}):
                with self.assertRaisesRegex(ValueError, 'index v2'):
                    scale_routes.create(destination, Path(folder)/'old.mkregions', Path(folder)/'routes.json',
                                        destination, 'forest-hill', sys.executable, Path(folder)/'must-not-generate')
            self.assertFalse((Path(folder)/'routes.json').exists())
            self.assertFalse((Path(folder)/'must-not-generate').exists())


if __name__ == '__main__': unittest.main()
