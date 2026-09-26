#!/usr/bin/env python3
"""Course-first, independently authored arcade networks (metres, MIT).

Shared road/asset/packing tools are reused; no previous regional layout is read.
Every output directory must be new. Existing source, packages and evidence survive.
"""
import argparse
import copy
import hashlib
import io
import json
import math
import random
import sys
from pathlib import Path
from PIL import Image
from reference_maps import empty, road, canonical
from special_driving_maps import place as structure

MAPS = [
    ('village', '마을 드라이빙 파크', 'Village Driving Park', (224,192), 'Connected practice loops, school streets and a village park.', ['School circuit','Slalom and hairpins','Village discovery']),
    ('neon-harbor', '네온 항만', 'Neon Harbor', (384,256), 'Layered dock roads, warehouse passages and a canal choice under neon lights.', ['Dock orientation','Crane express','Canal choice']),
    ('deep-forest', '깊은 숲', 'Deep Forest', (352,352), 'Branching forest roads meet around an island lake and gentle boat exits.', ['Forest clearing','Log trail','Lake choice']),
    ('red-canyon', '붉은 협곡', 'Red Canyon', (480,240), 'A long upper ridge and lower ravine meet at a quarry with an aerial jump.', ['Quarry road','Canyon flight','Ridge and ravine']),
    ('snow-mountain', '설산', 'Snow Mountain', (320,416), 'Climbing hairpins, a long descent and a sheltered tunnel through snowy slopes.', ['Lodge practice','Halfpipe descent','Summit switchbacks']),
    ('machine-factory', '기계 공장', 'Machine Factory', (288,288), 'Dense workshops, upper catwalks and machinery connect through a driving cylinder.', ['Workshop orientation','Cylinder shift','Moving assembly']),
    ('sky-park', '공중 놀이공원', 'Sky Amusement Park', (384,320), 'Ground attractions connect to colorful skyways, a vertical loop and aerial rings.', ['Carousel promenade','Sky loop','Aerial spectacle']),
]

def distance(p,a,b):
    dx,dz=b[0]-a[0],b[1]-a[1];length=dx*dx+dz*dz
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dz)/length)) if length else 0
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dz),t
def lerp(a,b,t):return [x+(y-x)*t for x,y in zip(a,b)]
def ease(v):v=max(0,min(1,v));return v*v*(3-2*v)
def digest(data):return hashlib.sha256(data).hexdigest()
def inside(p,poly):
    hit=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit

class World:
    def __init__(self,spec,kit):
        self.id,self.name,self.en,self.size,self.description,self.course_names=spec
        self.w,self.h=self.size;self.kit=kit
        self.doc=empty('arcade-world-'+self.id,self.w*100,3200)
        self.doc['bounds']['max']=[self.w*100,self.h*100]
        self.doc.update(water_bodies=[],gimmicks=[],surface_areas=[],courses=[])
        self.doc['provenance'].update(tool_id='mapeditor-arcade-world',build_id='arcade-world-v1',first_created='2026-09-26T00:00:00Z',last_edited='2026-09-26T00:00:00Z')
        self.doc['attributions']=[dict(source='arcade-world-original-layouts',license='MIT',notice='Original fictional course networks and scenery. Design references do not supply layouts or assets.')]
        self.aprons=[];self.paths={};self.routes=[];self.alternatives=[];self.exits=[];self.landmarks=[];self.views=[];self.occupied=[];self.segments=[];self.payloads={};self.used=set();self.assets={};self.asset_roots={}
        for library in ['richer-library','arcade-library']:
            base=kit/'assets'/library
            for a in json.loads((base/'library.json').read_text())['assets']:
                self.assets[a['id']]=a;self.asset_roots[a['id']]=base
        self.templates=json.loads((kit/'godot/driving_templates.json').read_text())
        self.rng=random.Random(9026+next(i for i,v in enumerate(MAPS) if v[0]==self.id))

    def link(self,name,points,width=5,kind='ground',surface='asphalt'):
        # Points use (x,map-y,height). Exact XYZ endpoints reuse nodes; crossings do not.
        xyz=[[round(x*100),round(h*100),round(z*100)] for x,z,h in points]
        def node(p):return 'node-'+'-'.join(map(str,p))
        road(self.doc,name,xyz,kind,round(width*100),surface,node(xyz[0]),node(xyz[-1]))
        self.paths[name]=points
        for a,b in zip(points,points[1:]):self.segments.append((a,b,width,kind,name))
        self.doc['roads'][-1]['markings']=dict(lanes=2 if width>=5 else 1,center_line=width>=5,edge_lines=True,crosswalk_start=False,crosswalk_end=False)

    def route(self,index,paths,required=None,choices=None):
        self.routes.append(dict(id=['intro','technical','expedition'][index],name=self.course_names[index],road_path=paths,required=required or [],choices=choices or []))

    def water(self,ident,polygon,level=0,flow=(0,0),islands=None,exits=None):
        self.doc['water_bodies'].append(dict(id=ident,polygon=[[round(x*100),round(z*100)] for x,z in polygon],islands=[[[round(x*100),round(z*100)] for x,z in ring] for ring in (islands or [])],surface_cm=round(level*100),bottom_cm=round((level-8)*100),flow_cm_s=list(flow)))
        self.exits.extend(dict(water=ident,land_m=list(p),width_m=7 if self.id=='neon-harbor' else 8,max_slope=.18) for p in (exits or []))

    def gimmick(self,kind,ident,p,yaw=0,scale=None):
        g=structure(self.templates,kind,[p[0]*100,p[2]*100,p[1]*100],yaw)
        g['id']=ident
        if scale:g['scale_per_mille']=scale
        # Exact conservative template extent, including translation. Landing is
        # additionally kept clear by the map's authored scenery exclusion.
        if 'track' in g:
            t=g['track'];r=4*t['radius_cm']+(2*t['width_cm'] if kind=='loop' else t['length_cm']//2)+40
        else:r=max(sum(abs(v[i])*g['scale_per_mille'][i]/1000 for i in range(3)) for part in g['parts'] for v in part['vertices'])+40
        margin=1800 if 'effect' in g else 150
        delta=g['motion']['delta_cm'];g['safety_min_cm']=[round(v-r-margin+min(0,delta[i])) for i,v in enumerate(g['position'])];g['safety_max_cm']=[round(v+r+margin+max(0,delta[i])) for i,v in enumerate(g['position'])]
        self.doc['gimmicks'].append(g)
        return dict(id=ident,position_m=list(p),kind=kind)

    def required(self,g,after,height=None):
        p=g['position_m'].copy()
        if height is not None:p[2]=height
        return dict(gimmick=g['id'],after_road=after,position_cm=[round(p[0]*100),round(p[2]*100),round(p[1]*100)],radius_cm=100,shape='sphere',placement_mode='free',surface_id='')

    def village(self):
        self.link('school-straight',[(35,145,1),(95,145,1)],6)
        self.link('school-turn',[(95,145,1),(114,127,1),(107,102,1),(82,88,1),(54,100,1),(35,120,1),(35,145,1)],5.5)
        self.link('s-curves',[(95,145,1),(131,143,1),(147,128,1),(127,111,1),(142,91,1),(166,89,1)],4)
        self.link('hairpins',[(166,89,1),(187,80,1),(194,59,1),(180,48,1),(162,55,1),(161,35,1),(140,25,1),(111,38,1),(107,102,1)],4)
        self.link('school-return',[(107,102,1),(72,64,1),(35,77,1),(35,120,1)],4.5)
        self.link('village-tour',[(95,145,1),(134,169,1),(196,164,1),(207,130,1),(189,103,1),(166,89,1)],5)
        self.link('park-crossing',[(82,88,1),(77,43,1),(45,26,1),(24,43,1),(35,77,1)],4)
        # Branch endpoints are explicit: split interior junction nodes into roads below.
        self.route(0,['school-straight','school-turn'])
        self.route(1,['school-straight','s-curves','hairpins','school-return'])
        self.route(2,['school-straight','village-tour','-s-curves'])
        self.gimmick('ramp','practice-ramp',(135,169,1),90)
        self.landmarks=[('arcade-school',75,116,0),('richer-shop-1',151,151,0),('richer-house-2',190,145,0)]
        self.views=[('signature',[125,23,177],[87,1,115])]

    def neon_harbor(self):
        self.link('quay-start',[(45,205,2),(115,205,2)],6)
        self.link('dock-loop',[(115,205,2),(130,180,2),(106,151,2),(65,155,2),(42,175,2),(45,205,2)],5)
        self.link('freight-west',[(115,205,2),(170,205,2),(185,174,2),(185,140,2)],6)
        self.link('warehouse-run',[(185,140,2),(155,120,2),(120,110,2),(90,88,2),(65,60,2)],4)
        self.link('warehouse-return',[(65,60,2),(36,92,2),(35,144,2),(45,205,2)],5)
        self.link('sky-ramp',[(115,205,2),(145,229,2),(218,227,8)],6,'elevated')
        self.link('sky-crossing',[(218,227,8),(249,203,8),(254,147,8),(229,105,8),(184,92,8),(157,68,8)],6,'elevated')
        self.link('sky-exit',[(157,68,8),(112,40,8),(65,60,2)],6,'elevated')
        self.link('canal-bank',[(185,140,2),(219,130,1),(238,90,1),(281,73,1),(325,86,1),(341,130,1),(321,158,1),(280,170,1)],5)
        self.link('canal-return',[(280,170,1),(256,193,1),(213,194,2),(185,174,2)],5)
        self.water('harbor-canal',[(242,110),(310,107),(326,132),(313,147),(271,151),(245,137)],0,(25,0),exits=[(219,130,1),(341,130,1)])
        self.link('boat-entry',[(219,130,1),(233,126,.4),(248,126,-.3)],7)
        self.link('boat-exit',[(319,131,-.3),(331,131,.3),(341,130,1)],7)
        self.alternatives=[dict(id='canal-choice',land=['canal-bank'],water=['boat-entry','boat-exit'],split=[219,130,1],merge=[341,130,1])]
        panel=self.gimmick('target_speed','quay-boost',(158,205,2),90)
        self.gimmick('barrier','loading-barrier',(149,116,2),70)
        self.route(0,['quay-start','dock-loop'])
        self.route(1,['quay-start','freight-west','warehouse-run','warehouse-return'],[self.required(panel,'freight-west')])
        self.route(2,['quay-start','freight-west','canal-bank','canal-return'],choices=['canal-choice'])
        self.landmarks=[('richer-dock-crane',274,186,0),('richer-dock-crane',325,177,0),('arcade-tank',204,105,0)]
        self.views=[('signature',[310,21,180],[262,0,132])]

    def deep_forest(self):
        self.link('clearing-start',[(42,275,1),(104,275,1)],6,'ground','dirt')
        self.link('clearing-loop',[(104,275,1),(125,250,1),(98,218,1),(59,223,1),(37,246,1),(42,275,1)],5,'ground','dirt')
        self.link('lake-west',[(104,275,1),(117,225,1),(108,175,1),(112,127,2),(142,94,2)],5,'ground','dirt')
        self.link('north-trail',[(142,94,2),(183,71,3),(213,81,3),(245,120,2),(269,156,1)],3,'ground','dirt')
        self.link('south-trail',[(117,225,1),(163,256,1),(211,246,1),(253,220,1),(269,156,1)],4,'ground','dirt')
        self.link('deep-trail',[(142,94,2),(97,67,4),(68,86,5),(51,128,4),(70,171,3),(98,218,1)],3,'ground','dirt')
        self.water('island-lake',[(135,135),(156,116),(203,115),(238,143),(246,183),(222,218),(178,230),(142,207),(127,167)],0,islands=[[(177,150),(194,147),(206,161),(195,176),(179,174)]],exits=[(108,175,1),(269,156,1)])
        self.link('lake-entry',[(108,175,1),(120,174,.25),(135,174,-.4)],8,'ground','dirt')
        self.link('lake-exit',[(239,177,-.4),(254,170,.25),(269,156,1)],8,'ground','dirt')
        self.alternatives=[dict(id='lake-choice',land=['lake-west','north-trail'],water=['lake-entry','lake-exit'],split=[108,175,1],merge=[269,156,1])]
        log=self.gimmick('log','fallen-log',(208,79,3),65)
        self.gimmick('ramp','forest-hop',(68,88,5),0)
        self.route(0,['clearing-start','clearing-loop'])
        self.route(1,['clearing-start','lake-west','north-trail','-south-trail'],[self.required(log,'north-trail',3.35)])
        self.route(2,['clearing-start','lake-west','north-trail','-south-trail'],choices=['lake-choice'])
        self.landmarks=[('richer-nord-1',72,242,0),('richer-bench',157,108,0)]
        self.views=[('signature',[140,20,219],[185,0,170])]

    def red_canyon(self):
        self.link('quarry-start',[(43,174,3),(110,174,3)],6,'ground','gravel')
        self.link('quarry-loop',[(110,174,3),(130,149,3),(115,117,3),(75,109,3),(43,139,3),(43,174,3)],5,'ground','gravel')
        self.link('ridge-ascent',[(110,174,3),(156,181,5),(196,164,10),(235,136,16)],5,'ground','gravel')
        self.link('upper-ridge',[(235,136,16),(275,122,18),(322,106,18),(369,79,18),(426,75,16)],5,'ground','gravel')
        self.link('rim-return',[(426,75,16),(446,121,14),(432,187,10),(354,206,8),(283,193,7),(212,211,5),(156,181,5)],5,'ground','gravel')
        self.link('lower-ravine',[(110,174,3),(161,123,1),(223,103,1),(280,82,1),(350,52,2),(399,45,4),(426,75,16)],5,'ground','dirt')
        self.link('rock-cave',[(223,103,1),(247,149,1),(295,157,1),(334,141,1),(350,52,2)],4,'tunnel','gravel')
        jump=self.gimmick('jump_height','canyon-launch',(287,118,18),109)
        ring=self.gimmick('air_ring','canyon-ring',(294,116,20.5),109)
        self.route(0,['quarry-start','quarry-loop'])
        self.route(1,['quarry-start','ridge-ascent','upper-ridge','rim-return'],[self.required(jump,'upper-ridge',18.3),self.required(ring,'upper-ridge')])
        self.route(2,['quarry-start','lower-ravine','rim-return'])
        self.landmarks=[('richer-dock-crane',94,139,0),('arcade-tank',126,187,0)]
        self.views=[('signature',[314,40,162],[293,18,116])]

    def snow_mountain(self):
        self.link('lodge-start',[(50,347,2),(120,347,2)],6)
        self.link('lodge-loop',[(120,347,2),(138,321,2),(109,288,3),(62,290,3),(43,319,2),(50,347,2)],5)
        self.link('hairpin-climb',[(120,347,2),(185,332,5),(238,296,9),(236,271,11),(186,259,13),(150,264,16),(127,247,18),(139,221,20),(184,210,23),(244,210,26),(269,188,28),(258,163,30),(204,151,32),(148,144,34),(130,122,36),(158,95,38),(172,86,40),(250,64,42)],5)
        self.link('long-descent',[(250,64,42),(278,99,36),(285,171,26),(286,256,15),(268,343,5),(214,378,2),(139,376,2),(120,347,2)],7)
        self.link('tunnel-shortcut',[(186,259,13),(174,283,10),(168,314,6),(185,332,5)],5,'tunnel')
        self.link('halfpipe-road',[(109,288,3),(130,265,7),(150,257,8),(176,258,12),(186,259,13)],5)
        half=self.gimmick('halfpipe','snow-halfpipe',(150,257,8),90)
        self.route(0,['lodge-start','lodge-loop'])
        self.route(1,['lodge-start','lodge-loop@0:2','halfpipe-road','tunnel-shortcut','-hairpin-climb@0:1'],[self.required(half,'-halfpipe-road',8.25)])
        self.route(2,['lodge-start','hairpin-climb'])
        self.landmarks=[('richer-nord-0',85,313,0),('richer-nord-2',105,326,0)]
        self.views=[('signature',[196,74,269],[162,22,217])]

    def machine_factory(self):
        self.link('factory-start',[(42,230,1),(109,230,1)],6)
        self.link('workshop-loop',[(109,230,1),(133,206,1),(119,177,1),(82,165,1),(47,184,1),(42,230,1)],5)
        self.link('assembly-line',[(109,230,1),(173,230,1),(208,203,1),(208,164,1),(208,115,1),(187,82,1),(142,73,1)],5)
        self.link('service-aisle',[(142,73,1),(111,91,1),(126,119,1),(163,143,1),(155,177,1),(119,177,1)],4)
        self.link('catwalk-up',[(47,184,1),(31,145,1),(50,108,6),(78,79,6)],4.5,'elevated')
        self.link('catwalk-grid',[(78,79,6),(152,111,6),(226,80,6),(248,121,6),(238,177,6),(208,203,1)],4.5,'elevated')
        self.link('cross-aisle',[(82,165,1),(97,140,1),(126,119,1)],4)
        cylinder=self.gimmick('cylinder','factory-cylinder',(208,140,1),180)
        rotor=self.gimmick('rotate','mixing-rotor',(153,137,1),55)
        platform=self.gimmick('platform','assembly-lift',(173,230,1),90)
        self.route(0,['factory-start','workshop-loop'])
        self.route(1,['factory-start','assembly-line','service-aisle'],[self.required(cylinder,'assembly-line',5.6)])
        self.route(2,['factory-start','assembly-line','service-aisle'],[self.required(platform,'assembly-line',1.5),self.required(rotor,'service-aisle',1.2)])
        self.landmarks=[('arcade-tank',170,190,0),('arcade-tank',178,186,0),('arcade-pipe-gantry',198,93,0),('richer-shed-3',101,191,0)]
        self.views=[('signature',[230,20,176],[208,3,140])]

    def sky_park(self):
        self.link('park-start',[(50,250,1),(118,250,1)],6)
        self.link('promenade',[(118,250,1),(136,225,1),(119,196,1),(82,182,1),(47,207,1),(50,250,1)],6)
        self.link('sky-climb',[(118,250,1),(170,269,1),(215,274,6),(258,251,12)],6,'elevated')
        self.link('sky-loop-road',[(258,251,12),(258,214,12),(258,170,12),(283,145,12),(325,135,12)],6,'elevated')
        self.link('sky-return',[(325,135,12),(348,95,12),(316,63,12),(251,58,12),(199,85,12),(170,135,8),(154,181,4),(118,250,1)],6,'elevated')
        self.link('stunt-approach',[(118,250,1),(168,214,1),(182,182,1),(204,165,1)],5)
        self.link('stunt-straight',[(204,165,1),(234,165,1),(281,165,1),(314,177,1)],6)
        self.link('attraction-return',[(314,177,1),(329,215,1),(310,259,1),(260,286,1),(206,296,1),(170,269,1)],5)
        loop=self.gimmick('loop','sky-vertical-loop',(258,193,12),180)
        self.gimmick('target_speed','loop-speed',(259.43,199,12),180)
        launch=self.gimmick('jump_height','park-launch',(228,165,1),90)
        ring=self.gimmick('air_ring','park-air-ring',(235,165,3.5),90)
        self.route(0,['park-start','promenade'])
        self.route(1,['park-start','sky-climb','sky-loop-road','sky-return'],[self.required(loop,'sky-loop-road',17)])
        self.route(2,['park-start','stunt-approach','stunt-straight','attraction-return'],[self.required(launch,'stunt-straight',1.3),self.required(ring,'stunt-straight')])
        self.landmarks=[('arcade-ferris-wheel',185,246,0),('arcade-carousel',97,218,0),('arcade-carousel',299,239,0)]
        self.views=[('signature',[282,28,213],[258,14,193])]

    def wet(self,x,z):
        best=(1e9,0,False)
        for body in self.doc['water_bodies']:
            poly=[[p[0]/100,p[1]/100] for p in body['polygon']];holes=[[[p[0]/100,p[1]/100] for p in ring] for ring in body['islands']]
            wet=inside([x,z],poly) and not any(inside([x,z],h) for h in holes)
            d=min(distance([x,z],a,b)[0] for ring in [poly]+holes for a,b in zip(ring,ring[1:]+ring[:1]))
            d=-d if wet else d
            if d<best[0]:best=(d,body['surface_cm']/100,wet)
        return best

    def height(self,x,z):
        natural={'village':1,'neon-harbor':2,'deep-forest':2+1.4*math.sin(x/40)*math.sin(z/55),'red-canyon':3+13*math.sin(z/35)**2,'snow-mountain':max(2,(380-z)/8),'machine-factory':1,'sky-park':1}[self.id]
        d,level,wet=self.wet(x,z)
        if d<0:natural=level-.12-min(3,-d*.16)
        elif d<12:natural=(level+.12)*(1-ease(d/12))+natural*ease(d/12)
        nearest=(1e9,natural)
        for a,b,width,kind,name in self.segments:
            if kind!='ground':continue
            ds,t=distance([x,z],a,b);edge=ds-width/2
            if edge<nearest[0]:nearest=(edge,a[2]+(b[2]-a[2])*t)
        if nearest[0]<7:natural=nearest[1]*(1-ease((nearest[0]-.6)/6.4))+natural*ease((nearest[0]-.6)/6.4)
        for ax,az,ah in self.aprons:
            d=math.hypot(x-ax,z-az)
            if d<12:natural=ah*(1-ease((d-8)/4))+natural*ease((d-8)/4)
        return round(natural*100)

    def place(self,asset,x,z,turn=0,force=False):
        a=self.assets[asset];xs=[];zs=[]
        for c in a['collision']:
            xs.append(abs(c['center'][0])+c['size_cm'][0]/2);zs.append(abs(c['center'][2])+c['size_cm'][2]/2)
        for c in a.get('convex_collision',[]):
            xs.extend(abs(p[0]) for p in c['vertices']);zs.extend(abs(p[2]) for p in c['vertices'])
        rx=max(xs,default=100)/100;rz=max(zs,default=100)/100
        if turn%2:rx,rz=rz,rx
        radius=math.hypot(rx,rz)+.7
        if not(radius<x<self.w-radius and radius<z<self.h-radius):return False
        if self.wet(x,z)[0]<radius+2:return False
        if any(distance([x,z],a,b)[0]<w/2+radius+1 for a,b,w,_,_ in self.segments):return False
        if any(abs(x-xx)<rx+xxr+1 and abs(z-zz)<rz+zzr+1 for xx,zz,xxr,zzr in self.occupied):return False
        if any(g['safety_min_cm'][0]/100-radius<x<g['safety_max_cm'][0]/100+radius and g['safety_min_cm'][2]/100-radius<z<g['safety_max_cm'][2]/100+radius for g in self.doc['gimmicks']):return False
        self.doc['placements'].append(dict(id='prop-'+str(len(self.doc['placements'])),asset_id=asset,position=[round(x*100),self.height(x,z),round(z*100)],quarter_turns=turn))
        self.used.add(asset);self.occupied.append((x,z,rx,rz));return True

    def scenery(self):
        for asset,x,z,turn in self.landmarks:
            if not self.place(asset,x,z,turn):
                found=False
                for radius in range(2,33,2):
                    for angle in range(16):
                        if self.place(asset,x+radius*math.cos(angle*math.tau/16),z+radius*math.sin(angle*math.tau/16),turn):found=True;break
                    if found:break
                if not found:raise ValueError(('landmark clearance',self.id,asset,x,z))
        styles={'village':['richer-house-0','richer-shop-2','richer-house-1'],'neon-harbor':['richer-container','richer-shed-1','richer-container'],'deep-forest':['richer-canopy-0','richer-canopy-1','richer-grove-2'],'red-canyon':['richer-rock-0','richer-rock-1','richer-rock-2'],'snow-mountain':['arcade-pine','arcade-pine','richer-rock-0'],'machine-factory':['arcade-tank','arcade-pipe-gantry','richer-shed-0'],'sky-park':['richer-shop-2','richer-canopy-1','richer-house-3']}[self.id]
        count={'village':100,'neon-harbor':150,'deep-forest':650,'red-canyon':170,'snow-mountain':300,'machine-factory':100,'sky-park':110}[self.id]
        for _ in range(count*10):
            x=self.rng.uniform(12,self.w-12);z=self.rng.uniform(12,self.h-12)
            if self.id in ['deep-forest','snow-mountain'] and math.sin(x/23)*math.cos(z/29)<-.45:continue
            if self.place(self.rng.choice(styles),x,z,self.rng.randrange(4)):count-=1
            if count==0:break
        # Legibility: small lamps/cones/benches flank starts and junction approaches.
        for a,b,w,kind,name in self.segments:
            if kind!='ground':continue
            length=math.dist(a[:2],b[:2]);dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
            for side in [-1,1]:
                p=lerp(a,b,.5);x,z=p[0]-dz*side*(w/2+3),p[1]+dx*side*(w/2+3)
                self.place('arcade-cone' if self.id=='village' else 'richer-lamp',x,z)

    def finish_routes(self):
        # Every authored vertex is a graph node. Shared XYZ nodes connect branches;
        # overpasses at the same XZ with different heights remain separate.
        originals={r['id']:r for r in self.doc['roads']}
        self.doc['roads']=[];self.doc['nodes']=[];self.segments=[]
        degree={}
        for rr in originals.values():
            for a,b in zip(rr['points'],rr['points'][1:]):
                for point in [a,b]:degree[tuple(point)]=degree.get(tuple(point),0)+1
        types={}
        for rr in originals.values():
            for a,b in zip(rr['points'],rr['points'][1:]):
                kind='ground' if degree[tuple(a)]>2 or degree[tuple(b)]>2 else rr['kind']
                for point in [a,b]:types.setdefault(tuple(point),set()).add(kind)
        mixed={p for p,kinds in types.items() if 'ground' in kinds and len(kinds)>1}
        self.aprons=[(p[0]/100,p[2]/100,p[1]/100) for p in sorted(mixed)]
        split={}
        for name,rr in originals.items():
            split[name]=[]
            for i,(a,b) in enumerate(zip(rr['points'],rr['points'][1:])):
                kind='ground' if degree[tuple(a)]>2 or degree[tuple(b)]>2 else rr['kind']
                length=math.dist(a,b);part=[a]
                # Flat, wide mouths at all terrain/deck/tunnel transitions.
                if tuple(a) in mixed:
                    p=[round(v) for v in lerp(a,b,min(.3,800/length))];p[1]=a[1];part.append(p)
                if tuple(b) in mixed:
                    p=[round(v) for v in lerp(a,b,1-min(.3,800/length))];p[1]=b[1];part.append(p)
                part.append(b);group=[]
                for j,(aa,bb) in enumerate(zip(part,part[1:])):
                    rid=name+'-s'+str(i)+'-p'+str(j);group.append(rid)
                    self.segments.append(([aa[0]/100,aa[2]/100,aa[1]/100],[bb[0]/100,bb[2]/100,bb[1]/100],rr['widths_cm'][i]/100,kind,rid))
                    road(self.doc,rid,[aa,bb],kind,rr['widths_cm'][i],rr['surfaces'][i],
                         'node-'+'-'.join(map(str,aa)),'node-'+'-'.join(map(str,bb)))
                    self.doc['roads'][-1]['markings']=copy.deepcopy(rr['markings'])
                    if self.id=='sky-park':self.doc['roads'][-1]['markings']['color']=[40,145,205] if name.startswith('sky-') else ([205,72,99] if name.startswith('stunt-') else [198,148,39])
                split[name].append(group)
        roads={r['id']:r for r in self.doc['roads']}
        for route in self.routes:
            itinerary=[]
            for key in route['road_path']:
                base=key.lstrip('-').split('@')[0];ids=split[base]
                if '@' in key:
                    lo,hi=map(int,key.split('@')[1].split(':'));ids=ids[lo:hi]
                ids=[rid for group in ids for rid in group]
                itinerary.extend((rid,key.startswith('-'),base) for rid in (ids[::-1] if key.startswith('-') else ids))
            points=[];total=0;previous=None;ordered=[];required_added=set()
            for rid,reverse,base in itinerary:
                rr=roads[rid];a,b=rr['points'][::-1] if reverse else rr['points']
                if previous is not None and a!=previous:raise ValueError(('disconnected route',self.id,route['id'],rid,previous,a))
                previous=b;length=math.dist(a,b);offset=total;total+=length/100
                steps=max(1,math.ceil(length/2700))
                for n in range(steps):
                    t=(n+.5)/steps;p=lerp(a,b,t);along=offset+length*t/100
                    if along<30:continue
                    ordered.append((along,dict(x_cm=round(p[0]),y_cm=round(p[2]),surface_id=rid,structural=rr['kind']!='ground')))
                for cp in route['required']:
                    if cp['after_road'].lstrip('-').split('@')[0]!=base:continue
                    p=cp['position_cm'];d,t=distance([p[0],p[2]],[a[0],a[2]],[b[0],b[2]])
                    if d<150 and 0<=t<=1 and cp['gimmick'] not in required_added:
                        required_added.add(cp['gimmick'])
                        ordered.append((offset+length*t/100,dict(checkpoint={k:v for k,v in cp.items() if k in ['position_cm','radius_cm','shape','placement_mode','surface_id']},gimmick=cp['gimmick'],x_cm=p[0],y_cm=p[2])))
            # Branch gates are common, immediately BEFORE the split and AFTER the
            # merge. Interior land gates disappear so either side can complete.
            for choice in [c for c in self.alternatives if c['id'] in route['choices']]:
                gates=[];running=0
                for rid,reverse,base in itinerary:
                    rr=roads[rid];a,b=rr['points'][::-1] if reverse else rr['points'];length=math.dist(a,b)/100
                    for label in ['split','merge']:
                        p=choice[label];d,t=distance(p,[a[0]/100,a[2]/100],[b[0]/100,b[2]/100])
                        if d<.01:
                            gates.append((label,running+length*t))
                    running+=length
                lo=min(v for k,v in gates if k=='split')-4;hi=max(v for k,v in gates if k=='merge')+4
                ordered=[(t,p) for t,p in ordered if t<lo or t>hi]
                for target in [lo,hi]:
                    running=0
                    for rid,reverse,base in itinerary:
                        rr=roads[rid];a,b=rr['points'][::-1] if reverse else rr['points'];length=math.dist(a,b)/100
                        if running<=target<=running+length:
                            p=lerp(a,b,(target-running)/length);ordered.append((target,dict(x_cm=round(p[0]),y_cm=round(p[2]),surface_id=rid,structural=rr['kind']!='ground',choice_gate=choice['id'])))
                            break
                        running+=length
            points=[p for _,p in sorted(ordered,key=lambda v:v[0])]
            # A required elevated checkpoint replaces nearby ordinary surface gates.
            required_positions=[(t,p) for t,p in ordered if 'gimmick' in p]
            points=[p for t,p in sorted(ordered,key=lambda v:v[0]) if 'gimmick' in p or all(abs(t-rt)>5 for rt,_ in required_positions)]
            if {p.get('gimmick') for p in points if 'gimmick' in p}!={p['gimmick'] for p in route['required']}:raise ValueError(('missing required gate',self.id,route['id']))
            rid,reverse,_=itinerary[0];a,b=roads[rid]['points'];start=lerp(a,b,1800/math.dist(a,b));gate=lerp(a,b,2600/math.dist(a,b))
            points.insert(0,dict(x_cm=round(gate[0]),y_cm=round(gate[2]),surface_id=rid,structural=False))
            route.update(road_path=[('-' if rev else '')+rid for rid,rev,_ in itinerary],waypoints=points,start=dict(x_cm=round(start[0]),y_cm=round(start[2]),surface_id=rid,heading_radians=-math.atan2(b[0]-a[0],b[2]-a[2])),mode='sprint',laps=1,length_m=round(total,2),checkpoint_radius_cm=180)
            if not 120<=total<=920:raise ValueError(('course length',self.id,route['id'],total))
            if len(points)>64:raise ValueError(('too many checkpoints',self.id,route['id'],len(points)))

    def write(self,destination):
        getattr(self,self.id.replace('-','_'))()
        self.finish_routes();self.scenery()
        # Environment uses the shared public defaults, with intentional lighting/climate.
        concept,architecture,climate,settlement={'village':('countryside','rural','temperate','village'),'neon-harbor':('metropolis','modern','temperate','urban'),'deep-forest':('jungle','timber','temperate','wilderness'),'red-canyon':('desert','adobe','arid','sparse'),'snow-mountain':('polar','timber','polar','sparse'),'machine-factory':('metropolis','modern','temperate','urban'),'sky-park':('metropolis','modern','temperate','village')}[self.id]
        self.doc['environment']=dict(version=1,start_minutes=1200 if self.id=='neon-harbor' else 720,concept=concept,architecture=architecture,climate=climate,settlement=settlement,latitude_mdeg=37000,longitude_mdeg=127000,utc_offset_minutes=540,sunrise_minutes=360,sunset_minutes=1080,regions=[],lights=[])
        self.doc['environment']['ground_color']={'village':[117,148,86],'neon-harbor':[78,94,103],'deep-forest':[65,101,62],'red-canyon':[170,76,42],'snow-mountain':[217,228,232],'machine-factory':[115,120,116],'sky-park':[109,145,82]}[self.id]
        for ident in sorted(self.used):
            a=copy.deepcopy(self.assets[ident]);data=(self.asset_roots[ident]/a['path']).read_bytes();a['path']='assets/'+digest(data)+'.glb';self.payloads[a['path']]=data;self.doc['assets'].append(a)
        heights=[];side=17
        for z in range(math.ceil(self.h/32)):
            for x in range(math.ceil(self.w/32)):
                values=[self.height(x*32+i*2,z*32+j*2) for j in range(side) for i in range(side)];heights.extend(values)
                image=Image.new('I',(side,side));image.putdata([v+10000 for v in values]);out=io.BytesIO();image.convert('I;16').save(out,format='PNG',compress_level=9)
                data=out.getvalue();path='terrain/'+digest(data)+'.png';self.payloads[path]=data
                self.doc['heightmaps'].append(dict(cell=dict(x=x,y=z),path=path,spacing_cm=200,offset_cm=-10000,step_cm=1,source_accuracy_cm=None))
        # Material roles are read from our original GLBs, never inferred by region ID.
        sys.path.insert(0,str(self.kit/'scripts'))
        from richer_assets import unpack
        for asset in self.doc['assets']:
            gltf,_=unpack(self.payloads[asset['path']]);windows=[i for i,m in enumerate(gltf['materials']) if m.get('name')=='mk_glass']
            if windows:self.doc['environment']['lights'].append(dict(asset_id=asset['id'],window_materials=[] if asset['id']=='richer-lamp' else windows,bulb_materials=windows if asset['id']=='richer-lamp' else [],position_cm=[0,270,0],range_cm=500,color=[110,210,255] if self.id=='neon-harbor' else [255,214,151]))
        self.payloads['document.json']=canonical(self.doc)
        meta=dict(id=self.id,name=self.name,en=self.en,description=self.description,size=list(self.size),cell_size_m=32,relief=(max(heights)-min(heights))/100,theme=self.id,surface='dirt' if self.id=='deep-forest' else 'asphalt',districts=[],landmarks=[a[0] for a in self.landmarks],routes=self.routes,start=self.routes[0]['start'],alternatives=self.alternatives,water_exits=self.exits,review_views=[dict(name=n,position_m=p,target_m=t) for n,p,t in self.views],source_files={p:digest(d) for p,d in self.payloads.items()},validation_status='unverified')
        folder=destination/self.id;folder.mkdir(parents=True,exist_ok=False)
        for path,data in {**self.payloads,'region.json':canonical(meta)}.items():
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return meta

def build(destination,kit):
    if destination.exists():raise FileExistsError('New destination required: '+str(destination))
    destination.mkdir(parents=True);(destination/'.gdignore').write_text('')
    result=[]
    for spec in MAPS:
        meta=World(spec,kit).write(destination);result.append(meta);print(meta['id'],[r['length_m'] for r in meta['routes']],flush=True)
    (destination/'arcade-world.json').write_bytes(canonical(dict(version=1,maps=[r['id'] for r in result],originals_preserved=True)))
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);p.add_argument('--kit',type=Path,required=True);a=p.parse_args();build(a.destination,a.kit.resolve())
