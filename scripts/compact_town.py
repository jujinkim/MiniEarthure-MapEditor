"""One-time authoring conversion of the town layout to actual game metres.

Shapely is used only by this optional authoring tool. MapKit remains the compiler
and final collision validator. Runtime never rescales a custom map.
"""
import math
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union, nearest_points


def compact(t):
    d = t.doc
    d['recipe_version'] = 5
    # Re-space the seven glove turns in their district before widening the road.
    finger = {r['id'] for r in d['roads'] if r['id'].startswith(('kart-finger-', 'kart-thumb-'))}
    moved = {}
    adjusted_nodes = {}
    adjusted_tangents = {}
    expanded_arcs = set()
    def point(p, ident=''):
        x, h, y = p
        if ident in finger and x > 330000:
            y = 466000 + (y - 491000) * 1.6
        return [round(x / 32), round(h / 32), round(y / 32)]
    for r in d['roads']:
        r['points'] = [point(p, r['id']) for p in r['points']]
        if r['id'].startswith(('kart-finger-tip-', 'kart-finger-inside-')):
            cx = r['points'][0][0]
            for p in r['points']: p[0] = round(cx + (p[0] - cx) * 1.6)
        r['widths_cm'] = [round(w / 4) for w in r['widths_cm']]
        if r['id'].startswith(('kart-freeway-', 'kart-thumb-')) and len(r['points']) >= 5:
            # Preserve circular corners, expanding tight radii to contain the
            # wider carriageway. Adjacent graph endpoints move with the arc.
            ps = r['points']
            a,b,c = [ps[i] for i in (0,len(ps)//3,2*len(ps)//3)]
            ax,ay,bx,by,cx,cy = a[0],a[2],b[0],b[2],c[0],c[2]
            det = 2*(ax*(by-cy)+bx*(cy-ay)+cx*(ay-by))
            if abs(det)>1:
                ux=((ax*ax+ay*ay)*(by-cy)+(bx*bx+by*by)*(cy-ay)+(cx*cx+cy*cy)*(ay-by))/det
                uy=((ax*ax+ay*ay)*(cx-bx)+(bx*bx+by*by)*(ax-cx)+(cx*cx+cy*cy)*(bx-ax))/det
                radius=math.hypot(ax-ux,ay-uy)
                minimum=max(r['widths_cm'])/2+80
                if radius<minimum and all(abs(math.hypot(p[0]-ux,p[2]-uy)-radius)<3 for p in ps):
                    for p in ps:
                        p[0]=round(ux+(p[0]-ux)*minimum/radius)
                        p[2]=round(uy+(p[2]-uy)*minimum/radius)
                    adjusted_nodes[r['from']]=ps[0]
                    adjusted_nodes[r['to']]=ps[-1]
                    sign = 1 if (ps[0][0]-ux)*(ps[1][2]-uy)-(ps[0][2]-uy)*(ps[1][0]-ux)>0 else -1
                    adjusted_tangents[r['from']] = (sign*(ps[0][2]-uy),-sign*(ps[0][0]-ux))
                    adjusted_tangents[r['to']] = (-sign*(ps[-1][2]-uy),sign*(ps[-1][0]-ux))
                    expanded_arcs.add(r['id'])
        r['sidewalk_cm'] = 0
        if r.get('clearance_cm') is not None: r['clearance_cm'] = max(45, round(r['clearance_cm'] / 32))
        # The RC chassis is unchanged: retain a safe bridge deck height.
        if r['id'].startswith('kart-finger-bridge'):
            for p in r['points']: p[1] = round(p[1] * 4)
        moved[r['from']] = r['points'][0]
        moved[r['to']] = r['points'][-1]
    # The two exit corners originally shared a short horizontal link. Expanding
    # their radii independently would turn that link into an impossible 5 m-wide
    # S bend. Move the second corner down to retain the horizontal approach.
    exit_corner = next(r for r in d['roads'] if r['id'] == 'kart-freeway-exit-left')
    descent_corner = next(r for r in d['roads'] if r['id'] == 'kart-freeway-descent-entry')
    shift = exit_corner['points'][-1][2] - descent_corner['points'][0][2]
    for p in descent_corner['points']: p[2] += shift
    adjusted_nodes[descent_corner['from']] = descent_corner['points'][0]
    adjusted_nodes[descent_corner['to']] = descent_corner['points'][-1]
    moved.update(adjusted_nodes)
    kink = next(r for r in d['roads'] if r['id'] == 'kart-freeway-highway-kink')
    start = moved[kink['from']]
    dx,dy = adjusted_tangents[kink['from']]
    norm = math.hypot(dx,dy)
    moved[kink['to']] = [round(start[0]+dx*1000/norm),start[1],round(start[2]+dy*1000/norm)]
    for n in d['nodes']: n['position'] = moved.get(n['id'], point(n['position']))
    for r in d['roads']:
        r['points'][0] = moved[r['from']]
        r['points'][-1] = moved[r['to']]
        if r['id'] in expanded_arcs: continue
        if r['id'] in ('kart-freeway-highway-kink', 'kart-freeway-exit-link'):
            r['points'] = [r['points'][0],r['points'][-1]]
            r['widths_cm'] = [max(r['widths_cm'])]
            r['surfaces'] = [r['surfaces'][0]]
            continue
        if r['from'] not in adjusted_tangents and r['to'] not in adjusted_tangents: continue
        ps = r['points']
        width = max(r['widths_cm'])
        length = math.hypot(ps[-1][0]-ps[0][0],ps[-1][2]-ps[0][2])
        reach = length/3
        controls = []
        for node,p,other in [(r['from'],ps[0],ps[-1]),(r['to'],ps[-1],ps[0])]:
            dx,dy=adjusted_tangents.get(node,(other[0]-p[0],other[2]-p[2])); norm=math.hypot(dx,dy)
            controls.append((p[0]+dx*reach/norm,p[2]+dy*reach/norm))
        points=[]
        for i in range(7):
            u=i/6;v=1-u
            height_u=max(0,min(1,(u-1/6)/(4/6)))
            points.append([round(v**3*ps[0][0]+3*v*v*u*controls[0][0]+3*v*u*u*controls[1][0]+u**3*ps[-1][0]),
                round(ps[0][1]+height_u*(ps[-1][1]-ps[0][1])),
                round(v**3*ps[0][2]+3*v*v*u*controls[0][1]+3*v*u*u*controls[1][1]+u**3*ps[-1][2])])
        r['points'] = points
        r['widths_cm'] = [width]*(len(r['points'])-1)
        r['surfaces'] = [r['surfaces'][0]]*(len(r['points'])-1)
    # Leave a full-width level approach at the wrist's three-way junction.
    # Keep both bridge crests, with RC-scale heights and room for the arch.
    bridge_in = next(r for r in d['roads'] if r['id'] == 'kart-finger-bridge-in')
    clock = next(r for r in d['roads'] if r['id'] == 'kart-finger-clock-tower')
    bridge_out = next(r for r in d['roads'] if r['id'] == 'kart-finger-bridge-out')
    bridge_in['points'][-2][2] = bridge_in['points'][-1][2] - 300
    clock['points'][-1][2] += 100
    # Endpoints share the graph's lists; keep its node record exact as well.
    bridge_out['points'][0] = clock['points'][-1]
    bridge_out['points'][1][2] = bridge_out['points'][0][2] + 200
    for n in d['nodes']:
        if n['id'] == clock['to']: n['position'] = clock['points'][-1]
    for r in (bridge_in, bridge_out):
        for p in r['points']: p[1] = round(p[1] / 2)
    d['bounds']['max'] = [19200, 19200]
    d['cell_size_cm'] = 1600
    for h in d['heightmaps']: h['spacing_cm'] = 400
    corridors = []
    for r in d['roads']:
        # Mitres bound the compiler's planar strip at bends, including endpoints.
        line = LineString([(p[0], p[2]) for p in r['points']])
        corridors.append(line.buffer(max(r['widths_cm']) / 2 + 3, cap_style=3, join_style=2))
    occupied = unary_union(corridors)
    bounds = Polygon([(0,0),(19200,0),(19200,19200),(0,19200)])
    # Retain every city/home landmark; fit small footprints within widened blocks.
    buildings = []
    for b in d['buildings']:
        if '-rail-' in b['id']: continue
        poly = Polygon([(round(x/32), round(y/32)) for x,y in b['footprint']])
        cx, cy = poly.centroid.coords[0]
        if '-cylinder-' in b['id']:
            if b['id'].startswith(('kart-finger-', 'kart-thumb-')): cy = (466000 + (cy*32 - 491000)*1.6)/32
            poly = Point(cx,cy).buffer(10, quad_segs=12)
        if b['id'].startswith('city-block-'):
            _, _, i, j, k = b['id'].split('-')
            x, y = (3300+int(i)*220)*100/32, (400+int(j)*220)*100/32
            cx, cy = x+289+(int(k)%2)*109, y+289+(int(k)//2)*109
            poly = Polygon([(cx-35,cy-35),(cx+35,cy-35),(cx+35,cy+35),(cx-35,cy+35)])
        # Search nearby vacant space without dropping the building.
        from shapely.affinity import translate
        placed = None
        for radius in range(0, 1601, 20):
            for angle in range(0, 360, 15) if radius else [0]:
                candidate = translate(poly, radius*math.cos(math.radians(angle)), radius*math.sin(math.radians(angle)))
                if bounds.contains(candidate) and not occupied.intersects(candidate):
                    placed = candidate; break
            if placed is not None: break
        if placed is None: raise ValueError('No safe position for ' + b['id'])
        b['footprint'] = [[round(x), round(y)] for x,y in list(placed.exterior.coords)[:-1]]
        b['base_cm'] = round(b['base_cm']/32)
        b['height_cm'] = max(1, round(b['height_cm']/32))
        if '-cylinder-' in b['id']: b['height_cm'] = max(28, b['height_cm'])
        occupied = occupied.union(placed.buffer(3))
        buildings.append(b)
    # Continuous widened track boundaries replace the old narrow rails. Every
    # segment is a solid prism; road corridors are subtracted at access mouths.
    roads_union = unary_union(corridors)
    rails = []
    for r in d['roads']:
        for a,b in zip(r['points'],r['points'][1:]):
            line = LineString([(a[0],a[2]),(b[0],b[2])])
            rails.append((r, line.buffer(max(r['widths_cm'])/2+3, cap_style=2, join_style=2)))
    for section, (r, corridor) in enumerate(rails):
        if not r['id'].startswith(('kart-freeway-', 'kart-finger-', 'kart-thumb-')) or 'access' in r['id'] or 'shortcut' in r['id']: continue
        boundary = corridor.buffer(10, join_style=2).difference(roads_union.buffer(3)).difference(occupied)
        parts = list(boundary.geoms) if hasattr(boundary, 'geoms') else [boundary]
        for i, poly in enumerate(parts):
            if poly.geom_type != 'Polygon' or poly.area < 10: continue
            ring = [[round(x), round(y)] for x,y in list(poly.exterior.coords)[:-1]]
            if len(set(map(tuple,ring))) != len(ring): continue
            if not Polygon(ring).is_valid or Polygon(ring).area < 1: continue
            holes = [[[round(x),round(y)] for x,y in list(h.coords)[:-1]] for h in poly.interiors]
            b = dict(id=r['id']+'-rail-'+str(section)+'-'+str(i), footprint=ring, base_cm=min(p[1] for p in r['points'])-2,
                height_cm=max(p[1] for p in r['points'])-min(p[1] for p in r['points'])+28,
                usage='industrial', material='concrete', roof='flat')
            if holes: b['holes'] = holes
            buildings.append(b)
            occupied = occupied.union(poly.buffer(3))
    d['buildings'] = buildings
    for z in d['zones']:
        z['polygon'] = [[round(x/32), round(y/32)] for x,y in z['polygon']]
        z['spacing_cm'] = max(25, round(z['spacing_cm']/32))
        # Preserve the original generated trees as scaled authored models below.
        # A default built-in tree is 4 m tall in actual-metre custom documents.
        z['density_per_mille'] = 0
    # Scale both glTF meshes and their authored convex collision together.
    from driving_school_map import glb, box, oriented_faces
    for asset in d['assets']:
        solids = []
        for convex in asset['convex_collision']:
            convex['vertices'] = [[round(v/32) for v in p] for p in convex['vertices']]
            convex['faces'] = oriented_faces(convex['vertices'])
            solids.append(([tuple(v/100 for v in p) for p in convex['vertices']], (1,0.66,0.08,1)))
        t.payloads[asset['path']] = glb(solids)
    for placement in d['placements']:
        p = point(placement['position'])
        spot = Point(p[0], p[2])
        if occupied.buffer(10).contains(spot):
            free = bounds.difference(occupied.buffer(12))
            x,y = nearest_points(spot, free)[1].coords[0]
            p[0],p[2] = round(x),round(y)
        placement['position'] = p
    from compact_vegetation import place_vegetation
    place_vegetation(t, bounds, occupied)
    for location in t.locations:
        location['position_cm'] = point(location['position_cm'], location['surface_id'])
        road = next(r for r in d['roads'] if r['id'] == location['surface_id'])
        line = LineString([(p[0],p[2]) for p in road['points']])
        distance = line.project(Point(location['position_cm'][0], location['position_cm'][2]))
        apron = min(line.length/2, max(road['widths_cm'])/2+80)
        q = line.interpolate(max(apron,min(line.length-apron,distance)))
        location['position_cm'][0],location['position_cm'][2] = round(q.x),round(q.y)
        distance = line.project(q)
        for a,b in zip(road['points'], road['points'][1:]):
            length = math.hypot(b[0]-a[0], b[2]-a[2])
            if distance <= length + 0.001:
                location['position_cm'][1] = round(a[1] + (b[1]-a[1])*distance/length)
                location['heading_degrees'] = round(-math.degrees(math.atan2(b[0]-a[0],b[2]-a[2])),3)
                break
            distance -= length
        location['title'] = location['title'].replace('2km', '62.5m')
        location['purpose'] = location['purpose'].replace('2.2 × 2.2km', '68.75 × 68.75m').replace('470m', '14.69m').replace('반경 170m / 폭 20m', '반경 5.31m / 폭 5m').replace('반경 90m, 폭 12m', '반경 2.81m, 폭 3m').replace('높이 20m, 길이 650m', '높이 0.625m, 길이 20.31m').replace('반경 45m U턴 / 34.7m 원통형 충돌 벽', '확장한 U턴과 원통형 안쪽 벽').replace('폭 10m', '폭 2.5m')
    for route in t.routes: route['title'] = route['title'].replace('2km', '62.5m')


def atlas(t, kind=None):
    """Exact authored metres, with road width and height distinctions to scale."""
    prefix = ('kart-freeway-',) if kind == 'freeway' else ('kart-finger-', 'kart-thumb-') if kind else None
    box = (100,95,80,48) if kind == 'freeway' else (100,142,80,42) if kind else (0,0,192,192)
    x,y,w,h = box
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{round(h/w*1200)}" viewBox="{x} {y} {w} {h}">',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#849879"/>']
    for r in t.doc['roads']:
        if prefix and not r['id'].startswith(prefix): continue
        points = ' '.join(f'{p[0]/100},{p[2]/100}' for p in r['points'])
        color = '#d4a64e' if any(p[1] > 0 for p in r['points']) else '#35443f'
        parts.append(f'<polyline points="{points}" stroke="{color}" stroke-width="{r["widths_cm"][0]/100}" stroke-linejoin="round" fill="none"/>')
    for b in t.doc['buildings']:
        if prefix and not b['id'].startswith(prefix): continue
        points = ' '.join(f'{p[0]/100},{p[1]/100}' for p in b['footprint'])
        color = '#c49474' if '-rail-' not in b['id'] else '#cad0bd'
        parts.append(f'<polygon points="{points}" fill="{color}"/>')
    parts.append('</svg>')
    return '\n'.join(parts)+'\n'
