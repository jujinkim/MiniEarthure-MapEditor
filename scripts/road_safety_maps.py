#!/usr/bin/env python3
"""Create Belmont's revised level bridge apron in a NEW source directory (MIT)."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def build(destination: Path) -> Path:
    source = ROOT / 'examples/miniature-streets/belmont'
    if destination.exists():
        raise FileExistsError(f'Preserve existing source: {destination}')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('*.import', '.DS_Store'))
    document = json.loads((source / 'document.json').read_text())
    road = next(r for r in document['roads'] if r['id'] == 'arterial-2-s1')
    centers = [road['points'][0], road['points'][-1]]
    changed = 0
    for h in document['heightmaps']:
        image = Image.open(source / h['path']).copy()
        edited = False
        for y in range(image.height):
            for x in range(image.width):
                px = h['cell']['x'] * document['cell_size_cm'] + x * h['spacing_cm']
                py = h['cell']['y'] * document['cell_size_cm'] + y * h['spacing_cm']
                distance = min(math.hypot(px-p[0], py-p[2]) for p in centers)
                weight = max(0, min(1, (1000-distance)/400))
                old = image.getpixel((x, y))
                height = old*h['step_cm'] + h['offset_cm']
                new = round((height*(1-weight)-h['offset_cm'])/h['step_cm'])
                if new != old:
                    image.putpixel((x, y), new); edited = True
        if edited:
            data = io.BytesIO(); image.save(data, format='PNG')
            content = data.getvalue()
            h['path'] = 'terrain/' + hashlib.sha256(content).hexdigest() + '.png'
            (destination / h['path']).write_bytes(content)
            changed += 1
    document['map_id'] = 'road-safety-belmont'
    document['revision'] = 1
    document['provenance'].update(tool_id='mapeditor-road-safety', build_id='road-safety-authoring-v1',
                                  first_created='2026-09-26T00:00:00Z', last_edited='2026-09-26T00:00:00Z')
    (destination/'document.json').write_text(json.dumps(document, sort_keys=True, separators=(',', ':'))+'\n')
    meta = json.loads((source/'region.json').read_text())
    meta['road_safety_revision'] = dict(source='miniature-streets/belmont', changed_heightmaps=changed,
                                      bridge_id=road['id'], flat_radius_cm=600, blend_radius_cm=1000)
    meta['source_files'] = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(destination.rglob('*')) if p.is_file() and p.name != 'region.json'}
    (destination/'region.json').write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n')
    print(f'Belmont: {changed} height tiles; original sources/packages preserved')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    build(parser.parse_args().destination)
