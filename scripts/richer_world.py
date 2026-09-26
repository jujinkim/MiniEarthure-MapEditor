#!/usr/bin/env python3
"""Direct metre authoring for seven fictional miniature living regions (MIT).

Existing source folders are inputs for environment/labels only, never scaled.
The destination must be new. Geometry, bitmap and water helpers belong to MapKit.
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
from regional_maps import PLANS

ROOT=Path(__file__).resolve().parents[1]
SPECS={
 'haeon':dict(size=[320,320],core=[[55,222],[113,222],[122,177],[85,157],[48,180],[55,222]],tech=[[122,177],[148,147],[125,119],[77,122],[48,180]],
   outer=[[113,222],[191,260],[265,240],[282,176],[253,97],[170,56],[97,65],[45,108],[48,180]],
   river=[[301,43],[279,67],[295,107],[278,142],[300,182],[291,218],[272,250],[239,277],[201,292]],width=5,pond=[228,277,15,10],hill=10,styles=['shop','tower','house','shed'],coast=True),
 'belmont':dict(size=[384,288],core=[[53,187],[111,187],[134,149],[107,121],[60,135],[53,187]],tech=[[134,149],[164,135],[163,95],[119,80],[107,121]],
   outer=[[111,187],[192,227],[283,236],[344,196],[337,121],[287,63],[213,42],[129,53],[60,135]],
   river=[[254,13],[242,46],[263,81],[246,112],[258,153],[241,184],[256,218],[233,256],[239,276]],width=5,pond=[251,183,13,9],hill=6,styles=['farm','house','farm','shed']),
 'nord':dict(size=[416,208],core=[[63,129],[125,129],[143,93],[118,61],[75,64],[63,129]],tech=[[143,93],[182,83],[193,46],[144,28],[118,61]],
   outer=[[125,129],[212,160],[313,155],[379,120],[367,67],[292,39],[231,52],[182,83]],
   river=[[392,19],[385,42],[398,67],[383,94],[399,121],[381,149],[345,177],[301,189]],width=4,pond=[325,175,10,6],hill=5,styles=['nord','shed','nord','shed'],coast=True),
 'safra':dict(size=[288,288],core=[[52,196],[105,196],[126,157],[102,129],[59,147],[52,196]],tech=[[126,157],[159,139],[156,103],[115,91],[102,129]],
   outer=[[105,196],[172,238],[213,239],[231,173],[229,100],[189,49],[117,41],[55,78],[59,147]],
   river=[[258,43],[246,83],[263,124],[249,164],[267,211],[240,256]],width=2.5,pond=[242,224,12,9],hill=8,styles=['courtyard','shop','house','courtyard']),
 'red-wadi':dict(size=[416,256],core=[[67,186],[128,186],[142,147],[105,120],[64,142],[67,186]],tech=[[142,147],[179,133],[173,94],[126,80],[105,120]],
   outer=[[128,186],[208,218],[301,222],[377,186],[361,109],[311,54],[230,35],[162,51],[64,142]],
   river=[[278,13],[260,52],[282,92],[265,130],[286,168],[269,200],[282,241]],width=3,pond=[284,174,12,7],hill=10,styles=['shed','house','shed','house']),
 'kanupi':dict(size=[384,288],core=[[51,209],[110,209],[135,166],[103,141],[57,156],[51,209]],tech=[[135,166],[164,132],[144,99],[100,107],[57,156]],
   outer=[[110,209],[182,246],[267,249],[342,215],[337,142],[297,69],[220,41],[160,53],[100,107]],
   river=[[252,16],[231,48],[250,80],[235,122],[258,164],[242,208],[258,246],[245,275]],width=6,pond=[250,87,16,11],hill=9,styles=['stilt','house','shed','stilt']),
 'bansai':dict(size=[352,256],core=[[126,186],[184,186],[212,141],[161,113],[118,132],[126,186]],tech=[[212,141],[225,117],[206,82],[164,77],[161,113]],
   outer=[[184,186],[193,224],[273,226],[320,178],[306,102],[259,51],[196,31],[131,45],[118,132]],
   river=[[223,12],[231,43],[212,83],[233,116],[221,159],[240,202],[221,244]],width=5,pond=[255,197,12,8],hill=2.4,styles=['stilt','shop','stilt','farm']),
}

def lerp(a,b,t):return [a[i]+(b[i]-a[i])*t for i in range(len(a))]
def distance(p,a,b):
    v=[b[i]-a[i] for i in range(2)];l=sum(c*c for c in v)
    t=max(0,min(1,sum((p[i]-a[i])*v[i] for i in range(2))/l)) if l else 0
    q=lerp(a,b,t)
    return math.dist(p,q),t
def ease(x):x=max(0,min(1,x));return x*x*(3-2*x)
def digest(data):return hashlib.sha256(data).hexdigest()
def smooth(points,spacing=4):
    result=[]
    for i in range(len(points)-1):
        a,b,c,d=points[max(0,i-1)],points[i],points[i+1],points[min(len(points)-1,i+2)]
        steps=max(1,math.ceil(math.dist(b,c)/spacing))
        for j in range(steps):
            t=j/steps
            result.append([.5*((2*b[k])+(-a[k]+c[k])*t+(2*a[k]-5*b[k]+4*c[k]-d[k])*t*t+(-a[k]+3*b[k]-3*c[k]+d[k])*t*t*t) for k in range(2)])
    return result+[points[-1]]

class Region:
    def __init__(self,ident,kit):
        self.ident=ident;self.spec=copy.deepcopy(SPECS[ident]);self.w,self.h=self.spec['size']
        self.meta=copy.deepcopy(next(p for p in PLANS if p['id']==ident));self.meta.update(size=self.spec['size'])
        self.doc=empty('richer-world-'+ident,self.w*100,1600);self.doc['bounds']['max']=[self.w*100,self.h*100]
        self.doc.update(courses=[],gimmicks=[],surface_areas=[])
        self.doc['provenance'].update(tool_id='mapeditor-richer-world',build_id='richer-world-v1',first_created='2026-09-26T00:00:00Z',last_edited='2026-09-26T00:00:00Z')
        self.doc['environment']=json.loads((ROOT/'examples/special-driving'/ident/'document.json').read_text())['environment']
        self.doc['environment']['lights']=[];self.doc['environment']['regions']=[]
        self.assets={a['id']:a for a in json.loads((kit/'assets/richer-library/library.json').read_text())['assets']}
        self.kit=kit;self.used=set();self.payloads={};self.segments=[];self.paths={};self.parcels=[];self.occupied=[];self.water=[]
        self.rng=random.Random(2660+list(SPECS).index(ident))
        self.build_water()
        self.network('main',self.spec['core'],4.8,'asphalt')
        self.network('lane',self.spec['tech'],3.4,'dirt' if ident=='kanupi' else 'asphalt')
        self.network('explore',self.spec['outer'],3.8,'dirt' if ident=='kanupi' else 'gravel' if ident=='red-wadi' else 'asphalt')
        if ident in ['haeon','safra','bansai','nord']:
            core=self.spec['core'];center=[sum(p[k] for p in core[:-1])/5 for k in range(2)]
            self.network('residential',[core[3],center,core[0]],2.8,'asphalt')
        joins={n for r in self.doc['roads'] if r['kind']=='bridge' for n in [r['from'],r['to']]}
        for r in self.doc['roads']:
            if r['kind']!='ground':continue
            a,b=r['points'][0],r['points'][-1];fraction=min(.3,800/math.dist(a,b));points=[a]
            if r['from'] in joins:
                p=[round(v) for v in lerp(a,b,fraction)];p[1]=a[1];points.append(p)
            if r['to'] in joins:
                p=[round(v) for v in lerp(a,b,1-fraction)];p[1]=b[1];points.append(p)
            points.append(b);r.update(points=points,widths_cm=[r['widths_cm'][0]]*(len(points)-1),surfaces=[r['surfaces'][0]]*(len(points)-1))
        self.segments=[([a[0]/100,a[2]/100],[b[0]/100,b[2]/100],r['widths_cm'][i]/100,r['id'],a[1]/100,b[1]/100,r['kind']) for r in self.doc['roads'] for i,(a,b) in enumerate(zip(r['points'],r['points'][1:]))]
        self.build_routes()

    def raw(self,x,z):
        u=x/self.w;v=z/self.h;hill=self.spec['hill']
        if self.ident=='red-wadi':return .8+hill*(.30*math.sin(x/32+z/57)**2+.6*math.exp(-((x-350)/45)**2))+1.8*math.sin(z/31)**2
        if self.ident=='safra':return .8+hill*(1-v)*(.5+.4*math.sin(x/100)**2)+.25*math.sin(z/7)
        if self.ident=='bansai':return .8+hill*(.2+u*.25+.25*math.sin(x/57+z/45)**2)
        return .8+hill*(.25*math.sin(x/61+z/89)**2+.7*(1-v)**2)+.35*math.sin(x/21)*math.sin(z/28)

    def wet(self,x,z):
        best=(1e6,0,0)
        for water in self.water:
            if water['kind']=='coast':
                poly=water['polygon'];d=min(distance([x,z],a,b)[0] for a,b in zip(poly,poly[1:]+poly[:1]));inside=False
                for a,b in zip(poly,poly[1:]+poly[:1]):
                    if (a[1]>z)!=(b[1]>z) and x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:inside=not inside
                if inside:d=-d
                depth=min(1,max(0,-d/6))
            elif water['kind']=='pond':
                cx,cz,rx,rz=water['shape'];q=math.hypot((x-cx)/rx,(z-cz)/rz)
                d=(q-1)*min(rx,rz);depth=min(1,max(0,1-q))
            else:
                d=1e6;depth=0
                for a,b,ra,rb in water['segments']:
                    ds,t=distance([x,z],a,b);width=ra+(rb-ra)*t
                    if ds-width<d:d=ds-width;depth=max(0,1-ds/width)
            if d<best[0]:best=(d,self.water_level(x,z),depth)
        return best

    def water_level(self,x,z):
        return 1.6*(1-ease((z-75)/1.0)) if self.ident=='kanupi' else 0.0

    def natural(self,x,z):
        d,level,depth=self.wet(x,z)
        if d<0:return level-.16-1.8*depth
        # Low banks ease into the surrounding terrain over a full 10m.
        value=self.raw(x,z)
        if d<12:value=(level+.22)*(1-ease(d/12))+value*ease(d/12)
        if self.ident=='red-wadi':
            # Branching dry gullies join the wet low basin, rather than random dunes.
            for a,b in [([185,24],[268,128]),([361,78],[278,145])]:
                ds,_=distance([x,z],a,b);value-=1.4*math.exp(-(ds/8)**2)
        return value

    def height(self,x,z):
        value=self.natural(x,z)
        nearest=(1e6,value)
        for a,b,width,ident,ya,yb,kind in self.segments:
            if kind!='ground':continue
            d,t=distance([x,z],a,b);edge=d-width/2
            if edge<nearest[0]:nearest=(edge,ya+(yb-ya)*t)
        if nearest[0]<5:value=nearest[1]*(1-ease((nearest[0]-.4)/4.6))+value*ease((nearest[0]-.4)/4.6)
        for road in self.doc['roads']:
            if road['kind']!='bridge':continue
            for p in [road['points'][0],road['points'][-1]]:
                d=math.hypot(x-p[0]/100,z-p[2]/100)
                if d<14:value=(p[1]/100)*(1-ease((d-10)/4))+value*ease((d-10)/4)
        for parcel in self.parcels:
            dx=abs(x-parcel['x'])-parcel['rx'];dz=abs(z-parcel['z'])-parcel['rz'];d=max(dx,dz)
            if d<2:value=parcel['height']*(1-ease(d/2))+value*ease(d/2)
        return round(value*100)

    def network(self,name,points,width,surface):
        path=[]
        for index,(a,b) in enumerate(zip(points,points[1:])):
            ident=name+'-'+str(index);length=math.dist(a,b)
            # Crossings are bridges only where this road really crosses a watercourse.
            samples=[self.wet(*lerp(a,b,i/40))[0] for i in range(41)]
            wet=[i for i,v in enumerate(samples) if v<3.5]
            spans=[]
            if wet:
                lo=max(0,(min(wet)-7)/40);hi=min(1,(max(wet)+7)/40)
                spans=([(0,lo,'ground','-approach')] if lo>0 else [])+[(lo,hi,'bridge','-bridge')]+([(hi,1,'ground','-departure')] if hi<1 else [])
            else:spans=[(0,1,'ground','')]
            for t0,t1,kind,suffix in spans:
                aa,bb=lerp(a,b,t0),lerp(a,b,t1);rid=ident+suffix
                # Core start apron is level and large enough for all eight cars.
                def altitude(p):return .95 if name=='main' and index==0 else max(.8,self.natural(*p))
                ya,yb=altitude(aa),altitude(bb)
                if kind=='bridge':ya=max(self.water_level(*aa)+1.2,ya);yb=max(self.water_level(*bb)+1.2,yb)
                pa=[round(aa[0]*100),round(ya*100),round(aa[1]*100)];pb=[round(bb[0]*100),round(yb*100),round(bb[1]*100)]
                key=lambda p:'n-'+str(p[0])+'-'+str(p[2])
                road(self.doc,rid,[pa,pb],kind,round(width*100),surface,start=key(pa),end=key(pb))
                rr=self.doc['roads'][-1]
                if kind=='bridge' and math.dist(pa,pb)>800:
                    fraction=min(.3,800/math.dist(pa,pb));p1=[round(v) for v in lerp(pa,pb,fraction)];p2=[round(v) for v in lerp(pa,pb,1-fraction)];p1[1]=pa[1];p2[1]=pb[1]
                    rr.update(points=[pa,p1,p2,pb],widths_cm=[round(width*100)]*3,surfaces=[surface]*3)
                if name=='main':
                    rr['sidewalk_cm']=65
                    rr['markings']=dict(lanes=2,center_line=True,edge_lines=True,crosswalk_start=True,crosswalk_end=True)
                self.segments.append((aa,bb,width,rid,ya,yb,kind));path.append(rid)
        self.paths[name]=path
        # Shared endpoint heights also grade dry bridge approaches.
        nodes={n['id']:n for n in self.doc['nodes']}
        for r in self.doc['roads']:
            for end,point in [('from',0),('to',-1)]:
                n=nodes[r[end]]
                n['position'][1]=max(n['position'][1],r['points'][point][1]);n['level']=0
        for r in self.doc['roads']:
            r['points'][0]=nodes[r['from']]['position'].copy();r['points'][-1]=nodes[r['to']]['position'].copy()
        roads={r['id']:r for r in self.doc['roads']}
        self.segments=[(a,b,w,i,roads[i]['points'][0][1]/100,roads[i]['points'][-1][1]/100,k) for a,b,w,i,ya,yb,k in self.segments]

    def build_water(self):
        # All levels are authority-independent static authored geometry.
        points=smooth(self.spec['river']);width=self.spec['width']
        self.water=[dict(id='channel',kind='flow',level=0.0,segments=[(a,b,width*(.9+.18*math.sin(i*.19)),width*(.9+.18*math.sin((i+1)*.19))) for i,(a,b) in enumerate(zip(points,points[1:]))])]
        self.water.append(dict(id='pond',kind='pond',level=0.0,shape=self.spec['pond']))
        if self.ident=='red-wadi':self.water[0]['kind']='dry'
        if self.ident in ['kanupi','bansai','haeon']:
            endpoint=self.spec['river'][3];start=[self.w-27,55 if self.ident!='haeon' else 27]
            self.water.append(dict(id='tributary',kind='flow',level=0.0,segments=[(start,endpoint,width*.35,width*.6)]))
        if self.ident=='haeon':self.water.append(dict(id='coast',kind='coast',level=0.0,polygon=[[310,18],[319,18],[319,319],[177,319],[200,298],[243,280],[279,252],[304,216]]))
        if self.ident=='nord':self.water.append(dict(id='coast',kind='coast',level=0.0,polygon=[[399,20],[415,20],[415,207],[280,207],[301,186],[346,173],[385,143]]))

    def build_routes(self):
        roads={r['id']:r for r in self.doc['roads']}
        def route_path(ids):
            out=[]
            for ident in ids:
                r=roads[ident];a,b=r['points'][0],r['points'][-1]
                for i in range(max(2,math.ceil(math.dist(a,b)/850))):
                    t=(i+.20)/max(2,math.ceil(math.dist(a,b)/850))
                    p=lerp(a,b,t);out.append(dict(x_cm=round(p[0]),y_cm=round(p[2]),surface_id=ident,structural=r['kind']!='ground'))
            return out
        main=self.paths['main'];join=self.spec['core'].index(self.spec['tech'][-1]);tech=main[:2]+self.paths['lane']+main[join:]
        # The start is 18m from the junction; gates begin 8m ahead of it.
        first=roads[main[0]]['points'];a,b=first[0],first[-1];length=math.dist(a,b)
        startp=lerp(a,b,1800/length);gate=lerp(a,b,2600/length)
        start=dict(x_cm=round(startp[0]),y_cm=round(startp[2]),surface_id=main[0],heading_radians=-math.atan2(b[0]-a[0],b[2]-a[2]))
        routes=[]
        for index,(ident,ids,mode) in enumerate([('intro',main,'circuit'),('technical',tech,'circuit'),('sprint',[main[0]]+self.paths['explore'],'sprint')]):
            wp=route_path(ids)
            wp=[p for p in wp if p['surface_id']!=main[0] or p['x_cm']>gate[0]+300]
            wp.insert(0,dict(x_cm=round(gate[0]),y_cm=round(gate[2]),surface_id=main[0],structural=False))
            if mode=='circuit':
                wp.extend([dict(x_cm=round(a[0]+500),y_cm=a[2],surface_id=main[0],structural=False),dict(x_cm=round(startp[0]),y_cm=round(startp[2]),surface_id=main[0],structural=False)])
            if ident=='sprint':
                trimmed=[wp[0]];distance_m=0
                for p in wp[1:]:
                    distance_m+=math.hypot(p['x_cm']-trimmed[-1]['x_cm'],p['y_cm']-trimmed[-1]['y_cm'])/100
                    if distance_m>430:break
                    trimmed.append(p)
                wp=trimmed
            metres=sum(math.hypot(q['x_cm']-p['x_cm'],q['y_cm']-p['y_cm']) for p,q in zip(wp,wp[1:]))/100
            if mode=='circuit':metres+=math.hypot(wp[0]['x_cm']-wp[-1]['x_cm'],wp[0]['y_cm']-wp[-1]['y_cm'])/100
            routes.append(dict(id=ident,name=self.meta['courses'][index],mode=mode,laps=3 if mode=='circuit' else 1,start=start.copy(),waypoints=wp,road_path=ids,length_m=round(metres,2),checkpoint_radius_cm=180))
        self.meta.update(routes=routes,start=start,surface='dirt' if self.ident=='kanupi' else 'asphalt')

    def radius(self,a):
        points=[]
        for c in a['collision']:
            points.extend((abs(c['center'][0])+c['size_cm'][0]/2,abs(c['center'][2])+c['size_cm'][2]/2) for _ in [0])
        for c in a.get('convex_collision',[]):points.extend((abs(p[0]),abs(p[2])) for p in c['vertices'])
        return max((p[0] for p in points),default=50)/100,max((p[1] for p in points),default=50)/100

    def place(self,kind,x,z,turn=0,parcel=False):
        asset='richer-'+kind;a=self.assets[asset];rx,rz=self.radius(a)
        if kind.startswith(('canopy','palm')):rx=max(rx,1.5);rz=max(rz,1.5)
        if turn%2:rx,rz=rz,rx
        radius=math.hypot(rx,rz)
        if not (rx+3<x<self.w-rx-3 and rz+3<z<self.h-rz-3):return False
        if self.wet(x,z)[0]<radius+2:return False
        if any(distance([x,z],aa,bb)[0]<w/2+radius+(1.0 if rid.startswith('main') else .5) for aa,bb,w,rid,*_ in self.segments):return False
        if any(abs(x-xx)<rx+rrx+.8 and abs(z-zz)<rz+rrz+.8 for xx,zz,rrx,rrz in self.occupied):return False
        y=self.height(x,z)
        if parcel:
            nearest=min(self.segments,key=lambda s:distance([x,z],s[0],s[1])[0]);_,t=distance([x,z],nearest[0],nearest[1]);entrance=lerp(nearest[0],nearest[1],t)
            y=round((nearest[4]+(nearest[5]-nearest[4])*t)*100)
            self.parcels.append(dict(x=x,z=z,rx=rx+.35,rz=rz+.35,height=y/100,entrance=entrance,road=nearest[3]))
            # A short tapered yard apron meets the road; no disconnected door island.
            dx,dz=x-entrance[0],z-entrance[1];length=math.hypot(dx,dz);nx,nz=-dz/length*.65,dx/length*.65
            self.doc['surface_areas'].append(dict(id='access-'+str(len(self.parcels)),polygon=[[round((px+sx*nx)*100),round((pz+sx*nz)*100)] for px,pz,sx in [(x,z,-1),(*entrance,-1),(*entrance,1),(x,z,1)]],surface='concrete'))
        ident='parcel-' if parcel else 'nature-'
        ident+=str(len(self.doc['placements']))
        self.doc['placements'].append(dict(id=ident,asset_id=asset,position=[round(x*100),y+(3 if kind.startswith('crop-') else 0),round(z*100)],quarter_turns=turn))
        self.occupied.append((x,z,rx,rz));self.used.add(asset)
        return True

    def settlement(self):
        styles=self.spec['styles']
        # Purposeful, uneven parcels along the core and lanes. Countryside/desert
        # leave gaps and group their small number of farm/workshop compounds.
        count=0
        for a,b,width,rid,*_ in list(self.segments):
            urban=rid.startswith('main');lane=rid.startswith(('lane','residential'))
            if not urban and not lane:continue
            length=math.dist(a,b);t=5+self.rng.uniform(0,3)
            while t<length-5:
                sparse=self.ident in ['belmont','red-wadi','kanupi']
                for side in [-1,1]:
                    if self.rng.random() < (.57 if sparse else .12):continue
                    style=styles[(count//4)%len(styles)]
                    if style=='tower' and (not urban or side<0):style='shop'
                    v=self.rng.randrange(4);aasset=self.assets['richer-'+style+'-'+str(v)];rx,rz=self.radius(aasset)
                    setback=width/2+math.hypot(rx,rz)+self.rng.uniform(1,3.2)
                    dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
                    x=a[0]+dx*t-dz*side*setback;z=a[1]+dz*t+dx*side*setback
                    # Front local -z points towards the actual access street.
                    turn=round(math.atan2(-dx*side,-dz*side)/(math.pi/2))%4
                    if self.place(style+'-'+str(v),x,z,turn,True):count+=1
                t+=self.rng.uniform(6.2,10.4)
        # Outlying farms/cargo/research compounds are separated by open land.
        for segment in self.segments:
            a,b,w,rid,*_=segment
            if not rid.startswith('explore') or segment[-1]!='ground':continue
            if self.rng.random()<.4:continue
            x,z=lerp(a,b,.4);length=math.dist(a,b);x-=(b[1]-a[1])/length*10;z+=(b[0]-a[0])/length*10
            style='farm' if self.ident in ['belmont','bansai'] else 'shed' if self.ident in ['nord','red-wadi','kanupi','haeon'] else 'courtyard'
            accepted=self.place(style+'-'+str(self.rng.randrange(4)),x,z,0,True)
            if accepted and style=='shed':
                for dx,dz in [(7,0),(7,2.2),(7,4.4),(10,0)]:self.place('container',x+dx,z+dz)
        # Irregular crop fields and clearings, kept away from road corridors/water.
        for index in range(14):
            x=self.rng.uniform(self.w*.46,self.w*.88);z=self.rng.uniform(35,self.h-30);rx=self.rng.uniform(7,16);rz=self.rng.uniform(5,12)
            if self.wet(x,z)[0]<max(rx,rz)+5 or any(distance([x,z],a,b)[0]<max(rx,rz)+w for a,b,w,*_ in self.segments):continue
            polygon=[[round((x+rx*dx)*100),round((z+rz*dz)*100)] for dx,dz in [(-1,-.7),(-.3,-1),(1,-.6),(.8,1),(-.8,.8)]]
            self.doc['surface_areas'].append(dict(id='field-'+str(index),polygon=polygon,surface='dirt' if index%2 else 'grass'))
            if self.ident in ['belmont','bansai','safra']:self.place('crop-'+str(index%4),x,z,0,True)
        # Clumped canopy/rocks with clearings. Deterministic jitter, no grid rows.
        trees=900 if self.ident=='kanupi' else 200 if self.ident in ['haeon','belmont','bansai'] else 55
        for index in range(trees*4):
            x=self.rng.uniform(5,self.w-5);z=self.rng.uniform(5,self.h-5)
            cluster=math.sin(x/17+math.cos(z/23))*math.cos(z/19)
            if cluster<-.05:continue
            kind=('palm' if self.ident in ['kanupi','bansai','safra'] else 'canopy')+'-'+str(index%3)
            if self.ident=='kanupi' and index%5:kind='grove-'+str(index%3)
            if self.ident in ['red-wadi','nord'] or index%6==0:kind='rock-'+str(index%3)
            self.place(kind,x,z,index%4)
            trees-=1
            if trees<=0:break
        self.meta['parcels']=self.parcels
        if self.ident in ['haeon','nord']:
            cx,cz=(261,261) if self.ident=='haeon' else (341,160)
            self.place('dock-crane',cx,cz,0,True)
            for dx,dz in [(-9,0),(-9,2.5),(-9,5),(-12,0)]:self.place('container',cx+dx,cz+dz)
        for a,b,w,rid,*_ in self.segments:
            if not rid.startswith('main'):continue
            length=math.dist(a,b);dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
            for t in [.22,.62]:
                x,z=lerp(a,b,t);self.place('lamp',x-dz*(w/2+1.5),z+dx*(w/2+1.5))
                if t==.62:self.place('bench',x+dz*(w/2+2),z-dx*(w/2+2))

    def waters(self):
        from richer_assets import export, ATTRIBUTION, water_mesh
        polygons=[]
        for water in self.water:
            if water['kind']=='dry':continue
            if water['kind']=='coast':polygons.append((water['polygon'],'still'));continue
            if water['kind']=='pond':
                x,z,rx,rz=water['shape']
                # Slightly irregular shoreline, entirely inside the carved basin.
                poly=[(x+rx*.93*(1+.035*math.sin(i*2.7))*math.cos(i*math.tau/24),z+rz*.93*(1+.035*math.sin(i*2.7))*math.sin(i*math.tau/24)) for i in range(24)]
                polygons.append((poly,'still'));continue
            # Shared bank vertices avoid triangular dry notches between curved
            # reaches. Width varies along the centreline without independent caps.
            segments=water['segments'];points=[segments[0][0]]+[s[1] for s in segments]
            radii=[segments[0][2]]+[s[3] for s in segments];left=[];right=[]
            for i,(p,radius) in enumerate(zip(points,radii)):
                a=points[max(0,i-1)];b=points[min(len(points)-1,i+1)]
                length=math.dist(a,b);nx,nz=-(b[1]-a[1])/length,(b[0]-a[0])/length
                left.append((p[0]+nx*radius*.91,p[1]+nz*radius*.91))
                right.append((p[0]-nx*radius*.91,p[1]-nz*radius*.91))
            polygons.append((left+right[::-1],'flow'))
        # Union confluences before tessellation: separate overlapping placement
        # proxies are forbidden by the current contract. Work in integer cm.
        from shapely import constrained_delaunay_triangles, set_precision
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        bodies=[Polygon([(round(x*100),round(z*100)) for x,z in p]) for p,_ in polygons]
        merged=set_precision(unary_union(bodies),1)
        from shapely.geometry import box
        for z in range(self.h//16):
            for x in range(self.w//16):
                part=merged.intersection(box(x*1600,z*1600,(x+1)*1600,(z+1)*1600))
                if part.is_empty or part.area<100:continue
                parts=[part]
                if self.ident=='kanupi' and z==4:
                    parts=[part.intersection(box(x*1600,lo,(x+1)*1600,hi)) for lo,hi in [(6400,7500),(7500,7600),(7600,8000)]]
                triangles=[[(round(xx)/100,round(zz)/100) for xx,zz in list(t.exterior.coords)[:-1]] for section in parts if not section.is_empty for t in constrained_delaunay_triangles(section).geoms]
                origin=[x*16+8,z*16+8]
                flowing=not any(k=='still' and body.covers(part.representative_point()) for body,(_,k) in zip(bodies,polygons))
                model=water_mesh(triangles,origin,flowing,lambda xx,zz:self.wet(xx,zz)[2],self.water_level)
                if not model.convex:continue
                if len(model.convex)>32:raise ValueError(('water cell convex budget',self.ident,x,z,len(model.convex)))
                asset='water-'+str(x)+'-'+str(z);path='assets/'+asset+'.glb';self.payloads[path]=export(model)
                self.doc['assets'].append(dict(id=asset,path=path,attribution=ATTRIBUTION,collision=[],convex_collision=model.convex))
                self.doc['placements'].append(dict(id='placed-'+asset,asset_id=asset,position=[origin[0]*100,0,origin[1]*100],quarter_turns=0))

    def finish(self,destination):
        self.settlement()
        from shapely.geometry import Polygon
        occupied=[];areas=[]
        for area in self.doc['surface_areas']:
            poly=Polygon(area['polygon'])
            if not poly.is_valid or any(poly.intersection(p).area>.01 for p in occupied):continue
            occupied.append(poly);areas.append(area)
        self.doc['surface_areas']=areas
        self.waters()
        for ident in sorted(self.used):
            a=copy.deepcopy(self.assets[ident]);self.doc['assets'].append(a);self.payloads[a['path']]=(self.kit/'assets/richer-library'/a['path']).read_bytes()
        # Optional edge panel, clear of grids and with >2m conventional bypass.
        from special_driving_maps import place
        templates=json.loads((self.kit/'godot/driving_templates.json').read_text())
        lane=next(s for s in self.segments if s[3].startswith('lane') and s[-1]=='ground')
        a,b,w,rid,*_=lane;p=lerp(a,b,.5);length=math.dist(a,b);dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
        p=[p[0]-dz*(w/2-.65),p[1]+dx*(w/2-.65)];kind='jump_height' if self.ident in ['red-wadi','kanupi'] else 'target_speed'
        g=place(templates,kind,[p[0]*100,self.height(*p),p[1]*100],math.degrees(math.atan2(dx,dz)),60)
        g['id']='optional-skill';g['scale_per_mille'][0]=550
        self.doc['gimmicks']=[g];self.meta['challenges']=[dict(id=g['id'],road_id=rid,bypass_width_cm=round(w*100)-110)]
        values=[]
        for z in range(self.h//16):
            for x in range(self.w//16):
                hs=[self.height(x*16+i*2,z*16+j*2) for j in range(9) for i in range(9)];values.extend(hs)
                image=Image.new('I',(9,9));image.putdata([h+4000 for h in hs]);out=io.BytesIO();image.convert('I;16').save(out,format='PNG',compress_level=9)
                data=out.getvalue();path='terrain/'+digest(data)+'.png';self.payloads[path]=data
                self.doc['heightmaps'].append(dict(cell=dict(x=x,y=z),path=path,spacing_cm=200,offset_cm=-4000,step_cm=1,source_accuracy_cm=None))
        # Preserve existing night-window roles through material indices.
        for a in self.doc['assets']:
            from richer_assets import unpack
            gltf,_=unpack(self.payloads[a['path']]);windows=[i for i,m in enumerate(gltf['materials']) if m.get('name')=='mk_glass']
            if windows:self.doc['environment']['lights'].append(dict(asset_id=a['id'],window_materials=[] if a['id']=='richer-lamp' else windows,bulb_materials=windows if a['id']=='richer-lamp' else [],position_cm=[0,270,0],range_cm=400,color=[255,214,151]))
        self.payloads['document.json']=canonical(self.doc)
        self.meta.update(relief=round((max(values)-min(values))/100,2),elevation_range_m=[min(values)/100,max(values)/100],water_bodies=self.water,source_files={p:digest(d) for p,d in self.payloads.items()},
            review_views=[dict(name='waterfront',position_m=[self.spec['pond'][0]-22,12,self.spec['pond'][1]-15],target_m=[self.spec['pond'][0],0,self.spec['pond'][1]]),dict(name='district',position_m=[self.spec['core'][0][0]-8,10,self.spec['core'][0][1]-18],target_m=[self.spec['core'][0][0]+12,1,self.spec['core'][0][1]])])
        folder=destination/self.ident;folder.mkdir(parents=True,exist_ok=False)
        for path,data in {**self.payloads,'region.json':canonical(self.meta)}.items():
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return self.meta

def build(destination,kit):
    if destination.exists():raise FileExistsError('New destination required: '+str(destination))
    sys.path.insert(0,str(kit/'scripts'));destination.mkdir(parents=True)
    (destination/'.gdignore').write_text('')
    result=[]
    for ident in SPECS:
        meta=Region(ident,kit).finish(destination);result.append(meta)
        print(ident,meta['size'],[r['length_m'] for r in meta['routes']],len(meta['parcels']),'parcels',flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);p.add_argument('--kit',type=Path,required=True);a=p.parse_args();build(a.destination,a.kit.resolve())
