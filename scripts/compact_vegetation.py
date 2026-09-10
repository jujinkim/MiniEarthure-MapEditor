"""Retain the v2 synthetic map's 1,226 trees at one quarter displayed size.

The adjacent snapshot was emitted by MapKit from the archived v2 package; no
generation rules are duplicated here. Empty zone outlines remain editable.
"""
import json
import math
from pathlib import Path
from shapely.geometry import Point


def place_vegetation(t, bounds, occupied):
    from driving_school_map import box, glb
    radius, height, center = 1.84/32, 4/32, 4.8/32
    vertices = [(0, center-height/2, 0)]
    for row in range(1, 8):
        angle = -math.pi/2 + math.pi*row/8
        for column in range(12):
            yaw = 2*math.pi*column/12
            vertices.append((radius*math.cos(angle)*math.cos(yaw),
                             center+height/2*math.sin(angle), radius*math.cos(angle)*math.sin(yaw)))
    vertices.append((0, center+height/2, 0))
    faces = []
    for column in range(12):
        a, b = 1+column, 1+(column+1)%12
        faces.append((0,a,b))
        for row in range(6):
            c, e = a+row*12, b+row*12
            faces.extend(((c,c+12,e), (e,c+12,e+12)))
        faces.append((a+72, len(vertices)-1, b+72))
    name = 'compact-tree'
    path = 'assets/'+name+'.glb'
    t.payloads[path] = glb([(box((0,0.06,0),(.02,.12,.02)),(.42,.30,.19,1)),
                          (vertices,(.282,.392,.278,1),faces)])
    t.doc['assets'].append(dict(id=name,path=path,attribution=t.doc['attributions'][0],
        collision=[dict(center=[0,6,0],size_cm=[2,12,2])],convex_collision=[]))
    snapshot = json.loads(Path(__file__).with_name('driving_school_vegetation_v2.json').read_text())
    assert snapshot['package_sha256'] == '12c54057dd0c7b751e928c3abfc370e78ad9603d0f1fbc56e9ab8d4a43ee4104'
    assert len(snapshot['objects']) == 1226
    # Reserve full canopies, including trees moved aside for a widened road.
    occupied = occupied.buffer(7)
    for source in snapshot['objects']:
        x, h, y = [round(v/32) for v in source['position']]
        found = None
        for radius_cm in range(0, 1601, 20):
            for angle in range(0,360,30) if radius_cm else [0]:
                p = Point(round(x+radius_cm*math.cos(math.radians(angle))),
                          round(y+radius_cm*math.sin(math.radians(angle))))
                if bounds.contains(p.buffer(7)) and not occupied.intersects(p):
                    found = p; break
            if found is not None: break
        if found is None: raise ValueError('No space for retained tree '+source['id'])
        occupied = occupied.union(found.buffer(14))
        t.doc['placements'].append(dict(id='scaled-'+source['id'].replace(':','-'), asset_id=name,
            position=[round(found.x),h,round(found.y)],quarter_turns=source['quarter_turns']))
