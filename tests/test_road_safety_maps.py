import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from road_safety_maps import build

class RoadSafetySource(unittest.TestCase):
    def test_reproducible_preserved_source_and_height_seams(self):
        original=ROOT/'examples/miniature-streets/belmont'
        hashes=lambda root:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.name.endswith('.import')}
        before=hashes(original)
        with tempfile.TemporaryDirectory() as temp:
            target=build(Path(temp)/'belmont')
            self.assertEqual(hashes(target),hashes(ROOT/'examples/road-safety/belmont'))
            with self.assertRaises(FileExistsError):build(target)
            d=json.loads((target/'document.json').read_text())
            old=json.loads((original/'document.json').read_text())
            for field in ['roads','nodes','placements','gimmicks','buildings']:
                self.assertEqual(d[field],old[field],field)
            grids={}
            for h in d['heightmaps']:
                with Image.open(target/h['path']) as image:
                    grids[h['cell']['x'],h['cell']['y']]=[[image.getpixel((x,y))*h['step_cm']+h['offset_cm'] for x in range(9)] for y in range(9)]
            for (x,y),grid in grids.items():
                if (x+1,y) in grids:self.assertEqual([r[-1] for r in grid],[r[0] for r in grids[x+1,y]])
                if (x,y+1) in grids:self.assertEqual(grid[-1],grids[x,y+1][0])
        self.assertEqual(before,hashes(original))

if __name__=='__main__':unittest.main()
