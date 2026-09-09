import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driving_test_map as maps
from reference_maps import canonical, sha


class DrivingMapTests(unittest.TestCase):
    def test_frozen_source_and_closed_route(self):
        doc = maps.document()
        lock = json.loads(Path(__file__).with_name('driving_map.lock.json').read_text())
        self.assertEqual(sha(canonical(doc)), lock['source_sha256'])
        roads = {r['id']: r for r in doc['roads']}
        route = [roads[key] for key in ['straight', 'east-corner', 'tunnel', 'west-bridge']]
        for a, b in zip(route, route[1:] + route[:1]):
            self.assertEqual(a['to'], b['from'])
            self.assertEqual(a['points'][-1], b['points'][0])
        self.assertEqual(roads['surface-lane']['surfaces'], ['asphalt', 'gravel', 'dirt'])
        self.assertEqual([p[1] for p in roads['bumps']['points']].count(140), 2)

    def test_shipped_example_matches_creator(self):
        root = Path(__file__).resolve().parents[1] / 'examples' / 'driving'
        lock = json.loads(Path(__file__).with_name('driving_map.lock.json').read_text())
        self.assertEqual(root.joinpath('document.json').read_bytes(), canonical(maps.document()))
        self.assertEqual(sha(root.with_suffix('.memap').read_bytes()), lock['inspection']['package_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = maps.create(Path(tmp)/'project')
            self.assertEqual(json.loads(root.joinpath('driving.json').read_text()), manifest)

    def test_repeatable_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp)/'first', Path(tmp)/'second'
            manifest = maps.create(first)
            self.assertEqual(manifest, maps.create(second))
            before = {p.name:p.read_bytes() for p in first.iterdir()}
            with self.assertRaises(FileExistsError): maps.create(first)
            self.assertEqual(before, {p.name:p.read_bytes() for p in first.iterdir()})
            self.assertEqual(before['document.json'], (second/'document.json').read_bytes())
            self.assertEqual(manifest['start']['heading_degrees'], 0)

if __name__ == '__main__': unittest.main()
