"""Acceptance measurements from emitted geometry, never object-count proxies."""
from collections import Counter, defaultdict, deque
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from environment_layout import geometry_record, polygon, xy
from asset_derivatives import unpack


def topology(document):
    adjacent=defaultdict(list)
    for road in document['roads']:
        adjacent[road['from']].append((road['to'],road['id']))
        adjacent[road['to']].append((road['from'],road['id']))
    visited=set();components=0
    for node in adjacent:
        if node in visited: continue
        components+=1;queue=[node];visited.add(node)
        while queue:
            for other,_ in adjacent[queue.pop()]:
                if other not in visited: visited.add(other);queue.append(other)
    return dict(components=components,cycle_rank=len(document['roads'])-len(adjacent)+components,
                junctions=sum(len(edges)>2 for edges in adjacent.values()),
                dead_ends=sum(len(edges)==1 for edges in adjacent.values())),adjacent


def road_route(document, first, last):
    roads={r['id']:r for r in document['roads']}
    if first not in roads or last not in roads: return []
    if first==last: return [first]
    _,graph=topology(document)
    queue=deque([(roads[first]['from'],[first]),(roads[first]['to'],[first])]);seen=set()
    while queue:
        node,path=queue.popleft()
        if node in (roads[last]['from'],roads[last]['to']): return path+[last]
        if node in seen: continue
        seen.add(node)
        for other,key in graph[node]:
            if other not in seen: queue.append((other,path+[key]))
    return []


def measure(g):
    errors=[];issues=[];metrics={}
    def fail(message,site=None):
        errors.append(message)
        if site: issues.append(dict(stage='composition',error=message,id=site['id'],district=site.get('district',''),position_cm=xy(site['anchor'])))
        else: issues.append(dict(stage='composition',error=message,position_cm=xy(g.window.centroid.coords[0])))
    doc=g.doc;assets={a['id']:a for a in doc['assets']};placed={p['id']:p for p in doc['placements']}
    footprints={}
    for key,p in placed.items():
        if p['asset_id'] in assets:
            footprints[key]=g.footprint(assets[p['asset_id']],(p['position'][0]/100,p['position'][2]/100),p.get('quarter_turns',0)*90+p.get('yaw_offset_mdeg',0)/1000)
    graph,_=topology(doc);metrics['road_graph']=graph
    grades=[];staging=[]
    for road,line in zip(doc['roads'],g.road_lines):
        for a,b in zip(road['points'],road['points'][1:]):
            length=math.hypot(b[0]-a[0],b[2]-a[2])
            grades.append(abs(b[1]-a[1])/max(1,length))
        if road['kind']=='ground' and line.length>=200:
            for offset in range(0,max(1,int(line.length)-199),20):
                a,b=line.interpolate(offset),line.interpolate(offset+200)
                chord=LineString([a,b])
                deviation=max(chord.distance(line.interpolate(offset+d)) for d in range(0,201,10))
                if deviation<.08 and a.distance(b)>=199.95:
                    staging.append(dict(road_id=road['id'],start_m=offset,length_m=200));break
    metrics['max_road_grade']=round(max(grades,default=0),5)
    metrics['staging_straights']=staging
    crossings=0
    if g.request.mode=='new':
        tree=STRtree(g.road_lines)
        def level(road,line,point):
            distance=line.project(point);along=0
            for a,b in zip(road['points'],road['points'][1:]):
                length=math.hypot(b[0]-a[0],b[2]-a[2])/100
                if along+length>=distance: return (a[1]+(b[1]-a[1])*(distance-along)/max(.01,length))/100
                along+=length
            return road['points'][-1][1]/100
        for i,(road,line) in enumerate(zip(doc['roads'],g.road_lines)):
            for j in tree.query(line):
                if j<=i: continue
                other=doc['roads'][j]
                if set((road['from'],road['to'])) & set((other['from'],other['to'])): continue
                point=line.intersection(g.road_lines[j])
                if point.geom_type!='Point': continue
                crossings+=1
                if abs(level(road,line,point)-level(other,g.road_lines[j],point))<3:
                    fail('Unjoined or low-clearance crossing: '+road['id']+' / '+other['id'])
    metrics['grade_separated_crossings']=crossings
    if g.request.mode=='new':
        if graph['components']!=1: fail('Road graph is disconnected')
        if max(grades,default=0)>.1205: fail('Road grade exceeds 12 percent')
        if not staging: fail('No grounded 200 m launch straight')
        if g.profile.road_mode=='loop':
            if graph['cycle_rank']!=1 or not 2<=graph['dead_ends']<=4 or graph['junctions']!=graph['dead_ends']:
                fail('Wilderness requires one loop and 2–4 access branches')
    land=g.window.difference(g.water)
    core=unary_union([d['geometry'] for d in g.districts if d['core']]).intersection(land)
    metrics['core_land_fraction']=round(core.area/max(1,land.area),5)
    if g.request.mode=='new' and g.profile.road_mode=='hierarchy' and not .20<=metrics['core_land_fraction']<=.35:
        fail('Urban core must cover 20–35 percent of land')
    developed=unary_union([g.road_space,*[s['geometry'] for s in g.sites if s['landuse'] not in ('forest','scrub','grassland','bare_rock','farmland','park')]])
    metrics['natural_land_fraction']=round(land.difference(developed).area/max(1,land.area),5)
    if g.request.mode=='new' and metrics['natural_land_fraction']<g.profile.natural_minimum:
        fail('Natural/green/field space below theme minimum')
    occupancy=[];frontages=defaultdict(list);access_count=0
    for site in g.sites:
        present=[key for key in site['objects'] if key in footprints]
        rule=next(r for r in g.profile.rules if r.id==site['group'])
        if rule.access and present:
            if not site.get('road_id') or site['entrance'].is_empty or site['entrance'].distance(g.road_union)>.05*g.scale:
                if not site.get('retained'): fail('Entrance does not reach a road: '+site['id'],site)
            for key in [key for key in present if '-crop-' not in key]:
                if site['entrance'].distance(footprints[key])>.06*g.scale and not site.get('retained'):
                    fail('Required member has no access: '+key,site)
            access_count+=sum('-crop-' not in key for key in present)
        counted=[key for key in present if any(word in placed[key]['asset_id'] for word in ('home-','market-','hall-','lodge-','house-','shop-','shed-','nord-'))]
        if site['composition']=='frontage' and site['landuse'] in ('residential','commercial') and counted:
            low,high=.30,.55
        elif site['group'] in ('production','warehouse','logistics') and counted:
            low,high=.25,.45
            counted=present # Fixed working equipment contributes alongside halls.
        else: continue
        occupied=unary_union([footprints[key] for key in counted]).intersection(site['geometry']).area
        ratio=occupied/max(.01,site['geometry'].area)
        occupancy.append(dict(id=site['id'],district=site.get('district'),landuse=site['landuse'],plot_m2=round(site['geometry'].area,2),occupied_m2=round(occupied,2),ratio=round(ratio,4),target=[low,high]))
        if g.request.mode=='new' and g.request.density==1 and not low-.005<=ratio<=high+.005:
            fail('Parcel occupancy outside target: '+site['id'],site)
        if len(counted)==1 and 'frontage' in site:
            key=site['frontage'][:2];frontages[tuple(key)].append((site['frontage'][2],placed[counted[0]]['asset_id'],site))
    metrics['parcel_occupancy']=occupancy;metrics['accessed_members']=access_count
    repetitions=0
    for values in frontages.values():
        values.sort(key=lambda p:p[0])
        for a,b,c in zip(values,values[1:],values[2:]):
            if a[1]==b[1]==c[1]: repetitions+=1;fail('Three repeated frontage silhouettes',b[2])
    metrics['triple_frontage_repetitions']=repetitions
    # Relations use the real road graph and member access, including working
    # facilities and attraction/queue connections. No synthetic count shortcut.
    relationships=[]
    for site in g.sites:
        rule=next(r for r in g.profile.rules if r.id==site['group'])
        if not site.get('required') or not site.get('road_id'): continue
        for group in rule.adjacent:
            others=[s for s in g.sites if s['group']==group and s.get('road_id')]
            if not others: continue
            other=min(others,key=lambda s:Point(s['anchor']).distance(Point(site['anchor'])))
            route=road_route(doc,site['road_id'],other['road_id'])
            if not route: fail('Disconnected facility relationship: '+site['group']+' → '+group,site)
            relationships.append(dict(source=site['id'],target=other['id'],road_ids=route,
                access_paths=[site.get('access_lines',[]),other.get('access_lines',[])],district=site.get('district')))
    g.relationships=relationships;metrics['relationships']=len(relationships)
    if g.profile.id=='sky-park':
        plazas=[s for s in g.sites if s['group']=='plaza']
        metrics['plaza_open_fraction']=min((s['geometry'].difference(unary_union([footprints[key] for key in s['objects'] if key in footprints])).area/s['geometry'].area for s in plazas),default=0)
        if g.request.mode=='new' and metrics['plaza_open_fraction']<.8: fail('Amusement plaza must remain at least 80 percent open')
    metrics['habitat_areas_m2']={h['id']:round(h['geometry'].area,2) for h in g.habitats}
    if g.request.mode=='new' and (len(g.habitats)<4 or metrics['habitat_areas_m2'].get('transition',0)<=0): fail('Theme needs three landscapes and transitions')
    # Rank every touched cell by physical proxy/triangle cost, then include
    # terrain/roads/surface geometry. Large solids contribute to all touched cells.
    cell_cost=defaultdict(lambda:[0,0,0])
    visual={}
    for key,record in assets.items():
        payload=g.payloads.get(record['path'])
        if payload is None and g.context.project:
            source=Path(g.context.project)/record['path']
            if source.is_file(): payload=source.read_bytes()
        if payload and record['path'].endswith('.glb'):
            gltf,_=unpack(payload)
            visual[key]=sum(gltf['accessors'][p.get('indices',p['attributes']['POSITION'])]['count']//3
                for mesh in gltf.get('meshes',[]) for p in mesh['primitives'])
    def cells(area):
        a,b,A,B=area.bounds;ox,oy=(v/100 for v in doc['bounds']['min']);step=doc['cell_size_cm']/100
        return [(ix,iy) for ix in range(max(0,math.floor((a-ox)/step)),math.floor((A-ox)/step)+1)
                for iy in range(max(0,math.floor((b-oy)/step)),math.floor((B-oy)/step)+1)]
    for key,area in footprints.items():
        record=assets[placed[key]['asset_id']]
        collisions=len(record.get('collision',[]))+len(record.get('convex_collision',[]))
        triangles=visual.get(record['id'],12*len(record.get('collision',[])))+sum(len(c['faces']) for c in record.get('convex_collision',[]))
        for cell in cells(area):
            value=cell_cost[cell];value[0]+=collisions;value[1]+=triangles;value[2]+=1
    for surface in doc.get('surface_areas',[]):
        for cell in cells(polygon(surface)): cell_cost[cell][1]+=max(1,len(surface['polygon'])-2)
    for road,line in zip(doc['roads'],g.road_lines):
        for cell in cells(line.buffer(max(road['widths_cm'])/200)):
            cell_cost[cell][0]+=1;cell_cost[cell][1]+=max(2,len(road['points'])*2)
    ranked=sorted(cell_cost,key=lambda c:(-(cell_cost[c][0]*32+cell_cost[c][1]),c))[:6]
    metrics['cost_cells']=[dict(x=c[0],y=c[1],collision_proxies=cell_cost[c][0],triangle_estimate=cell_cost[c][1]+512,objects=cell_cost[c][2]) for c in ranked]
    return metrics,errors,issues
