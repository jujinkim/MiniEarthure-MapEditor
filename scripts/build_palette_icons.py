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
    ribbon = []
    if '_extra_wide' in preset:
        sides = [[], []]
        for s in samples:
            n, f = s['normal'], s['forward']
            right = [n[1]*f[2]-n[2]*f[1], n[2]*f[0]-n[0]*f[2], n[0]*f[1]-n[1]*f[0]]
            length = sum(v*v for v in right)**.5
            for side, sign in enumerate([-1, 1]):
                v = [s['position_cm'][j]+sign*right[j]/length*s['lateral_cm'] for j in range(3)]
                sides[side].append((v[0]*.85-v[2]*.36, -v[1]*.9-v[2]*.68))
        ribbon = sides[0]+list(reversed(sides[1]))
    bounds = ribbon or points
    minimum = [min(p[j] for p in bounds) for j in range(2)]
    maximum = [max(p[j] for p in bounds) for j in range(2)]
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
<path d="{path}" fill="none" stroke="#344f73" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
<path d="{path}" fill="none" stroke="#99c8ed" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="{xy[0][0]:.2f}" cy="{xy[0][1]:.2f}" r="2.1" fill="#df704b" stroke="#344f73" stroke-width=".8"/>
<path d="{arrow_path}" fill="none" stroke="#344f73" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    if ribbon:
        outline = 'M'+'L'.join(f'{(x-center[0])*scale+16:.2f},{(y-center[1])*scale+16:.2f}' for x,y in ribbon)+'Z'
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
<path d="{outline}" fill="#99c8ed" stroke="#344f73" stroke-width="1.2" stroke-linejoin="round"/>
<path d="{path}" fill="none" stroke="#ffffff" stroke-width=".8" stroke-dasharray="2 1"/>
<circle cx="{xy[0][0]:.2f}" cy="{xy[0][1]:.2f}" r="1.8" fill="#df704b" stroke="#344f73" stroke-width=".7"/>
<path d="{arrow_path}" fill="none" stroke="#344f73" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="19" y="23" width="12" height="8" rx="2" fill="#ffffff" stroke="#344f73" stroke-width=".7"/>
<path d="M21.5 25.3L23 24.5V29.5M25.5 25.4C25.5 23.8 28.5 23.8 28.5 25.4C28.5 26.2 27 27.1 25.5 29H29" fill="none" stroke="#344f73" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    (output / f'piece_{preset}.svg').write_text(svg)
print(f'Wrote {len(frames)} palette SVGs')
