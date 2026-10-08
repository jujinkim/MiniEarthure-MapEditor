#!/usr/bin/env python3
"""Publish seven new authoring projects and route plans; never replace originals.

Runtime seals the route plans separately. No private game dependency is needed
to generate these public source projects. --prepared reuses a fingerprint-matched
candidate from the current engine; it verifies every referenced payload first.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import shutil
import subprocess

from environment_generation import (PROFILES, GenerationRequest, canonical, digest,
    fingerprint, generate, new_context, rng, write_result)
from shapely.geometry import LineString, Point

DESCRIPTIONS={
    'village':'Village streets, school grounds, farmsteads and fields in a broad green landscape.',
    'neon-harbor':'Working docks, warehouses, residential districts and a connected waterfront bridge.',
    'deep-forest':'Layered woodland, a lake, campsites and winding forestry roads.',
    'red-canyon':'Red ridges, exposed strata, a quarry and viewpoints above a dry valley.',
    'snow-mountain':'Alpine vegetation, snowy ridges, lodges and guarded mountain roads.',
    'machine-factory':'Production halls, service yards, pipes, tanks and power facilities.',
    'sky-park':'Amusement grounds, plazas and elevated promenades on visible supports.'}


def routes(document):
    """Choose hub routes on the existing graph; wilderness shares its one loop."""
    import heapq
    roads={r['id']:r for r in document['roads']}
    geometry={key:LineString([(p[0]/100,p[2]/100) for p in r['points']]) for key,r in roads.items()}
    graph=defaultdict(list)
    for key,r in roads.items():
        graph[r['from']].append((r['to'],key,True));graph[r['to']].append((r['from'],key,False))
    metadata=next(json.loads(a['notice']) for a in document['attributions'] if a['source'].startswith('mapeditor-environment-v1:'))
    hierarchy=metadata['road_hierarchy'];remote=PROFILES[metadata['request']['theme']].road_mode=='loop'
    candidates=[]
    for key,line in geometry.items():
        if roads[key]['kind']!='ground' or line.length<200: continue
        direct=LineString([line.interpolate(0),line.interpolate(200)])
        if max(direct.distance(line.interpolate(i)) for i in range(0,201,10))<.05:
            candidates.append((0 if abs(line.length-260)<.05 else 1,-line.length,key))
    if not candidates: raise ValueError('No grounded 200 m eight-car staging road')
    first_id=min(candidates)[2];first=roads[first_id];line=geometry[first_id]
    start=line.interpolate(60);gate=line.interpolate(100);heading=line.interpolate(110)
    spawn=dict(x_cm=round(start.x*100),y_cm=round(start.y*100),surface_id=first_id,
        heading_radians=-math.atan2(heading.x-gate.x,heading.y-gate.y))
    sites=[s for s in metadata['sites'] if s.get('required') and s.get('road_id') and s['objects']]
    def reach(node,key,used):
        target=roads[key];queue=[(0,node,[])];best={node:0}
        while queue:
            distance,current,path=heapq.heappop(queue)
            if distance!=best[current]: continue
            if current in (target['from'],target['to']):
                forward=current==target['from']
                return path+[(key,forward)],target['to'] if forward else target['from'],distance
            for nxt,edge,forward in sorted(graph[current]):
                cost=distance+geometry[edge].length*(3 if edge in used else 1)
                if cost<best.get(nxt,float('inf')):
                    best[nxt]=cost;heapq.heappush(queue,(cost,nxt,path+[(edge,forward)]))
        raise ValueError('Disconnected recommendation hub')
    ranked=sorted(sites,key=lambda s:(reach(first['to'],s['road_id'],{first_id})[2],s['id']))
    output=[]
    for identity,name in (('intro','Intro Drive'),('tour','Scenic Tour'),('technical','District Route')):
        walk=[(first_id,True)];node=first['to'];used={first_id}
        if remote and identity=='tour':
            while node!=first['from']:
                options=[(edge,forward,nxt) for nxt,edge,forward in graph[node] if hierarchy.get(edge)=='main' and edge not in used]
                if not options: raise ValueError('Incomplete wilderness scenic loop')
                edge,forward,node=min(options);walk.append((edge,forward));used.add(edge)
        else:
            targets=ranked[:1] if identity=='intro' else ranked[-1:] if remote else ranked[1:4] if identity=='technical' else ranked[::-1][:4]
            for site in targets:
                path,node,_=reach(node,site['road_id'],used)
                for edge,forward in path:
                    if walk[-1]!=(edge,forward): walk.append((edge,forward))
                    used.add(edge)
        points=[];travelled=0
        # Uniform samples follow each oriented edge, preserving real surfaces and
        # leaving room at junctions. Different courses never create extra roads.
        for hop,(key,forward) in enumerate(walk):
            r=roads[key];path=geometry[key]
            if not forward: path=LineString(list(path.coords)[::-1])
            distances=([100,150] if hop==0 else [])+list(range(200 if hop==0 else 40,int(path.length-12),100))
            distances.append(path.length-12)
            for distance in sorted(set(distances)):
                if distance< (100 if hop==0 else min(12,path.length/2)): continue
                p=path.interpolate(distance)
                if points and Point(points[-1]['x_cm']/100,points[-1]['y_cm']/100).distance(p)<18: continue
                points.append(dict(x_cm=round(p.x*100),y_cm=round(p.y*100),surface_id=key,structural=r['kind']!='ground'))
            travelled+=path.length-(100 if hop==0 else 0)
        if len(points)>60:
            # Preserve the first two launch gates and distribute the remaining
            # checkpoints along the complete route, rather than cutting its end.
            tail=points[2:];points=points[:2]+[tail[round(i*(len(tail)-1)/57)] for i in range(58)]
        if len(points)<3: raise ValueError('No connected recommendation route')
        output.append(dict(id=identity,name=name,waypoints=points,start=spawn,mode='sprint',laps=1,
            checkpoint_radius_cm=400,length_m=round(travelled,1),hub_ids=[s['id'] for s in (ranked if identity=='tour' else targets)]))
    if len({canonical(r['waypoints']) for r in output})!=3: raise ValueError('Recommendations require three distinct hub routes')
    return output


def region(document, report):
    p=PROFILES[report['request']['theme']]
    planned=routes(document)
    sites=report['sites'];main=next(s for s in sites if s['id'].startswith('env-facility-') and s['objects'])
    anchor=next(v for v in document['placements'] if v['id']==main['objects'][0])['position']
    x,h,y=[v/100 for v in anchor]
    # Frame an inhabited district away from the finite world boundary. Nature
    # props do not outweigh civic/working facilities when selecting this view.
    occupied=[v for v in document['placements'] if '-object-' in v['id']]
    candidates=[v for v in occupied if 160<v['position'][0]/100<p.minimum_size_m[0]-160 and 160<v['position'][2]/100<p.minimum_size_m[1]-160]
    if candidates:
        selected=max(candidates,key=lambda a:(sum(math.hypot(a['position'][0]-b['position'][0],a['position'][2]-b['position'][2])<14000 for b in occupied),a['id']))
        x,h,y=[v/100 for v in selected['position']]
    if p.id=='deep-forest':
        trees=[a for a in document['placements'] if 'mature' in a['asset_id'] and 220<a['position'][0]/100<p.minimum_size_m[0]-220 and 220<a['position'][2]/100<p.minimum_size_m[1]-220]
        cells=defaultdict(int)
        for tree in trees: cells[(tree['position'][0]//12800,tree['position'][2]//12800)]+=1
        if trees:
            selected=max(trees,key=lambda a:(cells[(a['position'][0]//12800,a['position'][2]//12800)],a['id']))
            x,h,y=[v/100 for v in selected['position']]
    second=next((s for s in sites if s['id'].startswith('env-facility-') and s['group'] in ('attractions','school','warehouse','lodge-village','campground','quarry','production')),main)
    pos=next(v for v in document['placements'] if v['id']==second['objects'][0])['position']
    X,H,Y=[v/100 for v in pos]
    if p.id=='sky-park': x,h,y=X,H,Y
    # Actual eye height on an emitted road, facing a complete facility frontage.
    foreground=next((s for s in sites if s['group'] in ('housing','commercial','production','lodge-village','campground','overlook','attractions') and s.get('road_id')),main)
    if p.id=='red-canyon': foreground=next(s for s in sites if s['group']=='quarry' and s.get('road_id'))
    road_record=next(r for r in document['roads'] if r['id']==foreground['road_id'])
    lane=LineString([(p[0]/100,p[2]/100) for p in road_record['points']])
    anchor=foreground['anchor'];distance=lane.project(Point(anchor))
    eye_distance=max(0,distance-(0 if p.id=='red-canyon' else 16))
    eye=lane.interpolate(eye_distance)
    def road_level(record, distance):
        along=0
        for a,b in zip(record['points'],record['points'][1:]):
            length=math.hypot(b[0]-a[0],b[2]-a[2])/100
            if along+length>=distance: return (a[1]+(b[1]-a[1])*max(0,min(1,(distance-along)/max(.01,length))))/100
            along+=length
        return record['points'][-1][1]/100
    eye_height=road_level(road_record,eye_distance)
    target=next(v for v in document['placements'] if v['id']==foreground['objects'][0])['position']
    core=next((d for d in report['districts'] if d['core']),report['districts'][0])
    transition=min(document['placements'],key=lambda a:abs(math.hypot(a['position'][0]/100-core['anchor'][0],a['position'][2]/100-core['anchor'][1])-180))['position']
    nature=[a for a in document['placements'] if a['id'].startswith('env-nature-') and 220<a['position'][0]/100<p.minimum_size_m[0]-220 and 220<a['position'][2]/100<p.minimum_size_m[1]-220]
    outer=max(nature,key=lambda a:min(math.hypot(a['position'][0]/100-d['anchor'][0],a['position'][2]/100-d['anchor'][1]) for d in report['districts'] if d['core']))['position'] if nature else pos
    views=[dict(name='signature',position_m=[X+65,H+45,Y+65],target_m=[X,H+5,Y])]
    for name,point in [('transition',transition),('outer',outer)]:
        a,b,c=[v/100 for v in point]
        views.append(dict(name=name,position_m=[a+70,b+70,c+70],target_m=[a,b+3,c]))
    return dict(id=p.id,name=p.name,en=p.english,description=DESCRIPTIONS[p.id],theme=p.id,
        size=list(p.minimum_size_m),cell_size_m=32,relief=p.relief_m,surface='dirt' if p.id=='deep-forest' else 'asphalt',
        districts=sorted({s['landuse'] for s in sites}),landmarks=[r.id for r in p.rules],routes=planned,start=planned[0]['start'],
        preview_center_m=[x,h,y],review_views=views,
        ground_position_m=[eye.x,eye_height+1.7,eye.y],ground_target_m=[target[0]/100,target[1]/100+1.7,target[2]/100],
        authoring=dict(algorithm=report['algorithm'],seed=9026,texture_profile=256,units='metres',formats=1),
        acceptance='Routes and art require user review; no human completion evidence is asserted.')


def publish(destination,kit,prepared=None,cli=None):
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'.gdignore').write_text('')
    for key,p in PROFILES.items():
        target=destination/key
        if prepared:
            source=prepared/key
            result=json.loads((source/'generation.json').read_text())
            document=json.loads((source/'document.json').read_text())
            if result['algorithm']!=fingerprint() or result['diagnostics']['errors']: raise ValueError('Candidate requires regeneration: '+key)
            paths={a['path'] for field in ('assets','heightmaps') for a in document[field]}
            for path in paths:
                if Path(path).is_absolute() or '..' in Path(path).parts or digest((source/path).read_bytes())!=result['payloads'][path]: raise ValueError('Candidate payload changed: '+path)
            target.mkdir()
            shutil.copy2(source/'document.json',target/'document.json')
            for path in paths:
                (target/path).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/path,target/path)
        else:
            request=GenerationRequest('new',key,9026,[0,0,p.minimum_size_m[0]*100,p.minimum_size_m[1]*100])
            generated=generate(request,new_context(request),kit)
            if generated.diagnostics['errors']: raise ValueError(generated.diagnostics['errors'])
            write_result(generated,target)
            document=generated.document;result=dict(metadata=generated.metadata,diagnostics=generated.diagnostics)
            (target/'generation.json').unlink() # Transient command/report; provenance stays in document.
        meta=region(document,result['metadata'])
        meta['validation']={k:result['diagnostics'][k] for k in ('counts','required','present','facilities','texture_memory_bytes','payload_bytes','metrics')}
        (target/'region.json').write_bytes(canonical(meta))
        if cli:
            subprocess.run([str(cli.resolve()),'pack',str(target),str(destination/(key+'.memap'))],check=True,stdout=subprocess.DEVNULL)
        print('ENVIRONMENT_SOURCE',key,len(document['placements']),flush=True)
    (destination/'arcade-world.json').write_bytes(canonical(dict(format_version=1,maps=list(PROFILES),owner='MapEditor',algorithm=fingerprint(),originals_preserved=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path);parser.add_argument('--kit',type=Path,required=True);parser.add_argument('--prepared',type=Path)
    parser.add_argument('--cli',type=Path,help='Built MapKit CLI; also validate and package each project')
    args=parser.parse_args();publish(args.destination,args.kit,args.prepared,args.cli)
