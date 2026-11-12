"""Author-approved footprint cuts against retained carriageways, in source metres."""
import math
import shapely
from shapely.geometry import LineString, MultiPoint, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from osm_furniture import Furniture


def junction(arms, unit, joint):
    """Multi-arm exterior, including exposed offset intersections and fillets.

    Mouth hulls alone cut off the outside lane of a bend. Follow the shared
    road planner's exposed-mouth rule; an arm hidden inside the hull cannot
    create a new exterior lobe. Units are source metres per map centimetre.
    """
    # The native planner rounds displacement before adding the authored node.
    # Work in integer map centimetres so translated/negative coordinates cannot
    # change which mouths coincide, and thereby suppress a corner fillet.
    source_unit = unit
    def nearest(value):
        return int(math.copysign(math.floor(abs(value)+.5),value))
    arms = [(tuple(nearest(v/unit) for v in at),
             tuple(nearest(v/unit) for v in other), nearest(2*half/unit)/2, ids)
            for at,other,half,ids in arms]
    unit = 1
    joint = Furniture.__new__(Furniture)
    joint.scale = 1
    radius = max(a[2] for a in arms)
    round_value = nearest
    def point(x,y):return (nearest(x),nearest(y))
    mouths, directions = [], []
    for at, other, half, _ in arms:
        dx, dy = other[0]-at[0], other[1]-at[1]
        length = math.hypot(dx,dy)
        ux,uy = dx/length,dy/length
        directions.append((ux,uy,length))
        back = min(radius,length*.4)
        centre=(at[0]+nearest(ux*back),at[1]+nearest(uy*back))
        offset=point(-uy*half,ux*half)
        mouths.append([point(centre[0]+offset[0]*sign,centre[1]+offset[1]*sign) for sign in (-1,1)])
    points = [p for mouth in mouths for p in mouth]
    if all(u*directions[0][0]+v*directions[0][1]>.9999 for u,v,_ in directions):
        at=arms[0][0];ux,uy,_=directions[0]
        points += [(at[0]-ux*radius-uy*radius*sign,at[1]-uy*radius+ux*radius*sign) for sign in (-1,1)]
    hull = MultiPoint(points).convex_hull
    if hull.geom_type != "Polygon": return shapely.affinity.scale(hull,source_unit,source_unit,origin=(0,0))
    ring=list(hull.exterior.coords)[:-1]
    if not hull.exterior.is_ccw:ring.reverse()
    exposed={i for i,m in enumerate(mouths) if any(a in m and ring[(k+1)%len(ring)] in m for k,a in enumerate(ring))}
    corners=[]
    for k,a in enumerate(ring):
        c=ring[(k+1)%len(ring)]
        owner=next((i for i,m in enumerate(mouths) if a in m),0)
        corners.append((a,owner,True))
        cross_arm=next((i for i,m in enumerate(mouths) if a in m and c in m),None)
        if cross_arm is not None:
            ux,uy,length=directions[cross_arm]
            extra=min(radius+200*unit,length*.45)-min(radius,length*.4)
            corners += [(point(p[0]+round_value(ux*extra),p[1]+round_value(uy*extra)),cross_arm,False) for p in (a,c)]
            continue
        for ai in sorted(exposed):
            if a not in mouths[ai]:continue
            for bi in sorted(exposed):
                if c not in mouths[bi]:continue
                ux,uy,_=directions[ai];vx,vy,_=directions[bi]
                ux,uy,vx,vy=-ux,-uy,-vx,-vy
                det=ux*vy-uy*vx
                if abs(det)<1e-9:continue
                dx,dy=c[0]-a[0],c[1]-a[1]
                t=(dx*vy-dy*vx)/det;s=(dx*uy-dy*ux)/det
                if t < -1e-9 or s < -1e-9:continue
                p=point(a[0]+ux*t,a[1]+uy*t)
                if p!=a and p!=c:corners.append((p,ai,True))
                break
            else:continue
            break
    # Quantized coincident mouths have one corner. Keeping a zero-length
    # neighbour would suppress the native fillet at narrow, near-right bends.
    clean=[]
    for corner in corners:
        if clean and clean[-1][0]==corner[0]:clean.pop()
        clean.append(corner)
    if len(clean)>1 and clean[0][0]==clean[-1][0]:clean.pop()
    corners=clean
    rounded=[]
    for i,(p,owner,curve) in enumerate(corners):
        before,after=corners[i-1][0],corners[(i+1)%len(corners)][0]
        radius=min(max(.3*arms[owner][2],20*unit),100*unit)
        rounded.extend((joint._fillet(before,p,after,radius) or [p]) if curve else [p])
    polygon=Polygon(rounded)
    # Only the derived approach envelope is unioned; original source buildings
    # are never repaired. Native validation remains authoritative.
    polygon = polygon if polygon.is_valid else shapely.make_valid(polygon)
    return shapely.affinity.scale(polygon,source_unit,source_unit,origin=(0,0))


def corridors(roads, scale, source_ids):
    """Reuse city junction geometry; sidewalks and discarded source roads do not cut buildings."""
    shapes, sources, decks, ends = [], [], [], {}
    joint = Furniture.__new__(Furniture)
    joint.scale = scale / 100  # Its geometry helpers express map centimetres in the working units.
    def add(shape, identities, deck=None):
        if shape is not None and not shape.is_empty and shape.area > 0:
            # Mouth centres, offsets, intersections, tangencies and building
            # vertices round independently: five diagonal half-centimetres
            # fit within four map centimetres.
            # Bridge edge collision extends 20 map cm beyond the deck.
            shapes.append(shape.buffer((4 + (20 if deck and deck[4] in ("bridge","mixed_bridge") else 0)) * scale / 100, join_style="mitre"))
            sources.append(sorted(set(identities)))
            decks.append(deck)
    for f, g in roads:
        p = f["properties"]
        kind=p.get("_city_estimated_kind",p.get("road_kind", "ground"))
        if kind not in ("ground","bridge","elevated","tunnel"): continue
        points = list(g.coords)
        heights=p.get("elevations_m",p.get("_city_estimated_m",[float(p.get("elevation_m",0))]*len(points)))
        structural=kind != "ground"
        envelope_kind="tunnel" if kind == "tunnel" else "bridge"
        if kind == "tunnel":
            clearance=float(p.get("clearance_m",p.get("_city_estimated_clearance_m",4.5)))
            heights=[h+clearance for h in heights]
        widths = p.get("_city_widths_m") or [float(p.get("width_m", 8))] * (len(points)-1)
        identities = source_ids(f)
        for i, (a,b) in enumerate(zip(points,points[1:])):
            deck=(a,b,heights[i],heights[i+1],envelope_kind) if structural else None
            add(LineString([a,b]).buffer(widths[i]/2,cap_style="flat"),identities,deck)
        # MapKit triangulates a bend's fan between its neighbours' heights, so
        # a fan takes the highest neighbouring tunnel ceiling (lowest bridge deck).
        extreme=max if kind == "tunnel" else min
        for i in range(1,len(points)-1):
            fan=extreme(heights[i-1:i+2])
            add(junction([(points[i],points[i-1],widths[i-1]/2,identities),
                          (points[i],points[i+1],widths[i]/2,identities)],scale/100,joint),identities,
                (points[i],points[i],fan,fan,envelope_kind) if structural else None)
        refs = p.get("osm_node_refs",p.get("_city_point_refs",p.get("_city_refs",[])))
        for at, other, half, ref in ((points[0],points[1],widths[0]/2,refs[0] if refs else None),
                                     (points[-1],points[-2],widths[-1]/2,refs[-1] if refs else None)):
            key = ("ref",str(ref)) if ref is not None else ("point",at)
            height=extreme(heights[:2]) if at==points[0] else extreme(heights[-2:])
            ends.setdefault(key,[]).append((at,other,half,identities,height if structural else None,envelope_kind))
    for arms in ends.values():
        if len(arms)<2: continue
        identities = [s for a in arms for s in a[3]]
        heights=[a[4] for a in arms if a[4] is not None]
        # A mixed ground/structure junction cannot inherit the structure's
        # vertical exemption. Pure tunnel ceilings use the highest approach.
        tunnel=all(a[4] is not None and a[5]=="tunnel" for a in arms)
        bridge=all(a[4] is not None and a[5]=="bridge" for a in arms)
        height=max(heights) if tunnel else min(heights) if heights else 0
        deck=(arms[0][0],arms[0][0],height,height,"tunnel" if tunnel else "bridge") if tunnel or bridge else None
        if deck is None and any(a[4] is not None and a[5]=="bridge" for a in arms):
            deck=(arms[0][0],arms[0][0],height,height,"mixed_bridge")
        add(junction([a[:4] for a in arms],scale/100,joint),identities,deck)
    return shapes,sources,STRtree(shapes),decks,scale


def trim(geometry, index, building_top=math.inf, building_base=0):
    shapes,sources,tree,decks,scale=index
    overlapping,conflicting=[],set()
    for raw in tree.query(geometry):
        i=int(raw);overlap=geometry.intersection(shapes[i])
        if overlap.area<=1e-8:continue
        overlapping.append(i)
        deck=decks[i]
        if deck is not None:
            a,b,h0,h1,kind=deck;dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
            fractions=[min(1,max(0,((x-a[0])*dx+(y-a[1])*dy)/length)) if length else 0
                       for x,y in shapely.get_coordinates(overlap)]
            heights=[h0+(h1-h0)*t for t in fractions]
            if kind == "tunnel":
                if max(heights)+.5*scale <= building_base:continue
            elif kind == "bridge" and min(heights)>=building_top+.5*scale:continue
        conflicting.update(sources[i])
    # MapKit exempts a building above or below a structure only when every
    # overlapping face of that road clears it, so one conflicting piece cuts
    # every overlapping piece of the same road (no footprint left wrapped
    # around an exempt stretch).
    ids=[i for i in overlapping if conflicting.intersection(sources[i])]
    if not ids:return geometry,[],Polygon()
    result=geometry.difference(unary_union([shapes[i] for i in ids]))
    return result,sorted({s for i in ids for s in sources[i]}),geometry.difference(result)
