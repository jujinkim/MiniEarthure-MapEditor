"""Snow Mountain: a wooded valley, mountain lodges, snowline and rock ridges, MIT."""
import math,random
import numpy as np
from shapely.geometry import Point,Polygon,LineString,box
from shapely.ops import unary_union
from default_worlds import smooth

def roadbed(x,y):return 60+90*smooth((1700-np.asarray(y))/1300)
def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y)
    h=roadbed(x,y)+4*np.sin(x/150)*np.sin(y/170)
    h=h+135*np.exp(-((x-65)/180)**2)+170*np.exp(-((x-1515)/185)**2)
    h=h+140*np.exp(-((x-840)/430)**2-((y-100)/180)**2)
    h=h+32*np.exp(-((x-795)/190)**2-((y-1100)/310)**2)
    return h

def compose(w):
    w.base=terrain;w.doc['theme']='rural'
    w.doc['environment'].update(concept='polar',architecture='timber',climate='polar',settlement='sparse',ground_color=[202,214,214],start_minutes=800)
    w.spawn=dict(x_cm=35000,y_cm=172000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(290,1720);B=(550,1720);C=(820,1710);D=(1060,1470);E=(1190,1170);F=(1180,850)
    G=(1040,520);H=(630,480);I=(460,755);J=(510,1050);K=(430,1360);L=(310,1500)
    M=(700,1330);N=(910,1110)
    w.path('arrival-road',[A,B],10,level=60)
    for name,points in [('lodge-lane',[B,(690,1730),C]),('eastern-ascent',[C,(990,1630),D]),
        ('timberline-road',[D,(1150,1340),E]),('rock-cirque',[E,(1230,1010),F]),
        ('snow-wall-climb',[F,(1140,700),G]),('summit-ridge',[G,(835,474),H]),
        ('western-switchback',[H,(515,540),(412,605),I]),('fir-slope',[I,(505,893),J]),
        ('valley-descent',[J,(462,1210),K]),('lower-fir-road',[K,(352,1400),L]),
        ('lodge-return',[L,(289,1610),A]),('valley-link',[K,(570,1333),M]),
        ('central-climb',[M,(806,1212),N]),('cirque-link',[N,(1040,1139),E]),
        ('lodge-shortcut',[M,(654,1500),(599,1622),B]),
        ('snowline-link',[J,(681,1017),(797,1048),N])]:
        w.path(name,points,7.5,level=lambda x,y:float(roadbed(x,y)))
    w.places=['Alpine Lodge Village','Lower Fir Valley','Frozen Tarn','Timberline Bend',
        'Snow Wall','Summit Lookout','Rock Cirque','Western Switchback']
    yards=[]
    for i,(x,y,a,kind) in enumerate([(605,1682,180,0),(659,1686,180,1),(712,1690,180,1),
            (548,1770,0,1),(596,1780,0,0),(674,1786,0,1)]):
        z=60;w.pads.append((x,y,20,18,z));w.place('lodge-'+str(i),'alpine-lodge-'+str(kind),x,y,a,z,True)
        yard=box(x-17,y-17,x+17,y+17);yards.append(yard.buffer(8));w.paint('lodge-yard-'+str(i),yard,'gravel')
        roadpoint=w.routes['lodge-lane'].interpolate(w.routes['lodge-lane'].project(Point(x,y)))
        w.paint('lodge-access-'+str(i),LineString([(x,y),(roadpoint.x,roadpoint.y)]).buffer(2.4),'gravel')
        w.place('lodge-car-'+str(i),'parked-car',x+13,y,a,z)
        w.place('lodge-bin-'+str(i),'bin',x-11,y+10,level=z)
    # A solid ice sheet in a shallow sculpted basin is a frozen watercourse,
    # not liquid water wearing an ice texture; its physical top is explicit.
    w.pads.append((946,1280,48,34,92.6));w.place('frozen-tarn','frozen-lake',946,1280,0,93)
    tarn=Point(946,1280).buffer(1);from shapely import affinity
    tarn=affinity.scale(tarn,56,40);yards.append(tarn.buffer(26))
    for i,a in enumerate(np.arange(0,math.tau,.42)):
        x=946+53*math.cos(a);y=1280+38*math.sin(a)
        w.place('tarn-shore-'+str(i),'alpine-crag-2',x,y,i*27,solid=False)
    line=w.routes['summit-ridge'];p=line.interpolate(line.length*.53);q=line.interpolate(line.length*.53+1)
    yaw=math.degrees(math.atan2(q.x-p.x,-(q.y-p.y)))
    dx=q.x-p.x;dy=q.y-p.y;length=math.hypot(dx,dy);sx=p.x-dy/length*26;sy=p.y+dx/length*26
    w.place('summit-shelter','snow-gallery',sx,sy,yaw,float(w.height(p.x,p.y)),True)
    w.paint('summit-lookout-access',LineString([(p.x,p.y),(sx,sy)]).buffer(2.8),'gravel')
    # Rails and snowbanks follow the actual road curve, with open junctions.
    for name in ['timberline-road','rock-cirque','snow-wall-climb','western-switchback','eastern-ascent']:
        line=w.routes[name]
        for i,s in enumerate(np.arange(30,line.length-25,23)):
            p=line.interpolate(s);q=line.interpolate(s+.5);dx=q.x-p.x;dy=q.y-p.y;length=math.hypot(dx,dy)
            yaw=math.degrees(math.atan2(dy,dx))
            for side in (-1,1):
                x=p.x-dy/length*side*6.1;y=p.y+dx/length*side*6.1
                w.place(name+'-rail-'+str(side)+'-'+str(i),'alpine-rail',x,y,yaw,float(w.height(p.x,p.y)),solid=False)
                if i%2==0:w.place(name+'-drift-'+str(side)+'-'+str(i),'snowbank',p.x-dy/length*side*9,y=p.y+dx/length*side*9,yaw=yaw,solid=False)
    exclusion=w.road_area(12).union(unary_union(yards))
    rng=random.Random(9153)
    # Forest thins deliberately by altitude; the upper cirque is rock and snow.
    for row,y in enumerate(range(550,2030,18)):
        for col,x in enumerate(range(190,1400,18)):
            x=x+rng.uniform(-4,4);y1=y+rng.uniform(-4,4)
            density=float(smooth((y1-600)/500))
            if rng.random()>density or exclusion.contains(Point(x,y1)):continue
            w.place('valley-fir-'+str(row)+'-'+str(col),'snow-fir-'+str(rng.randrange(3)),x,y1,rng.randrange(360),solid=False)
            if (row+col)%9==0:w.place('valley-stone-'+str(row)+'-'+str(col),'alpine-crag-2',x+6,y1+5,rng.randrange(360),solid=False)
    for label,cx,cy,rx,ry in [('west-ridge',208,750,45,610),('east-ridge',1380,940,60,760),('north-ridge',820,285,470,48),('central-rocks',800,980,55,155)]:
        for i in range(44 if label!='central-rocks' else 15):
            x=rng.uniform(cx-rx,cx+rx);y=rng.uniform(cy-ry,cy+ry)
            if exclusion.contains(Point(x,y)):continue
            w.place(label+'-'+str(i),'alpine-crag-'+str(i%3),x,y,rng.randrange(360),solid=False)
    outer=['arrival-road','lodge-lane','eastern-ascent','timberline-road','rock-cirque','snow-wall-climb','summit-ridge','western-switchback','fir-slope','valley-descent','lower-fir-road','lodge-return']
    routes=[w.course('intro','Alpine Lodge Circuit',['arrival-road','-lodge-shortcut','-valley-link','lower-fir-road','lodge-return']),
        w.course('tour','Snowline Summit Tour',outer),
        w.course('technical','Frozen Tarn Climb',['arrival-road','-lodge-shortcut','central-climb','cirque-link','rock-cirque','snow-wall-climb','summit-ridge','western-switchback','fir-slope','snowline-link','-central-climb','-valley-link','lower-fir-road','lodge-return'])]
    def view(name,road,s,look=85):
        line=w.routes[road];a=line.interpolate(s);b=line.interpolate(s+look)
        return dict(name=name,position_m=[a.x,float(w.height(a.x,a.y))+1.7,a.y],target_m=[b.x,float(w.height(b.x,b.y))+2,b.y],quality=2,view_distance_m=384)
    views=[view('valley-road','lower-fir-road',40),view('lodge-road','lodge-lane',42),view('snow-road','summit-ridge',100),
        dict(name='distant',position_m=[917,float(w.height(917,1228))+1.7,1228],target_m=[946,93.4,1290],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[643,260,1770],target_m=[643,60,1710],projection='orthogonal',size_m=280,quality=2,view_distance_m=384)]
    return dict(id='snow-mountain',name='설산',en='Snow Mountain',theme='snow-mountain',size=list(w.size),surface='asphalt',
        description='Alpine lodges and fir woods climb past a frozen tarn to exposed crags, snow walls and a sheltered summit lookout.',
        districts=['lodge village','fir valley','snowline','rock cirque','summit ridge'],landmarks=w.places,routes=routes,start=routes[0]['start'],review_views=views,
        preview_center_m=[643,60,1710],ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='lodge-road',signature_preview='snow-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
