"""Retain the v2 synthetic map's 1,226 trees using the city's full-size model.

The adjacent snapshot was emitted by MapKit from the archived v2 package; no
generation rules are duplicated here. Empty zone outlines remain editable.
"""
import json
import math
from pathlib import Path
from shapely.geometry import MultiPoint, box
from shapely.prepared import prep
from shapely.ops import unary_union
from city_assets import tree, TREE_CANOPY_WIDTH_M


def place_vegetation(t, bounds, occupied):
    # These coordinates are already centimetres. Only the old source positions
    # are converted below; the shared GLB and its planter/trunk collision stay 1:1.
    name = tree(t)
    half = math.ceil(TREE_CANOPY_WIDTH_M * 100 / 2)
    clearance = 5
    assets = {a['id']: a for a in t.doc['assets']}
    obstacles = [occupied]
    for placement in t.doc['placements']:
        points = []
        asset = assets[placement['asset_id']]
        for shape in asset.get('collision', []):
            x, _, y = shape['center']; w, _, d = shape['size_cm']
            points.extend((x+dx*w/2, y+dy*d/2) for dx in (-1,1) for dy in (-1,1))
        for shape in asset.get('convex_collision', []):
            points.extend((p[0],p[2]) for p in shape['vertices'])
        transformed = []
        for x,y in points:
            for _ in range(placement['quarter_turns']): x,y = -y,x
            transformed.append((x+placement['position'][0],y+placement['position'][2]))
        if transformed: obstacles.append(MultiPoint(transformed).convex_hull)
    blocked = prep(unary_union(obstacles).buffer(clearance))
    # Fixed-size canopy footprints need only their own and eight adjacent bins.
    # Keep accepted centres separately instead of repeatedly unioning the map.
    separation = 2*half + clearance
    bins = {}
    def clear_of_trees(px,py):
        bx,by = px//separation,py//separation
        return not any(abs(px-ox)<=separation and abs(py-oy)<=separation
                       for dx in (-1,0,1) for dy in (-1,0,1)
                       for ox,oy in bins.get((bx+dx,by+dy), []))
    free_sites = None
    snapshot = json.loads(Path(__file__).with_name('driving_school_vegetation_v2.json').read_text())
    assert snapshot['package_sha256'] == '12c54057dd0c7b751e928c3abfc370e78ad9603d0f1fbc56e9ab8d4a43ee4104'
    assert len(snapshot['objects']) == 1226
    for source in snapshot['objects']:
        x, h, y = [round(v/32) for v in source['position']]
        found = None
        for radius_cm in range(0, 1601, 20):
            for angle in range(0,360,30) if radius_cm else [0]:
                px = round(x+radius_cm*math.cos(math.radians(angle)))
                py = round(y+radius_cm*math.sin(math.radians(angle)))
                canopy = box(px-half,py-half,px+half,py+half)
                if not bounds.contains(canopy) or blocked.intersects(canopy): continue
                if not clear_of_trees(px,py): continue
                found = (px,py); break
            if found is not None: break
        if found is None:
            # Tiny former parks cannot hold all their full-size canopies within
            # 16 m. Use the nearest remaining safe site in the practice grounds,
            # never shrink/drop a tree or change a road to make it fit.
            if free_sites is None:
                left,bottom,right,top = map(int,bounds.bounds)
                free_sites = []
                for px in range(left+half+clearance,right-half,separation+1):
                    for py in range(bottom+half+clearance,top-half,separation+1):
                        canopy = box(px-half,py-half,px+half,py+half)
                        if bounds.contains(canopy) and not blocked.intersects(canopy): free_sites.append((px,py))
            for px,py in sorted(free_sites,key=lambda p: ((p[0]-x)**2+(p[1]-y)**2,p)):
                if clear_of_trees(px,py):
                    found = (px,py); break
        if found is None: raise ValueError('No space for retained tree '+source['id'])
        px,py = found
        bins.setdefault((px//separation,py//separation), []).append(found)
        t.doc['placements'].append(dict(id='scaled-'+source['id'].replace(':','-'), asset_id=name,
            position=[px,h,py],quarter_turns=source['quarter_turns']))
