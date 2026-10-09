"""Deep Forest: cedar slopes, a river gorge and a quiet lakeside camp, MIT."""
import math
import random
import numpy as np
from shapely.geometry import LineString,Point,Polygon,box
from shapely import affinity
from shapely.ops import unary_union
from default_worlds import smooth

def river_x(y):return 1070+72*np.sin(np.asarray(y)/330)+20*np.sin(np.asarray(y)/113)

def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y)
    h=33+4*np.sin(x/160)*np.cos(y/150)
    for cx,cy,rise,sx,sy in [(230,320,73,330,430),(1520,320,94,300,370),
            (1590,1530,62,280,290),(270,1540,35,350,200),(710,610,28,195,220)]:
        h=h+rise*np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2)
    valley=np.abs(x-river_x(y));bank=smooth((valley-10)/52)
    h=h*bank+18*(1-bank)
    lake=((x-1110)/128)**2+((y-1115)/118)**2
    h=h*smooth((lake-.88)/.45)+18*(1-smooth((lake-.88)/.45))
    # Author the two gorge openings beneath the independent bridge decks.
    # Endpoint pads below restore the level abutments; the rest is original
    # valley terrain and no longer depends on a nearby ground road's height.
    for lo,hi,cy,deck in [(960,1240,1370,36),(980,1200,570,40)]:
        distance=np.maximum(np.maximum(lo-x,x-hi),np.abs(y-cy)-8)
        weight=1-smooth(distance/8)
        h=np.minimum(h,h*(1-weight)+(deck-3)*weight)
    return h

def compose(w):
    w.base=terrain;w.doc['theme']='rural'
    w.doc['environment'].update(concept='jungle',settlement='wilderness',ground_color=[70,101,65],start_minutes=880)
    w.spawn=dict(x_cm=31000,y_cm=130000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(250,1300);B=(510,1300);C=(755,1360);D=(960,1370);E=(1240,1370)
    F=(1450,1280);G=(1480,950);H=(1420,680);I=(1200,570);J=(980,570)
    K=(820,500);L=(565,420);M=(360,600);N=(265,930);P=(710,840);Q=(680,1040);R=(840,1190)
    w.path('arrival-road',[A,B],10,level=32)
    w.path('ranger-lane',[B,(624,1307),C],7,level=lambda x,y:32+2*float(smooth((x-510)/245)))
    w.path('south-gorge-approach',[C,(840,1370),(910,1370),D],7.5,level=lambda x,y:34+2*float(smooth((x-755)/145)))
    w.path('south-gorge-bridge',[D,E],7.5,kind='bridge',level=36)
    w.path('east-gorge-approach',[E,(1280,1370),(1380,1340),F],7.5,level=lambda x,y:36+6*float(smooth((x-1280)/170)))
    w.path('cedar-valley',[F,(1500,1170),(1525,1055),G],7,level=lambda x,y:42+8*float(smooth((1280-y)/330)))
    w.path('granite-bend',[G,(1510,848),(1480,755),H],7,level=lambda x,y:50+8*float(smooth((950-y)/270)))
    w.path('north-gorge-approach',[H,(1357,610),(1290,570),(1250,570),I],7.5,
        level=lambda x,y:40+18*float(smooth((x-1250)/190)))
    w.path('north-gorge-bridge',[I,J],7.5,kind='bridge',level=40)
    w.path('beech-crest',[J,(950,570),(900,547),K],7.5,level=lambda x,y:40+4*float(smooth((950-x)/130)))
    w.path('upper-canopy',[K,(733,437),(652,415),L],7,level=lambda x,y:44+14*float(smooth((820-x)/255)))
    w.path('old-growth-bend',[L,(475,449),(394,507),M],7,level=lambda x,y:48+10*float(smooth((x-360)/205)))
    w.path('western-descent',[M,(279,708),(239,820),N],7,level=lambda x,y:34+14*float(smooth((930-y)/330)))
    w.path('ranger-return',[N,(248,1065),(247,1190),A],7,level=lambda x,y:32+2*float(smooth((1300-y)/370)))
    w.path('fern-hollow',[K,(759,634),(699,730),P],6.5,level=lambda x,y:36+8*float(smooth((840-y)/340)))
    w.path('creekside-track',[P,(701,946),Q],6.5,level=lambda x,y:31+5*float(smooth((1040-y)/200)))
    w.path('ranger-shortcut',[Q,(600,1140),(547,1230),B],6.5,level=lambda x,y:31+float(smooth((y-1040)/260)))
    w.path('camp-inlet',[Q,(762,1095),(817,1140),R],6,level=lambda x,y:31+float(smooth((y-1040)/150)))
    w.path('camp-return',[R,(830,1273),(791,1328),C],6,level=lambda x,y:32+2*float(smooth((y-1190)/170)))
    for x,y,z in [(*D,36),(*E,36),(*I,40),(*J,40)]:w.pads.append((x,y,10,10,z))
    river=LineString([(float(river_x(y)),y) for y in range(0,1761,16)]).buffer(8,cap_style=2)
    lake=affinity.scale(Point(1110,1115).buffer(1,quad_segs=32),120,110)
    w.water_body('cedar-river-and-lake',river.union(lake),20)
    for name,y,xs,z in [('south',1370,(1010,1070,1130,1190),11),('north',570,(1020,1075,1130,1180),15)]:
        for i,x in enumerate(xs):w.place(name+'-pier-'+str(i),'forest-pier',x,y,90,z,solid=False)
    w.places=['Ranger Station','Cedar Valley','Granite Bend','Old-growth Ridge',
        'Fern Hollow','Lakeside Camp','South Gorge Bridge','North River Crossing']
    # A station yard and three cabins have real service access to the arrival road.
    clearings=[]
    for i,(x,y,yaw) in enumerate([(420,1268,180),(376,1268,180),(854,1151,0)]):
        z=32
        w.pads.append((x,y,21,18,z));w.place('ranger-building-'+str(i),'ranger-lodge',x,y,yaw,z,True)
        yard=box(x-19,y-16,x+19,y+18);clearings.append(yard.buffer(8));w.paint('station-yard-'+str(i),yard,'gravel')
        target=(x,1300) if i<2 else (833,1153)
        w.paint('station-drive-'+str(i),LineString([(x,y),target]).buffer(3),'gravel')
        w.place('station-car-'+str(i),'parked-car',x+13,y+11,yaw,z)
        w.place('station-bin-'+str(i),'bin',x-11,y+8,level=z)
    camp=Polygon([(851,1195),(938,1182),(953,1248),(899,1271),(850,1249)])
    clearings.append(camp.buffer(7));w.paint('camp-ground',camp,'dirt')
    w.pads.append((902,1223,42,33,32))
    w.paint('camp-access',LineString([(836,1220),(895,1220)]).buffer(2.8),'gravel')
    for i,(x,y,a) in enumerate([(873,1203,20),(901,1200,-25),(932,1210,80),(931,1240,120),(894,1250,180)]):
        w.place('camp-tent-'+str(i),'camp-tent',x,y,a,32,True)
        w.place('camp-bench-'+str(i),'bench',x+6,y+5,a,32)
    w.place('camp-shelter','picnic-shelter',885,1225,90,32,True)
    w.place('camp-table','table',916,1224,0,32)
    # A gravel lake walk has rocks, reeds and a seated outlook; it is scenery,
    # not a fourth race course or simulated pedestrian system.
    w.paint('lake-walk',LineString([(938,1220),(973,1190),(982,1140),(974,1080)]).buffer(1.4),'gravel')
    for i,(x,y) in enumerate([(977,1184),(980,1151),(976,1090)]):
        w.place('lake-bench-'+str(i),'bench',x-3,y,90)
        w.place('lake-rock-'+str(i),'rock-'+str(i),x+2,y+6,solid=False)
    occupied=unary_union([a for _,a in w.obstacles]).buffer(4)
    exclusion=w.road_area(5).union(unary_union(w.water).buffer(8)).union(occupied).union(unary_union(clearings))
    # Different age/species bands are authored explicitly. Randomness only
    # jitters the fill inside these habitats, never the roads or facilities.
    habitats=[('old-growth',box(24,28,850,970),16,['beech','cedar-2','cedar-0']),
        ('south-woods',box(28,982,985,1730),16.5,['cedar-0','beech','cedar-1']),
        ('east-cedars',box(1190,25,1730,1715),15.5,['cedar-2','cedar-0','cedar-1']),
        ('river-groves',box(865,25,1180,1715),18,['beech','tree-2','cedar-1'])]
    for label,area,spacing,kinds in habitats:
        rng=random.Random(7719+sum(map(ord,label)));a,b,c,d=area.bounds;index=0
        for y in np.arange(b+7,d-6,spacing):
            for x in np.arange(a+7,c-6,spacing):
                x=float(x+rng.uniform(-4,4));ty=float(y+rng.uniform(-4,4));p=Point(x,ty)
                if not area.contains(p) or exclusion.contains(p):continue
                w.place(label+'-canopy-'+str(index),rng.choice(kinds),x,ty,rng.randrange(360),solid=False)
                if index%3==0:w.place(label+'-young-'+str(index),'sapling-'+str(index%2),x+4,ty+3,rng.randrange(360),solid=False)
                if index%2==0:w.place(label+'-understory-'+str(index),'shrub',x-4,ty+3,rng.randrange(360),solid=False)
                if index%4==0:w.place(label+'-ferns-'+str(index),'fern-patch',x+4,ty-4,rng.randrange(360),solid=False)
                if index%47==0:w.place(label+'-fallen-'+str(index),'fallen-cedar',x-3,ty-4,rng.randrange(360),solid=False)
                index+=1
    # Road edges stay richly layered without allowing solid trunks into driving.
    for name in ('fern-hollow','creekside-track','old-growth-bend','cedar-valley','granite-bend'):
        line=w.routes[name]
        for i,s in enumerate(np.arange(18,line.length-16,10.5)):
            p=line.interpolate(s);q=line.interpolate(s+.3);dx=q.x-p.x;dy=q.y-p.y;length=math.hypot(dx,dy)
            side=-1 if i%2 else 1
            for band,kind,distance in [('fern','fern-patch',6.5),('young','sapling-'+str(i%2),10.5),('bush','shrub',8.4)]:
                x=p.x-dy/length*side*distance;y=p.y+dx/length*side*distance
                if unary_union(w.water).buffer(3).contains(Point(x,y)):continue
                w.place(name+'-'+band+'-'+str(i),kind,x,y,i*47,solid=False)
    for i,y in enumerate(range(58,1710,22)):
        x=float(river_x(y));side=-1 if i%2 else 1
        for offset,kind in [(9,'reeds'),(15,'shrub'),(25,'sapling-0')]:
            if lake.buffer(5).contains(Point(x+side*offset,y)):continue
            w.place('river-edge-'+str(i)+'-'+str(offset),kind,x+side*offset,y,i*37,level=19.6 if offset==9 else None,solid=False)
        if i%4==0 and not lake.buffer(4).contains(Point(x-side*12,y+4)):
            w.place('river-boulder-'+str(i),'rock-'+str(i%3),x-side*12,y+4,i*29,solid=False)
    # Exposed outcrops mark the granite turn and crest, with scattered scree.
    for cluster,(x,y) in enumerate([(1485,788),(1515,914),(730,511),(481,471),(1550,1010)]):
        for i,(dx,dy) in enumerate([(-6,-3),(0,0),(4,6),(9,-4),(-2,9)]):
            w.place('outcrop-'+str(cluster)+'-'+str(i),'rock-'+str(i%3),x+dx,y+dy,i*69,solid=False)
    routes=[w.course('intro','Ranger and Fern Hollow',['arrival-road','-ranger-shortcut','-creekside-track','-fern-hollow','upper-canopy','old-growth-bend','western-descent','ranger-return']),
        w.course('tour','Cedar River Tour',['arrival-road','ranger-lane','south-gorge-approach','south-gorge-bridge','east-gorge-approach','cedar-valley','granite-bend','north-gorge-approach','north-gorge-bridge','beech-crest','upper-canopy','old-growth-bend','western-descent','ranger-return']),
        w.course('technical','Lakeside Forest Loop',['arrival-road','ranger-lane','-camp-return','-camp-inlet','-creekside-track','-fern-hollow','-beech-crest','-north-gorge-bridge','-north-gorge-approach','-granite-bend','-cedar-valley','-east-gorge-approach','-south-gorge-bridge','-south-gorge-approach'])]
    def view(name,eye,target):
        return dict(name=name,position_m=[eye[0],float(w.height(*eye))+1.7,eye[1]],target_m=[target[0],float(w.height(*target))+2,target[1]],quality=2,view_distance_m=384)
    line=w.routes['fern-hollow'];eye=line.interpolate(line.length-40);target=line.interpolate(line.length-120)
    views=[view('forest-road',(eye.x,eye.y),(target.x,target.y)),view('ranger-road',(393,1300),(480,1268)),
        view('camp-road',(839,1208),(908,1227)),
        dict(name='distant',position_m=[1010,37.7,1370],target_m=[1085,23,1160],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[1020,230,1245],target_m=[1020,22,1200],projection='orthogonal',size_m=280,quality=2,view_distance_m=384)]
    return dict(id='deep-forest',name='깊은 숲',en='Deep Forest',theme='deep-forest',size=list(w.size),surface='asphalt',
        description='Layered cedar and beech woods open onto a river gorge, quiet lake, ranger station and sheltered camp.',
        districts=['old-growth forest','cedar valley','river groves','fern hollow','ranger station','lakeside camp'],landmarks=w.places,
        routes=routes,start=routes[0]['start'],review_views=views,preview_center_m=[904,32,1220],
        ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='forest-road',signature_preview='camp-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
