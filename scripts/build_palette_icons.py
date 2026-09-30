"""Create MIT SVG diagrams from palette_icon_source.gd's public MapKit frames.

Usage: python build_palette_icons.py /path/to/frames.json
This is artwork authoring only; the editor loads the checked-in SVGs.
"""
import json
from pathlib import Path
import sys

frames = json.loads(Path(sys.argv[1]).read_text())
output = Path(__file__).resolve().parents[1] / 'ui/icons'
for preset, samples in frames.items():
    # An oblique projection retains height as well as turn direction. Use the
    # public centerline rather than maintaining a second catalogue of shapes.
    points = [(s['position_cm'][0] * .85 - s['position_cm'][2] * .36,
               -s['position_cm'][1] * .9 - s['position_cm'][2] * .68)
              for s in samples]
    minimum = [min(p[j] for p in points) for j in range(2)]
    maximum = [max(p[j] for p in points) for j in range(2)]
    scale = 24 / max(maximum[j] - minimum[j] for j in range(2))
    center = [(a + b) / 2 for a, b in zip(minimum, maximum)]
    xy = [((x - center[0]) * scale + 16, (y - center[1]) * scale + 16)
          for x, y in points]
    path = 'M' + 'L'.join(f'{x:.2f},{y:.2f}' for x, y in xy)
    tip = xy[-1]
    previous = next((p for p in reversed(xy[:-1]) if (p[0]-tip[0])**2+(p[1]-tip[1])**2 > 4), xy[0])
    dx, dy = tip[0]-previous[0], tip[1]-previous[1]
    length = max(.001, (dx*dx+dy*dy)**.5)
    dx, dy = dx/length, dy/length
    arrow = [(tip[0]-4*dx+2*dy, tip[1]-4*dy-2*dx), tip,
             (tip[0]-4*dx-2*dy, tip[1]-4*dy+2*dx)]
    arrow_path = 'M' + 'L'.join(f'{x:.2f},{y:.2f}' for x, y in arrow)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
<path d="{path}" fill="none" stroke="#202020" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
<path d="{path}" fill="none" stroke="#85c7f2" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="{xy[0][0]:.2f}" cy="{xy[0][1]:.2f}" r="2.1" fill="#ff947e" stroke="#202020" stroke-width=".8"/>
<path d="{arrow_path}" fill="none" stroke="#202020" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    (output / f'piece_{preset}.svg').write_text(svg)
print(f'Wrote {len(frames)} palette SVGs')
