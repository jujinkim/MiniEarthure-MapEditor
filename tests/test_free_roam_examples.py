import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('refresh_free_roam', ROOT / 'scripts/refresh_free_roam_examples.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FreeRoamExamples(unittest.TestCase):
    def test_sources_and_new_output_preserve_original(self):
        for ident in module.IDS:
            doc = json.loads((ROOT / 'examples/free-roam-world' / ident / 'document.json').read_text())
            self.assertTrue(doc['free_roam'])
            self.assertFalse(doc.get('courses'))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            destination = Path(directory) / 'output'
            for ident in module.IDS:
                path = source / ident; path.mkdir(parents=True)
                (path / 'document.json').write_text(json.dumps(dict(free_roam=False, revision=1, provenance={}, courses=[])))
            original = (source / module.IDS[0] / 'document.json').read_bytes()
            self.assertEqual(module.refresh(source, destination), 8)
            self.assertEqual((source / module.IDS[0] / 'document.json').read_bytes(), original)
            with self.assertRaises(ValueError): module.refresh(source, destination)
            path = source / module.IDS[1] / 'document.json'
            value = json.loads(path.read_text()); value['courses'] = [{}]; path.write_text(json.dumps(value))
            with self.assertRaises(ValueError): module.refresh(source, Path(directory) / 'races')

if __name__ == '__main__': unittest.main()
