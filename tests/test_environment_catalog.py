"""Source/package linkage and bounded recommendations for the shipped worlds."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from environment_generation import fingerprint, PROFILES
from environment_catalog import routes

SOURCE=Path(__file__).resolve().parents[1]/'examples/environment-world'


class EnvironmentCatalogTests(unittest.TestCase):
    def test_current_dimensions_facilities_and_algorithm(self):
        self.assertEqual(json.loads((SOURCE/'arcade-world.json').read_text())['algorithm'],fingerprint())
        for key,profile in PROFILES.items():
            with self.subTest(theme=key):
                meta=json.loads((SOURCE/key/'region.json').read_text())
                doc=json.loads((SOURCE/key/'document.json').read_text())
                self.assertEqual(meta['size'],list(profile.minimum_size_m))
                self.assertEqual(doc['cell_size_cm'],3200)
                self.assertEqual(meta['authoring']['algorithm'],fingerprint())
                self.assertEqual(set(meta['validation']['required']),set(meta['validation']['present']))
                ids=[p['id'] for p in doc['placements']]
                self.assertEqual(len(ids),len(set(ids)))

    def test_package_payloads_match_editable_sources(self):
        for key in PROFILES:
            with self.subTest(theme=key),zipfile.ZipFile(SOURCE/(key+'.memap')) as package:
                manifest=json.loads(package.read('manifest.json'))
                self.assertEqual(manifest['format_version'],1)
                for entry in manifest['files']:
                    payload=package.read(entry['path'])
                    self.assertEqual(hashlib.sha256(payload).hexdigest(),entry['sha256'])
                    if entry['path']!='document.json':
                        self.assertEqual(payload,(SOURCE/key/entry['path']).read_bytes())

    def test_distinct_reproducible_routes_use_existing_roads(self):
        for key in PROFILES:
            with self.subTest(theme=key):
                doc=json.loads((SOURCE/key/'document.json').read_text())
                planned=json.loads((SOURCE/key/'region.json').read_text())['routes']
                self.assertEqual(routes(doc),planned)
                self.assertEqual(len({json.dumps(r['waypoints'],sort_keys=True) for r in planned}),3)
                roads={r['id']:r for r in doc['roads']}
                for route in planned:
                    self.assertGreaterEqual(len(route['waypoints']),3)
                    self.assertLessEqual(len(route['waypoints']),60)
                    self.assertEqual(roads[route['start']['surface_id']]['kind'],'ground')
                    self.assertTrue(all(w['surface_id'] in roads for w in route['waypoints']))


if __name__=='__main__': unittest.main()
