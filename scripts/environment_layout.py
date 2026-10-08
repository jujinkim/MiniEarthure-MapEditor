"""Editor composition geometry; deterministic, metre-scale, MIT.

No product schema additions. Districts and the unsplit road hierarchy are
authoring metadata; ordinary v1 roads remain the only runtime transport geometry.
"""
import hashlib
import heapq
import math
import random

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union, substring
from reference_maps import canonical


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def rng(seed, *keys):
    return random.Random(int(digest([seed, *keys])[:16], 16))


def polygons(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "Polygon": return [geometry]
    return [p for child in getattr(geometry, "geoms", []) for p in polygons(child)]


def lines(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "LineString": return [geometry]
    return [p for child in getattr(geometry, "geoms", []) for p in lines(child)]


def xy(point): return [round(point[0]*100), round(point[1]*100)]


def rings(poly):
    return [xy(p) for p in list(poly.exterior.coords)[:-1]], [[xy(p) for p in list(h.coords)[:-1]] for h in poly.interiors]


def polygon(record, key="polygon", holes="holes"):
    return Polygon([(p[0]/100,p[1]/100) for p in record[key]],
                   [[(p[0]/100,p[1]/100) for p in h] for h in record.get(holes,[])])


def geometry_record(area):
    return [dict(zip(("polygon","holes"), rings(p))) for p in polygons(area)]


def districts(g):
    if not g.new_layout:
        return [dict(id=r['id'],landuse=r['landuse'],geometry=polygon(r).intersection(g.window),
                     anchor=polygon(r).representative_point().coords[0],core=False,density=(.3,.6),groups=())
                for r in g.context.regions if not r.get('protected')]
    x,y,X,Y=g.world.bounds;w,h=X-x,Y-y
    result=[];land=g.world.difference(g.water.buffer(8))
    for rule in g.profile.districts:
        random=rng(g.request.seed,'district',rule.id)
        centre=(x+w*(rule.anchor[0]+random.uniform(-.012,.012)),y+h*(rule.anchor[1]+random.uniform(-.012,.012)))
        # Prefer dry, gentler nearby ground without moving the whole town when
        # another district's seed stream changes.
        choices=[(centre[0]+dx,centre[1]+dy) for dx,dy in ((0,0),(-24,0),(24,0),(0,-24),(0,24))]
        def cost(p):
            slope=math.hypot(g.raw_height(p[0]+8,p[1])-g.raw_height(p[0]-8,p[1]),g.raw_height(p[0],p[1]+8)-g.raw_height(p[0],p[1]-8))/16
            return (0 if land.covers(Point(p)) else 10000)+slope*80+Point(p).distance(Point(centre))*.15
        centre=min(choices,key=cost)
        area=affinity.scale(Point(centre).buffer(1,quad_segs=16),w*rule.radii[0],h*rule.radii[1])
        result.append(dict(id=rule.id,landuse=rule.landuse,anchor=centre,geometry=area,
                           core=rule.core,density=rule.density,groups=rule.groups))
    if g.profile.road_mode=='hierarchy':
        # Area is measured on the land union, not the sum of overlapping ellipses.
        for _ in range(6):
            core=unary_union([d['geometry'] for d in result if d['core']]).intersection(land)
            factor=math.sqrt(.265*land.area/max(1,core.area))
            for d in result:
                if d['core']: d['geometry']=affinity.scale(d['geometry'],factor,factor,origin=d['anchor'])
    occupied=Polygon()
    for d in result:
        d['geometry']=d['geometry'].intersection(land).difference(occupied)
        occupied=unary_union([occupied,d['geometry']])
    return result


def slope_path(g, start, end, obstacles=None):
    """Bounded A* with slope and deviation cost, then a conservative simplifier."""
    if Point(start).distance(Point(end))<48: return LineString([start,end])
    direct=LineString([start,end]);step=32
    corridor=direct.buffer(110,cap_style=3).intersection(g.world.buffer(-24))
    forbidden=g.water.buffer(12) if obstacles is None else obstacles
    ox,oy=direct.bounds[:2]
    def cell(p): return (round((p[0]-ox)/step),round((p[1]-oy)/step))
    a,b=cell(start),cell(end)
    def point(c): return start if c==a else end if c==b else (ox+c[0]*step,oy+c[1]*step)
    queue=[(0,0,a)];costs={a:0};previous={};closed=set()
    while queue and len(closed)<6000:
        _,cost,node=heapq.heappop(queue)
        if node in closed: continue
        if node==b: break
        closed.add(node);p=point(node)
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nxt=(node[0]+dx,node[1]+dy);q=point(nxt)
            edge=LineString([p,q]);length=edge.length
            if length<.1 or not corridor.covers(Point(q)) or edge.intersects(forbidden): continue
            grade=abs(g.raw_height(*q)-g.raw_height(*p))/length
            value=cost+length*(1+grade*12+max(0,grade-.12)*80)+direct.distance(Point(q))*.08
            if value>=costs.get(nxt,float('inf')): continue
            costs[nxt]=value;previous[nxt]=node
            heapq.heappush(queue,(value+Point(q).distance(Point(end)),value,nxt))
    if b not in costs: raise ValueError('No terrain-safe connection between district anchors')
    points=[point(b)];node=b
    while node!=a: node=previous[node];points.append(point(node))
    path=LineString(points[::-1])
    simplified=path.simplify(18)
    return simplified if not simplified.intersects(forbidden) else path


def plan_paths(g):
    x,y,X,Y=g.world.bounds;w,h=X-x,Y-y
    paths=[]
    def add(points,role,width,kind='ground'):
        line=points if isinstance(points,LineString) else LineString(points)
        if line.length>1: paths.append(dict(geometry=line,role=role,width=width,kind=kind))
    if g.profile.road_mode=='loop':
        # One nonrectangular loop, anchored on the landscape rather than edges.
        staging=[(x+w*.33,y+h*.80),(x+w*.33+260,y+h*.80)]
        anchors=[staging[0],(x+w*.20,y+h*.59),(x+w*.24,y+h*.35),
                 (x+w*.42,y+h*.22),(x+w*.65,y+h*.32),(x+w*.63,y+h*.53),
                 (x+w*.57,y+h*.71),staging[1]]
        segments=[slope_path(g,a,b) for a,b in zip(anchors,anchors[1:])]
        loop=LineString([p for line in segments for p in list(line.coords)[:-1]]+[staging[1]])
        add(loop,'main',6);add(staging,'main',6)
        targets=[d['anchor'] for d in g.districts if d['core']]
        # Two facility accesses and one entry; branch count ignores density.
        targets=targets[:2]+[(x+w*.19,y+h*.77)]
        for target in targets:
            road_point=loop.interpolate(loop.project(Point(target)))
            if road_point.distance(Point(target))<60:
                dx,dy=target[0]-road_point.x,target[1]-road_point.y
                length=max(.1,math.hypot(dx,dy))
                target=(road_point.x+dx/length*90,road_point.y+dy/length*90)
            add(slope_path(g,road_point.coords[0],target),'access',4)
    else:
        cores=[d for d in g.districts if d['core']]
        # A compact hierarchy ties district centres together. No perimeter road.
        staging=[(x+w*.24,y+h*.81),(x+w*.24+260,y+h*.81)]
        add(staging,'arterial',10)
        centers=[d['anchor'] for d in cores]
        for a,b in zip(centers,centers[1:]): add(slope_path(g,a,b),'arterial',12)
        add(slope_path(g,staging[0],centers[0]),'arterial',10)
        add(slope_path(g,staging[1],centers[-1]),'connector',8)
        for d in g.districts:
            if d['geometry'].is_empty: continue
            cx,cy=d['anchor'];a,b,A,B=d['geometry'].bounds
            spacing=120 if d['landuse'] in ('industrial','recreation_ground') else 94
            # The field only determines direction inside this district.
            angle=g.tensor(cx,cy);c,s=math.cos(angle),math.sin(angle)
            extent=max(A-a,B-b)
            local=[]
            for offset in range(-math.ceil(extent/spacing),math.ceil(extent/spacing)+1):
                if not d['core'] and offset!=0: continue
                for minor in (False,True):
                    if not d['core'] and minor: continue
                    theta=angle+(math.pi/2 if minor else 0);u,v=math.cos(theta),math.sin(theta)
                    mid=(cx-v*offset*spacing,cy+u*offset*spacing)
                    ray=LineString([(mid[0]-u*extent,mid[1]-v*extent),(mid[0]+u*extent,mid[1]+v*extent)])
                    for line in lines(ray.intersection(d['geometry'].buffer(-20))):
                        if line.length<48: continue
                        local.append(line)
                        add(line,'connector' if offset==0 else 'service',8 if offset==0 else 5)
            if not d['core']:
                nearest=min(centers,key=lambda p:Point(p).distance(Point(d['anchor'])))
                add(slope_path(g,nearest,d['anchor']),'connector',6)
        if g.profile.id=='neon-harbor':
            # A working waterfront bridge has two dry approaches and a basin span.
            a=(x+w*.73,y+h*.18);b=(x+w*.73,y+h*.72);cx=x+w*.825
            add([centers[0],a],'connector',8)
            add([a,(cx,a[1]),(cx,b[1]),b],'connector',8,'bridge')
            add([b,centers[0]],'connector',8)
        if g.profile.id=='sky-park':
            # A supported high promenade with long, gentle approach ramps.
            a=(x+w*.22,y+h*.31);b=(x+w*.76,y+h*.31)
            add([centers[1],a],'connector',8)
            add([a,(a[0],a[1]-120),(b[0],a[1]-120),b],'promenade',6,'elevated')
            add([b,centers[1]],'connector',8)
    # Low ramps reserve a corridor. Local streets stop outside it instead of
    # crossing through a deck with insufficient vehicle clearance.
    structures=[p for p in paths if p['kind']!='ground']
    if structures:
        ramps=unary_union([part.buffer(12,cap_style=2) for p in structures for part in
            (substring(p['geometry'],0,min(75,p['geometry'].length/2)),
             substring(p['geometry'],max(0,p['geometry'].length-75),p['geometry'].length))])
        paths=[{**p,'geometry':part} for p in paths for part in
               (lines(p['geometry'].difference(ramps)) if p['kind']=='ground' and p['role']=='service' else [p['geometry']]) if part.length>2]
    # Connect the projected spur endpoints exactly before quantized noding.
    network=unary_union([p['geometry'] for p in paths])
    network=shapely.union_all([network],grid_size=.01)
    segments=lines(network)
    if g.profile.road_mode=='hierarchy':
        # A clipped ellipse may leave an isolated short street at its rim. It
        # has no frontage yet: discard that remnant before assigning parcels.
        adjacency={}
        for i,line in enumerate(segments):
            for p in (line.coords[0],line.coords[-1]): adjacency.setdefault(tuple(xy(p)),[]).append(i)
        components=[];seen=set()
        for i in range(len(segments)):
            if i in seen: continue
            stack=[i];part=[];seen.add(i)
            while stack:
                j=stack.pop();part.append(j)
                for p in (segments[j].coords[0],segments[j].coords[-1]):
                    for k in adjacency[tuple(xy(p))]:
                        if k not in seen: seen.add(k);stack.append(k)
            components.append(part)
        if len(components)>1:
            main=max(components,key=lambda c:sum(segments[i].length for i in c))
            g.diagnostics.append(dict(stage='roads',discarded_rim_fragments=sum(len(c) for c in components if c is not main)))
            segments=[segments[i] for i in main]
    return paths,segments
