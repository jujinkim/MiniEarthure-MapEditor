"""Red Canyon: eroded wall corridors, a dry wash and a working quarry, MIT."""
import math
import random
import numpy as np
from shapely.geometry import LineString,Point,Polygon,box
from shapely.ops import unary_union
from default_worlds import smooth,curve

def wash_y(x):return 625+48*np.sin(np.asarray(x)/300)+20*np.sin(np.asarray(x)/117)

def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y);distance=np.abs(y-wash_y(x))
    base=16+2*np.sin(x/240)
    wall=83*smooth((distance-80)/90)+16*smooth((distance-165)/75)
    return base+wall+9*np.sin(x/96)*smooth((distance-105)/70)+5*np.cos(y/80)*smooth((distance-90)/110)

def compose(w):
    w.base=terrain;w.doc['theme']='rural'
    w.doc['environment'].update(concept='desert',climate='arid',settlement='sparse',ground_color=[167,115,76],start_minutes=930)
    w.spawn=dict(x_cm=24000,y_cm=97000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(180,970);B=(440,970);C=(670,900);D=(670,780);E=(670,435)
    F=(1100,400);G=(1570,430);H=(1920,470);I=(1920,815);J=(1510,875);K=(1100,900)
    Q=(1100,710);R=(1550,690)
    def ramp(name,points,a,b,width=7.5,surface='asphalt'):
        line=LineString(curve(points))
        return w.path(name,points,width,level=lambda x,y:a+(b-a)*line.project(Point(x,y))/line.length,surface=surface)
    w.path('arrival-road',[A,B],10,level=70)
    ramp('quarry-gate',[B,(550,947),C],70,60)
    w.path('west-bridge-apron',[C,(670,840),(670,805),D],8,level=60)
    w.path('west-canyon-bridge',[D,E],8,kind='bridge',level=60)
    w.path('north-bridge-apron',[E,(670,410),(680,380),(740,360)],8,level=60)
    ramp('red-wall-road',[(740,360),(890,373),F],60,66)
    ramp('layered-cliff-road',[F,(1280,413),(1450,411),G],66,66)
    ramp('east-overlook',[G,(1730,400),(1850,422),(1920,440)],66,60)
    w.path('east-bridge-apron',[(1920,440),H],8,level=60)
    w.path('east-canyon-bridge',[H,I],8,kind='bridge',level=60)
    w.path('south-bridge-apron',[I,(1920,845),(1900,876),(1850,895)],8,level=60)
    ramp('south-mesa-road',[(1850,895),(1680,881),J],60,72)
    ramp('quarry-ridge',[J,(1310,919),K],72,70)
    ramp('quarry-return',[K,(880,950),C],70,60)
    ramp('western-rim',[C,(539,1080),(365,1100),(227,1060),A],60,70)
    ramp('wash-descent',[B,(627,933),(810,812),(968,746),Q],70,22,7)
    ramp('dry-river-road',[Q,(1270,690),(1410,705),R],22,22,7)
    # A deliberate switchback gives the eastern climb enough length for 12%.
    ramp('wash-climb',[R,(1650,601),(1770,640),(1840,743),(1810,805),(1780,817),(1775,850),(1850,895)],22,60,7)
    # Broad excavated shoulders follow each designed grade. The narrow common
    # road cut then adds only its final verge; it must not form a 50 m trench.
    ground_roads=[r for r in w.doc['roads'] if r['kind']=='ground']
    def sculpted(x,y):
        x=np.asarray(x);y=np.asarray(y);h=terrain(x,y)
        best=np.full(np.broadcast_shapes(x.shape,y.shape),np.inf);z=h.copy()
        for r in ground_roads:
            for a,b in zip(r['points'],r['points'][1:]):
                ax,az,ay=np.array(a)/100;bx,bz,by=np.array(b)/100
                dx=bx-ax;dy=by-ay;t=np.clip(((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy),0,1)
                distance=np.hypot(x-ax-t*dx,y-ay-t*dy);take=distance<best
                best=np.minimum(best,distance);z=np.where(take,az+t*(bz-az),z)
        weight=1-smooth((best-15)/65);h=h*(1-weight)+z*weight
        for cx,lo,hi in [(670,435,780),(1920,470,815)]:
            weight=(1-smooth((np.abs(x-cx)-15)/45))*(1-smooth((np.maximum(lo+22-y,y-hi+22))/22))
            h=h*(1-weight)+np.minimum(h,45)*weight
        distance=np.maximum(np.abs(x-1080)-142,np.abs(y-1050)-60)
        weight=1-smooth(distance/50);h=h*(1-weight)+73*weight
        return h
    w.base=sculpted
    for x,y in (D,E,H,I):w.pads.append((x,y,11,11,60))
    for label,x in [('west',670),('east',1920)]:
        for i,y in enumerate((510,575,640,705)):
            w.place(label+'-pier-'+str(i),'canyon-pier',x,y,0,15,solid=False)
    w.places=['Red Wall Corridor','Layered Cliffs','West Canyon Bridge','East Overlook',
        'Dry River Switchback','Ochre Quarry','Mesa Service Yard']
    wash=LineString([(x,float(wash_y(x))) for x in range(0,2401,15)])
    w.paint('dry-wash',wash.buffer(13,cap_style=2),'gravel')
    w.paint('wash-sand',wash.buffer(31,cap_style=2),'dirt')
    quarry=Polygon([(900,975),(1090,960),(1230,1000),(1270,1120),(940,1140)])
    w.pads.append((1080,1050,140,58,73));w.paint('quarry-floor',quarry,'gravel')
    w.paint('quarry-access',LineString([(1080,1050),K]).buffer(5),'gravel')
    for i,(x,y,yaw) in enumerate([(980,1030,0),(1120,1060,80)]):
        w.place('crusher-'+str(i),'quarry-crusher',x,y,yaw,73,True)
        w.place('conveyor-'+str(i),'quarry-conveyor',x+19,y+5,yaw,73)
        w.place('loader-'+str(i),'quarry-loader',x+36,y-9,35+i*60,73)
    w.place('quarry-office','quarry-office',1040,997,0,73,True)
    w.place('quarry-car','parked-car',1064,996,80,73)
    for i,(x,y) in enumerate([(960,1090),(1000,1110),(1180,1090),(1210,1070)]):
        w.place('stockpile-'+str(i),'canyon-stockpile',x,y,i*73,73,solid=False)
    w.paint('overlook-bay',box(1686,432,1738,451),'gravel')
    for i,x in enumerate(range(1693,1734,12)):w.place('overlook-bench-'+str(i),'bench',x,438,180)
    w.place('overlook-car','parked-car',1727,430,95)
    # Terrain forms the continuous walls; placed eroded fins define different
    # silhouettes and strata without using a fence of identical boxed cliffs.
    rng=random.Random(1947);exclusion=w.road_area(13).union(quarry.buffer(18))
    for side in (-1,1):
        for i,x in enumerate(range(70,2340,27)):
            y=float(wash_y(x))+side*(148+13*math.sin(x/76))
            if exclusion.contains(Point(x,y)):continue
            w.place('wall-'+str(side)+'-'+str(i),'sandstone-'+str((i+int(side))%3),x,y,rng.uniform(-18,18),solid=False)
        for i,x in enumerate(range(48,2370,19)):
            y=float(wash_y(x))+side*rng.uniform(45,115)
            if exclusion.contains(Point(x,y)):continue
            w.place('talus-'+str(side)+'-'+str(i),'canyon-rubble',x,y,rng.randrange(360),solid=False)
    for row,y in enumerate(range(38,1170,22)):
        for col,x in enumerate(range(30,2370,23)):
            x=x+rng.uniform(-6,6);y1=y+rng.uniform(-6,6)
            if exclusion.contains(Point(x,y1)) or wash.distance(Point(x,y1))<20:continue
            kind='cactus' if (row+col)%13==0 else 'desert-scrub'
            w.place('arid-'+str(row)+'-'+str(col),kind,x,y1,rng.randrange(360),solid=False)
    outer=['arrival-road','quarry-gate','west-bridge-apron','west-canyon-bridge','north-bridge-apron','red-wall-road','layered-cliff-road','east-overlook','east-bridge-apron','east-canyon-bridge','south-bridge-apron','south-mesa-road','quarry-ridge','quarry-return','western-rim']
    routes=[w.course('intro','Quarry Rim',['arrival-road','quarry-gate','western-rim']),
        w.course('tour','Twin Canyon Bridges',outer),
        w.course('technical','Dry Wash Climb',['arrival-road','wash-descent','dry-river-road','wash-climb','south-mesa-road','quarry-ridge','quarry-return','western-rim'])]
    def road_view(name,road,s,look=90):
        line=w.routes[road];a=line.interpolate(s);b=line.interpolate(s+look)
        return dict(name=name,position_m=[a.x,float(w.height(a.x,a.y))+1.7,a.y],target_m=[b.x,float(w.height(b.x,b.y))+1.8,b.y],quality=2,view_distance_m=384)
    views=[road_view('canyon-road','red-wall-road',80),road_view('wash-road','dry-river-road',80),
        dict(name='quarry-road',position_m=[1090,74.7,1038],target_m=[980,80,1030],quality=2,view_distance_m=384),
        dict(name='distant',position_m=[670,61.7,630],target_m=[855,56,665],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[1040,270,1115],target_m=[1040,70,1060],projection='orthogonal',size_m=280,quality=2,view_distance_m=384)]
    return dict(id='red-canyon',name='붉은 협곡',en='Red Canyon',theme='red-canyon',size=list(w.size),surface='asphalt',
        description='Layered red cliffs frame a dry river road, twin gorge bridges, mesa overlooks and a working quarry.',
        districts=['red walls','dry wash','mesa rim','quarry'],landmarks=w.places,routes=routes,start=routes[0]['start'],review_views=views,
        preview_center_m=[1040,73,1060],ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='canyon-road',signature_preview='wash-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
