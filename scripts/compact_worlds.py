"""Shared metre-scale authoring tools for the seven compact, original worlds.

Recipes own every road, facility and habitat. These helpers never scale vehicles,
road widths or models and never scatter outside the supplied habitat polygons.
"""
import math
import random
import numpy as np
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union

WALKS={
    'intro':['arrival-road','inner-approach','inner-grove','west-lane','return-road'],
    'tour':['arrival-road','south-road','east-road','upper-road','ridge-road','west-ridge','west-lane','return-road'],
    'technical':['arrival-road','inner-approach','inner-grove','-west-ridge','-ridge-road','-upper-road'],
}

def road_height(w,name,point):
    road=next(r for r in w.doc['roads'] if r['id']==name)
    distances=[0]
    for a,b in zip(road['points'],road['points'][1:]):distances.append(distances[-1]+math.hypot(b[0]-a[0],b[2]-a[2])/100)
    return float(np.interp(w.routes[name].project(point),distances,[p[1]/100 for p in road['points']]))

def terrain(w,level,hills=(),river=None):
    from default_worlds import smooth
    def base(x,y):
        x=np.asarray(x);y=np.asarray(y)
        h=level+.65*np.sin(x/48)*np.sin(y/61)
        for cx,cy,rise,sx,sy in hills:h=h+rise*np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2)
        if river:
            axis,center,bed,width=river
            distance=np.abs((y if axis=='x' else x)-center)
            edge=bed+1.6*smooth(distance/width)
            blend=smooth((distance-width)/14)
            h=edge*(1-blend)+h*blend
        return h
    w.base=base

def network(w,nodes,levels=None,bends=None,bridges=(),width=7.5):
    levels=levels or {};bends=bends or {}
    w.nodes_m=nodes;w.bridge_links={}
    edges=[('arrival-road','A','B'),('south-road','B','C'),('east-road','C','D'),
        ('upper-road','D','E'),('ridge-road','E','F'),('west-ridge','F','G'),
        ('west-lane','G','H'),('return-road','H','A'),('inner-approach','B','I'),
        ('inner-grove','I','G'),('inner-east','I','D')]
    for name,a,b in edges:
        points=[nodes[a],*bends.get(name,[]),nodes[b]]
        line=LineString(points);start=levels.get(a,9);end=levels.get(b,9)
        def profile(x,y,line=line,start=start,end=end):
            return start+(end-start)*line.project(Point(x,y))/line.length
        if name in bridges:
            p=line.interpolate(40);q=line.interpolate(line.length-40)
            entry=(p.x,p.y);exit=(q.x,q.y)
            w.path(name+'-entry',[nodes[a],entry],width,level=profile,shoulder_m=8)
            w.path(name,[entry,exit],width,level=profile,kind='bridge',shoulder_m=8)
            w.path(name+'-exit',[exit,nodes[b]],width,level=profile,shoulder_m=8)
            w.bridge_links[name]=[name+'-entry',name,name+'-exit']
            for x,y in (entry,exit):w.pads.append((x,y,8,8,float(profile(x,y))))
        else:
            w.path(name,points,10 if name=='arrival-road' else width,
                sidewalk=1.5 if name=='arrival-road' else 0,level=profile,shoulder_m=8)
    a=nodes['A'];w.spawn=dict(x_cm=round((a[0]+60)*100),y_cm=round(a[1]*100),
        surface_id='arrival-road',heading_radians=-math.pi/2)

def facility(w,name,asset,at,yaw=0,level=None,yard=4,surface='gravel'):
    x,y=at
    z=float(w.height(x,y)) if level is None else level
    shape=w.place(name,asset,x,y,yaw,z,True)
    if yard:w.paint(name+'-yard',shape.buffer(yard,join_style=2),surface)
    return shape

def grove(w,name,area,kinds,spacing=16,understory='shrub',water_margin=4):
    """Irregular groves, with empty glades and local young/mature clusters."""
    w.habitats.append(dict(id=name,polygon=list(area.exterior.coords),assets=kinds,spacing_m=spacing))
    rng=random.Random(1703+sum(map(ord,name)))
    avoid=w.road_area(6).union(unary_union(w.water).buffer(water_margin))
    # Jittered clusters have species/age patches, never a uniform tree lattice.
    a,b,c,d=area.bounds;index=0
    for cy in np.arange(b+spacing,d,spacing*2.4):
        for cx in np.arange(a+spacing,c,spacing*2.4):
            if rng.random()<.12:continue
            species=rng.randrange(len(kinds))
            for j in range(6):
                angle=rng.random()*math.tau;radius=spacing*rng.uniform(.15,1.25)
                x=float(cx+math.cos(angle)*radius);y=float(cy+math.sin(angle)*radius)
                p=Point(x,y)
                if not area.contains(p) or avoid.contains(p):continue
                _,bounds=w.asset(kinds[(species+j//3)%len(kinds)])
                if not box(2,2,w.size[0]-2,w.size[1]-2).contains(p.buffer(max(abs(bounds[0][0]),abs(bounds[1][0]),abs(bounds[0][2]),abs(bounds[1][2])))):continue
                if w.place(name+'-'+str(index),kinds[(species+j//3)%len(kinds)],x,y,rng.randrange(360),solid=False) is not None:
                    if understory and index%3==0:w.place(name+'-under-'+str(index),understory,x+3,y+3,rng.randrange(360),solid=False)
                    index+=1

def verge(w,roads,kinds,spacing=17,offset=12):
    for name in roads:
        line=w.routes[name]
        for i,s in enumerate(np.arange(22,line.length-22,spacing)):
            p=line.interpolate(s);q=line.interpolate(s+.5);dx=q.x-p.x;dy=q.y-p.y;n=math.hypot(dx,dy)
            side=1 if i%3 else -1;x=p.x-dy/n*offset*side;y=p.y+dx/n*offset*side
            if not box(12,12,w.size[0]-12,w.size[1]-12).contains(Point(x,y)):continue
            if any(water.buffer(4).contains(Point(x,y)) for water in w.water):continue
            w.place(name+'-verge-'+str(i),kinds[i%len(kinds)],x,y,i*47,solid=False)

def streetscape(w,road,kinds,start=20,stop=None,step=20,setback=18,sides=(-1,1),yard=None):
    """Designed roadside bands: fixed stations, local road height and clear corners."""
    line=w.routes[road]
    for i,s in enumerate(np.arange(start,min(stop or line.length-22,line.length-22),step)):
        p=line.interpolate(s);q=line.interpolate(s+.5)
        dx=q.x-p.x;dy=q.y-p.y;length=math.hypot(dx,dy)
        for side in sides:
            asset=kinds[(i+(side==1))%len(kinds)]
            bounds=w.asset(asset)[1]
            radius=max(abs(bounds[0][0]),abs(bounds[1][0]),abs(bounds[0][2]),abs(bounds[1][2]))
            distance=max(setback,radius+10)
            nx=-dy/length*side;ny=dx/length*side
            x=p.x+nx*distance;y=p.y+ny*distance
            if not box(2,2,w.size[0]-2,w.size[1]-2).contains(Point(x,y).buffer(radius)):continue
            if any(water.buffer(radius+2).contains(Point(x,y)) for water in w.water):continue
            shape=w.place(road+'-band-'+str(i)+'-'+str(side),asset,x,y,
                math.degrees(math.atan2(-nx,ny)),road_height(w,road,p),foundation=True,solid=False)
            if shape is not None and yard:w.paint(road+'-court-'+str(i)+'-'+str(side),shape.buffer(3),yard)

def shortcut(w,entry,exit,level,kind='ramp_low',rise=0):
    """A separately authored lane between a fork and a merge on south-road.

    The ordinary bypass is continuous and every recommendation gates outside it.
    Track entry is snapped by the v1 road connection; both source IDs and actual
    execution IDs are retained for probes after compilation.
    """
    a=np.array(entry,dtype=float);b=np.array(exit,dtype=float);delta=b-a
    direction=delta/np.linalg.norm(delta);normal=np.array([-direction[1],direction[0]])
    # Dedicated, ordinary approach and exit make the branch's ports explicit.
    approach=a-direction*18;runout=b+direction*18
    w.path('shortcut-entry',[tuple(approach),tuple(a)],8,level=level,shoulder_m=4)
    w.path('shortcut-exit',[tuple(b),tuple(runout)],8,level=level,shoulder_m=4)
    # Connect these spurs through the same two road graph nodes as the bypass.
    # Caller authors these endpoints as part of the main road via split_south.
    length=float(np.linalg.norm(delta))
    controls=[[0,round(y*100),round(t*length*100)] for t,y in
        [(0,0),(.12,0),(.22,rise),(.33,rise),(.44,rise),(.56,rise),(.67,rise),(.78,rise),(.88,0),(1,0)]]
    w.track_source=dict(original_seed=None,grounded_supports=False,
        settings=dict(seed=13,circuit=False,duration_seconds=60,difficulty='normal',categories=['driving'],time_minutes=840),
        terrain_integration=True,terrain_policies={'scenic-shortcut':'auto_fit' if not rise else 'elevated'},
        instances=[dict(id='scenic-shortcut',preset='free_curve',position_cm=[0,0,0],rotation_mdeg=[0,0,0],
            width_cm=800,entry_width_cm=800,exit_width_cm=800,control_points=controls)],
        road_connections=[dict(road='shortcut-entry',start=False,instance='scenic-shortcut')],
        connections=[],paths=[],checkpoints=[],actions=[],attachments=[])
    clearance=LineString([tuple(approach),tuple(a),tuple(b),tuple(runout)]).buffer(27 if kind=='grind_rail' else 9)
    w.shortcuts.append(dict(id='scenic-shortcut',base_roads=['south-road'],clearance=clearance,
        entry_m=list(approach),merge_m=list(runout),surface='track:scenic-shortcut',kind=kind,
        landing_runway_m=18,underpass_clearance_m=None))
    w.attachments.append(dict(id='scenic-action',surface=dict(surface_id='track:scenic-shortcut',station_cm=round(length*50)),
        kind=kind,height_cm=80,panel_width_percent=50,panel_alignment='center',side=1))
    if kind=='grind_rail':
        # The rail is the direct branch across the broad ordinary bend, with
        # supported runways on both ends and no road deck under the span.
        rise=max(.4,rise);runway=max(12,rise*7)
        span=length-2*runway
        if span<6:raise ValueError('Rail shortcut needs two supported runways')
        def instance(name,preset,distance,height):
            return dict(id=name,preset=preset,position_cm=[0,0,0],rotation_mdeg=[0,0,0],
                width_cm=800,entry_width_cm=800,exit_width_cm=800,
                control_points=[[0,0,0],[0,0,round(distance*100/3)],
                    [0,round(height*100),round(distance*200/3)],[0,round(height*100),round(distance*100)]])
        source=w.track_source
        source['instances']=[instance('scenic-shortcut','free_curve',runway,rise),
            instance('shortcut-rail','flight_curve',span,0),instance('shortcut-landing','free_curve',runway,-rise)]
        source['connections']=[dict(from_='scenic-shortcut',to='shortcut-rail'),dict(from_='shortcut-rail',to='shortcut-landing')]
        source['connections']=[{'from':c['from_'],'to':c['to']} for c in source['connections']]
        source['terrain_policies']={i['id']:'elevated' for i in source['instances']}
        start=a+direction*runway;end=b-direction*runway;center=(start+end)/2
        position=[round(center[0]*100),round((level+rise-.4)*100),round(center[1]*100)]
        half=round(span*50)
        vertices=[[x,y,z] for x,y,z in [(-20,0,-half),(20,0,-half),(20,40,-half),(-20,40,-half),
            (-20,0,half),(20,0,half),(20,40,half),(-20,40,half)]]
        faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
        radius=half+100
        source['structures']=[dict(id='authored-shortcut-rail',position=position,
            rotation_mdeg=[0,round(math.degrees(math.atan2(direction[0],direction[1]))*1000),0],scale_per_mille=[1000]*3,
            parts=[dict(vertices=vertices,faces=faces)],surface='concrete',color=[255,200,40,255],
            motion=dict(kind='static',delta_cm=[0]*3,axis=1,period_ms=4000,phase_ms=0,impulse_cmps=[0]*3,cooldown_ms=1500),
            safety_min_cm=[v-radius for v in position],safety_max_cm=[v+radius for v in position])]
        source['grind_lines']=[dict(id='shortcut-rail',control_points=[[round(p[0]*100),round((level+rise)*100),round(p[1]*100)] for p in (start,end)],
            up=[0,1000000,0],capture_width_cm=40,start_connections=[],end_connections=[])]
        w.attachments=[v for v in w.attachments if v['id']!='scenic-action']
        branch=w.shortcuts[-1]
        # The Bezier control-polygon length bounds each sloping runway from
        # above. Include vertical travel and both ordinary-road approaches.
        branch_length=span+36+sum(sum(math.dist(a,b)/100 for a,b in zip(i['control_points'],i['control_points'][1:]))
            for i in (source['instances'][0],source['instances'][2]))
        branch.update(exit_surface='track:shortcut-landing',rail_id='shortcut-rail',landing_runway_m=runway+18,
            shortcut_length_m=branch_length,main_length_m=w.routes['south-road'].length)
        if branch['shortcut_length_m']>branch['main_length_m']*.8 or branch['main_length_m']-branch['shortcut_length_m']<5:
            raise ValueError('Rail shortcut must save 20% and 5 m including approach/exit')
    # Show a common boost on ordinary road as well as the attached track object.
    w.attachments.append(dict(id='arrival-boost',surface=dict(surface_id='arrival-road',station_cm=14500),
        kind='acceleration_panel',height_cm=80,panel_width_percent=50,panel_alignment='right',side=1))
    w._road_exclusion=None

def split_south(w,entry,exit,level,kind='ramp_low',rise=0):
    # Main road's exact endpoints are the branch fork and merge. Side approach
    # roads are part of the same connected graph; no implicit crossing contract.
    road=next(r for r in w.doc['roads'] if r['id']=='south-road')
    a=np.array(entry,dtype=float);b=np.array(exit,dtype=float);direction=(b-a)/np.linalg.norm(b-a)
    fork=tuple(a-direction*18);merge=tuple(b+direction*18)
    original=list(w.routes['south-road'].coords)
    w.doc['roads'].remove(road);w.routes.pop('south-road');w.shoulders.pop('south-road')
    # The bypass bows outward; its travel is always ordinary asphalt.
    normal=np.array([-direction[1],direction[0]])
    bow=85 if kind=='grind_rail' else 38
    shoulder=70 if kind=='grind_rail' else 30
    middle=tuple((a+b)/2+normal*bow)
    w.path('south-road',[fork,tuple(a+normal*shoulder),middle,tuple(b+normal*shoulder),merge],7.5,level=level,shoulder_m=6)
    w.path('south-entry',[original[0],fork],7.5,level=level,shoulder_m=6)
    w.path('south-exit',[merge,original[-1]],7.5,level=level,shoulder_m=6)
    shortcut(w,entry,exit,level,kind,rise)

def finish(w,identity,name,en,description,districts,landmarks,views,walks=None,weather=None):
    w.places=landmarks
    walks={key:list(value) for key,value in (walks or WALKS).items()}
    for key,walk in walks.items():
        expanded=[]
        for step in walk:
            road_name=step.lstrip('-')
            if road_name in w.bridge_links:
                links=w.bridge_links[road_name]
                expanded+=['-'+s for s in links[::-1]] if step.startswith('-') else links
            else:expanded.append(step)
        walks[key]=expanded
    if w.shortcuts:
        for key,walk in walks.items():
            expanded=[]
            for step in walk:
                if step=='south-road':expanded+=['south-entry','south-road','south-exit']
                elif step=='-south-road':expanded+=['-south-exit','-south-road','-south-entry']
                else:expanded.append(step)
            walks[key]=expanded
    routes=[w.course(key,{'intro':'Welcome Loop','tour':'Scenic Tour','technical':'Technical Roads'}[key],walks[key]) for key in ('intro','tour','technical')]
    reviews=[]
    for label,road,station,ahead in views:
        line=w.routes[road];p=line.interpolate(station);q=line.interpolate(max(0,min(line.length,station+ahead)))
        reviews.append(dict(name=label,position_m=[p.x,road_height(w,road,p)+1.7,p.y],target_m=[q.x,road_height(w,road,q)+2,q.y],
            quality=2,view_distance_m=384,time_minutes=840,fov=68))
    if w.shortcuts:
        branch=w.shortcuts[0];a=branch['entry_m'];b=branch['merge_m']
        reviews.append(dict(name='special-branch',position_m=[a[0],float(w.height(*a))+1.7,a[1]],
            target_m=[b[0],float(w.height(*b))+2,b[1]],quality=2,view_distance_m=384,time_minutes=840,fov=68))
    if hasattr(w,'landmark_review'):
        road,station,target=w.landmark_review;p=w.routes[road].interpolate(station)
        reviews.append(dict(name='landmark',position_m=[p.x,road_height(w,road,p)+1.7,p.y],
            target_m=[target[0],float(w.height(*target))+3,target[1]],quality=2,view_distance_m=384,time_minutes=840,fov=68))
    p=w.routes['arrival-road'].interpolate(55);q=w.routes['arrival-road'].interpolate(130)
    reviews.append(dict(name='entry',position_m=[p.x,float(w.height(p.x,p.y))+1.7,p.y],
        target_m=[q.x,float(w.height(q.x,q.y))+2,q.y],quality=2,view_distance_m=384,time_minutes=840,fov=68))
    center=[w.size[0]/2,w.size[1]/2]
    reviews.append(dict(name='overview',position_m=[center[0],float(w.height(*center))+600,center[1]+160],target_m=[center[0],float(w.height(*center)),center[1]],
        projection='orthogonal',size_m=max(w.size[0]*.625,w.size[1])*1.08,quality=2,
        view_distance_m=math.hypot(*w.size)+700,force_distant=True,time_minutes=840))
    if weather:
        extra=reviews[0].copy();extra.update(weather);reviews.append(extra)
    return dict(id=identity,name=name,en=en,theme=identity,size=list(w.size),surface='asphalt',description=description,
        districts=districts,landmarks=landmarks,routes=routes,start=routes[0]['start'],review_views=reviews,
        habitats=w.habitats,optional_branches=[{k:v for k,v in b.items() if k!='clearance'} for b in w.shortcuts],
        preview_center_m=[center[0],9,center[1]],ground_position_m=reviews[0]['position_m'],ground_target_m=reviews[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview=reviews[0]['name'],signature_preview=reviews[1]['name']),
        acceptance='Human completion, Android performance and final art acceptance remain unverified.')
