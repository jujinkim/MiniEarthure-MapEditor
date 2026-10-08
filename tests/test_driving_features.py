"""Shared placement extraction retains the five independent practice features."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from driving_features import build,place

class DrivingFeatures(unittest.TestCase):
    def test_new_destination_and_reproducible_five_feature_demo(self):
        with tempfile.TemporaryDirectory() as temporary:
            first=Path(temporary)/'first';second=Path(temporary)/'second'
            for destination in (first,second):build(destination,ROOT/'addons/mapkit')
            with self.assertRaises(FileExistsError):build(first,ROOT/'addons/mapkit')
            doc=json.loads((first/'demo/document.json').read_text())
            self.assertEqual({g.get('track',{}).get('kind',g['motion']['kind']) for g in doc['gimmicks']},
                {'target_speed','jump_height','air_ring','loop','cylinder'})
            for path in first.rglob('*'):
                if path.is_file():self.assertEqual(path.read_bytes(),(second/path.relative_to(first)).read_bytes())

if __name__=='__main__':unittest.main()
