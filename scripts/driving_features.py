#!/usr/bin/env python3
"""Public driving-feature placement and a standalone synthetic demonstration."""
import argparse, copy, json, math
from pathlib import Path

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")

def place(templates,kind,position,yaw=0,strength=100):
    g=copy.deepcopy(templates[kind]);g['position']=list(map(round,position));g['rotation_mdeg']=[0,round(yaw*1000),0]
    if 'effect' in g:g['effect']['strength_percent']=strength
    if kind in ['target_speed','jump_height']:
        for part in g['parts']:
            for v in part['vertices']:v[1]=1 if v[1]>0 else -1
    if 'track' in g:
        t=g['track'];radius=4*t['radius_cm']+(2*t['width_cm'] if kind=='loop' else t['length_cm']//2)+40
    else:radius=max(sum(abs(c) for c in v) for p in g['parts'] for v in p['vertices'])
    margin=1800 if 'effect' in g else 0
    g['safety_min_cm']=[p-radius-margin for p in g['position']];g['safety_max_cm']=[p+radius+margin for p in g['position']]
    return g

def build(destination,kit):
    if destination.exists():raise FileExistsError(destination)
    destination.mkdir(parents=True)
    templates=json.loads((kit/"godot/driving_templates.json").read_text())
    # Independent demonstration: all five features plus a conventional outer circuit.
    d=json.loads((kit/'examples/placement/document.json').read_text())
    d.update(map_id='special-driving-demo',revision=1,bounds={'min':[0,0],'max':[19200,12800]},cell_size_cm=1600,terrain_base_cm=0,
             nodes=[],roads=[],placements=[],repetitions=[],zones=[],buildings=[],assets=[],heightmaps=[],surface_areas=[],courses=[],gimmicks=[])
    def road(ident,points,width=800):
        first,last=ident+'-a',ident+'-b'
        d['nodes'].extend([{'id':first,'position':points[0],'level':0},{'id':last,'position':points[-1],'level':0}])
        d['roads'].append({'id':ident,'from':first,'to':last,'points':points,'kind':'ground','clearance_cm':None,'sidewalk_cm':0,'widths_cm':[width]*(len(points)-1),'surfaces':['asphalt']*(len(points)-1)})
    corners=[[2500,0,2500],[16700,0,2500],[16700,0,10300],[2500,0,10300]]
    for i in range(4):road('bypass-'+str(i),[corners[i],corners[(i+1)%4]],600)
    for x in [4200,7800,13000]:road('lane-'+str(x),[[x,0,2500],[x,0,10300]])
    specs=[('target_speed',[4200,0,3500],50),('jump_height',[4200,0,4600],100),('air_ring',[4200,250,5100],100),('loop',[7800,0,7000],100),('target_speed',[7657,0,6900],70),('cylinder',[13000,0,7000],100)]
    for i,(kind,p,strength) in enumerate(specs):
        g=place(templates,kind,p,0,strength);g['id']='demo-'+str(i)+'-'+kind;d['gimmicks'].append(g)
    d['provenance'].update(tool_id='mapeditor-special-driving',build_id='special-driving-v1',last_edited='2026-09-26T00:00:00Z')
    target=destination/'demo';target.mkdir();write(target/'document.json',d)
    meta={'size':[192,128],'start':{'x_cm':4200,'y_cm':2800,'surface_id':'lane-4200','heading_radians':math.pi},'review_views':[
        {'name':'loop','position_m':[85,6,61],'target_m':[78,1,70]},
        {'name':'cylinder','position_m':[136,6,57],'target_m':[130,2.5,70]},
        {'name':'panels','position_m':[49,5,40],'target_m':[42,1.5,49]}]}
    write(target/'region.json',meta)
    manifest={'format_version':1,'originals_preserved':True,'maps':['demo'],'features':['target_speed','jump_height','air_ring','loop','cylinder']}
    write(destination/'special-driving.json',manifest)
    return manifest
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path);parser.add_argument('--kit',type=Path,required=True)
    args=parser.parse_args();print(build(args.destination,args.kit))
