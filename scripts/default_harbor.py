"""Neon Harbor: authored street blocks, working quays and a coastal crossing."""
import json
import math
import random
import struct
import numpy as np
from shapely.geometry import Point,Polygon,LineString,box
from shapely.ops import unary_union
from default_worlds import smooth

def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y)
    h=7.2+1.3*np.sin(x/280)*np.sin(y/230)
    for cx,cy,rise,sx,sy in [(170,150,28,230,195),(1050,140,25,340,185),(1840,220,37,225,260)]:
        h=h+rise*np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2)
    coast=np.full(np.broadcast_shapes(x.shape,y.shape),860.)
    coast=np.where((x>=820)&(x<=1210),1080.,coast)
    coast=np.where((x>=1210)&(x<=1300),900.,coast)
    coast=np.where((x>=1300)&(x<=1800),1060.,coast)
    bank=1-smooth((y-coast+5)/11)
    return h*bank-4*(1-bank)

def compose(w):
    w.base=terrain
    w.doc['theme']='urban'
    w.doc['environment'].update(concept='metropolis',architecture='modern',settlement='urban',
        start_minutes=1080,ground_color=[104,121,104])
    w.spawn=dict(x_cm=26000,y_cm=56000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(200,560);B=(450,560);C=(690,560);D=(900,560);E=(1230,600);F=(1640,700)
    G=(1660,970);H=(1360,960);I=(1170,960);J=(940,960);K=(900,770)
    L=(690,760);M=(450,750);N=(230,730);U=(450,350);V=(690,330);W=(900,350)
    # A 250 m arrival straight precedes continuous high-street frontage.
    w.path('arrival-road',[A,B],12,3,level=8)
    w.path('neon-avenue',[B,C],12,3.2,level=8)
    w.path('hotel-street',[C,D],11,3,level=8)
    w.path('freight-boulevard',[D,(1020,562),(1130,584),E],11,2,level=8)
    w.path('container-way',[E,(1380,616),(1510,667),F],10,1.4,level=8)
    w.path('east-port-approach',[F,(1680,794),(1685,895),G],10,level=lambda x,y:8-(y-700)/270*2)
    w.path('east-pier-road',[G,(1550,997),(1440,985),H],10,level=lambda x,y:6+4*float(smooth((1500-x)/110)))
    w.path('channel-bridge',[H,I],10,kind='bridge',level=10)
    w.path('west-pier-road',[I,(1145,960),(1090,960),(1030,960),J],10,level=lambda x,y:6+4*float(smooth((x-1020)/125)))
    w.path('dock-gateway',[J,(922,875),(900,820),K],10,level=6)
    w.path('quay-boulevard',[K,(801,775),L],10,2.5,level=6)
    w.path('waterfront-street',[L,(570,757),M],10,3,level=6)
    w.path('old-quay',[M,(335,753),N],8,2,level=6)
    w.path('west-coast-road',[N,(190,673),(193,609),A],9,1.8,level=lambda x,y:8-2*float(smooth((y-560)/170)))
    w.path('station-street',[B,(453,447),U],9,2.8,level=lambda x,y:8+2*float(smooth((560-y)/210)))
    w.path('north-market',[U,(565,330),V],9,2.4,level=10)
    w.path('upper-hotel-road',[V,(800,328),W],9,2.4,level=10)
    w.path('east-residential',[W,(906,450),D],9,2.2,level=lambda x,y:10-2*float(smooth((y-350)/210)))
    w.path('central-tram-street',[V,(681,437),C],10,3,level=lambda x,y:10-2*float(smooth((y-330)/230)))
    w.path('market-seafront',[B,(448,652),M],9,2.5,level=lambda x,y:8-2*float(smooth((y-560)/190)))
    w.path('hotel-seafront',[C,(682,659),L],9,2.5,level=lambda x,y:8-2*float(smooth((y-560)/200)))
    w.path('warehouse-gate',[D,(911,681),K],10,1.5,level=lambda x,y:8-2*float(smooth((y-560)/210)))
    w.path('hill-loop',[U,(320,325),(248,353),(211,442),A],8,1.5,level=lambda x,y:8+2*float(smooth((560-y)/210)))
    w.path('upper-port-road',[W,(1033,344),(1165,418),(1225,519),E],9,1.5,
        level=lambda x,y:8+2*float(smooth((600-y)/250)))
    w.path('coast-access',[K,(1010,790),(1140,813),(1290,823),(1360,830)],7,level=6)
    # Split explicitly at the shared coastal/service junction.
    T=(1360,830)
    w.path('port-service-road',[E,(1312,748),T],9,level=lambda x,y:8-2*float(smooth((y-600)/230)))
    w.path('port-service-south',[T,(1360,895),(1360,930),H],9,level=lambda x,y:6+4*float(smooth((y-830)/100)))
    # Sea follows the authored quay outline, including the open bridge channel.
    water=Polygon([(0,860),(780,860),(820,890),(820,1080),(1210,1080),(1210,900),
        (1300,900),(1300,1060),(1800,1060),(1800,860),(1920,860),(1920,1280),(0,1280)])
    w.water_body('harbor-sea',water,2.8)
    # Raised industrial slabs make piers continuous land rather than floating props.
    for x,y,rx,ry in [(1015,985,193,92),(1550,983,246,75)]:w.pads.append((x,y,rx,ry,6))
    for x,y in (H,I):w.pads.append((x,y,12,12,10))
    w.pads.extend([(533,817.5,242,25,6),(390,852,390,8,6)])
    w.paint('west-working-pier',box(825,875,1207,1077),'concrete')
    w.paint('east-working-pier',box(1303,871,1797,1057),'concrete')
    w.paint('freight-yard',Polygon([(982,619),(1210,650),(1285,773),(991,759)]),'concrete')
    w.paint('container-yard',Polygon([(1410,700),(1635,745),(1610,925),(1410,922)]),'concrete')
    w.places=['Neon Avenue and Night Market','Station Quarter','Hotel Courtyards',
        'Waterfront Promenade','West Cargo Quay','Channel Bridge','East Container Terminal',
        'Freight Warehouse Yards','Coastal Hills']

    def row(road_id,stations,side,variants,label,setback=19):
        line=w.routes[road_id]
        for i,s in enumerate(stations):
            if min(s,line.length-s)<42:continue
            p=line.interpolate(s);q=line.interpolate(s+.5);dx=q.x-p.x;dy=q.y-p.y;l=math.hypot(dx,dy)
            nx=-dy/l*side;ny=dx/l*side;x=p.x+nx*setback;y=p.y+ny*setback
            yaw=math.degrees(math.atan2(-nx,ny));kind='urban-'+str(variants[i%len(variants)])
            ground=float(w.height(p.x,p.y));name=label+'-'+str(i)
            w.place(name,kind,x,y,yaw,ground,True)
            w.paint(name+'-front',LineString([(x,y),(p.x,p.y)]).buffer(4.7,cap_style=2),'concrete')
            w.paint(name+'-rear',Point(x+nx*10,y+ny*10).buffer(4.4,quad_segs=3),'concrete')
            w.place(name+'-bin','bin',x+nx*9.8,y+ny*9.8,yaw,ground)
            if i%3==1:
                w.place(name+'-car','parked-car',p.x+nx*8.6,p.y+ny*8.6,math.degrees(math.atan2(dx,-dy)),ground)
            elif i%2==0:w.place(name+'-planter','planter',p.x+nx*8.7,p.y+ny*8.7,yaw,ground)

    for road_id,stations,variants in [('arrival-road',range(118,237,20),[2,5,0,1]),
            ('neon-avenue',range(27,221,21),[0,1,3,5,2,4]),('hotel-street',range(26,192,22),[3,4,1,0]),
            ('station-street',range(32,184,22),[1,2,0,5]),('central-tram-street',range(34,205,23),[2,4,1,0]),
            ('north-market',range(32,216,23),[5,0,2]),('upper-hotel-road',range(32,182,23),[1,4,3]),
            ('east-residential',range(32,186,23),[0,4,1,3]),('market-seafront',range(33,167,23),[0,5,1]),
            ('hotel-seafront',range(34,181,24),[3,2,4])]:
        for side in (-1,1):row(road_id,stations,side,variants,road_id+('-west' if side==1 else '-east'))
    row('waterfront-street',range(28,216,22),1,[3,0,2,1,5],'promenade-row',21)
    row('quay-boulevard',range(30,188,24),1,[5,0,2],'quay-row',20)
    # Designed block interiors: service alleys, squares and small gardens.
    for i,(cx,cy) in enumerate([(563,439),(791,440),(567,650)]):
        w.paint('courtyard-'+str(i),box(cx-60,cy-36,cx+60,cy+36),'concrete')
        w.paint('courtyard-link-'+str(i),LineString([(cx,cy),(cx,cy+105)]).buffer(2),'concrete')
        for j in range(5):
            w.place('court-tree-'+str(i)+'-'+str(j),'tree-'+str(1+j%3),cx-44+j*22,cy+22,solid=False)
            w.place('court-bench-'+str(i)+'-'+str(j),'bench',cx-44+j*22,cy+16,180)
        for j in range(6):
            w.place('court-parking-'+str(i)+'-'+str(j),'parked-car',cx-38+j*13,cy-22,90)
        for j in range(3):
            w.place('court-table-'+str(i)+'-'+str(j),'table',cx-20+j*20,cy,0)
        # Service workshop and two residential wings define an interior garden;
        # rear alleys connect them to the surrounding street fronts.
        if i<2:w.place('court-workshop-'+str(i),'warehouse-1',cx,cy-54,180,foundation=True)
        for side in (-1,1):
            px=cx+side*43;py=cy+(56 if i==2 else 66)
            w.place('court-wing-'+str(i)+'-'+str(side),'urban-'+str((i+side+6)%6),px,py,180,foundation=True)
            w.paint('court-wing-access-'+str(i)+'-'+str(side),LineString([(px,py),(px,cy+36)]).buffer(2.2),'concrete')
            for step in range(3):
                w.place('court-garden-'+str(i)+'-'+str(side)+'-'+str(step),'shrub',px+side*13,py-8+step*7,solid=False)
    w.paint('promenade',box(292,793,775,842),'concrete')
    w.paint('promenade-link',LineString([(455,750),(455,805)]).buffer(3.5),'concrete')
    for i,x in enumerate(range(307,766,29)):
        w.place('sea-bench-'+str(i),'bench',x,826,180,6)
        w.place('sea-tree-'+str(i),'tree-'+str(1+i%3),x,798,level=6,solid=False)
        w.place('sea-lamp-'+str(i),'port-lamp',x+11,834,level=6)
    # Warehouse service backs, covered docks, parked trucks and connected pipe runs.
    facilities=[('freight-west',1017,661,1,0),('freight-east',1100,686,2,0),
        ('freight-upper',1154,508,0,180),('west-quay-shed',1075,894,0,180),
        ('east-yard-shed',1530,808,2,90),('east-yard-office',1762,824,1,90)]
    for label,x,y,variant,yaw in facilities:
        level=6 if y>860 else 8
        w.pads.append((x,y,32,32,level))
        w.place(label,'warehouse-'+str(variant),x,y,yaw,level,True)
        w.paint(label+'-apron',box(x-30,y-31,x+30,y+31),'concrete')
        w.place(label+'-truck','parked-truck',x+22,y-24,yaw,level)
        for j in range(3):w.place(label+'-crate-'+str(j),'crate',x-13+j*2,y+22,level=level)
    for i,x in enumerate(range(995,1189,17)):w.place('freight-pipe-'+str(i),'pipeline',x,738,level=8)
    for i,x in enumerate((977,1000,1023)):
        w.place('quay-loading-truck-'+str(i),'parked-truck',x,929,180,6)
        for j in range(3):w.place('quay-cargo-crate-'+str(i)+'-'+str(j),'crate',x+4+j*1.3,929,level=6)
    for i,x in enumerate(range(998,1187,16)):
        for j,y in enumerate((1003,1030)):
            w.place('west-container-'+str(i)+'-'+str(j),'container-stack-'+str((i+j)%4),x,y,level=6,foundation=True)
    for i,x in enumerate(range(1405,1606,17)):
        for j,y in enumerate((871,888,907,927)):
            w.place('east-container-'+str(i)+'-'+str(j),'container-stack-'+str((i+j)%4),x,y,level=8 if y<910 else 6,foundation=True)
    for i,x in enumerate((885,983,1100)):
        w.place('west-quay-crane-'+str(i),'dock-crane',x,1051,180,6,True)
    for i,x in enumerate((1393,1510,1675)):
        w.place('east-quay-crane-'+str(i),'dock-crane',x,1034,180,6,True)
    for i,x in enumerate((1229,1287)):
        w.place('bridge-pier-'+str(i),'harbor-pier',x,960,90,-2.2,solid=False)
    # Quay walls and fenders, with actual corners and an open navigable channel.
    for name,line in [('old-seawall',LineString([(22,860),(777,860)])),
        ('west-quay-edge',LineString([(834,1080),(1200,1080)])),
        ('east-quay-edge',LineString([(1310,1060),(1790,1060)])),
        ('west-channel-edge',LineString([(1210,913),(1210,1070)])),
        ('east-channel-edge',LineString([(1300,913),(1300,1050)]))]:
        for i,s in enumerate(np.arange(8,line.length-7,15.3)):
            p=line.interpolate(s);q=line.interpolate(s+.3);yaw=math.degrees(math.atan2(q.y-p.y,q.x-p.x))
            w.place(name+'-'+str(i),'quay-wall',p.x,p.y,yaw,6,solid=False)
    for i,x in enumerate(range(841,1197,30)):
        w.place('west-mooring-'+str(i),'bollard',x,1074,level=6)
    for i,x in enumerate(range(1315,1780,32)):
        w.place('east-mooring-'+str(i),'bollard',x,1053,level=6)
    # Functional terminal fence lines leave their road and loading entrances open.
    for label,y,xs in [('cargo-north',771,range(990,1240,7)),('yard-east',766,range(1401,1612,7))]:
        for i,x in enumerate(xs):w.place(label+'-fence-'+str(i),'port-fence',x,y,solid=False)
    for label in ('arrival-road','neon-avenue','hotel-street','waterfront-street','freight-boulevard','container-way','east-port-approach'):
        line=w.routes[label]
        for i,s in enumerate(np.arange(22,line.length-18,36)):
            p=line.interpolate(s);q=line.interpolate(s+.4);dx=q.x-p.x;dy=q.y-p.y;l=math.hypot(dx,dy)
            for side in (-1,1):
                x=p.x-dy/l*side*8.2;y=p.y+dx/l*side*8.2
                w.place(label+'-light-'+str(i)+'-'+str(side),'port-lamp',x,y,solid=False)
    # Northern hills and western coastal park frame the city. Randomness only
    # fills these authored habitat polygons and never chooses streets/facilities.
    habitats=[('station-hill',Polygon([(22,26),(730,26),(694,240),(402,270),(177,348),(36,414)]),13.0),
        ('east-ridge',Polygon([(845,25),(1890,25),(1880,751),(1757,765),(1717,535),(1377,406),(1194,260),(850,239)]),13.5),
        ('west-coastal-park',Polygon([(20,436),(126,416),(141,631),(181,759),(738,844),(21,843)]),19.0)]
    occupied=unary_union([area for _,area in w.obstacles]).buffer(4)
    excluded=w.road_area(6).union(water.buffer(4)).union(occupied)
    for label,area,spacing in habitats:
        rng=random.Random(9107+sum(map(ord,label)));a,b,c,d=area.bounds;index=0
        for y in np.arange(b+8,d-7,spacing):
            for x in np.arange(a+8,c-7,spacing):
                x=float(x+rng.uniform(-3,3));ty=float(y+rng.uniform(-3,3));p=Point(x,ty)
                if not area.contains(p) or excluded.contains(p):continue
                w.place(label+'-tree-'+str(index),'tree-'+str(rng.choice([0,1,2,3,4])),x,ty,rng.randrange(360),solid=False)
                if index%2==0:w.place(label+'-shrub-'+str(index),'shrub',x+3,ty+3,solid=False)
                if index%4==0:w.place(label+'-grass-'+str(index),'grass',x-3,ty+2,solid=False)
                index+=1
    # Material bindings are paired by stable material order in both GLBs.
    for asset in w.doc['assets']:
        if not asset['id'].startswith(('authored-urban-','authored-port-lamp')):continue
        documents=[]
        for field in ('path','distant_path'):
            data=w.payloads[asset[field]];documents.append(json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]]))
        colors=[[m['pbrMetallicRoughness']['baseColorFactor'] for m in doc['materials']] for doc in documents]
        if colors[0]!=colors[1]:raise ValueError('Near/far light material order differs: '+asset['id'])
        windows=[i for i,color in enumerate(colors[0]) if color==[.17,.29,.31,1]]
        bulbs=[i for i,color in enumerate(colors[0]) if color in ([.24,.88,.90,1],[.91,.32,.58,1],[.92,.77,.40,1])]
        w.doc['environment']['lights'].append(dict(asset_id=asset['id'],window_materials=windows,bulb_materials=bulbs,
            position_cm=[0,320,-700] if 'urban' in asset['id'] else [0,960,0],range_cm=1600,color=[181,217,231]))
    routes=[w.course('intro','Neon Streets',['arrival-road','neon-avenue','hotel-street','-east-residential','-upper-hotel-road','central-tram-street','hotel-seafront','waterfront-street','-market-seafront']),
        w.course('tour','Cargo and Coast',['arrival-road','neon-avenue','hotel-street','freight-boulevard','container-way','east-port-approach','east-pier-road','channel-bridge','west-pier-road','dock-gateway','quay-boulevard','waterfront-street','old-quay','west-coast-road']),
        w.course('technical','Harbor Crossings',['arrival-road','station-street','north-market','upper-hotel-road','upper-port-road','port-service-road','port-service-south','channel-bridge','west-pier-road','dock-gateway','-warehouse-gate','-hotel-street','hotel-seafront','waterfront-street'])]
    def view(name,eye,target,time=1088):
        return dict(name=name,position_m=[eye[0],float(w.height(*eye))+1.7,eye[1]],
            target_m=[target[0],float(w.height(*target))+2,target[1]],quality=2,view_distance_m=384,time_minutes=time)
    views=[view('main-street',(478,560),(591,560)),view('day-street',(478,560),(591,560),900),
        view('port-road',(950,960),(1080,1003),840),
        view('coastal-road',(465,758),(640,805),1030),
        dict(name='distant',position_m=[1280,11.7,960],target_m=[1440,20,1028],quality=2,view_distance_m=384,time_minutes=1010),
        dict(name='overview',position_m=[680,230,615],target_m=[610,8,555],projection='orthogonal',size_m=300,quality=2,view_distance_m=384,time_minutes=840)]
    return dict(id='neon-harbor',name='네온 항만',en='Neon Harbor',theme='neon-harbor',size=list(w.size),surface='asphalt',
        description='Neon shop streets and lived-in blocks lead to a seawall promenade, working cargo quays and the channel bridge.',
        districts=['commercial streets','residential blocks','waterfront','warehouses','cargo quays','container terminal','coastal hills'],
        landmarks=w.places,routes=routes,start=routes[0]['start'],review_views=views,preview_center_m=[570,8,552],
        ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='day-street',signature_preview='port-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
