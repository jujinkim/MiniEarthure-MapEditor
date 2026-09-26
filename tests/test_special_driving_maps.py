import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('special_driving_maps', ROOT / 'scripts/special_driving_maps.py')
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


class SpecialDrivingMaps(unittest.TestCase):
    def test_new_outputs_preserve_sources_bypasses_and_determinism(self):
        sources = [ROOT / ('examples/road-safety/belmont' if ident == 'belmont' else 'examples/miniature-streets/' + ident) for ident in maps.IDS]
        files = [f for source in sources for f in source.rglob('*') if f.is_file() and f.suffix != '.import' and f.name != '.DS_Store']
        hashes = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / 'a', Path(temp) / 'b'
            for output in [first, second]:
                maps.build(output, ROOT / 'addons/mapkit')
            with self.assertRaises(FileExistsError):
                maps.build(first, ROOT / 'addons/mapkit')
            for ident, source in zip(maps.IDS, sources):
                original = json.loads((source / 'document.json').read_text())
                changed = json.loads((first / ident / 'document.json').read_text())
                metadata = json.loads((first / ident / 'region.json').read_text())
                self.assertEqual(changed['roads'], original['roads'])
                self.assertEqual(changed['gimmicks'][:-1], original.get('gimmicks', []))
                self.assertGreaterEqual(metadata['special_driving']['bypass_width_cm'], 160)
                self.assertEqual(metadata['special_driving']['user_verification'], 'unverified')
                for file in source.rglob('*'):
                    if file.is_file() and file.name not in ['document.json', 'region.json', '.DS_Store'] and file.suffix != '.import':
                        self.assertEqual(file.read_bytes(), (first / ident / file.relative_to(source)).read_bytes())
            demo = json.loads((first / 'demo/document.json').read_text())
            kinds = {g.get('track', {}).get('kind', g['motion']['kind']) for g in demo['gimmicks']}
            self.assertEqual(kinds, {'target_speed', 'jump_height', 'air_ring', 'loop', 'cylinder'})
            for file in first.rglob('*'):
                if file.is_file():
                    self.assertEqual(file.read_bytes(), (second / file.relative_to(first)).read_bytes())
        self.assertEqual(hashes, {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files})


if __name__ == '__main__':
    unittest.main()
