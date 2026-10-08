"""Village: explicit road/landscape composition in metres, original MIT.

Old market street -> orchard homes -> farm lanes -> river bridge -> wooded ridge.
Vegetation fills only the authored habitat polygons below; no generated city grid.
"""
import math
import random
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

def compose(w):
    from default_worlds import smooth
    A=(160,480);B=(400,480);C=(540,480);D=(650,480);E=(800,550)
    F=(940,640);G=(925,800);H=(720,815);I=(530,730);J=(400,610);K=(250,625);L=(175,560)
    N=(650,355);O=(650,245);P=(965,245);S=(965,320);Q=(390,365);R=(648,395)
    # The launch road is a true 240m straight, wider than all eight car footprints.
    w.path('arrival-road',[A,B],10,2,level=9)
    w.path('market-street',[B,C],10,2.2,level=9)
    w.path('east-high-street',[C,D],9,1.8,level=9)
    w.path('farm-approach',[D,(700,495),(754,515),E],7.5,level=9)
    w.path('mill-lane',[E,(868,576),(920,604),F],7,level=9)
    w.path('east-farm-lane',[F,(968,705),(958,758),G],7,level=lambda x,y:9+(y-640)*.012)
    w.path('harvest-road',[G,(850,829),(790,824),H],7,level=lambda x,y:10.92+(925-x)*.004)
    w.path('pasture-road',[H,(650,805),(594,777),I],7,level=lambda x,y:11.74-(720-x)*.012)
    w.path('orchard-road',[I,(500,679),(456,638),J],7,level=9.46)
    w.path('south-cottages',[J,(349,639),(298,642),K],6.5,1,level=9.46)
    w.path('meadow-bend',[K,(210,607),(185,582),L],7,level=9.46)
    w.path('west-gateway',[L,(162,523),A],7,level=9.46)
    w.path('orchard-homes',[B,(392,522),(394,567),J],6.5,1.6,level=9.25)
    w.path('garden-homes',[C,(552,535),(556,583),(555,645),I],6.5,1.2,level=9.3)
    bridge_level=lambda x,y:9+2*float(smooth((480-y)/100))
    w.path('bridge-approach',[D,(645,435),R],7.5,1.2,level=bridge_level)
    w.path('bridge-gate',[R,N],7.5,1.2,level=bridge_level)
    w.path('river-bridge',[N,O],7.5,kind='bridge',level=11)
    def woodland_level(x,y):
        # A deliberate broad crest follows the northern hillside, with level
        # bridge aprons at both ends and a maximum profile grade below 12%.
        return 11+15*float(smooth((x-665)/200))-6*float(smooth((x-865)/80))
    w.path('woodland-road',[O,(675,217),(725,190),(802,193),(875,194),(925,213),P],7,level=woodland_level)
    for x,y in (N,O):w.pads.append((x,y,10,10,11))
    w.path('east-river-bridge',[P,S],7,kind='bridge',level=20)
    for x,y in (P,S):w.pads.append((x,y,10,10,20))
    w.path('ridge-descent',[S,(993,410),(994,484),(980,568),F],7,
        level=lambda x,y:9+11*float(smooth((640-y)/300)))
    w.path('ridge-homes',[R,(713,390),(770,424),(792,485),E],6.5,1.2,
        level=lambda x,y:9+(bridge_level(*R)-9)*float(smooth((800-x)/152)))
    w.path('riverside-lane',[A,(152,424),(219,380),(300,362),Q],6.5,
        level=lambda x,y:9+max(0,480-y)*.004)
    w.path('green-lane',[Q,(452,380),(510,416),C],6.5,1.2,level=9.3)
    w.path('river-walk-access',[Q,(398,342),(401,323)],4,surface='gravel',
        level=lambda x,y:8+(y-323)/42*1.46,markings=False)
    w.places=['Market Street and Clock Hall','Orchard Cottages','Ridge Gardens',
        'Mill Farm','South Farm and Crops','River Meadow','Bridge and Woodland Ridge']

    # Low river valley, continuous water with curved banks, then wooded hills.
    river=LineString([(x,float(w.river_y(x))) for x in range(0,1121,16)])
    w.water_body('willow-river',river.buffer(5.5,cap_style=2),3.8)
    # Irrigation is a functional field edge, away from carriageways and entrances.
    for i,(x,y,X,Y) in enumerate([(680,580,800,582),(680,691,800,693),(690,742,824,744)]):
        # These shallow canals are set into separate low strips with sloping banks.
        w.water_body('irrigation-'+str(i),box(x,y,X,Y),8.25)
        w.pads.append(((x+X)/2,(y+Y)/2,(X-x)/2+.3,1.4,7.4))

    # Continuous village frontages, deliberately varied shop rhythms and rear yards.
    w.frontage('arrival-road',[130,143,156,169,183,198,213,227],-1,
        ['shop-0','home-3','shop-1','home-1','shop-2','home-3','shop-0','home-2'],'west-high-north',12.9)
    w.frontage('arrival-road',[136,151,167,181,198,217],1,
        ['home-3','shop-2','home-0','shop-1','home-1','shop-3'],'west-high-south',13.6)
    w.frontage('market-street',[22,36,51],-1,['shop-1','shop-0','home-3'],'market-west',13.2)
    w.frontage('market-street',[21,36,51,66,83,100,117],1,
        ['shop-2','home-3','shop-1','shop-0','home-1','shop-2','home-2'],'market-south',13.5)
    w.frontage('east-high-street',[24,40,57,75,91],-1,
        ['home-1','shop-3','home-0','home-2','home-4'],'east-high-north',14)
    w.frontage('east-high-street',[25,44,63,83],1,
        ['home-0','shop-2','home-5','home-4'],'east-high-south',15)
    # Hall faces the square; its colonnade is traversably open in both LODs.
    w.place('clock-hall','market-hall',495,443,180,9,True)
    w.paint('market-square',box(465,439,526,472),'concrete')
    for x in (469,520):
        w.place('square-tree-'+str(x),'tree-1',x,446,level=9,solid=False)
        for y in (452,463):w.place('square-bench-'+str(x)+'-'+str(y),'bench',x,y,90 if x<500 else -90,9)
    for x in (476,486,507,518):w.place('square-planter-'+str(x),'planter',x,469,level=9)
    for i,(x,y) in enumerate([(477,452),(486,452),(508,452),(516,452)]):
        w.place('market-table-'+str(i),'table',x,y,0,9)
        w.place('market-crate-'+str(i),'crate',x+.9,y+1.1,0,9)
    for i,x in enumerate(range(278,637,27)):
        for side in (-1,1):
            # Keep junction mouths, the hall entrance and pedestrian accesses clear.
            if min(abs(x-v) for v in (400,540,650))<9:continue
            w.place('high-street-lamp-'+str(i)+'-'+str(side),'lamp',x,480+side*7.8,side*90,9)

    # Distinct neighbourhoods: cottages with gardens vs taller ridge houses.
    w.frontage('orchard-homes',[38,66,96],1,['home-0','home-2','home-5'],'orchard-west',18)
    w.frontage('orchard-homes',[39,68,96],-1,['home-4','home-0','home-2'],'orchard-east',18)
    w.frontage('south-cottages',[25,51,79,107,133],-1,['home-2','home-0','home-5'],'south-garden',18)
    w.frontage('garden-homes',[41,71,104,137,169],1,['home-0','home-5','home-4'],'garden-west',18)
    w.frontage('garden-homes',[42,73,108],-1,['home-2','home-1','home-4'],'garden-east',18)
    w.frontage('ridge-homes',[35,64,97,130,164,200],-1,['home-1','home-3','home-4'],'ridge-east',18)
    w.frontage('ridge-homes',[70,101,133,167],1,['home-5','home-1','home-3'],'ridge-west',18)
    w.frontage('green-lane',[34,65,96],-1,['home-5','home-0','home-2'],'river-houses',17)
    # Village green is open on purpose; footpaths connect it to both housing groups.
    w.paint('green-path',LineString([(420,565),(465,555),(529,570)]).buffer(1.7),'gravel')
    for i,(x,y) in enumerate([(432,545),(475,576),(503,550),(449,594)]):
        w.place('green-oak-'+str(i),'tree-0',x,y,solid=False)
        w.place('green-bench-'+str(i),'bench',x+5,y+2,90)

    # Two working farms with yard accesses, roofed equipment storage and crops.
    for farm,x,y,yaw in [('mill',851,620,0),('south',631,744,180)]:
        z=9 if farm=='mill' else 10.8
        w.place(farm+'-barn','barn',x,y,yaw,z,True)
        w.place(farm+'-house','home-4',x-27,y+3,yaw,z,True)
        w.place(farm+'-shed','shed',x+23,y+6,yaw,z,True)
        w.place(farm+'-tractor','tractor',x+23,y-5,yaw,z)
        w.paint(farm+'-yard',box(x-41,y-22,x+38,y+17),'gravel')
        for i in range(4):w.place(farm+'-hay-'+str(i),'hay',x+12+i*1.7,y+12,yaw,z)
        for i in range(3):w.place(farm+'-crate-'+str(i),'crate',x-10+i,y-11,yaw,z)
    w.paint('mill-drive',LineString([(851,608),(858,580)]).buffer(3.6),'gravel')
    w.paint('south-drive',LineString([(631,752),(645,800)]).buffer(3.6),'gravel')

    fields=[('mill-upper-wheat',Polygon([(816,527),(864,551),(927,584),(943,573),(935,529),(841,505)]),'wheat'),
        ('north-wheat',box(680,589,800,651),'wheat'),('east-cabbage',box(884,658,930,758),'cabbage'),
        ('central-cabbage',box(687,660,800,682),'cabbage'),('south-wheat',box(680,704,827,733),'wheat'),
        ('south-cabbage',box(703,753,824,783),'cabbage'),('west-wheat',box(585,625,654,689),'wheat')]
    road_clear=w.road_area(3.0);occupied=unary_union([p for _,p in w.obstacles])
    for label,field,kind in fields:
        field=field.difference(road_clear).difference(occupied.buffer(3))
        w.paint(label+'-soil',field,'dirt')
        a,b,c,d=field.bounds;index=0
        for y in np.arange(b+4,d-3,8.5):
            for x in np.arange(a+4,c-3,8.5):
                if field.covers(box(x-4,y-4,x+4,y+4)):
                    w.place(label+'-'+str(index),kind,float(x),float(y),solid=False);index+=1
        # A visibly maintained hedgerow defines the field boundary, with gates.
        for i,x in enumerate(np.arange(a+4,c-3,4.3)):
            if abs(x-(a+c)/2)<5:continue
            if road_clear.distance(Point(x,b-2))<2:continue
            w.place(label+'-hedge-'+str(i),'hedge',float(x),b-2,solid=False)

    # A real orchard has aligned fruit trees and an open access aisle.
    for row in range(5):
        for col in range(7):
            x=298+col*10;y=699+row*11
            w.place('fruit-orchard-'+str(row)+'-'+str(col),'tree-3',x,y,(row*43+col*79)%360,solid=False)
    w.paint('orchard-track',LineString([(319,681),(319,755)]).buffer(1.7),'dirt')
    for side in (-1,1):
        for i in range(17):w.place('orchard-fence-'+str(side)+'-'+str(i),'fence',285+i*4.1,720+side*32,solid=False)

    # Buried bases and intermediate bank piers meet the underside of the deck.
    for index,cy in enumerate((344,318,296,258)):
        w.place('bridge-support-'+str(index),'bridge-support',650,cy,level=4.0,solid=False)
    for index,cy in enumerate((260,296)):
        w.place('east-bridge-support-'+str(index),'bridge-support-high',965,cy,level=2.0,solid=False)

    # Explicit habitat bands: grove, river riparian edge, hillside canopy and meadow.
    habitats=[('northwest-wood',Polygon([(25,28),(515,28),(530,190),(385,205),(280,225),(30,226)]),11.7),
        ('ridge-wood',Polygon([(715,38),(1090,35),(1090,390),(1025,380),(937,279),(803,156),(720,164)]),11.8),
        ('west-grove',box(30,348,120,765),11.5),('east-grove',box(1018,430,1090,894),11.0),
        ('south-grove',Polygon([(90,806),(440,846),(690,880),(1090,900),(1090,934),(40,932)]),13.0),
        ('river-meadow',Polygon([(65,338),(1050,330),(1005,420),(700,425),(595,399),(335,421),(135,391)]),24.0)]
    blocked=unary_union([p for name,p,asset in w.scenery if asset!='grass']).buffer(2)
    water_clear=unary_union(w.water).buffer(4)
    road_exclusion=w.road_area(6)
    for label,area,spacing in habitats:
        randomizer=random.Random(1033+sum(map(ord,label)))
        a,b,c,d=area.bounds;index=0
        for y in np.arange(b+6,d-4,spacing):
            for x in np.arange(a+6,c-4,spacing):
                x=float(x+randomizer.uniform(-3,3));y2=float(y+randomizer.uniform(-3,3));point=Point(x,y2)
                if not area.contains(point) or road_exclusion.contains(point) or blocked.contains(point) or water_clear.contains(point):continue
                variant=randomizer.choices([0,1,2,3,4],[4,2,3,1,1])[0]
                w.place(label+'-tree-'+str(index),'tree-'+str(variant),x,y2,randomizer.randrange(360),solid=False)
                if index%2==0:w.place(label+'-understory-'+str(index),'shrub',x+3.6,y2+1.7,randomizer.randrange(360),solid=False)
                if index%4==0:w.place(label+'-litter-'+str(index),'grass',x-3,y2-2,solid=False)
                if index%27==0:w.place(label+'-fallen-'+str(index),'log',x+3,y2-3,randomizer.randrange(360),solid=False)
                index+=1
    # Riparian willows, reeds, rocks and grass continue beyond the bridge sightline.
    for i,x in enumerate(range(42,1080,15)):
        y=float(w.river_y(x));side=-1 if i%2 else 1
        if abs(x-650)<15:continue
        w.place('river-reeds-'+str(i),'reeds',x,y+side*5.7,level=3.1,solid=False)
        for edge in (-1,1):
            w.place('river-bank-shrub-'+str(i)+'-'+str(edge),'shrub',x+4,y+edge*11.5,i*41,solid=False)
            w.place('river-bank-grass-'+str(i)+'-'+str(edge),'grass',x-3,y+edge*14.5,i*29,solid=False)
        if i%2==0:w.place('river-willow-'+str(i),'tree-'+str(2+i%3),x,y+side*18,i*31,solid=False)
        if i%3==0:w.place('river-rock-'+str(i),'rock-'+str((i//3)%3),x+3,y-side*9,solid=False)
    # Roadside field boundaries and loose tree groups replace empty corridors.
    exclusion=w.road_area(5)
    clear=unary_union([p for _,p in w.obstacles]).buffer(2)
    for name in ('meadow-bend','riverside-lane','woodland-road','ridge-descent','mill-lane','farm-approach','harvest-road','pasture-road'):
        line=w.routes[name]
        for i,s in enumerate(np.arange(18,line.length-12,14)):
            p=line.interpolate(s);q=line.interpolate(s+.3);dx=q.x-p.x;dy=q.y-p.y;l=math.hypot(dx,dy)
            side=-1 if i%2 else 1;x=p.x-dy/l*side*12;y=p.y+dx/l*side*12
            point=Point(x,y)
            if exclusion.contains(point) or clear.contains(point) or water_clear.contains(point):continue
            w.place(name+'-verge-'+str(i),'shrub' if i%3 else 'tree-'+str(i%3),x,y,i*51,solid=False)
            w.place(name+'-grass-'+str(i),'grass',p.x-dy/l*side*5.6,p.y+dx/l*side*5.6,solid=False)

    routes=[w.course('intro','Market and Gardens',['arrival-road','market-street','garden-homes','orchard-road','-orchard-homes']),
        w.course('tour','River and Harvest Tour',['arrival-road','market-street','east-high-street','bridge-approach',
            'bridge-gate','river-bridge','woodland-road','east-river-bridge','ridge-descent','east-farm-lane','harvest-road','pasture-road','orchard-road',
            'south-cottages','meadow-bend','west-gateway']),
        w.course('technical','Village Lane Circuit',['arrival-road','market-street','east-high-street','farm-approach',
            '-ridge-homes','-bridge-approach','-east-high-street','-green-lane','-riverside-lane'])]
    def view(name,eye,target):
        return dict(name=name,position_m=[eye[0],float(w.height(*eye))+1.7,eye[1]],
            target_m=[target[0],float(w.height(*target))+2,target[1]],quality=2,view_distance_m=384)
    def road_view(name,road_id,station,look_ahead):
        line=w.routes[road_id];eye=line.interpolate(station);target=line.interpolate(station+look_ahead)
        return view(name,(eye.x,eye.y),(target.x,target.y))
    reviews=[view('main-street',(425,482),(502,463)),road_view('farm-road','mill-lane',130,-105),
        road_view('nature-road','woodland-road',70,78),
        dict(name='distant',position_m=[653,12.7,287],target_m=[842,8,float(w.river_y(842))],quality=2,view_distance_m=384),
        dict(name='overview',position_m=[500,130,550],target_m=[500,9,480],projection='orthogonal',size_m=300,quality=2,view_distance_m=384)]
    return dict(id='village',name='마을',en='Village Driving Park',theme='village',size=list(w.size),surface='asphalt',
        description='A lived-in market village, orchard homes and working farms beside a wooded river valley.',
        districts=['market','orchard homes','ridge gardens','farmland','river meadow','woodland'],landmarks=w.places,
        routes=routes,start=routes[0]['start'],review_views=reviews,preview_center_m=[482,9,484],
        ground_position_m=reviews[0]['position_m'],ground_target_m=reviews[0]['target_m'],
        acceptance='First village art direction awaits user review; routes have no claimed human completion.')
