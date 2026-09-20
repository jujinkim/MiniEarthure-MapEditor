#!/usr/bin/env python3
"""Original editable district layouts. Existing v1 contracts, actual metre units."""
import argparse
import copy
import hashlib
import heapq
import json
import math
import random
import struct
import zlib
from pathlib import Path
from reference_maps import empty, road, canonical, sha
from regional_maps import PLANS


def segment_distance(p,a,b):
    vx,vz=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vz)/(vx*vx+vz*vz)))
    return math.hypot(p[0]-a[0]-t*vx,p[1]-a[1]-t*vz)


def rect_distance(a,b,box):
    x0,z0,x1,z1=box;lo,hi=0,1
    for origin,delta,start,end in [(a[0],b[0]-a[0],x0,x1),(a[1],b[1]-a[1],z0,z1)]:
        if abs(delta)<1e-9:
            if not start<=origin<=end:lo,hi=1,0;break
        else:
            u,v=sorted(((start-origin)/delta,(end-origin)/delta));lo=max(lo,u);hi=min(hi,v)
    if lo<=hi:return 0
    corners=[(x0,z0),(x1,z0),(x1,z1),(x0,z1)]
    def to_box(p):return math.hypot(max(x0-p[0],0,p[0]-x1),max(z0-p[1],0,p[1]-z1))
    return min([to_box(a),to_box(b)]+[segment_distance(p,a,b) for p in corners])


class Region:
    def __init__(self,ident,size,library):
        self.plan=copy.deepcopy(next(p for p in PLANS if p['id']==ident));self.plan['size']=list(size)
        self.id=ident;self.w,self.h=size;self.library=Path(library)
        self.doc=empty('district-'+ident,self.w*100,1600);self.doc['bounds']['max']=[self.w*100,self.h*100];self.doc['surface_areas']=[]
        self.doc['theme']='urban' if ident in ['haeon','safra','bansai'] else 'rural'
        source=Path(__file__).resolve().parents[1]/'examples/world-themes-atmosphere'/self.plan['theme']
        self.doc['environment']=json.loads((source/'document.json').read_text())['environment'];self.doc['environment']['lights']=[]
        self.doc['provenance'].update(tool_id='mapeditor-district-maps',build_id='authored-districts',first_created='2026-09-21T00:00:00Z',last_edited='2026-09-21T00:00:00Z')
        self.doc['attributions']=[dict(source='mapeditor-district-maps',license='MIT',notice='Original fictional land-use layout: '+self.plan['en']+'. No surveyed data or extracted game assets.')]
        self.assets={a['id']:a for a in json.loads((self.library/'library.json').read_text())['assets']}
        self.used=set();self.payloads={};self.traces=[];self.parcels=[];self.landmarks=[];self.route_anchors=[];self.districts=[]
        sign_doc=json.loads((source/'document.json').read_text())
        sign=copy.deepcopy(next(a for a in sign_doc['assets'] if a['id']=='map-writing'));sign['id']='district-writing';self.assets[sign['id']]=sign
        for path in (source/'signs').iterdir():
            if path.is_file() and not path.name.endswith('.import'):self.payloads['signs/'+path.name]=path.read_bytes()
        self.graph={};self.edges={};self.rng=random.Random(20260921+len(ident));self.serial=0

    def height(self,x,z):
        if self.id=='haeon':
            if z>948:return -round(200*min(1,(z-948)/6))
            north=max(0,(390-z)/390);west=max(0,(560-x)/560)
            return round(7400*north**1.3*(.3+.7*west))
        if self.id=='belmont':
            river=580+48*math.sin(x/190)
            if abs(z-river)<18:return -180
            return round(2100*max(0,(300-z)/300)**1.5)
        if self.id=='nord':
            if z>566:return -200
            return round(4200*max(0,(220-z)/220)**1.4+1400*max(0,(x-1060)/348))
        if self.id=='safra':return round(4200*max(0,(400-z)/400)**1.4*(.4+.6*max(0,(650-x)/650)))
        if self.id=='red-wadi':
            spine=[(64,590),(240,590),(410,490),(530,370),(720,310),(880,370),(1050,260),(1300,180)]
            distance=min(segment_distance((x,z),t['a'],t['b']) for t in self.traces) if self.traces else min(segment_distance((x,z),a,b) for a,b in zip(spine,spine[1:]))
            return round(6200*max(0,min(1,(distance-35)/110))**1.2+1800*max(0,(1100-x)/1100)+1600*max(0,(360-z)/360))
        if self.id=='kanupi':
            river=620+45*math.sin(x/170)
            if abs(z-river)<18:return -160
            return round(4600*max(0,(370-z)/370)**1.5)
        if self.id=='bansai':
            if abs(z-420)<12 or (abs(x-736)<12 and z>=240):return -130
            return round(700*max(0,(220-z)/220))
        return 0

    def trace(self,name,points,width=10,sidewalk=0,surface='asphalt',kind='ground',rise=0):
        for i,(a,b) in enumerate(zip(points,points[1:])):
            if a==b:continue
            self.traces.append(dict(name=f'{name}-{i}',a=tuple(a),b=tuple(b),width=width,sidewalk=sidewalk,surface=surface,kind=kind,rise=(rise[i],rise[i+1]) if isinstance(rise,list) else (rise,rise)))

    def paint(self,name,polygon,surface='concrete'):
        self.doc['surface_areas'].append(dict(id=name,polygon=[[round(x*100),round(z*100)] for x,z in polygon],surface=surface))

    def district(self,name,polygon,character):
        self.districts.append(dict(name=name,polygon_m=polygon,character=character))

    def compile_roads(self):
        # Split actual planar junctions before assigning graph identities. Separate
        # decks intersect only at intentionally shared endpoint elevations.
        cuts=[{0.,1.} for _ in self.traces]
        for i,r in enumerate(self.traces):
            a,b=r['a'],r['b'];dx,dz=b[0]-a[0],b[1]-a[1]
            for j in range(i):
                s=self.traces[j]
                if r['kind']!='ground' or s['kind']!='ground':continue
                c,d=s['a'],s['b'];ex,ez=d[0]-c[0],d[1]-c[1];den=dx*ez-dz*ex
                if abs(den)<1e-8:continue
                ux,uz=c[0]-a[0],c[1]-a[1];t=(ux*ez-uz*ex)/den;u=(ux*dz-uz*dx)/den
                if -1e-8<=t<=1+1e-8 and -1e-8<=u<=1+1e-8:cuts[i].add(max(0,min(1,t)));cuts[j].add(max(0,min(1,u)))
        # Keep bridge mouths away from road junctions. Split each bank approach
        # at explicit points outside the excavated channel, preserving its deck.
        for i,r in enumerate(self.traces):
            length=math.dist(r['a'],r['b'])
            wet=[t/256 for t in range(257) if self.height(r['a'][0]+(r['b'][0]-r['a'][0])*t/256,r['a'][1]+(r['b'][1]-r['a'][1])*t/256)<-50]
            if wet and r['kind']=='ground':
                cuts[i].update([max(0,min(wet)-24/length),min(1,max(wet)+24/length)])
        used={}
        for r,parts in zip(self.traces,cuts):
            a,b=r['a'],r['b'];points=[(round((a[0]+(b[0]-a[0])*t)*100)/100,round((a[1]+(b[1]-a[1])*t)*100)/100) for t in sorted(parts)]
            for n,(a,b) in enumerate(zip(points,points[1:])):
                if math.dist(a,b)<.05:continue
                token=tuple(sorted((a,b)))+(r['kind'],)
                if token in used:continue
                ident=f"{r['name']}-s{n}";used[token]=ident
                def vertex(p):
                    original_length=math.dist(r['a'],r['b']);t=math.dist(r['a'],p)/original_length
                    elevation=r['rise'][0]+(r['rise'][1]-r['rise'][0])*t
                    return [round(p[0]*100),self.height(*p)+round(elevation*100),round(p[1]*100)]
                pa,pb=vertex(a),vertex(b);node=lambda p:'node-'+'-'.join(map(str,p))
                road(self.doc,ident,[pa,pb],r['kind'],round(r['width']*100),r['surface'],node(pa),node(pb))
                rr=self.doc['roads'][-1];rr['sidewalk_cm']=round(r['sidewalk']*100)
                if r['kind']=='ground' and min(self.height(a[0]+(b[0]-a[0])*t/64,a[1]+(b[1]-a[1])*t/64) for t in range(65)) < -50:
                    rr['kind']='bridge'
                if r['surface']=='asphalt' and r['width']>=8:
                    rr['markings']=dict(lanes=4 if r['width']>=18 else 2,center_line=True,edge_lines=True,crosswalk_start=r['sidewalk']>0,crosswalk_end=r['sidewalk']>0)
                self.edges[ident]=dict(a=a,b=b,road=rr,width=r['width'],sidewalk=r['sidewalk'])
                for p,q in [(a,b),(b,a)]:self.graph.setdefault(p,[]).append((q,ident,math.dist(p,q)))

    def place(self,asset,x,z,turn=0,base=None,margin=.5,clear=True,label=None,walkway=False,under_deck=False,ignore_road=None):
        key='district-'+asset;record=self.assets[key]
        points=[]
        for c in record.get('collision',[]):
            for dx in [-.5,.5]:
                for dz in [-.5,.5]:points.append(((c['center'][0]+dx*c['size_cm'][0])/100,(c['center'][2]+dz*c['size_cm'][2])/100))
        for c in record.get('convex_collision',[]):points.extend((v[0]/100,v[2]/100) for v in c['vertices'])
        for _ in range(turn%4):points=[(-z,x) for x,z in points]
        if not points:return False
        box=(x+min(p[0] for p in points),z+min(p[1] for p in points),x+max(p[0] for p in points),z+max(p[1] for p in points))
        if box[0]<1 or box[1]<1 or box[2]>self.w-1 or box[3]>self.h-1:return False
        if clear:
            if any(rect_distance(e['a'],e['b'],box)<e['width']/2+(0 if walkway else e['sidewalk'])+margin for e in self.edges.values() if e['road']['id']!=ignore_road and (not under_deck or e['road']['kind']=='ground')):return False
            if any(not(box[2]+margin<q[0] or q[2]+margin<box[0] or box[3]+margin<q[1] or q[3]+margin<box[1]) for q in self.parcels):return False
        self.serial+=1;self.used.add(key)
        if base is None:base=max(self.height(xx,zz) for xx,zz in [(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])])
        if walkway:base+=12
        self.doc['placements'].append(dict(id=label or f'parcel-{self.serial}',asset_id=key,position=[round(x*100),round(base),round(z*100)],quarter_turns=turn%4))
        if clear:self.parcels.append(box)
        return True

    def landmark(self,name,asset,x,z,turn=0):
        assert self.place(asset,x,z,turn,label='landmark-'+str(len(self.landmarks))), (name,x,z)
        self.landmarks.append(dict(name=name,asset=asset,position_m=[x,z]))

    def path(self,a,b):
        start=min(self.graph,key=lambda p:math.dist(p,a));end=min(self.graph,key=lambda p:math.dist(p,b))
        assert math.dist(start,a)<1 and math.dist(end,b)<1,(a,b,start,end)
        costs={start:0};prev={};queue=[(0,start)]
        while queue:
            cost,p=heapq.heappop(queue)
            if p==end:break
            if cost!=costs[p]:continue
            for q,ident,length in self.graph[p]:
                if cost+length<costs.get(q,math.inf):costs[q]=cost+length;prev[q]=(p,ident);heapq.heappush(queue,(cost+length,q))
        assert end in costs,(a,b)
        result=[];p=end
        while p!=start:q,ident=prev[p];result.append((ident,q,p));p=q
        return list(reversed(result))

    def routes(self):
        result=[]
        for i,anchors in enumerate(self.route_anchors):
            edges=[]
            for a,b in zip(anchors,anchors[1:]):edges.extend(self.path(a,b))
            # First arterial must accommodate two ordered gates and all grid slots.
            ident,a,b=edges[0];length=math.dist(a,b);assert length>=160,(self.id,i,length)
            at=lambda d:dict(x_cm=round((a[0]+(b[0]-a[0])*d/length)*100),y_cm=round((a[1]+(b[1]-a[1])*d/length)*100),surface_id=ident,structural=False)
            points=[at(100),at(140)];last=(points[-1]['x_cm']/100,points[-1]['y_cm']/100)
            for rid,p,q in edges[1:]:
                midpoint=((p[0]+q[0])/2,(p[1]+q[1])/2)
                if math.dist(last,midpoint)<40:continue
                points.append(dict(x_cm=round(midpoint[0]*100),y_cm=round(midpoint[1]*100),surface_id=rid,structural=self.edges[rid]['road']['kind']!='ground'));last=midpoint
            assert len(points)<=64,(self.id,i,len(points))
            start=at(80);start.pop('structural');start['heading_radians']=math.atan2(-(b[0]-a[0]),-(b[1]-a[1]))
            result.append(dict(id=['intro','technical','ridge'][i],name=self.plan['courses'][i],mode='sprint' if i==2 else 'circuit',laps=1 if i==2 else 2,waypoints=points,start=start,road_path=[e[0] for e in edges],length_m=round(sum(math.dist(e[1],e[2]) for e in edges))))
        return result

    def finish(self,destination):
        elevations=[]
        for z in range(self.h//16):
            for x in range(self.w//16):
                samples=[[self.height(x*16+i*2,z*16+j*2) for i in range(9)] for j in range(9)];elevations.extend(v for row in samples for v in row)
                raw=b''.join(b'\0'+b''.join(struct.pack('>H',v+1000) for v in row) for row in samples)
                def block(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
                png=b'\x89PNG\r\n\x1a\n'+block(b'IHDR',struct.pack('>IIBBBBB',9,9,16,0,0,0,0))+block(b'IDAT',zlib.compress(raw,9))+block(b'IEND',b'')
                path='terrain/'+sha(png)+'.png';self.payloads[path]=png
                self.doc['heightmaps'].append(dict(cell=dict(x=x,y=z),path=path,spacing_cm=200,offset_cm=-1000,step_cm=1,source_accuracy_cm=None))
        for key in sorted(self.used):
            record=copy.deepcopy(self.assets[key]);self.doc['assets'].append(record);
            if record['path'] not in self.payloads:self.payloads[record['path']]=(self.library/record['path']).read_bytes()
        routes=self.routes();meta={k:copy.deepcopy(self.plan[k]) for k in ['id','name','en','theme','description','size']}
        meta.update(version=1,cell_size_cm=1600,relief=round((max(elevations)-min(elevations))/100,2),elevation_range_m=[min(elevations)/100,max(elevations)/100],surface='gravel' if self.id=='red-wadi' else 'dirt' if self.id=='kanupi' else 'asphalt',districts=[d['name'] for d in self.districts],district_records=self.districts,landmarks=[l['name'] for l in self.landmarks],landmark_records=self.landmarks,routes=routes,start=routes[0]['start'],review_views=getattr(self,'review_views',[]),ground_view={'haeon': 'market', 'belmont': 'town', 'nord': 'homes', 'safra': 'market', 'red-wadi': 'canyon', 'kanupi': 'forest', 'bansai': 'shops'}[self.id],source_files={'document.json':sha(canonical(self.doc)),**{p:sha(v) for p,v in self.payloads.items()}})
        folder=Path(destination)/self.id;folder.mkdir(parents=True,exist_ok=False)
        for path,data in {'document.json':canonical(self.doc),'region.json':canonical(meta),**self.payloads}.items():
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return meta


def haeon(library):
    r=Region('haeon',(1024,1024),library)
    r.district('항만 업무지구',[[608,248],[1000,248],[1000,820],[608,820]],'four-lane avenues, tower podiums and paved block interiors')
    r.district('구도심 시장',[[48,392],[608,392],[608,816],[48,816]],'offset narrow streets, continuous shop fronts and rear courts')
    r.district('산비탈 주거지',[[48,48],[608,48],[608,392],[48,392]],'contour streets, apartment terraces and retaining foundations')
    r.district('창고 부두',[[48,816],[1000,816],[1000,1000],[48,1000]],'quays, freight yards, broad service roads and sheds')
    r.paint('business-paving',[[608,248],[1000,248],[1000,816],[608,816]])
    r.paint('old-town-paving',[[48,392],[608,392],[608,816],[48,816]])
    r.paint('dock-apron',[[48,816],[1000,816],[1000,936],[48,936]])
    # Deliberately different urban fabrics, all connected to the waterfront spine.
    r.trace('waterfront',[(48,824),(176,824),(336,824),(496,824),(640,824),(800,824),(960,824)],22,4)
    for x in [640,800,960]:r.trace('business-ns-'+str(x),[(x,264),(x,424),(x,584),(x,824)],18,3.5)
    for z in [264,424,584]:r.trace('business-ew-'+str(z),[(496,z),(640,z),(800,z),(960,z)],16,3)
    r.trace('market-spine',[(176,824),(168,698),(190,568),(164,424),(176,312)],11,2.5)
    r.trace('old-east',[(496,824),(488,688),(512,552),(496,424),(496,264)],12,2.5)
    r.trace('market-west',[(64,824),(64,696),(88,562),(64,432),(176,312)],8,1.8)
    for name,points in [
        ('fish-street',[(64,696),(168,698),(290,716),(392,692),(488,688),(640,704)]),
        ('craft-street',[(88,562),(190,568),(278,592),(382,554),(512,552),(640,584)]),
        ('temple-street',[(64,432),(164,424),(272,446),(380,408),(496,424)]),
        ('inner-lane-a',[(290,716),(278,592),(272,446)]),
        ('inner-lane-b',[(392,692),(382,554),(380,408)])]:r.trace(name,points,6.5,1.2)
    r.trace('hill-approach',[(176,312),(300,320),(404,292),(496,264)],10,2)
    r.trace('hill-low',[(176,312),(96,260),(80,176),(152,120),(288,104),(416,136),(496,264)],8,1.8)
    r.trace('hill-high',[(96,260),(220,248),(336,224),(416,136)],7,1.5)
    r.trace('hill-climb',[(220,248),(184,196),(224,152),(288,104)],6,1)
    r.trace('dock-service',[(64,904),(336,904),(640,904),(960,904)],14,2)
    for x in [336,640,960]:r.trace('dock-entry-'+str(x),[(x,824),(x,904)],12,2)
    r.trace('viaduct-entry',[(496,824),(496,868)],10,2)
    r.trace('viaduct',[(496,868),(541,868),(650,780),(850,660),(920,604),(920,584)],10,0,kind='elevated',rise=[0,0,16,16,0,0])
    r.compile_roads()
    for edge in r.edges.values():
        rr=edge['road']
        if rr['kind']!='elevated':continue
        a,b=edge['a'],edge['b'];length=math.dist(a,b);dx=(b[0]-a[0])/length;dz=(b[1]-a[1])/length
        for distance in range(6,int(length)-4,3):
            t=distance/length;x=a[0]+dx*distance;z=a[1]+dz*distance;deck=rr['points'][0][1]+(rr['points'][1][1]-rr['points'][0][1])*t
            for side in [-1,1]:
                r.place('rail-'+str(round(math.degrees(math.atan2(dz,dx))/15)*15%180),x-dz*side*5.4,z+dx*side*5.4,base=deck,margin=.05,ignore_road=rr["id"])
            if distance%21==6:
                gap=math.ceil(abs(rr['points'][1][1]-rr['points'][0][1])/length*.6)+2
                for side in [-1,1]:
                    px=x-dz*side*3.2;pz=z+dx*side*3.2;steps=math.ceil((deck-r.height(px,pz)-gap)/50)
                    if 1<=steps<=40:r.place('support-'+str(steps),px,pz,base=deck-gap-steps*50,under_deck=True)
    r.place('writing',156,746,base=80,walkway=True)
    r.place('sign-post',156,746.2,base=0,walkway=True,clear=False)
    # Skyline is an actual central district: different towers around shared blocks.
    for row,(za,zb) in enumerate([(264,424),(424,584),(584,824)]):
        for col,(xa,xb) in enumerate([(640,800),(800,960)]):
            for k,(x,z) in enumerate([(xa+46,za+48),(xb-46,za+48),(xa+46,zb-48),(xb-46,zb-48)]):r.place('civic-tower-'+str((row+col+k)%4),x,z)
            r.place('canopy',(xa+xb)/2,(za+zb)/2)
    # Continuous street frontage on real parcels, with courts in between.
    for e in r.edges.values():
        a,b=e['a'],e['b'];length=math.dist(a,b)
        if max(a[0],b[0])>610 or min(a[1],b[1])<392 or max(a[1],b[1])>824:continue
        if abs(b[0]-a[0])>abs(b[1]-a[1]):
            z=(a[1]+b[1])/2
            for x in range(math.ceil(min(a[0],b[0])+30),math.floor(max(a[0],b[0])-22),44):
                for side in [-1,1]:r.place('streetwall-'+str((round(x)+round(z))%4),x,z+side*(e['width']/2+e['sidewalk']+11),0 if side==1 else 2)
        else:
            x=(a[0]+b[0])/2
            for z in range(math.ceil(min(a[1],b[1])+28),math.floor(max(a[1],b[1])-22),44):
                for side in [-1,1]:r.place('streetwall-'+str((round(x)+round(z))%4),x+side*(e['width']/2+e['sidewalk']+11),z,1 if side==1 else 3)
    # Back parcels form compact blocks around shared rear courts. Their fixed
    # 26m plot depths leave service passages; roadside setbacks remain explicit.
    for z in range(448,808,26):
        for x in range(88,590,44):r.place('streetwall-'+str((x//44+z//26)%4),x,z,0 if z//26%2 else 2)
    for z in [144,192,240,292,348]:
        for x in range(112,560,42):r.place('apartment-'+str((x//42+z//48)%4),x,z)
    for z in range(48,380,24):
        for x in range(48,600,24):r.place('canopy',x,z)
    for x in range(112,1000,70):
        r.place('dock-shed-'+str((x//70)%4),x,864)
        for z in [932]:r.place('container',x,z,clear=False,base=0)
    for x in range(16,1024,16):
        for z in range(960,1024,16):r.place('water',x,z,base=-8,clear=False)
        r.place('seawall',x,946,base=-300,clear=False)
    # Amenities use actual sidewalk parcels and obey the same clearance rules.
    for x in range(80,1000,40):
        r.place('street-lamp',x,810,margin=.1,walkway=True)
        r.place('bench',x+8,810,margin=.1,walkway=True)
    r.landmark('항만 크레인','crane',76,930)
    r.landmark('구도심 종탑','bell-tower',332,480)
    r.landmark('산정 전망대','observatory',280,64)
    r.route_anchors=[[(640,824),(800,824),(960,824),(960,264),(640,264),(640,824)],[(176,824),(336,824),(496,824),(488,688),(512,552),(496,424),(164,424),(64,432),(64,696),(168,698),(176,824)],[(336,904),(640,904),(496,824),(496,868),(541,868),(650,780),(850,660),(920,604),(920,584),(640,584),(496,424),(496,264),(176,312),(96,260),(220,248),(288,104)]]
    r.review_views=[dict(name=name,position_m=[x,r.height(x,z)/100+3,z],target_m=[tx,r.height(tx,tz)/100+2,tz]) for name,x,z,tx,tz in [('market',168,698,190,568),('business',800,780,800,584),('hillside',176,312,220,248),('harbour',400,904,640,904)]]
    return r


def district_box(r,name,box,character,surface=None):
    x,z,w,h=box;polygon=[[x,z],[x+w,z],[x+w,z+h],[x,z+h]]
    r.district(name,polygon,character)
    if surface:r.paint('district-'+str(len(r.districts)),polygon,surface)


def loops(r,intro,technical,ridge,surface='asphalt',walk=0):
    # Each region supplies its own road topology and waypoints. The first
    # straight of each course is authored wide enough for a full starting grid.
    for name,points,width in [('arterial',intro,12),('local',technical,8),('ridge',ridge,7)]:
        r.trace(name+'-grid',points[:2],14,walk,surface)
        r.trace(name,points[1:],width,walk if name!='ridge' else 0,surface)
    r.compile_roads();r.route_anchors=[intro,technical,ridge]
    bridge_rails(r)


def bridge_rails(r):
    for edge in r.edges.values():
        road=edge['road']
        if road['kind']!='bridge':continue
        a,b=edge['a'],edge['b'];length=math.dist(a,b);dx=(b[0]-a[0])/length;dz=(b[1]-a[1])/length
        angle=round(math.degrees(math.atan2(dz,dx))/15)*15%180
        for distance in range(5,int(length)-4,3):
            t=distance/length;x=a[0]+dx*distance;z=a[1]+dz*distance;deck=road['points'][0][1]+(road['points'][1][1]-road['points'][0][1])*t
            for side in [-1,1]:
                offset=edge['width']/2+edge['sidewalk']+.45
                r.place('rail-'+str(angle),x-dz*side*offset,z+dx*side*offset,base=deck,margin=.05,ignore_road=road['id'])


def buildings(r,style,box,spacing=(18,18),turn=0):
    x,z,w,h=box
    for j,zz in enumerate(range(z,z+h,spacing[1])):
        for i,xx in enumerate(range(x,x+w,spacing[0])):
            jitter=.8 if style=='courtyard-block' else 1.8
            r.place(style+'-'+str((i+2*j)%4),xx+(j%2)*spacing[0]*.28+r.rng.uniform(-jitter,jitter),zz+r.rng.uniform(-jitter,jitter),(turn+(j%2)*2+(1 if (i+j)%7==0 else 0))%4)


def grove(r,asset,box,spacing=20):
    x,z,w,h=box
    for zz in range(z,z+h,spacing):
        for xx in range(x,x+w,spacing):
            px=xx+r.rng.uniform(-spacing*.18,spacing*.18);pz=zz+r.rng.uniform(-spacing*.18,spacing*.18)
            r.place('forest-'+str(r.rng.randrange(3)) if asset=='forest' else asset,px,pz,base=r.height(px,pz))


def water_tile(r,x,z,size=16):
    # Smaller edge tiles preserve a continuous channel beneath the bridge while
    # keeping the v1 non-overlapping placement footprint contract unchanged.
    if r.place('water' if size==16 else 'water-'+str(size),x,z,base=-100,under_deck=True,margin=0):return
    if size>4:
        for dx in [-size/4,size/4]:
            for dz in [-size/4,size/4]:water_tile(r,x+dx,z+dz,size//2)


def river_tiles(r,axis,lo,hi,coordinate):
    # The water mesh follows the authored channel. The two-metre sampled bed
    # is lowered by height(); bridges are separate road surfaces above it.
    for t in range(lo,hi,16):
        v=coordinate(t)
        for offset in [-8,8]:
            x,z=(t,v+offset) if axis=='x' else (v+offset,t)
            water_tile(r,x,z)


def views(r,items):
    r.review_views=[dict(name=name,position_m=[x,r.height(x,z)/100+3,z],target_m=[tx,r.height(tx,tz)/100+2,tz]) for name,x,z,tx,tz in items]


def belmont(library):
    r=Region('belmont',(1280,896),library)
    district_box(r,'벨몽 읍내',(100,310,330,230),'compact stone-and-plaster farm town, paved square and service alleys','concrete')
    district_box(r,'경계 생울타리 농지',(440,320,780,240),'irregular cultivated parcels and connected farm lanes')
    district_box(r,'과수원 능선',(80,48,980,250),'contour farm roads, orchard rows and ridge mill')
    district_box(r,'하천 방앗간 마을',(60,640,1120,210),'river crossings and dispersed working farmyards')
    intro=[(120,480),(360,480),(680,500),(1000,460),(1120,680),(820,780),(420,760),(120,700),(120,480)]
    tech=[(360,480),(600,400),(840,360),(960,240),(660,180),(360,220),(240,340),(360,480)]
    ridge=[(120,700),(420,760),(820,780),(1120,680),(1000,460),(960,240),(660,180),(360,220),(140,120)]
    loops(r,intro,tech,ridge)
    r.trace('town-cross',[(120,380),(240,340),(360,480)],7,1.8)
    # Extra streets must be included before parcel clearance and route routing.
    r.doc['roads']=[];r.graph={};r.edges={};r.compile_roads()
    r.landmark('능선 풍차','windmill',124,80);r.landmark('하천 물레방앗간','watermill',590,625);r.landmark('읍내 종탑','bell-tower',320,390)
    river_tiles(r,'x',32,1250,lambda x:580+48*math.sin(x/190))
    buildings(r,'farm',(140,366,252,160),(19,20))
    for x,z in [(520,450),(760,440),(1050,730),(480,710)]:
        r.place('dock-shed-0',x,z);buildings(r,'farm',(x-42,z+32,90,35),(22,22))
    for i,(x,z,w,h) in enumerate([(460,530,230,30),(720,530,270,24),(440,260,120,100),(590,255,220,80),(60,790,260,55),(450,805,290,45),(850,810,220,40)]):
        r.paint('field-'+str(i),[[x,z],[x+w,z+7],[x+w-16,z+h],[x+8,z+h-4]],'dirt')
        for xx in range(x+12,x+w-12,16):
            for zz in range(z+12,z+h-8,16):r.place('field',xx,zz)
    # Large working parcels fill the valley, with staggered widths and access
    # gaps. Roads and river reserves trim the field pattern to the land.
    for row,z in enumerate([355,430,515,675,755,835]):
        for x in range(60+(row%2)*31,1240,74):r.place('crop-'+str((x//74+row)%4),x,z,base=r.height(x,z),margin=3)
    for x in range(390,890,26):
        for z in [78,106,134]:r.place('canopy',x,z,base=r.height(x,z))
    views(r,[('town',120,480,360,480),('orchard',660,180,360,220),('river',1120,680,1000,460)])
    return r


def nord(library):
    r=Region('nord',(1408,640),library)
    district_box(r,'서부 항만 창고',(40,374,420,180),'large low freight sheds and long open quays','concrete')
    district_box(r,'색채 주택군',(480,290,450,255),'tight parallel rows of small pitched-roof homes on snow')
    district_box(r,'동부 연구 기지',(960,260,400,285),'low laboratory compounds, service yards and antenna hill')
    district_box(r,'북쪽 암석 절개지',(40,32,1280,210),'switchback ascent below exposed rock and snow ridges')
    intro=[(80,520),(380,520),(620,520),(1040,500),(1320,440),(1260,320),(940,340),(620,370),(320,350),(80,400),(80,520)]
    tech=[(620,520),(1040,500),(940,460),(940,340),(780,370),(780,440),(620,440),(620,520)]
    ridge=[(80,520),(380,520),(620,370),(540,250),(340,220),(420,132),(740,110),(1060,160),(1260,100)]
    loops(r,intro,tech,ridge,walk=1.5)
    r.landmark('항구 화물 크레인','crane',100,553);r.landmark('연구 관측소','observatory',1260,60);r.landmark('주택가 시계탑','bell-tower',850,280)
    for x in range(130,440,75):
        for z in [402,470]:r.place('dock-shed-'+str(x%4),x,z)
    buildings(r,'polar',(505,302,410,190),(18,22))
    buildings(r,'warehouse',(1010,360,300,120),(34,34))
    for x,z in [(1040,400),(1150,460),(1230,365)]:r.place('workshop-0',x,z)
    grove(r,'rock',(60,66,1140,155),27);grove(r,'snow',(120,265,1100,55),33)
    for x in range(32,1400,16):
        for z in [584,600,616]:r.place('water',x,z,base=-12,clear=False)
        r.place('seawall',x,564,base=-310,clear=False)
    views(r,[('homes',620,440,780,440),('port',80,520,380,520),('research',1040,500,1320,440)])
    return r


def safra(library):
    r=Region('safra',(896,896),library)
    district_box(r,'중정 구도심',(65,370,470,340),'dense irregular stone parcels with inward courts','dirt')
    district_box(r,'그늘 시장 골목',(200,570,320,150),'narrow offset passages, canopies and continuous stone frontages','concrete')
    district_box(r,'신시가지 대로',(565,320,270,450),'regular avenues, larger mixed-use apartment blocks','concrete')
    district_box(r,'올리브 테라스',(70,50,660,260),'contour roads and stepped orchard plots')
    # Surface districts are disjoint even where their descriptive polygons meet.
    r.doc['surface_areas']=[]
    r.paint('old-town',[[65,370],[535,370],[535,740],[65,740]],'dirt');r.paint('new-town',[[565,320],[835,320],[835,780],[565,780]])
    intro=[(560,760),(800,760),(800,500),(800,340),(560,340),(560,520),(560,760)]
    tech=[(80,720),(280,720),(460,680),(480,550),(340,520),(400,410),(220,400),(140,510),(240,590),(80,580),(80,720)]
    ridge=[(560,760),(800,760),(560,520),(480,550),(400,410),(340,300),(160,270),(100,180),(260,150),(400,210),(540,130),(680,90)]
    loops(r,intro,tech,ridge,walk=1.5)
    r.landmark('돌문 광장','courtyard',545,820);r.landmark('언덕 전망대','observatory',704,58);r.landmark('구도심 종탑','bell-tower',310,350)
    buildings(r,'courtyard-block',(90,400,420,330),(25,24))
    for x,z in [(680,430),(680,610),(665,715),(750,580),(615,580)]:r.place('apartment-'+str(x%4),x,z)
    buildings(r,'shop',(592,350,190,390),(23,30))
    for x in range(90,750,24):
        for z in [68,100,242,282]:r.place('canopy',x,z,base=r.height(x,z))
    views(r,[('market',280,720,460,680),('avenue',800,760,800,500),('terrace',400,210,540,130)])
    return r


def red_wadi(library):
    r=Region('red-wadi',(1408,768),library)
    district_box(r,'열린 와디 분지',(40,470,470,240),'broad dry basin and a roadside service settlement')
    district_box(r,'사암 협로',(440,250,450,290),'high continuous terrain walls pinch the winding gravel road')
    district_box(r,'동부 사구',(920,350,410,340),'undulating exposed sand and long sightlines')
    district_box(r,'북부 암석 능선',(800,32,550,280),'ascending shelf road and outlook above the valley')
    intro=[(64,590),(240,590),(410,490),(530,370),(720,310),(880,370),(1050,480),(1090,640),(760,670),(430,660),(64,590)]
    tech=[(410,490),(620,560),(680,450),(820,490),(880,370),(720,310),(530,370),(410,490)]
    ridge=[(64,590),(240,590),(410,490),(530,370),(720,310),(880,370),(1050,260),(1160,310),(1260,230),(1300,180)]
    loops(r,intro,tech,ridge,surface='gravel')
    r.landmark('분지 정비소','service-canopy',120,540);r.landmark('쌍둥이 사암 봉우리','sandstone-3',670,360);r.landmark('능선 관측소','observatory',1340,150)
    r.paint('dry-basin',[[40,525],[295,500],[420,590],[410,705],[55,715]],'dirt')
    buildings(r,'stone',(90,620,260,70),(22,24));r.place('workshop-0',180,545)
    for j,(x,z,w,h) in enumerate([(360,320,110,150),(520,200,290,70),(740,370,70,190),(930,110,350,85)]):
        for zz in range(z,z+h,24):
            for xx in range(x,x+w,28):r.place('sandstone-'+str(1+(xx//28+zz//24)%3),xx,zz,base=r.height(xx,zz))
    grove(r,'dune',(960,510,360,180),34);grove(r,'rock',(110,370,240,110),24)
    views(r,[('settlement',64,590,240,590),('canyon',530,370,720,310),('ridge',1260,230,1300,180)])
    return r


def kanupi(library):
    r=Region('kanupi',(1280,896),library)
    district_box(r,'강변 정착지',(80,660,500,180),'compact raised timber houses below a looping river')
    district_box(r,'열대림 내부',(70,270,1050,270),'dense canopy clusters around winding dirt roads')
    district_box(r,'동부 연구 캠프',(920,680,290,160),'small cleared compound with cabins and working sheds','dirt')
    district_box(r,'폭포 능선',(200,45,900,235),'steep forested terraces and ascending shelf road')
    intro=[(100,760),(340,760),(620,800),(940,780),(1140,720),(1100,520),(840,470),(540,520),(260,480),(100,570),(100,760)]
    tech=[(260,480),(460,440),(620,350),(810,330),(900,400),(840,470),(680,450),(540,520),(420,560),(260,480)]
    ridge=[(100,760),(340,760),(620,800),(940,780),(1100,520),(900,400),(810,330),(700,240),(900,170),(1020,90)]
    loops(r,intro,tech,ridge,surface='dirt')
    r.landmark('능선 폭포','waterfall',1080,90);r.landmark('강변 마을 회관','courtyard',600,715);r.landmark('산림 관측소','observatory',960,70)
    river_tiles(r,'x',32,1248,lambda x:620+45*math.sin(x/170))
    buildings(r,'stilt',(138,697,380,105),(18,20));buildings(r,'warehouse',(940,704,235,90),(28,28))
    grove(r,'forest',(50,80,1130,460),17);grove(r,'palm',(65,680,1120,160),34)
    views(r,[('river-village',100,760,340,760),('forest',620,350,810,330),('camp',940,780,1140,720)])
    return r


def bansai(library):
    r=Region('bansai',(1152,768),library)
    district_box(r,'수변 상점가',(70,450,590,120),'continuous rows of awnings beside the canal','concrete')
    district_box(r,'고상 주택 마을',(80,270,540,120),'narrow waterside lanes and tightly grouped raised houses')
    district_box(r,'시장 마당',(790,450,270,190),'paved delivery square surrounded by shopfronts','concrete')
    district_box(r,'논과 외곽 제방',(650,65,440,290),'irregular rice parcels, irrigation cuts and raised lanes')
    intro=[(80,600),(340,600),(620,620),(860,680),(1060,610),(1040,470),(880,360),(940,200),(700,140),(420,180),(140,220),(80,360),(80,600)]
    tech=[(100,480),(320,480),(540,480),(660,520),(660,340),(470,330),(280,350),(100,330),(100,480)]
    ridge=[(80,600),(340,600),(620,620),(860,680),(1060,610),(880,360),(940,200),(700,140),(420,180),(140,220),(100,330),(100,480),(320,480)]
    loops(r,intro,tech,ridge,walk=1.5)
    r.landmark('수변 시장 회관','courtyard',600,680);r.landmark('마을 시계탑','bell-tower',440,385);r.landmark('논 전망 정자','service-canopy',1070,150)
    river_tiles(r,'x',32,1120,lambda x:420)
    for z in range(256,752,16):water_tile(r,736,z)
    buildings(r,'shop',(125,451,490,108),(13,17));buildings(r,'stilt',(132,278,468,111),(16,18));buildings(r,'shop',(815,480,225,125),(16,18))
    for i,(x,z,w,h) in enumerate([(700,205,140,100),(990,230,95,95),(550,225,110,65),(790,78,290,48)]):
        r.paint('paddy-'+str(i),[[x,z],[x+w,z+5],[x+w-8,z+h],[x+5,z+h]],'dirt')
        for xx in range(x+12,x+w-8,16):
            for zz in range(z+12,z+h-8,16):r.place('rice',xx,zz)
    # Narrow tributary; one tile row stays within its excavated channel.
    grove(r,'palm',(64,70,1030,110),30);grove(r,'palm',(130,650,620,75),34)
    views(r,[('shops',320,480,540,480),('stilt-homes',470,330,280,350),('market',1040,470,1060,610)])
    return r


BUILDERS={'haeon':haeon,'belmont':belmont,'nord':nord,'safra':safra,'red-wadi':red_wadi,'kanupi':kanupi,'bansai':bansai}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);p.add_argument('--library',type=Path,required=True);p.add_argument('--ids',nargs='+',default=list(BUILDERS));a=p.parse_args()
    a.destination.mkdir(parents=True,exist_ok=False);(a.destination/'.gdignore').write_text('')
    for ident in a.ids:
        region=BUILDERS[ident](a.library);meta=region.finish(a.destination)
        print(ident,meta['size'],'roads',len(region.doc['roads']),'parcels',len(region.doc['placements']))
