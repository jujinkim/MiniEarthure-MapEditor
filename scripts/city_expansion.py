"""Deterministic two-district expansion, after the frozen compact driving layout.

All values here are actual metres; no consumer scale or game dependency.
"""
import copy
import math
from shapely.geometry import Polygon, LineString, box as rectangle
from shapely.ops import unary_union
from driving_school_map import cm
from city_assets import building, props

def expand(t):
    d=t.doc
    original_nodes={tuple(n["position"]):n["id"] for n in d["nodes"]}
    original_ids={n["id"] for n in d["nodes"]}
    d['bounds']['max']=[57600,19200];d['recipe_version']=6
    template=copy.deepcopy(d['heightmaps'][0])
    d['heightmaps']=[dict(template,cell=dict(x=x,y=y)) for y in range(12) for x in range(36)]
    d['surface_areas']=[dict(id='city-paving',polygon=cm_ring([(192,0),(576,0),(576,192),(192,192)]),surface='concrete'),
        dict(id='city-approach-paving',polygon=cm_ring([(103.1,12.5),(172,12.5),(172,82),(103.1,82)]),surface='concrete')]
    props(t)
    libraries={False:[building(t,i) for i in range(8)],True:[building(t,i,True) for i in range(8)]}
    compact_library=[building(t,i,compact=True) for i in range(8)]
    new_roads=[];lots=[];medians=[]
    def road(name,points,width=4,sidewalk=1.2,lanes=2,center=True,crosswalk=True):
        ident=t.path(name,[(x,0,y) for x,y in points],width=width,sidewalk=sidewalk)
        r=d['roads'][-1]
        for key,p in [('from',r['points'][0]),('to',r['points'][-1])]:
            r[key]=original_nodes.get(tuple(p),r[key])
        r['markings']=dict(lanes=lanes,center_line=center,edge_lines=True,crosswalk_start=crosswalk,crosswalk_end=crosswalk)
        new_roads.append(r)
        return ident
    for name,xs,ys,avenue,tower in [
        ('korea',[204,238,272,306,340,376],[16,48,80,112,144,176],272,False),
        ('sky',[396,438,480,522,564],[16,56,96,136,176],480,True)]:
        split_x=sorted([x for x in xs if x!=avenue]+[avenue-2.25,avenue+2.25])
        for j,y in enumerate(ys):
            for i,(a,b) in enumerate(zip(split_x,split_x[1:])):
                road(f'{name}-ew-{j}-{i}',[(a,y),(b,y)],width=6 if j in [1,len(ys)-2] else 4)
        for i,x in enumerate(split_x):
            for j,(a,b) in enumerate(zip(ys,ys[1:])):
                divided=abs(x-avenue)==2.25
                road(f'{name}-ns-{i}-{j}',[(x,a),(x,b)],width=3 if divided else 4,center=not divided)
                if divided and x<avenue: medians.append((avenue,a+5,b-5))
        for j,(a,b) in enumerate(zip(ys,ys[1:])):
            for i,(left,right) in enumerate(zip(xs,xs[1:])):
                # Carriageway clearance and a continuous public sidewalk precede
                # building lots. Facing rows leave internal service alleys.
                x0=left+(3.75 if left==avenue else 2)+1.7
                x1=right-(3.75 if right==avenue else 2)-1.7
                y0=a+(3 if j in [1,len(ys)-2] else 2)+1.7
                y1=b-(3 if j+1 in [1,len(ys)-2] else 2)-1.7
                size=14 if tower else 11
                compact=not tower and 4*size*size/((x1-x0)*(y1-y0))>0.80
                if compact: size=10.5
                library=compact_library if compact else libraries[tower]
                for k,(cx,cy) in enumerate([(x0+size/2,y0+size/2),(x1-size/2,y0+size/2),(x0+size/2,y1-size/2),(x1-size/2,y1-size/2)]):
                    ident=f'{name}-block-{i}-{j}-{k}'
                    t.place(ident,library[(i*3+j*5+k)%8],(cx,0,cy),(i+j+k)%4)
                lots.append(dict(id=f'{name}-{i}-{j}',bounds=[x0,y0,x1,y1],buildings=4,footprint_m2=4*size*size))
        t.location('city-skyline' if tower else 'city','고층 업무 지구' if tower else '현대 한국 도심',
            (avenue-2.25,0,ys[1]+10),f'{name}-ns-{split_x.index(avenue-2.25)}-1',
            '192 × 192m 고층 빌딩·상업 광장' if tower else '192 × 192m 상가·주거·아파트·생활 골목',0)
    # Two independent gates connect through the unchanged eastern belt nodes.
    road('city-link-north',[(181.25,46.88),(192,46.88),(204,48)],width=4,sidewalk=0,crosswalk=False)
    road('city-link-south',[(181.25,81.25),(192,81.25),(204,80)],width=4,sidewalk=0,crosswalk=False)
    road('district-link-north',[(376,48),(386,48),(396,56)],width=6,crosswalk=False)
    road('district-link-south',[(376,144),(386,144),(396,136)],width=6,crosswalk=False)
    # Source geometry itself supplies full-footprint checks for repeatable street
    # furniture; no random retry or silent deletion after generation.
    occupied=[]
    assets={a['id']:a for a in d['assets']}
    def footprint(p):
        a=assets[p['asset_id']]; points=[]
        for shape in a.get('collision',[]):
            cx,_,cy=[v/100 for v in shape['center']];w,_,h=[v/100 for v in shape['size_cm']]
            for x,y in [(cx-w/2,cy-h/2),(cx+w/2,cy-h/2),(cx+w/2,cy+h/2),(cx-w/2,cy+h/2)]:
                for _ in range(p['quarter_turns']):x,y=-y,x
                points.append((x+p['position'][0]/100,y+p['position'][2]/100))
        return Polygon(points).convex_hull if points else None
    for p in d['placements']:
        poly=footprint(p)
        if poly is not None:occupied.append(poly)
    corridors=unary_union([LineString([(p[0]/100,p[2]/100) for p in r['points']]).buffer(max(r['widths_cm'])/200+0.025,cap_style=3,join_style=2) for r in d['roads']])
    bounds=rectangle(192,0,576,192)
    prop_counts={}
    def place(asset,x,y,turns=0,height=0.12):
        ident=f'{asset}-{prop_counts.get(asset,0)}'
        p=dict(id=ident,asset_id=asset,position=cm((x,height,y)),quarter_turns=turns)
        poly=footprint(p)
        if not bounds.contains(poly) or corridors.intersects(poly) or any(poly.intersects(old) for old in occupied):return False
        d['placements'].append(p);occupied.append(poly.buffer(0.04));prop_counts[asset]=prop_counts.get(asset,0)+1
        return True
    for x,a,b in medians:
        for y in range(math.ceil(a),math.floor(b),8):place('city-tree',x,y)
    for r in new_roads:
        if len(r['points'])!=2 or r['sidewalk_cm']==0:continue
        a,b=r['points'];ax,ay=a[0]/100,a[2]/100;bx,by=b[0]/100,b[2]/100
        length=math.hypot(bx-ax,by-ay)
        if length<16:continue
        dx,dy=(bx-ax)/length,(by-ay)/length
        for side in [-1,1]:
            away=r['widths_cm'][0]/200+0.62
            for offset in range(7,int(length)-5,9):
                x=ax+dx*offset-dy*away*side;y=ay+dy*offset+dx*away*side
                asset=['city-tree','city-lamp','city-bench'][(offset//9+len(r['id'])+(side==1))%3]
                place(asset,x,y,1 if dy else 0)
            if '-ew-' in r['id']:
                x=ax+dx*length*0.57-dy*away*side;y=ay+dy*length*0.57+dx*away*side
                if int(r['id'].split('-')[-2]) in [1,3] and int(r['id'].split('-')[-1]) in [1,3]:
                    place('city-bus-stop',x-dy*0.13*side,y+dx*0.13*side,0 if side==1 else 2)
                place('city-bin',x+2.1,y)
                for offset in [5.0,length-5.0]:place('city-bollard',ax+dx*offset-dy*away*side,ay+dy*offset+dx*away*side)
    # The old city spawn has the same stable UI identifier, now referring to the
    # expanded Korean district. Every other existing start keeps its exact pose.
    cities=[p for p in t.locations if p['id']=='city']
    if len(cities)>1:t.locations.remove(cities[0])
    used={r[key] for r in d['roads'] for key in ['from','to']}
    d['nodes']=[n for n in d['nodes'] if n['id'] in used or n['id'] in original_ids]
    t.city_report=dict(districts=[dict(id='korea',bounds_m=[192,0,384,192],blocks=25),dict(id='sky',bounds_m=[384,0,576,192],blocks=16)],
        buildings=164,props=prop_counts,lots=lots,grass_ground_fraction=0.0)

def cm_ring(points):return [[round(x*100),round(y*100)] for x,y in points]
