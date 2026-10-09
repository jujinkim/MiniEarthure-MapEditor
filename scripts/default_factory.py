"""Machine Factory: connected process yards and a legible industrial road network."""
import math,random
import numpy as np
from shapely.geometry import Point,LineString,Polygon,box
from shapely.ops import unary_union
from default_worlds import smooth

def terrain(x,y):
    x=np.asarray(x);y=np.asarray(y);h=12+2*np.sin(x/220)*np.cos(y/200)
    for cx,cy,rise,sx,sy in [(120,180,26,230,230),(1260,160,25,240,230),(170,1280,16,200,180)]:h=h+rise*np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2)
    canal=(1-smooth((np.abs(x-1280)-4)/13))*smooth((y-230)/35)*smooth((1250-y)/35)
    return h*(1-canal)+4*(canal)

def compose(w):
    w.base=terrain;w.doc['theme']='urban'
    w.doc['environment'].update(concept='metropolis',architecture='modern',settlement='urban',ground_color=[109,122,106],start_minutes=870)
    w.spawn=dict(x_cm=26000,y_cm=105000,surface_id='arrival-road',heading_radians=-math.pi/2)
    A=(200,1050);B=(450,1050);C=(750,1050);D=(1100,1050);E=(1100,750);F=(1100,430);G=(750,430);H=(450,430);I=(230,650);J=(230,850);M=(450,750);N=(750,750)
    for name,points,width in [('arrival-road',[A,B],12),('admin-boulevard',[B,C],11),('shipping-way',[C,D],11),
        ('east-loading-road',[D,E],10),('utility-road',[E,F],10),('north-process-road',[F,G],10),('north-production-road',[G,H],10),
        ('woodland-perimeter',[H,(312,477),I],8),('west-factory-road',[I,J],9),('gate-return',[J,(204,950),A],9),
        ('maintenance-street',[B,M],10),('production-street',[M,H],10),('assembly-cross-street',[M,N],10),
        ('loading-cross-street',[N,E],11),('central-production-road',[N,G],10),('dispatch-street',[C,N],10),
        ('admin-west-link',[J,(340,831),M],8)]:w.path(name,points,width,1.4 if width>=10 else 0,level=12)
    for cx,cy,rx,ry in [(599,590,135,138),(923,590,155,138),(599,900,135,135),(923,900,155,135),(344,949,74,63)]:w.pads.append((cx,cy,rx,ry,12))
    lots=[('production',box(470,451,730,729)),('process',box(771,451,1078,729)),('maintenance',box(472,772,730,1027)),('shipping',box(771,772,1078,1027)),('admin',box(270,887,425,1015))]
    for name,area in lots:w.paint(name+'-hardstanding',area,'concrete')
    for name,points in [('production-gate',[(450,605),(490,605)]),('production-north-gate',[(600,430),(600,483)]),
            ('process-gate',[(750,582),(798,582)]),('power-gate',[(1100,690),(1050,690)]),
            ('maintenance-gate',[(450,808),(500,808)]),('shipping-gate',[(1100,875),(1050,875)])]:
        w.paint(name,LineString(points).buffer(5.5),'concrete')
    w.places=['Gate and Administration','Production Halls','Process Tank Farm','Boiler Court',
        'Electrical Substation','Maintenance Yard','Shipping and Crane Yard','Drainage Greenbelt']
    for i,(x,y,a) in enumerate([(522,500,0),(650,500,0),(524,649,180),(656,649,180),(530,934,0),(653,938,0)]):
        w.place('production-hall-'+str(i),'production-'+str(i%3),x,y,a,12,True)
        for k in (-1,1):w.place('hall-bin-'+str(i)+'-'+str(k),'bin',x+k*24,y-28 if a==0 else y+28,level=12)
        w.place('hall-service-'+str(i),'compressor',x+45,y+13,a,12)
        w.paint('hall-access-'+str(i),LineString([(x,y),(x,575 if y<730 else 830)]).buffer(5),'concrete')
    # Continuous rack runs connect the production blocks' service backs.
    for label,y,xs in [('production',577,range(486,727,24)),('process',625,range(796,1061,24)),('maintenance',839,range(484,727,24))]:
        for i,x in enumerate(xs):w.place(label+'-rack-'+str(i),'pipe-rack',x,y,0,12)
    for row,y in enumerate((490,546)):
        for col,x in enumerate((807,851,895)):
            w.place('tank-'+str(row)+'-'+str(col),'process-tank-'+str((row+col)%3),x,y,level=12)
    for i,x in enumerate((807,851,895)):
        w.place('tank-link-'+str(i),'tank-link',x,518.5,level=12)
        w.place('process-feed-'+str(i),'process-feed',x,591,level=12)
    for i,x in enumerate((955,1030)):
        w.place('boiler-'+str(i),'boiler-bank',x,524,level=12)
        w.place('stack-'+str(i),'factory-stack',x+22,500,level=12)
        w.place('process-compressor-'+str(i),'compressor',x,583,level=12)
    for row,y in enumerate((676,704)):
        for col,x in enumerate((825,862,899,936,973,1010)):
            w.place('electrical-'+str(row)+'-'+str(col),'transformer',x,y,level=12)
    for row,y in enumerate((676,704)):
        for col,x in enumerate((843.5,880.5,917.5,954.5,991.5)):
            w.place('electrical-bus-'+str(row)+'-'+str(col),'electrical-busbar',x,y,level=12)
    # Fence openings lead to internal aisles; no pipe is placed across a road.
    for name,y,xs in [('power-fence',648,range(786,1070,7)),('north-fence',457,range(782,1070,7))]:
        for i,x in enumerate(xs):
            if 990<x<1019:continue
            w.place(name+'-'+str(i),'port-fence',x,y,level=12)
    for i,(x,y,a) in enumerate([(823,812,180),(949,814,180)]):
        w.place('shipping-hall-'+str(i),'warehouse-'+str(i),x,y,a,12,True)
    w.place('shipping-crane','dock-crane',1013,923,0,12)
    for row,y in enumerate((915,971)):
        for col,x in enumerate((802,832,862,892)):
            w.place('shipping-container-'+str(row)+'-'+str(col),'container-stack-'+str((row+col)%4),x,y,90,12)
    for i,(x,y,a) in enumerate([(963,978,90),(1039,977,90),(800,864,90),(958,868,90),(590,816,90),(694,802,0)]):w.place('truck-'+str(i),'parked-truck',x,y,a,12)
    for i,(x,y) in enumerate([(321,963),(384,959)]):
        w.place('administration-'+str(i),'factory-admin',x,y,0,12,True)
        w.paint('admin-access-'+str(i),LineString([(x,y),(x,1050)]).buffer(3.5),'concrete')
        for n in range(4):w.place('staff-car-'+str(i)+'-'+str(n),'parked-car',x-15+n*9,y+28,0,12)
    for i,(x,y) in enumerate([(380,880),(487,786),(777,1011),(1070,793),(718,467),(473,711)]):w.place('yard-lamp-'+str(i),'port-lamp',x,y,level=12)
    for i,x in enumerate(range(294,418,7)):
        if 315<x<333 or 375<x<395:continue
        w.place('admin-fence-'+str(i),'port-fence',x,1017,level=12)
    w.water_body('stormwater-channel',box(1276,275,1284,1208),5.7)
    for i,y in enumerate(range(300,1200,24)):w.place('channel-reed-'+str(i),'reeds',1287,y,level=5.2,solid=False)
    exclusion=w.road_area(15).union(unary_union([a for _,a in lots]).buffer(17)).union(unary_union(w.water).buffer(14))
    rng=random.Random(8610)
    for row,y in enumerate(range(35,1410,22)):
        for col,x in enumerate(range(34,1410,22)):
            x=x+rng.uniform(-5,5);y1=y+rng.uniform(-5,5)
            if exclusion.contains(Point(x,y1)):continue
            # Inner unbuilt space is maintained grass and shrubs; the outside
            # becomes a continuous greenbelt against the distant hills.
            outer=x<180 or x>1170 or y1<360 or y1>1150
            kind='tree-'+str((row+col)%5) if outer else 'shrub'
            w.place('greenbelt-'+str(row)+'-'+str(col),kind,x,y1,rng.randrange(360),solid=False)
    routes=[w.course('intro','Production and Service',['arrival-road','maintenance-street','assembly-cross-street','-dispatch-street','-admin-boulevard']),
        w.course('tour','Factory Perimeter',['arrival-road','admin-boulevard','shipping-way','east-loading-road','utility-road','north-process-road','north-production-road','woodland-perimeter','west-factory-road','gate-return']),
        w.course('technical','Process and Freight',['arrival-road','maintenance-street','production-street','-north-production-road','-central-production-road','loading-cross-street','-east-loading-road','-shipping-way','dispatch-street','-assembly-cross-street','-admin-west-link','gate-return'])]
    def view(name,eye,target):return dict(name=name,position_m=[eye[0],13.7,eye[1]],target_m=[target[0],16,target[1]],quality=2,view_distance_m=384)
    views=[view('production-road',(590,750),(630,630)),view('process-road',(930,430),(960,520)),view('shipping-road',(1100,965),(996,924)),
        dict(name='distant',position_m=[720,38,1090],target_m=[950,29,820],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[872,235,645],target_m=[872,12,585],projection='orthogonal',size_m=280,quality=2,view_distance_m=384)]
    return dict(id='machine-factory',name='기계 공장',en='Machine Factory',theme='machine-factory',size=list(w.size),surface='asphalt',
        description='Production halls, connected pipe racks and process tanks lead through electrical yards to warehouses, cranes and freight loading.',
        districts=['production','process','substation','maintenance','shipping','administration'],landmarks=w.places,routes=routes,start=routes[0]['start'],review_views=views,
        preview_center_m=[872,12,585],ground_position_m=views[0]['position_m'],ground_target_m=views[0]['target_m'],
        menu_views=dict(preview='overview',ground_preview='production-road',signature_preview='process-road'),
        acceptance='Authored using the approved Village art direction. Human driving and device acceptance remain unverified.')
