#!/usr/bin/env python3
"""Original compact driving layouts. Preserve district sources; write new output only."""
import argparse,copy,hashlib,io,json,math,struct,sys
from pathlib import Path
from PIL import Image

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def half(p):return [round(x/2) for x in p]

def scaled_glb(data):
    length,kind=struct.unpack_from('<II',data,12);doc=json.loads(data[20:20+length]);tail=data[20+length:]
    for scene in doc['scenes']:
        for index in scene['nodes']:
            n=doc['nodes'][index]
            if 'matrix' in n:
                n['matrix']=[x*.5 if i%4!=3 else x for i,x in enumerate(n['matrix'])]
            else:
                n['scale']=[x*.5 for x in n.get('scale',[1,1,1])]
                if 'translation' in n:n['translation']=[x*.5 for x in n['translation']]
    payload=canonical(doc);payload+=b' '*((-len(payload))%4)
    return struct.pack('<III',0x46546c67,2,20+len(payload)+len(tail))+struct.pack('<II',len(payload),kind)+payload+tail

def route_geometry(meta,doc,index):
    roads={r['id']:r for r in doc['roads']};route=meta['routes'][index]
    # Recover the ordered traversal from the existing authored connected path.
    ids=route['road_path'];result=[]
    start=[route['start']['x_cm']/2,route['start']['y_cm']/2]
    heading=route['start']['heading_radians'];direction=[-math.sin(heading),-math.cos(heading)]
    last=None
    for i,ident in enumerate(ids):
        r=roads[ident];pts=r['points'];a,b=pts[0],pts[-1]
        if i==0:
            if (b[0]-a[0])*direction[0]+(b[2]-a[2])*direction[1]<0:a,b=b,a
        elif math.dist([last[0],last[2]],[b[0],b[2]])<.1:a,b=b,a
        result.append((r,a,b));last=b
    return result

def routes(meta,doc,safe_grid=True):
    result=[]
    for i in range(3):
        segments=route_geometry(meta,doc,i)
        lengths=[math.dist(a,b)/100 for _,a,b in segments]
        total=sum(lengths)
        def at(distance):
            for (road,a,b),length in zip(segments,lengths):
                if distance<=length:
                    t=distance/length;return road,[round(a[k]+(b[k]-a[k])*t) for k in range(3)],math.atan2(-(b[0]-a[0]),-(b[2]-a[2]))
                distance-=length
            road,a,b=segments[-1];return road,b,math.atan2(-(b[0]-a[0]),-(b[2]-a[2]))
        begin=60.0 if safe_grid else 40.0
        second=75 if safe_grid else 65
        if i==0:
            turn=min(begin+225,total*.7);distances=[begin,second]+list(range(second+30,int(turn),35))+[turn]+list(range(int(turn)-35,second,-35))+[second]
            length=2*(turn-begin)
        elif i==1:
            distances=[begin,second]+list(range(100,int(total)-15,35));length=total
        else:
            end=min(total-10,begin+820);distances=[begin,second]+list(range(100,int(end),35))+[end];length=end-begin
        points=[]
        for dist in distances:
            road,p,_=at(dist)
            if i==0 and safe_grid and dist>90:
                a,b=road['points'][0],road['points'][-1];segment_length=math.hypot(b[0]-a[0],b[2]-a[2]);offset=min(road['widths_cm'])/4
                p=[round(p[0]+(b[2]-a[2])/segment_length*offset),p[1],round(p[2]-(b[0]-a[0])/segment_length*offset)]
            points.append(dict(x_cm=p[0],y_cm=p[2],surface_id=road['id'],structural=road['kind']!='ground'))
        road,p,heading=at(40 if safe_grid else 20)
        result.append(dict(id=['intro','technical','ridge'][i],name=meta['routes'][i]['name'],mode='sprint' if i==2 else 'circuit',laps=1,waypoints=points,start=dict(x_cm=p[0],y_cm=p[2],surface_id=road['id'],heading_radians=heading),road_path=[r['id'] for r,_,_ in segments],length_m=round(length)))
    return result

def build(source,destination,kit):
    sys.path.insert(0,str(kit/'scripts'))
    from driving_structures import definition,convex_hull
    doc=json.loads((source/'document.json').read_text());meta=json.loads((source/'region.json').read_text());old=copy.deepcopy(doc);payloads={}
    doc['map_id']='compact-'+meta['id'];doc['revision']=1;doc['bounds']={k:half(v) for k,v in doc['bounds'].items()};doc['terrain_base_cm']=round(doc['terrain_base_cm']/2);doc['courses']=[]
    doc['provenance'].update(tool_id='mapeditor-compact-maps',build_id='compact-active-v1',first_created='2026-09-24T00:00:00Z',last_edited='2026-09-24T00:00:00Z')
    for n in doc['nodes']:n['position']=half(n['position'])
    for r in doc['roads']:
        r['points']=[half(p) for p in r['points']];r['widths_cm']=[max(200,round(w/2)) for w in r['widths_cm']]
        if r.get('clearance_cm'):r['clearance_cm']=max(200,round(r['clearance_cm']/2))
        if r.get('sidewalk_cm'):r['sidewalk_cm']=round(r['sidewalk_cm']/2)
    for a in doc.get('surface_areas',[]):a['polygon']=[half(p) for p in a['polygon']]
    for p in doc['placements']:
        p['position']=half(p['position'])
        if p['asset_id'].startswith('district-support-'):p['position'][1]-=2
    for a in doc['assets']:
        path=a['path'];data=(source/path).read_bytes()
        payloads[path]=scaled_glb(data) if path.endswith('.glb') else data
        for c in a['collision']:
            c['center']=half(c['center']);c['size_cm']=[max(1,x) for x in half(c['size_cm'])]
            if a['id'].startswith('district-water'):
                c['size_cm'][0]=max(1,c['size_cm'][0]-4);c['size_cm'][2]=max(1,c['size_cm'][2]-4)
        a['convex_collision']=[convex_hull([half(v) for v in c['vertices']]) for c in a.get('convex_collision',[])]
    for p in source.rglob('*'):
        if p.is_file() and p.parts[-2]=='signs' and not p.name.endswith('.import'):payloads[str(p.relative_to(source))]=p.read_bytes()
    oldmaps={(h['cell']['x'],h['cell']['y']):h for h in old['heightmaps']};cache={};maxx=max(k[0] for k in oldmaps);maxz=max(k[1] for k in oldmaps)
    def base_height(x,z):
        cx=min(int(x//1600),maxx);cz=min(int(z//1600),maxz);h=oldmaps[cx,cz]
        if h['path'] not in cache:cache[h['path']]=Image.open(source/h['path']).copy()
        ix=round((x-cx*1600)/h['spacing_cm']);iz=round((z-cz*1600)/h['spacing_cm'])
        return round((cache[h['path']].getpixel((min(8,ix),min(8,iz)))*h['step_cm']+h['offset_cm'])/2)
    new_routes=routes(meta,doc)
    roads_by_id={r['id']:r for r in doc['roads']}
    pads=[]
    for route in new_routes:
        start=route['waypoints'][0];r=roads_by_id[start['surface_id']]
        if r['kind']!='ground':continue
        a,b=r['points'][0],r['points'][-1];length=math.hypot(b[0]-a[0],b[2]-a[2]);direction=((b[0]-a[0])/length,(b[2]-a[2])/length)
        backset=2000 if meta['id']=='red-wadi' else 400
        center=(start['x_cm']-direction[0]*backset,start['y_cm']-direction[1]*backset)
        pads.append((center,direction,base_height(center[0]*2,center[1]*2)))
    def height(x,z):
        value=base_height(x*2,z*2)
        for (cx,cz),(dx,dz),level in pads:
            along=abs((x-cx)*dx+(z-cz)*dz);across=abs((x-cx)*dz-(z-cz)*dx)
            weight=max(0,min(1,(2200-along)/800,(1800-across)/800))
            value=value*(1-weight)+level*weight
        return round(value)
    def ground(x,z):
        # Same diagonal as the public 2m sampled terrain contract.
        x0=math.floor(x/200)*200;z0=math.floor(z/200)*200;u=(x-x0)/200;v=(z-z0)/200
        h00,h10,h11,h01=[height(a,b) for a,b in [(x0,z0),(x0+200,z0),(x0+200,z0+200),(x0,z0+200)]]
        return round(h00+(h10-h00)*u+(h11-h10)*v if u>=v else h00+(h11-h01)*u+(h01-h00)*v)
    doc['heightmaps']=[];heights=[]
    for z in range(doc['bounds']['max'][1]//1600):
        for x in range(doc['bounds']['max'][0]//1600):
            values=[height(x*1600+i*200,z*1600+j*200) for j in range(9) for i in range(9)];heights.extend(values)
            im=Image.new('I',(9,9));im.putdata([v+1000 for v in values]);out=io.BytesIO();im.convert('I;16').save(out,format='PNG',compress_level=9);data=out.getvalue();path='terrain/'+digest(data)+'.png';payloads[path]=data
            doc['heightmaps'].append(dict(cell=dict(x=x,y=z),path=path,spacing_cm=200,offset_cm=-1000,step_cm=1,source_accuracy_cm=None))
    new_routes=routes(meta,doc)
    protected_routes=routes(meta,doc,False)
    styles={'haeon':['jump','ramp','barrier'],'belmont':['humps','ramp','rotate'],'nord':['jump','pipe','platform'],'safra':['ramp','jump','boost'],'red-wadi':['jump','halfpipe','launch'],'kanupi':['ramp','log','rotate'],'bansai':['jump','pipe','platform']}
    colors={'haeon':[204,100,48,255],'belmont':[126,92,56,255],'nord':[83,139,156,255],'safra':[214,183,118,255],'red-wadi':[187,92,46,255],'kanupi':[92,111,53,255],'bansai':[123,86,68,255]}
    doc['gimmicks']=[];challenges=[]
    # Every long road receives a lane-sized challenge; the remaining lane is a
    # continuous bypass. Junctions supply the variation on shorter segments.
    for road in doc['roads']:
        a,b=road['points'][0],road['points'][-1];length=math.dist(a,b)/100
        if length<40 or min(road['widths_cm'])<280:continue
        dx,dz=(b[0]-a[0])/(length*100),(b[2]-a[2])/(length*100)
        yaw=math.degrees(math.atan2(dx,dz))
        for distance in range(25,int(length)-12,35):
            t=distance/length;center=[round(a[k]+(b[k]-a[k])*t) for k in range(3)]
            # Keep all authored start/grid corridors unobstructed.
            if any(math.hypot(center[0]-r['start']['x_cm'],center[2]-r['start']['y_cm'])<3000 for r in protected_routes):continue
            index=len(challenges);kind=styles[meta['id']][index%3]
            if min(road['widths_cm'])<400 or (kind=='halfpipe' and min(road['widths_cm'])<550) or (kind=='rotate' and min(road['widths_cm'])<430):kind='humps'
            # Structures stay on one side and retain the maximum fleet envelope plus clearance.
            narrow=min(road['widths_cm'])<400
            footprint=288 if kind=='rotate' else 412 if kind=='halfpipe' else 232 if kind in ['pipe','log'] else 110 if narrow else 240
            offset=-min(road['widths_cm'])/2+footprint/2+4
            center[0]+=round(dz*offset);center[2]-=round(dx*offset)
            if road['kind']=='ground':center[1]=ground(center[0],center[2])
            center[1]+=2
            g=definition('challenge-'+str(index),kind,center,yaw,colors[meta['id']])
            rise=(ground(center[0]+dx*100,center[2]+dz*100)-ground(center[0]-dx*100,center[2]-dz*100))/200 if road['kind']=='ground' else (b[1]-a[1])/math.hypot(b[0]-a[0],b[2]-a[2])
            g['rotation_mdeg'][0]=-round(math.degrees(math.atan(rise))*1000)
            if narrow:g['scale_per_mille'][0]=500
            if kind=='barrier':
                g['motion']['delta_cm']=[round(dz*100),0,round(-dx*100)]
                radius=max(sum(abs(x) for x in v) for part in g['parts'] for v in part['vertices'])
                g['safety_min_cm']=[center[i]-radius+min(0,g['motion']['delta_cm'][i]) for i in range(3)]
                g['safety_max_cm']=[center[i]+radius+max(0,g['motion']['delta_cm'][i]) for i in range(3)]
            if any(g['safety_min_cm'][i*2]<0 or g['safety_max_cm'][i*2]>doc['bounds']['max'][i] for i in range(2)):continue
            doc['gimmicks'].append(g)
            district=min(meta['district_records'],key=lambda d:math.dist([center[0]/50,center[2]/50],[sum(p[0] for p in d['polygon_m'])/len(d['polygon_m']),sum(p[1] for p in d['polygon_m'])/len(d['polygon_m'])]))['name']
            challenges.append(dict(id=g['id'],kind=kind,district=district,road_id=road['id'],position_cm=center,bypass_width_cm=min(road['widths_cm'])-footprint-8))
    if len(doc['gimmicks'])>128:raise ValueError(('too many structures',meta['id'],len(doc['gimmicks'])))
    acceleration=[]
    for road in doc['roads']:
        a,b=road['points'][0],road['points'][-1];length=math.dist(a,b)/100
        positions=sorted(sum((c['position_cm'][i]-a[i])*(b[i]-a[i]) for i in range(3))/(length*100)/100 for c in challenges if c['road_id']==road['id'])
        for start,end in zip([0]+positions,positions+[length]):
            if end-start>80:acceleration.append(dict(road_id=road['id'],from_m=round(start,2),to_m=round(end,2),purpose='protected start-area acceleration approach'))
    meta.update(acceleration_sections=acceleration,grid_pads=[dict(center_cm=list(center),half_length_cm=1400,half_width_cm=1000,height_cm=level) for center,direction,level in pads],size=half(meta['size']),routes=new_routes,start=new_routes[0]['start'],challenges=challenges,relief=round((max(heights)-min(heights))/100,2),elevation_range_m=[min(heights)/100,max(heights)/100])
    for d in meta['district_records']:d['polygon_m']=[[v/2 for v in p] for p in d['polygon_m']]
    for l in meta['landmark_records']:l['position_m']=[v/2 for v in l['position_m']]
    # Review camera records have metre vectors, preserved under the same scale.
    for v in meta.get('review_views',[]):
        for k,val in v.items():
            if isinstance(val,list) and len(val)==3 and all(isinstance(x,(int,float)) for x in val):v[k]=[x/2 for x in val]
    payloads['document.json']=canonical(doc);meta['source_files']={p:digest(data) for p,data in payloads.items()}
    folder=destination/meta['id'];folder.mkdir(parents=True,exist_ok=False)
    for p,data in {**payloads,'region.json':canonical(meta)}.items():
        target=folder/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'examples/regional-districts');p.add_argument('--kit',type=Path,required=True);a=p.parse_args()
    for ident in ['haeon','belmont','nord','safra','red-wadi','kanupi','bansai']:
        m=build(a.source/ident,a.destination,a.kit);print(ident,m['size'],len(m['challenges']),[(r['id'],r['length_m']) for r in m['routes']],flush=True)
