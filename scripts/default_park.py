"""Sky Park: tiered gardens and static rides joined by supported viaducts, MIT."""
import math,random
import numpy as np
from shapely.geometry import Point,Polygon,LineString,box
from shapely.ops import unary_union
from default_worlds import smooth,curve

def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y);base=15+3*np.sin(x/170)*np.cos(y/190);h=base.copy()
    for cx,cy,rx,ry,z in [(420,1130,290,210,42),(550,840,230,220,58),(620,530,150,135,88),
            (1250,560,310,170,88),(1340,940,260,230,64)]:
        r=np.sqrt(((x-cx)/rx)**2+((y-cy)/ry)**2);weight=1-smooth((r-.82)/.43)
        h=np.maximum(h,base*(1-weight)+z*weight)
    r=np.sqrt(((x-542)/105)**2+((y-1030)/95)**2)
    weight=1-smooth((r-.8)/.8)
    h=np.maximum(h,h*(1-weight)+48*weight)
    # The decks retain clearance right up to their level abutments.
    for lo,hi,cy,z in [(760,1130,800,70),(760,1070,480,88)]:
        weight=(1-smooth((np.abs(y-cy)-8)/20))*smooth((x-lo)/25)*smooth((hi-x)/25)
        h=h*(1-weight)+np.minimum(h,z-12)*weight
    return h

def compose(w):
    w.base=terrain;w.doc['theme']='rural'
    w.doc['environment'].update(concept='countryside',architecture='modern',settlement='village',ground_color=[112,144,103],start_minutes=850)
    w.spawn=dict(x_cm=31000,y_cm=120000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(250,1200);B=(510,1200);C=(710,1060);D=(760,800);E=(1130,800);F=(1330,1000)
    G=(1490,710);H=(1430,480);I=(1070,480);J=(760,480);K=(530,750);L=(340,920)
    def ramp(name,points,a,b,width=8,start_apron=0,end_apron=0):
        line=LineString(curve(points))
        w.path(name,points,width,1.2,level=lambda x,y:a+(b-a)*np.clip(
            (line.project(Point(x,y))-start_apron)/(line.length-start_apron-end_apron),0,1))
    w.path('arrival-road',[A,B],12,2,level=42)
    ramp('garden-lane',[B,(615,1162),C],42,58)
    ramp('west-sky-approach',[C,(735,938),(760,845),(760,825),D],58,70,end_apron=35)
    w.path('central-skyway',[D,E],8,kind='bridge',level=70)
    ramp('wheel-promenade',[E,(1155,800),(1200,825),(1275,890),F],70,64,start_apron=35)
    ramp('eastern-terrace',[F,(1450,918),(1518,808),G],64,74)
    ramp('coaster-climb',[G,(1500,589),H],74,88)
    w.path('coaster-boulevard',[H,I],9,1.8,level=88)
    w.path('northern-skyway',[I,J],8,kind='bridge',level=88)
    ramp('west-garden-descent',[J,(742,480),(725,480),(655,512),(580,632),K],88,58,start_apron=35)
    ramp('sculpture-garden-road',[K,(420,787),(353,852),L],58,48)
    ramp('entry-return',[L,(286,1040),A],48,42)
    ramp('garden-shortcut',[K,(652,849),(710,965),C],58,58,7.5)
    for x,y,z in [(*D,70),(*E,70),(*I,88),(*J,88)]:w.pads.append((x,y,11,11,z))
    for name,y,kind,xs in [('central',800,'sky-pier-low',(820,890,960,1030,1095)),('north',480,'sky-pier-high',(805,865,925,985,1040))]:
        for i,x in enumerate(xs):w.place(name+'-pier-'+str(i),kind,x,y,90,10,solid=False)
    w.places=['Entrance Gardens','Carousel Court','Western Sculpture Garden','Central Skyway',
        'Observation Wheel Terrace','Coaster Heights','Northern Skyway','Upper Garden Lookout']
    courts=[];gardens=[]
    def court(name,cx,cy,rx,ry,z,islands=()):
        shape=Point(cx,cy).buffer(1,quad_segs=24);from shapely import affinity
        shape=affinity.scale(shape,rx,ry);w.pads.append((cx,cy,rx,ry,z));courts.append(shape.buffer(12))
        for i,(x,y) in enumerate(islands):
            shape=shape.difference(Point(x,y).buffer(7,quad_segs=12));gardens.append((name+'-garden-'+str(i),x,y,z))
        w.paint(name,shape,'concrete')
    court('carousel-court',542,1030,85,66,48,[(509,1018),(581,1012),(537,1060),(507,1050)])
    court('wheel-court',1380,897,76,64,64,[(1330,882),(1430,880),(1430,916),(1390,855)])
    court('coaster-court',1240,585,104,76,88)
    court('upper-garden',647,549,65,55,88)
    court('entrance-square',447,1130,65,42,42)
    w.place('carousel-landmark','carousel',542,1028,0,48)
    w.place('wheel-landmark','observation-wheel',1390,894,40,64)
    w.place('coaster-landmark','decorative-coaster',1240,585,0,88)
    for name,points in [('carousel-entry',[(542,1091),(585,1176)]),('wheel-entry',[(1372,961),(1330,1000)]),
            ('coaster-entry',[(1310,567),(1330,480)]),('upper-entry',[(647,494),(704,485)]),('entrance-entry',[(447,1170),(447,1200)])]:
        w.paint(name,LineString(points).buffer(4.5),'concrete')
    for i,(x,y,a,z) in enumerate([(483,1063,15,48),(599,1060,-20,48),(1320,907,-25,64),(1457,934,20,64),
            (1142,625,70,88),(1354,623,-70,88),(411,1130,0,42),(470,1130,0,42),(616,546,90,88)]):
        w.place('park-stall-'+str(i),'park-kiosk-'+str(i%3),x,y,a,z,True)
        w.place('stall-bin-'+str(i),'bin',x+7,y+2,level=z)
        w.place('stall-table-'+str(i),'table',x,y+10,level=z)
    # Queue rails leave real entrance/exit gaps. Rides remain static scenery.
    for label,cx,cy,z in [('carousel',563,1060,48),('wheel',1348,935,64),('coaster',1321,621,88)]:
        for row in range(4):
            for col in range(3):w.place(label+'-queue-'+str(row)+'-'+str(col),'queue-rail',cx+col*8.3,cy+row*3,level=z)
        w.paint(label+'-queue-walk',box(cx-4.5,cy-2,cx+21,cy+11),'concrete')
    for label,cx,cy,z in [('entrance',444,1111,42),('carousel',490,993,48),('wheel',1340,860,64),('upper',662,567,88)]:
        for i in range(4):
            w.place(label+'-flowers-'+str(i),'flowerbed',cx+i*10,cy,level=z)
            w.place(label+'-bench-'+str(i),'bench',cx+i*10,cy+5,180,z)
    for name,x,y,z in gardens:
        w.place(name+'-tree','tree-3',x,y,level=z)
        w.place(name+'-flowers','flowerbed',x,y-5.5,level=z)
        w.place(name+'-bench','bench',x,y+8,180,z)
    # Retained green strips separate plazas from roads and hold mature trees,
    # clipped hedges, smaller shrubs and lawn. High roads cross a real valley.
    exclusion=w.road_area(13).union(unary_union(courts)).union(unary_union([a for _,a in w.obstacles]).buffer(5))
    # Preserve a wide arrival sightline and the pedestrian approach to the carousel.
    exclusion=exclusion.union(LineString([(600,1170),(542,1028)]).buffer(24))
    rng=random.Random(91594)
    for row,y in enumerate(range(40,1560,21)):
        for col,x in enumerate(range(40,1880,22)):
            x=x+rng.uniform(-5,5);y1=y+rng.uniform(-5,5)
            if exclusion.contains(Point(x,y1)):continue
            if 770<x<1100 and (abs(y1-800)<35 or abs(y1-480)<35):continue
            kind='tree-'+str((row+col)%5) if (row+col)%4 else 'shrub'
            w.place('park-grove-'+str(row)+'-'+str(col),kind,x,y1,rng.randrange(360),solid=False)
    for label,road in [('arrival','arrival-road'),('garden','garden-lane')]:
        line=w.routes[road]
        for i,s in enumerate(np.arange(40,line.length-20,14)):
            p=line.interpolate(s);q=line.interpolate(s+.5);dx=q.x-p.x;dy=q.y-p.y;length=math.hypot(dx,dy)
            for side in (-1,1):w.place(label+'-hedge-'+str(side)+'-'+str(i),'hedge',p.x-dy/length*side*11,p.y+dx/length*side*11,math.degrees(math.atan2(dy,dx)),solid=False)
    outer=['arrival-road','garden-lane','west-sky-approach','central-skyway','wheel-promenade','eastern-terrace','coaster-climb','coaster-boulevard','northern-skyway','west-garden-descent','sculpture-garden-road','entry-return']
    routes=[w.course('intro','Gardens and Carousel',['arrival-road','garden-lane','-garden-shortcut','sculpture-garden-road','entry-return']),
        w.course('tour','Sky Park Grand Tour',outer),
        w.course('technical','Twin Skyways',['arrival-road','garden-lane','west-sky-approach','central-skyway','wheel-promenade','eastern-terrace','coaster-climb','coaster-boulevard','northern-skyway','west-garden-descent','garden-shortcut'])]
    def view(name,road,s,target):
        p=w.routes[road].interpolate(s)
        return dict(name=name,position_m=[p.x,float(w.height(p.x,p.y))+1.7,p.y],target_m=target,quality=2,view_distance_m=384)
    views=[view('garden-road','garden-lane',90,[542,53,1028]),view('wheel-road','wheel-promenade',230,[1390,84,894]),
        view('coaster-road','coaster-boulevard',100,[1240,101,585]),
        dict(name='distant',position_m=[1050,71.7,800],target_m=[1390,90,894],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[1335,160,960],target_m=[1380,64,895],projection='orthogonal',size_m=240,quality=2,view_distance_m=384),
        dict(name='skyway-supports',position_m=[940,42,958],target_m=[970,53,800],quality=2,view_distance_m=384)]
    return dict(id='sky-park',name='공중 놀이공원',en='Sky Amusement Park',theme='sky-park',size=list(w.size),surface='asphalt',
        description='Tiered gardens and plazas connect a carousel, observation wheel and decorative coaster through two supported skyways.',
        districts=['entrance gardens','carousel court','wheel terrace','coaster heights','upper garden'],landmarks=w.places,routes=routes,start=routes[0]['start'],review_views=views,
        preview_center_m=[1358,64,890],ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='garden-road',signature_preview='wheel-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
