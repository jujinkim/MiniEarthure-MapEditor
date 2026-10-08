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
    roads={r['id']:r for r in document['roads']}
    geometry={key:LineString([(p[0]/100,p[2]/100) for p in r['points']]) for key,r in roads.items()}
    adjacent=defaultdict(list)
    for r in roads.values():
        adjacent[r['from']].append(r['id']);adjacent[r['to']].append(r['id'])
    candidates=[]
    for key,line in geometry.items():
        if roads[key]['kind']!='ground' or line.length<180: continue
        a,b=line.interpolate(40),line.interpolate(160)
        direct=LineString([a,b])
        deviation=max(direct.distance(line.interpolate(i)) for i in range(40,161,10))
        if deviation<.5: candidates.append((deviation,-line.length,key))
    if not candidates: raise ValueError('No straight grounded eight-car staging road')
    first_id=min(candidates)[2];first=roads[first_id];line=geometry[first_id]
    start=line.interpolate(60);gate=line.interpolate(100);heading=line.interpolate(110)
    spawn=dict(x_cm=round(start.x*100),y_cm=round(start.y*100),surface_id=first_id,
        heading_radians=-math.atan2(heading.x-gate.x,heading.y-gate.y))
    output=[]
    for index,(identity,name,target) in enumerate((('intro','Intro Drive',900),('tour','Scenic Tour',3200),('technical','District Route',1800))):
        random=rng(document['seed'],'course',identity)
        points=[];travelled=0;visited=set();current=first_id;forward=True;node=first['to']
        for hop in range(120):
            r=roads[current];path=geometry[current]
            if not forward: path=LineString(list(path.coords)[::-1])
            begin=100 if hop==0 else 12
            distances=([100,150] if hop==0 else [])+[i for i in range(max(200 if hop==0 else 60,int(begin)),int(path.length-10),100)]
            distances.append(max(begin,path.length-12))
            for distance in sorted(set(distances)):
                if distance>path.length: continue
                p=path.interpolate(distance)
                if points and Point(points[-1]['x_cm']/100,points[-1]['y_cm']/100).distance(p)<18: continue
                points.append(dict(x_cm=round(p.x*100),y_cm=round(p.y*100),surface_id=current,structural=r['kind']!='ground'))
                if len(points)>=60: break
            travelled+=max(0,path.length-(60 if hop==0 else 0))
            visited.add(current)
            if travelled>=target or len(points)>=60: break
            choices=[key for key in adjacent[node] if key not in visited]
            if not choices: break
            # Route-specific stable draws select distinct districts without
            # changing the common straight launch area.
            current=random.choice(sorted(choices));r=roads[current]
            forward=r['from']==node;node=r['to'] if forward else r['from']
        if len(points)<3: raise ValueError('No connected recommendation route')
        output.append(dict(id=identity,name=name,waypoints=points,start=spawn,mode='sprint',laps=1,
            checkpoint_radius_cm=400,length_m=round(travelled,1)))
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
    second=next((s for s in sites if s['group'] in ('attractions','school','warehouse','lodge-village','campground','quarry','production')),main)
    pos=next(v for v in document['placements'] if v['id']==second['objects'][0])['position']
    X,H,Y=[v/100 for v in pos]
    return dict(id=p.id,name=p.name,en=p.english,description=DESCRIPTIONS[p.id],theme=p.id,
        size=list(p.minimum_size_m),cell_size_m=32,relief=p.relief_m,surface='dirt' if p.id=='deep-forest' else 'asphalt',
        districts=sorted({s['landuse'] for s in sites}),landmarks=[r.id for r in p.rules],routes=planned,start=planned[0]['start'],
        preview_center_m=[x,h,y],review_views=[dict(name='signature',position_m=[X+35,H+24,Y+35],target_m=[X,H+5,Y])],
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
        meta['validation']={k:result['diagnostics'][k] for k in ('counts','required','present','facilities','texture_memory_bytes','payload_bytes')}
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
