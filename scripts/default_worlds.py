#!/usr/bin/env python3
"""Reproducible authored worlds, one theme per invocation. Public MIT tooling.

The recipes design roads, terrain and places explicitly. Randomness only fills
declared landscape areas. Publish into a fresh per-theme source directory.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image
from shapely.geometry import LineString, Point, Polygon, MultiPoint, box
from shapely.ops import unary_union
from shapely import affinity
from shapely import constrained_delaunay_triangles

from reference_maps import empty, canonical, road

THEMES={'village':(1120,960),'neon-harbor':(1920,1280),'deep-forest':(1760,1760),
    'red-canyon':(2400,1200),'snow-mountain':(1600,2080),'machine-factory':(1440,1440),'sky-park':(1920,1600)}
def digest(data):return hashlib.sha256(data).hexdigest()
def smooth(value):return np.clip(value,0,1)**2*(3-2*np.clip(value,0,1))

def curve(points):
    if len(points)==2:return points
    output=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        before=points[max(0,i-1)];after=points[min(len(points)-1,i+2)]
        steps=max(2,math.ceil(math.dist(a,b)/18))
        for j in range(steps):
            t=j/steps
            output.append(tuple((2*t**3-3*t*t+1)*a[k]+(t**3-2*t*t+t)*(b[k]-before[k])*.35
                +(-2*t**3+3*t*t)*b[k]+(t**3-t*t)*(after[k]-a[k])*.35 for k in range(2)))
    return output+[points[-1]]

class World:
    def __init__(self,theme,kit):
        self.theme=theme;self.size=THEMES[theme];self.kit=kit
        sys.path.insert(0,str(kit/'scripts'))
        from authored_assets import library
        self.library=library();self.payloads={};self.pads=[];self.obstacles=[];self.scenery=[]
        if theme=='neon-harbor':
            from harbor_assets import library as harbor_library
            self.library.update(harbor_library())
        self.footprints=[];self.footprint_grid=defaultdict(list);self._road_exclusion=None
        self.routes={};self.paints=[];self.water=[];self.places=[];self.reviews=[]
        self.doc=empty('default-'+theme+'-authored-20261009',self.size[0]*100,3200)
        self.doc.update(bounds=dict(min=[0,0],max=[v*100 for v in self.size]),free_roam=True,
            seed=10092026,terrain_base_cm=0,surface_areas=[],water_bodies=[],courses=[],gimmicks=[])
        self.doc['attributions']=[dict(source='mapeditor-default-worlds-v1',license='MIT',
            notice='Original fictional landscape, roads and places; authored recipe in '+('default_village.py' if theme=='village' else 'default_harbor.py')+'. No surveyed/user data.')]
        self.doc['provenance'].update(tool_id='mapeditor-default-worlds',build_id='authored-worlds-v1',
            first_created='2026-10-09T00:00:00Z',last_edited='2026-10-09T00:00:00Z')
        self.doc['theme']='rural'
        self.doc['environment']=dict(version=1,concept='countryside',architecture='rural',climate='temperate',settlement='village',
            latitude_mdeg=37000,longitude_mdeg=127000,utc_offset_minutes=540,sunrise_minutes=360,sunset_minutes=1080,
            start_minutes=840,ground_color=[117,140,88],lights=[],regions=[])

    @staticmethod
    def river_y(x):return 292+32*np.sin(np.asarray(x)/170)+12*np.sin(np.asarray(x)/73)

    def base(self,x,y):
        x=np.asarray(x);y=np.asarray(y)
        h=8.5+1.2*np.sin(x/126)*np.sin(y/148)
        for cx,cy,height,sx,sy in [(135,110,24,165,165),(920,130,23,215,180),(1080,845,16,165,230),(60,860,12,170,170)]:
            h=h+height*np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2)
        valley=np.abs(y-self.river_y(x));bank=smooth((valley-6)/27)
        return 2.2*(1-bank)+h*bank

    def height(self,x,y):
        if np.ndim(x)==0 and np.ndim(y)==0:
            x=float(x);y=float(y);h=float(self.base(x,y));best=float('inf');level=h;width=0
            for cx,cy,rx,ry,z in self.pads:
                d=max(abs(x-cx)-rx,abs(y-cy)-ry);blend=max(0,min(1,d/6));blend=blend*blend*(3-2*blend)
                h=h*blend+z*(1-blend)
            for r in self.doc['roads']:
                if r['kind']!='ground':continue
                for a,b in zip(r['points'],r['points'][1:]):
                    ax,az,ay=[v/100 for v in a];bx,bz,by=[v/100 for v in b]
                    dx=bx-ax;dy=by-ay;t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
                    distance=math.hypot(x-ax-t*dx,y-ay-t*dy)
                    if distance<best:best=distance;level=az+t*(bz-az);width=r['widths_cm'][0]/200+r.get('sidewalk_cm',0)/100+1
            blend=max(0,min(1,(best-width)/24));blend=blend*blend*(3-2*blend)
            h=h*blend+level*(1-blend)
            return h
        x=np.asarray(x);y=np.asarray(y);h=self.base(x,y)
        for cx,cy,rx,ry,z in self.pads:
            d=np.maximum(np.abs(x-cx)-rx,np.abs(y-cy)-ry)
            blend=1-smooth(d/6)
            h=h*(1-blend)+z*blend
        best=np.full(np.broadcast_shapes(x.shape,y.shape),np.inf);level=h.copy();width=np.zeros_like(h)
        for r in self.doc['roads']:
            if r['kind']!='ground':continue
            for a,b in zip(r['points'],r['points'][1:]):
                ax,az,ay=[v/100 for v in a];bx,bz,by=[v/100 for v in b]
                dx=bx-ax;dy=by-ay;t=np.clip(((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy),0,1)
                distance=np.hypot(x-ax-t*dx,y-ay-t*dy)
                take=distance<best;best=np.where(take,distance,best)
                level=np.where(take,az+t*(bz-az),level)
                width=np.where(take,r['widths_cm'][0]/200+r.get('sidewalk_cm',0)/100+1,width)
        weight=1-smooth((best-width)/24)
        h=h*(1-weight)+level*weight
        return h

    def path(self,name,points,width=7,sidewalk=0,kind='ground',level=None,surface='asphalt',markings=True):
        points=curve(points)
        values=[]
        for x,y in points:
            h=float(self.base(x,y)) if level is None else (level(x,y) if callable(level) else level)
            values.append([round(x*100),round(h*100),round(y*100)])
        # A shared node owns its level. Approaches explicitly meet that level.
        for point in (values[0],values[-1]):
            node=next((n for n in self.doc['nodes'] if n['position'][::2]==point[::2]),None)
            if node:point[1]=node['position'][1]
        ids=['junction-'+str(p[0])+'-'+str(p[2]) for p in (values[0],values[-1])]
        road(self.doc,name,values,kind,round(width*100),surface,*ids)
        r=self.doc['roads'][-1];r['sidewalk_cm']=round(sidewalk*100)
        if markings and surface=='asphalt':
            r['markings']=dict(lanes=2,center_line=True,edge_lines=True,crosswalk_start=False,crosswalk_end=False)
        self.routes[name]=LineString([(p[0]/100,p[2]/100) for p in values])
        return name

    def road_area(self,margin=0):
        return unary_union([self.routes[r['id']].buffer(r['widths_cm'][0]/200+r.get('sidewalk_cm',0)/100+margin)
                           for r in self.doc['roads']])

    def asset(self,name):
        source,files,bounds=self.library[name]
        if not any(a['id']==source['id'] for a in self.doc['assets']):
            self.doc['assets'].append(copy.deepcopy(source));self.payloads.update(files)
        return source,bounds

    def place(self,name,asset,x,y,yaw=0,level=None,foundation=False,solid=True):
        record,bounds=self.asset(asset)
        area=affinity.translate(affinity.rotate(box(bounds[0][0],bounds[0][2],bounds[1][0],bounds[1][2]),yaw,origin=(0,0)),x,y)
        if not box(1,1,self.size[0]-1,self.size[1]-1).covers(area):raise ValueError('Outside world: '+name)
        points=[]
        for proxy in record['collision']:
            c=proxy['center'];s=proxy['size_cm']
            points.extend([(c[0]/100+dx*s[0]/200,c[2]/100+dy*s[2]/200) for dx in (-1,1) for dy in (-1,1)])
        points.extend((v[0]/100,v[2]/100) for convex in record.get('convex_collision',[]) for v in convex['vertices'])
        footprint=affinity.translate(affinity.rotate(MultiPoint(points).convex_hull,yaw,origin=(0,0)),x,y)
        a,b,c,d=footprint.bounds
        keys=[(gx,gy) for gx in range(math.floor(a/16),math.floor(c/16)+1) for gy in range(math.floor(b/16),math.floor(d/16)+1)]
        neighbors={index for key in keys for index in self.footprint_grid[key]}
        if not solid and not asset.startswith(('bridge-support','harbor-pier')):
            if self._road_exclusion is None:self._road_exclusion=self.road_area(.35)
            if footprint.intersects(self._road_exclusion):return None
            if any(footprint.buffer(.08).intersects(self.footprints[index][1]) for index in neighbors):return None
        z=float(self.height(x,y)) if level is None else level
        if foundation:
            a,b,c,d=area.bounds;self.pads.append(((a+c)/2,(b+d)/2,(c-a)/2+.35,(d-b)/2+.35,z))
        self.doc['placements'].append(dict(id=name,asset_id=record['id'],position=[round(x*100),round(z*100),round(y*100)],
            quarter_turns=0,yaw_offset_mdeg=round(((yaw+180)%360-180)*1000)))
        if solid and (record['collision'] or record.get('convex_collision')):self.obstacles.append((name,area))
        for key in keys:self.footprint_grid[key].append(len(self.footprints))
        self.footprints.append((name,footprint))
        self.scenery.append((name,area,asset))
        return area

    def paint(self,name,shape,surface):
        shape=shape.difference(self.road_area(.08))
        # A 2.5 cm separator prevents independently rounded clipped rings from
        # crossing their neighbour at the centimetre precision of current v1.
        if self.paints:shape=shape.difference(unary_union(self.paints).buffer(.025))
        parts=[shape] if isinstance(shape,Polygon) else list(getattr(shape,'geoms',[]))
        index=0
        for part in parts:
            if not isinstance(part,Polygon) or part.area<.5:continue
            polygons=list(constrained_delaunay_triangles(part).geoms) if part.interiors else [part]
            for polygon in polygons:
                # Clip operations can leave sub-centimetre edges. Collapse only
                # consecutive equal quantized vertices before writing v1 rings.
                points=[]
                for x,y in list(polygon.exterior.coords)[:-1]:
                    point=[round(x*100),round(y*100)]
                    if not points or point!=points[-1]:points.append(point)
                if len(points)>1 and points[-1]==points[0]:points.pop()
                if len(points)<3:continue
                quantized=Polygon(points)
                if quantized.area==0:continue
                if not quantized.is_valid:raise ValueError('Paint ring invalid after centimetre quantization: '+name)
                self.doc['surface_areas'].append(dict(id=name+'-'+str(index),surface=surface,
                    polygon=points));index+=1
            self.paints.append(part)

    def water_body(self,name,shape,level=3.8):
        shape=shape.intersection(box(0,0,*self.size)).simplify(.12)
        self.doc['water_bodies'].append(dict(id=name,polygon=[[round(x*100),round(y*100)] for x,y in list(shape.exterior.coords)[:-1]],
            islands=[],surface_cm=round(level*100),bottom_cm=round((level-1.6)*100),flow_cm_s=[45,0]))
        self.water.append(shape)

    def frontage(self,road_id,stations,side,variants,group,setback=13):
        line=self.routes[road_id]
        for i,distance in enumerate(stations):
            p=line.interpolate(distance);q=line.interpolate(min(line.length,distance+.5));dx=q.x-p.x;dy=q.y-p.y
            length=math.hypot(dx,dy);nx=-dy/length*side;ny=dx/length*side
            name=group+'-'+str(i);asset=variants[i%len(variants)]
            # Deep cottage porches and commercial awnings both clear the walk.
            setback_actual=max(setback,17 if asset.startswith('home') else 14.5)
            x=p.x+nx*setback_actual;y=p.y+ny*setback_actual;yaw=math.degrees(math.atan2(-nx,ny))
            ground=float(self.height(p.x,p.y))
            self.place(name,asset,x,y,yaw,ground,True)
            self.paint(name+'-access',LineString([(x,y),(p.x,p.y)]).buffer(1.15,cap_style=2),'concrete' if asset.startswith('shop') else 'gravel')
            # Deliberate rear yards, useful frontage objects and occasional cars.
            if asset.startswith('home'):
                self.place(name+'-garden-tree','tree-'+str((i%3)+2),x+nx*11,y+ny*11,(i*73)%360,solid=False)
                tangent=math.degrees(math.atan2(dy,dx))
                for edge in (-1,1):
                    self.place(name+'-front-hedge-'+str(edge),'hedge',p.x+nx*9.2+dx/length*edge*4.6,
                        p.y+ny*9.2+dy/length*edge*4.6,tangent,solid=False)
                if i%3==0 and road_id not in ('arrival-road','market-street','east-high-street'):
                    self.place(name+'-car','parked-car',x+dx/length*10.5,y+dy/length*10.5,yaw)
            else:
                self.place(name+'-rear-bin','bin',x+nx*7,y+ny*7,yaw)
                half_width=(self.library[asset][2][1][0]-self.library[asset][2][0][0])/2+.6
                court=Polygon([(p.x+dx/length*a+nx*b,p.y+dy/length*a+ny*b)
                    for a,b in [(-half_width,6.9),(half_width,6.9),(half_width,18),(-half_width,18)]])
                self.paint(name+'-forecourt',court,'concrete')
                if i%2==0:self.place(name+'-planter','planter',p.x+nx*7.8,p.y+ny*7.8,yaw,ground)
                if i%3==1:
                    self.place(name+'-customer-car','parked-car',p.x+nx*8.85+dx/length*3.7,
                        p.y+ny*8.85+dy/length*3.7,math.degrees(math.atan2(dx,-dy)),ground)

    def bake_terrain(self):
        xs=np.arange(0,self.size[0]+2,2);ys=np.arange(0,self.size[1]+2,2)
        heights=np.rint(self.height(xs[None,:],ys[:,None])*100).astype(np.int32)
        if np.max(heights)-np.min(heights)>65535:raise ValueError('Height profile out of range')
        # All tiles slice the same integer sample grid, including shared borders.
        offset=-10000
        for cy in range(math.ceil(self.size[1]/32)):
            for cx in range(math.ceil(self.size[0]/32)):
                values=heights[cy*16:cy*16+17,cx*16:cx*16+17]-offset
                if values.shape!=(17,17):values=np.pad(values,((0,17-values.shape[0]),(0,17-values.shape[1])),mode='edge')
                stream=io.BytesIO();Image.fromarray(values.astype(np.uint16)).save(stream,format='PNG',compress_level=9)
                data=stream.getvalue();path='terrain/'+digest(data)+'.png';self.payloads[path]=data
                self.doc['heightmaps'].append(dict(cell=dict(x=cx,y=cy),path=path,spacing_cm=200,
                    offset_cm=offset,step_cm=1,source_accuracy_cm=None))
        return heights

    def course(self,identity,name,walk):
        points=[];last=None;length=0
        records={r['id']:r for r in self.doc['roads']}
        for hop,spec in enumerate(walk):
            key=spec.removeprefix('-');forward=not spec.startswith('-');r=records[key]
            if last is not None and last!=(r['from'] if forward else r['to']):raise ValueError('Disconnected course '+identity+' '+key)
            last=r['to'] if forward else r['from']
            coords=list(self.routes[key].coords)
            line=LineString(coords if forward else coords[::-1]);length+=line.length
            distances=[100,145] if hop==0 else []
            distances+=list(range(195 if hop==0 else 35,int(line.length-10),75))
            distances.append(line.length-12)
            for distance in sorted(set(distances)):
                if distance< (100 if hop==0 else 12):continue
                p=line.interpolate(distance)
                if points and math.hypot(p.x-points[-1]['x_cm']/100,p.y-points[-1]['y_cm']/100)<14:continue
                points.append(dict(x_cm=round(p.x*100),y_cm=round(p.y*100),surface_id=key,structural=r['kind']!='ground'))
        if len(points)>60:
            tail=points[2:];points=points[:2]+[tail[round(i*(len(tail)-1)/57)] for i in range(58)]
        start=getattr(self,'spawn',dict(x_cm=22000,y_cm=48000,surface_id='arrival-road',heading_radians=-math.pi/2))
        return dict(id=identity,name=name,waypoints=points,start=copy.deepcopy(start),mode='sprint',laps=1,
            checkpoint_radius_cm=400,length_m=round(length-100,1))

    def validate(self):
        errors=[];roads=self.doc['roads'];nodes={n['id'] for n in self.doc['nodes']};reached={roads[0]['from']}
        while True:
            more={n for r in roads if r['from'] in reached or r['to'] in reached for n in [r['from'],r['to']]}
            if more<=reached:break
            reached|=more
        if nodes!=reached:errors.append('Disconnected road graph')
        grade=max(abs(b[1]-a[1])/math.hypot(b[0]-a[0],b[2]-a[2]) for r in roads for a,b in zip(r['points'],r['points'][1:]))
        if grade>.12:errors.append('Road grade exceeds 12%: '+str(grade))
        # Architectural solids must stay out of the travelled carriageway.
        carriageway=unary_union([self.routes[r['id']].buffer(r['widths_cm'][0]/200+.20) for r in roads])
        for name,shape in self.obstacles:
            if shape.intersection(carriageway).area>.02:errors.append('Roadside clearance: '+name)
        checked=set()
        for group in self.footprint_grid.values():
            for i in group:
                for j in group:
                    if i>=j or (i,j) in checked:continue
                    checked.add((i,j));a=self.footprints[i];b=self.footprints[j]
                    if a[1].intersection(b[1]).area>.002:errors.append('Asset footprints overlap: '+a[0]+' / '+b[0])
        if errors:raise ValueError('\n'.join(errors[:30]))
        counts=defaultdict(int)
        for _,_,asset in self.scenery:counts[asset]+=1
        return dict(road_graph_connected=True,max_road_grade=round(grade,5),placements=len(self.scenery),
            authored_places=self.places,asset_instances=dict(counts),texture_max_px=512,
            formats=1,cell_size_m=32,art_status='user review required')

def build(theme,kit):
    if theme=='village':
        from default_village import compose
    elif theme=='neon-harbor':
        from default_harbor import compose
    else:raise ValueError('Theme recipe has not yet been authored: '+theme)
    world=World(theme,kit);meta=compose(world)
    meta['validation']=world.validate()
    heights=world.bake_terrain();meta['relief']=round(float(heights.max()-heights.min())/100,2)
    sources=[Path(__file__),Path(__file__).with_name('default_village.py' if theme=='village' else 'default_harbor.py'),kit/'scripts/authored_assets.py',kit/'scripts/world_geometry.py']
    if theme=='neon-harbor':sources.append(kit/'scripts/harbor_assets.py')
    fingerprint=digest(b''.join(p.read_bytes() for p in sources))
    world.doc['provenance']['fingerprint']=fingerprint
    meta['authoring']=dict(recipe_sha256=fingerprint,texture_max_px=512,format_version=1,owner='MapEditor')
    return world,meta

def publish(destination,theme,kit,cli):
    target=destination/theme
    if target.exists() or (destination/(theme+'.memap')).exists():raise FileExistsError('Choose an empty per-theme destination')
    world,meta=build(theme,kit)
    destination.mkdir(parents=True,exist_ok=True);(destination/'.gdignore').write_text('')
    pending=destination/(theme+'.pending')
    if pending.exists():raise FileExistsError(pending)
    pending.mkdir()
    try:
        (pending/'document.json').write_bytes(canonical(world.doc))
        (pending/'region.json').write_bytes(canonical(meta))
        for path,data in world.payloads.items():
            full=pending/path;full.parent.mkdir(parents=True,exist_ok=True);full.write_bytes(data)
        temporary_package=destination/(theme+'.pending.memap')
        subprocess.run([str(cli.resolve()),'pack',str(pending),str(temporary_package)],check=True)
        checked=subprocess.run([str(cli.resolve()),'validate-cells',str(temporary_package)],capture_output=True,text=True)
        if checked.returncode:
            raise RuntimeError('Native all-cell validation failed: '+checked.stderr.strip())
        cells=json.loads(checked.stdout)
        meta['validation']['native_generated_cells']=len(cells)
        meta['validation']['cell_hashes_sha256']=digest(canonical(cells))
        (pending/'region.json').write_bytes(canonical(meta))
        pending.rename(target);temporary_package.rename(destination/(theme+'.memap'))
        ids=[key for key in THEMES if (destination/(key+'.memap')).is_file()]
        (destination/'default-worlds.json').write_bytes(canonical(dict(format_version=1,maps=ids,owner='MapEditor')))
    except BaseException:
        # Only this invocation's unpublished candidate, never prior/user data.
        shutil.rmtree(pending,ignore_errors=True)
        (destination/(theme+'.pending.memap')).unlink(missing_ok=True)
        raise
    print('AUTHORED_WORLD',theme,meta['validation'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path)
    p.add_argument('--theme',choices=THEMES,required=True);p.add_argument('--kit',type=Path,required=True);p.add_argument('--cli',type=Path,required=True)
    a=p.parse_args();publish(a.destination,a.theme,a.kit,a.cli)
