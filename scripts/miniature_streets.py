#!/usr/bin/env python3
"""MIT authoring for new miniature streets; never overwrite historical sources."""
import argparse, copy, hashlib, io, json, math, sys
from pathlib import Path
from PIL import Image
from compact_maps import canonical, digest, half, scaled_glb, route_geometry

IDS=['haeon','belmont','nord','safra','red-wadi','kanupi','bansai']

def near_segment(x,z,a,b):
    dx,dz=b[0]-a[0],b[2]-a[2];length=dx*dx+dz*dz
    t=max(0,min(1,((x-a[0])*dx+(z-a[2])*dz)/max(1,length)))
    px,pz=a[0]+t*dx,a[2]+t*dz
    return math.hypot(x-px,z-pz),t,px,pz

def build(source,destination,kit):
    sys.path.insert(0,str(kit/'scripts'))
    from driving_structures import definition, fit_to_surface, convex_hull
    from world_assets import street_tree
    old=json.loads((source/'document.json').read_text());meta=json.loads((source/'region.json').read_text())
    doc=copy.deepcopy(old);payloads={}
    doc.update(map_id='miniature-streets-'+meta['id'],revision=1,bounds={k:half(v) for k,v in old['bounds'].items()},terrain_base_cm=round(old['terrain_base_cm']/2),courses=[],gimmicks=[])
    doc['provenance'].update(tool_id='mapeditor-miniature-streets',build_id='street-authoring-v1',first_created='2026-09-24T00:00:00Z',last_edited='2026-09-24T00:00:00Z')
    grids={(h['cell']['x'],h['cell']['y']):h for h in old['heightmaps']};images={}
    maxx=max(k[0] for k in grids);maxz=max(k[1] for k in grids)
    def old_height(x,z):
        x=max(0,min(x,old['bounds']['max'][0]));z=max(0,min(z,old['bounds']['max'][1]))
        cx=min(int(x//1600),maxx);cz=min(int(z//1600),maxz);h=grids[cx,cz]
        if h['path'] not in images: images[h['path']]=Image.open(source/h['path']).copy()
        u=(x-cx*1600)/h['spacing_cm'];v=(z-cz*1600)/h['spacing_cm'];ix=min(7,int(u));iz=min(7,int(v));u-=ix;v-=iz
        a,b,c,d=[images[h['path']].getpixel((xx,zz))*h['step_cm']+h['offset_cm'] for xx,zz in [(ix,iz),(ix+1,iz),(ix+1,iz+1),(ix,iz+1)]]
        return a+(b-a)*u+(c-b)*v if u>=v else a+(c-d)*u+(d-a)*v
    cuts=[]
    pads=[dict(center_cm=[v/2 for v in p['center_cm']],half_length_cm=max(800,p['half_length_cm']//2),half_width_cm=max(600,p['half_width_cm']//2),height_cm=round(p['height_cm']/2)) for p in meta['grid_pads']]
    def height(x,z):
        value=old_height(x*2,z*2)/2
        for pad in pads:
            distance=max(abs(x-pad['center_cm'][0])/pad['half_length_cm'],abs(z-pad['center_cm'][1])/pad['half_width_cm'])
            weight=max(0,min(1,(1.5-distance)*2))
            value=value*(1-weight)+pad['height_cm']*weight
        flat=[]
        for cut in cuts:
            distance,_,_,_=near_segment(x,z,cut['a'],cut['b'])
            w=max(0,min(1,(1100-distance)/400))
            value=value*(1-w)+cut['height']*w
            if distance<=700:flat.append((distance,cut['height']))
        if flat:value=min(flat)[1]
        return round(value)
    def ground(x,z):
        x0=math.floor(x/200)*200;z0=math.floor(z/200)*200;u=(x-x0)/200;v=(z-z0)/200
        a,b,c,d=[height(xx,zz) for xx,zz in [(x0,z0),(x0+200,z0),(x0+200,z0+200),(x0,z0+200)]]
        return round(a+(b-a)*u+(c-b)*v if u>=v else a+(c-d)*u+(d-a)*v)
    for n in doc['nodes']:n['position']=half(n['position'])
    for r in doc['roads']:
        r['points']=[half(p) for p in r['points']]
        r['widths_cm']=[max(280,round(w/2)) for w in r['widths_cm']]
        if r.get('sidewalk_cm'):r['sidewalk_cm']=max(40,round(r['sidewalk_cm']/2))
        if r.get('clearance_cm'):r['clearance_cm']=max(220,round(r['clearance_cm']/2))
    for a in doc['surface_areas']:a['polygon']=[half(p) for p in a['polygon']]
    # Preserve route traversal, with half-length actual positions. Explicit
    # checkpoints are regenerated natively against the new map/content hash.
    for route in meta['routes']:
        route['length_m']=round(route['length_m']/2)
        for p in [route['start'],*route['waypoints']]:
            p['x_cm']=round(p['x_cm']/2);p['y_cm']=round(p['y_cm']/2)
    if meta['id']=='kanupi':
        route=meta['routes'][1];heading=route['start']['heading_radians']
        for point in [route['start'],*route['waypoints'][:2]]:
            point['x_cm']+=round(-math.sin(heading)*500)
            point['y_cm']+=round(-math.cos(heading)*500)
    pads=[]
    for route in meta['routes']:
        route['checkpoint_radius_cm']=300
        point=route['waypoints'][0];heading=route['start']['heading_radians']
        dx,dz=-math.sin(heading),-math.cos(heading)
        center=[round(point['x_cm']-1200*dx),round(point['y_cm']-1200*dz)]
        pads.append(dict(center_cm=center,half_length_cm=1500,half_width_cm=1500,height_cm=round(old_height(center[0]*2,center[1]*2)/2)))
        road=next(r for r in doc['roads'] if r['id']==point['surface_id'])
        road['widths_cm']=[max(600,w) for w in road['widths_cm']]
    if meta['id']=='red-wadi':
        # The old shallow merge ran through the scaled eight-slot start grid.
        # Bring the returning canyon street into a perpendicular junction.
        merge=next(r for r in doc['roads'] if r['id']=='arterial-8-s0')
        a,b=merge['points'][0],merge['points'][-1]
        bend=[b[0],ground(b[0],a[2]),a[2]]
        merge['points']=[a,bend,b];merge['widths_cm']*=2;merge['surfaces']*=2
        for route in meta['routes']:
            for point in route['waypoints']:
                if point['surface_id']==merge['id']:
                    nearest=min(near_segment(point['x_cm'],point['y_cm'],first,last) for first,last in zip(merge['points'],merge['points'][1:]))
                    point['x_cm'],point['y_cm']=round(nearest[2]),round(nearest[3])
    meta['start']=copy.deepcopy(meta['routes'][0]['start'])
    traversal=[[(r['id'],a==r['points'][0]) for r,a,b in route_geometry(meta,doc,i)] for i in range(3)]
    starts=[r['waypoints'][0] for r in meta['routes']]
    ridge=set(meta['routes'][2]['road_path'])
    candidates=[r for r in doc['roads'] if r['kind']=='ground' and r['id'] in ridge and math.dist(r['points'][0],r['points'][-1])>5500 and all(near_segment(p['x_cm'],p['y_cm'],r['points'][0],r['points'][-1])[0]>1600 for p in starts)]
    candidates.sort(key=lambda r:(-math.dist(r['points'][0],r['points'][-1]),r['id']))
    if len(candidates)<2:
        candidates=[r for r in doc['roads'] if r['kind']=='ground' and math.dist(r['points'][0],r['points'][-1])>5500 and all(near_segment(p['x_cm'],p['y_cm'],r['points'][0],r['points'][-1])[0]>1600 for p in starts)]
        candidates.sort(key=lambda r:(r['id'] not in ridge,-math.dist(r['points'][0],r['points'][-1]),r['id']))
    assert len(candidates)>=2,(meta['id'],'bridge approaches')
    bridges=[];underpass=None
    for index,r in enumerate(candidates[:2]):
        a,b=r['points'][0],r['points'][-1];dx,dz=b[0]-a[0],b[2]-a[2];length=math.hypot(dx,dz)
        center=[round((a[k]+b[k])/2) for k in range(3)]
        level=ground(center[0],center[2])
        if index==0:
            u=[round(center[0]+dz/length*1000),level,round(center[2]-dx/length*1000)]
            v=[round(center[0]-dz/length*1000),level,round(center[2]+dx/length*1000)]
            assert all(500<p[0]<doc['bounds']['max'][0]-500 and 500<p[2]<doc['bounds']['max'][1]-500 for p in [u,v])
            cuts.append(dict(a=u,b=v,height=level))
            for name,p in [('under-west',u),('under-east',v)]:doc['nodes'].append(dict(id=name,position=p,level=0))
            for name,start,end,from_id,to_id,kind in [('street-under-entry',a,u,r['from'],'under-west','ground'),('street-underpass',u,v,'under-west','under-east','underpass'),('street-under-exit',v,b,'under-east',r['to'],'ground')]:
                doc['roads'].append(dict(id=name,points=[start.copy(),end.copy()],widths_cm=[300],surfaces=['asphalt'],kind=kind,from_=from_id,to=to_id,sidewalk_cm=0,clearance_cm=240 if kind=='underpass' else None,markings=None))
                doc['roads'][-1]['from']=doc['roads'][-1].pop('from_')
                if kind=='ground':
                    # Portal mouths meet straight, with bends outside the roof.
                    sign=-1 if name=='street-under-entry' else 1
                    portal=u if sign<0 else v
                    extension=[round(portal[0]-sign*dz/length*400),level,round(portal[2]+sign*dx/length*400)]
                    points=[start.copy(),extension,end.copy()]
                    doc['roads'][-1].update(points=points,widths_cm=[300,300],surfaces=['asphalt','asphalt'])
            underpass=dict(road_id='street-underpass',bridge_id=r['id'],position_cm=center,clearance_cm=240,width_cm=300)
        deck=max(ground(a[0],a[2]),ground(b[0],b[2]),level)+260
        a[1]=ground(a[0],a[2]);b[1]=ground(b[0],b[2])
        r['kind']='bridge';r['sidewalk_cm']=0
        original_from,original_to=r['from'],r['to']
        entry=[round(a[0]+dx*.08),0,round(a[2]+dz*.08)];entry[1]=a[1]
        exit=[round(a[0]+dx*.92),0,round(a[2]+dz*.92)];exit[1]=b[1]
        r['from']=r['id']+'-bridge-entry';r['to']=r['id']+'-bridge-exit'
        doc['nodes'].extend([dict(id=r['from'],position=entry,level=0),dict(id=r['to'],position=exit,level=0)])
        for ident,start,end,first,last in [(r['id']+'-approach',a,entry,original_from,r['from']),(r['id']+'-departure',exit,b,r['to'],original_to)]:
            doc['roads'].append(dict(id=ident,points=[start.copy(),end.copy()],widths_cm=[max(320,min(r['widths_cm']))],surfaces=[r['surfaces'][0]],kind='ground',**{'from':first,'to':last},sidewalk_cm=0,clearance_cm=None,markings=None))
        for route in meta['routes']:
            for point in [route['start'],*route['waypoints']]:
                if point['surface_id']!=r['id']:continue
                t=near_segment(point['x_cm'],point['y_cm'],a,b)[1]
                if t<.08:point['surface_id']=r['id']+'-approach'
                elif t>.92:point['surface_id']=r['id']+'-departure'
        for original,portal in [(a,entry),(b,exit)]:cuts.append(dict(a=original.copy(),b=portal.copy(),height=portal[1]))
        flat_entry=[round(entry[0]+dx/length*300),entry[1],round(entry[2]+dz/length*300)]
        flat_exit=[round(exit[0]-dx/length*300),exit[1],round(exit[2]-dz/length*300)]
        r['points']=[entry,flat_entry]+[[round(a[0]+dx*t),deck,round(a[2]+dz*t)] for t in [.40,.60]]+[flat_exit,exit]
        r['widths_cm']=[max(320,min(r['widths_cm']))]*5;r['surfaces']=[r['surfaces'][0]]*5
        bridges.append(dict(road_id=r['id'],deck_height_cm=deck,underlying_height_cm=level,clearance_cm=deck-level,approach_grade=max(abs(deck-entry[1]),abs(deck-exit[1]))/(length*.32-300)))
    # Ground endpoints share terrain levels, including regraded underpass mouths.
    nodes={n['id']:n for n in doc['nodes']}
    for r in doc['roads']:
        if r['kind']=='ground':
            for p in r['points']:p[1]=ground(p[0],p[2])
        for key,p in [('from',r['points'][0]),('to',r['points'][-1])]:nodes[r[key]]['position']=p.copy()
    # All endpoints referencing a bridge or portal use the same exact vertex.
    for r in doc['roads']:
        r['points'][0]=nodes[r['from']]['position'].copy();r['points'][-1]=nodes[r['to']]['position'].copy()
    roads={r['id']:r for r in doc['roads']}
    for route,path in zip(meta['routes'],traversal):
        route['road_path']=[]
        for ident,forward in path:
            expanded=[ident+'-approach',ident,ident+'-departure'] if ident+'-approach' in roads else [ident]
            route['road_path'].extend(expanded if forward else expanded[::-1])
    for route in meta['routes']:
        for p in route['waypoints']:p['structural']=roads[p['surface_id']]['kind']!='ground'
    # Embed richer shared models only in the new sources. Historical libraries
    # remain byte-identical. Original scale is quarter-size, not vehicle scale.
    for a in doc['assets']:
        data=(source/a['path']).read_bytes()
        if a['path'].endswith('.glb'):
            if any(k in a['id'] for k in ['canopy','forest-','palm']) and 'service' not in a['id']:
                model=street_tree('palm' if 'palm' in a['id'] else 'canopy')
                data=scaled_glb(scaled_glb(model.export()))
            else:data=scaled_glb(data)
        payloads[a['path']]=data
        for c in a['collision']:c['center']=half(c['center']);c['size_cm']=[max(1,v) for v in half(c['size_cm'])]
        a['convex_collision']=[convex_hull([half(v) for v in c['vertices']]) for c in a.get('convex_collision',[])]
    for path in source.rglob('*'):
        if path.is_file() and path.parts[-2]=='signs' and not path.name.endswith('.import'):payloads[str(path.relative_to(source))]=path.read_bytes()
    assets={a['id']:a for a in doc['assets']}
    def radius(asset):
        points=[]
        for c in asset['collision']:
            points.extend([(c['center'][0]+sx*c['size_cm'][0]/2,c['center'][2]+sz*c['size_cm'][2]/2) for sx in [-1,1] for sz in [-1,1]])
        for c in asset.get('convex_collision',[]):points.extend((p[0],p[2]) for p in c['vertices'])
        return max([math.hypot(x,z) for x,z in points]+[20])
    def clearance(x,z,rad):
        return all(near_segment(x,z,a,b)[0]>=min(r['widths_cm'])/2+rad+25 for r in doc['roads'] for a,b in zip(r['points'],r['points'][1:]))
    placements=[];occupied=[]
    for p in doc['placements']:
        before=p['position'];p['position']=half(before);x,y,z=p['position']
        a=assets[p['asset_id']];rad=radius(a)
        if not clearance(x,z,rad):continue
        p['position'][1]=ground(x,z)+round((before[1]-old_height(before[0],before[2]))/2)
        placements.append(p);occupied.append((x,z,rad))
    # Street-side infill uses each region's existing shops/houses and vegetation.
    palette=[a for a in doc['assets'] if any(k in a['id'] for k in ['shop-','polar-','stone-','alpine-','tropical-','japanese-','warehouse-']) and radius(a)<450]
    if not palette:palette=[a for a in doc['assets'] if any(k in a['id'] for k in ['workshop-','apartment-','streetwall-','farm-','dock-shed-'])]
    count=0
    for r in doc['roads']:
        if r['kind']!='ground':continue
        for a,b in zip(r['points'],r['points'][1:]):
            dx,dz=b[0]-a[0],b[2]-a[2];length=math.hypot(dx,dz)
            for distance in range(700,int(length)-500,850):
                for side in [-1,1]:
                    if not palette:continue
                    asset=palette[count%len(palette)];rad=radius(asset)
                    offset=min(r['widths_cm'])/2+rad+80
                    x=round(a[0]+dx*distance/length+dz/length*offset*side);z=round(a[2]+dz*distance/length-dx/length*offset*side)
                    if not (rad<x<doc['bounds']['max'][0]-rad and rad<z<doc['bounds']['max'][1]-rad):continue
                    if not clearance(x,z,rad) or any(math.hypot(x-xx,z-zz)<rad+rr+35 for xx,zz,rr in occupied):continue
                    placements.append(dict(id='street-infill-'+str(count),asset_id=asset['id'],position=[x,ground(x,z),z],quarter_turns=round(math.atan2(dx,dz)/(math.pi/2))%4))
                    occupied.append((x,z,rad));count+=1
    doc['placements']=placements
    # Optional structures occupy only technical streets, leaving a 1.4m lane.
    technical=set(meta['routes'][1]['road_path'])-set(meta['routes'][0]['road_path'])-ridge
    challenges=[]
    for r in doc['roads']:
        if r['id'] not in technical or r['kind']!='ground':continue
        a,b=r['points'][0],r['points'][-1];length=math.hypot(b[0]-a[0],b[2]-a[2])
        if length<2600:continue
        dx,dz=(b[0]-a[0])/length,(b[2]-a[2])/length
        center=[round((a[0]+b[0])/2+dz*-85),0,round((a[2]+b[2])/2-dx*-85)]
        if any(math.hypot(center[0]-p['x_cm'],center[2]-p['y_cm'])<1600 for p in starts):continue
        center[1]=ground(center[0],center[2])
        kind=['ramp','jump','humps','barrier'][len(challenges)%4]
        g=definition('street-skill-'+str(len(challenges)),kind,center,math.degrees(math.atan2(dx,dz)))
        g['scale_per_mille'][0]=450
        if g['motion']['kind']=='static':fit_to_surface(g,ground)
        else:
            g['motion']['delta_cm']=[round(dx*60),0,round(dz*60)]
            radius_cm=math.ceil(max(sum(abs(v[a]*g['scale_per_mille'][a]/1000) for a in range(3)) for part in g['parts'] for v in part['vertices']))
            g['safety_min_cm']=[g['position'][a]-radius_cm+min(0,g['motion']['delta_cm'][a]) for a in range(3)]
            g['safety_max_cm']=[g['position'][a]+radius_cm+max(0,g['motion']['delta_cm'][a]) for a in range(3)]
        if any(g['safety_min_cm'][i*2]<0 or g['safety_max_cm'][i*2]>doc['bounds']['max'][i] for i in range(2)):continue
        doc['gimmicks'].append(g);challenges.append(dict(id=g['id'],kind=kind,road_id=r['id'],position_cm=center,bypass_width_cm=min(r['widths_cm'])-110))
    doc['heightmaps']=[];heights=[]
    for z in range(doc['bounds']['max'][1]//1600):
        for x in range(doc['bounds']['max'][0]//1600):
            values=[height(x*1600+i*200,z*1600+j*200) for j in range(9) for i in range(9)];heights.extend(values)
            offset=min(-1000,min(values));im=Image.new('I',(9,9));im.putdata([v-offset for v in values]);out=io.BytesIO();im.convert('I;16').save(out,format='PNG',compress_level=9);data=out.getvalue();path='terrain/'+digest(data)+'.png';payloads[path]=data
            doc['heightmaps'].append(dict(cell=dict(x=x,y=z),path=path,spacing_cm=200,offset_cm=offset,step_cm=1,source_accuracy_cm=None))
    meta.update(size=half(meta['size']),grid_pads=pads,challenges=challenges,bridges=bridges,underpass=underpass,street_infill_count=count,acceleration_sections=[],relief=round((max(heights)-min(heights))/100,2),elevation_range_m=[min(heights)/100,max(heights)/100])
    for d in meta['district_records']:d['polygon_m']=[[v/2 for v in p] for p in d['polygon_m']]
    for l in meta['landmark_records']:l['position_m']=[v/2 for v in l['position_m']]
    for view in meta.get('review_views',[]):
        for key,val in view.items():
            if isinstance(val,list) and len(val)==3 and all(isinstance(v,(float,int)) for v in val):view[key]=[v/2 for v in val]
    # Scale the optional authored environment regions as well as geometry.
    if isinstance(doc.get('environment'),dict):
        for region in doc['environment'].get('regions',[]):
            if 'polygon' in region:region['polygon']=[half(p) for p in region['polygon']]
    payloads['document.json']=canonical(doc);meta['source_files']={path:digest(data) for path,data in payloads.items()}
    folder=destination/meta['id'];folder.mkdir(parents=True,exist_ok=False)
    for path,data in {**payloads,'region.json':canonical(meta)}.items():
        target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'examples/compact-driving');p.add_argument('--kit',type=Path,required=True);a=p.parse_args()
    for ident in IDS:
        m=build(a.source/ident,a.destination,a.kit);print(ident,m['size'],'infill',m['street_infill_count'],'skills',len(m['challenges']),'bridges',[(b['road_id'],round(b['approach_grade'],2)) for b in m['bridges']],flush=True)
