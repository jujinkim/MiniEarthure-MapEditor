"""A hilltop amusement park with clear plazas and optional upper track, MIT."""
from shapely.geometry import Point,LineString,box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish

def compose(w):
    terrain(w,82,[(75,80,28,90,65),(860,80,25,80,80)])
    w.doc['environment'].update(concept='countryside',settlement='village',ground_color=[116,141,94])
    nodes=dict(A=(90,570),B=(270,570),C=(620,570),D=(790,440),E=(760,220),F=(510,150),G=(280,320),H=(100,350),I=(360,430))
    network(w,nodes,levels={k:82 for k in nodes},bends={'upper-road':[(807,330)],'west-ridge':[(410,195)],'return-road':[(78,460)]})
    split_south(w,(370,570),(500,570),82,'jump_panel',6)
    w.pads.extend([(200,550,88,90,82),(560,335,115,80,82)])
    # A separate ground channel leaves the elevated lane's entry/exit underside clear.
    w.pads.append((435,570,110,16,81))
    w.paint('entrance-plaza',box(125,485,270,623),'concrete')
    w.paint('wheel-terrace',box(470,275,610,365),'concrete')
    facility(w,'entrance-carousel','carousel',(231,513),180,82,13,'concrete')
    facility(w,'observation-wheel','observation-wheel',(555,300),180,82,16,'concrete')
    facility(w,'coaster-garden','decorative-coaster',(660,340),180,82,8,'concrete')
    for i,(x,y,a) in enumerate([(159,536,180),(190,536,180),(210,606,0),(247,609,0),(513,335,90),(550,346,180)]):
        facility(w,'park-kiosk-'+str(i),'park-kiosk-'+str(i%3),(x,y),a,82,4,'concrete')
    for i,(x,y) in enumerate([(213,482),(242,482),(526,331),(580,330),(709,458)]):
        w.place('queue-'+str(i),'queue-rail',x,y,0,82,foundation=True,solid=False)
    for i,(x,y,a) in enumerate([(178,550,0),(212,550,0),(315,500,45),(470,330,90),(580,360,0),(710,465,0)]):
        w.place('flower-border-'+str(i),'flowerbed',x,y,a,82,foundation=True,solid=False)
    # Medium structures connect the attractions into streets and waiting courts.
    for i,(x,y,a) in enumerate([(267,508,90),(505,346,0),(730,410,90)]):
        w.place('shade-arcade-'+str(i),'park-pergola',x,y,a,82,foundation=True,solid=False)
    w.paint('wheel-promenade',LineString([(440,420),(510,350),(555,330)]).buffer(4),'concrete')
    w.boundary('carousel-court','park-railing',[(204,487),(259,487),(259,536),(204,536),(204,487)],gates=[(231,536),(259,512)],level=82)
    grove(w,'ridge-garden',box(25,25,900,118),['tree-0','tree-1','tree-2'],20)
    grove(w,'west-topiary',box(30,180,235,305),['tree-4','tree-3','tree-2'],13)
    grove(w,'east-garden',box(843,250,935,715),['tree-1','tree-4'],17)
    grove(w,'south-terrace',box(30,655,825,774),['tree-3','tree-2','tree-4'],17)
    verge(w,['inner-approach','inner-grove','ridge-road','upper-road'],['flowerbed','tree-4','planter','lamp'],20,13)
    streetscape(w,'arrival-road',['flowerbed','park-pergola','park-kiosk-1','planter'],step=19,setback=16,yard='concrete')
    streetscape(w,'inner-east',['park-pergola','park-kiosk-0','flowerbed','tree-4'],step=22,setback=19,yard='concrete')
    streetscape(w,'east-road',['tree-3','park-kiosk-2','flowerbed','park-pergola'],step=24,setback=20,yard='concrete')
    streetscape(w,'ridge-road',['tree-1','tree-2','flowerbed'],step=17,setback=15)
    streetscape(w,'upper-road',['tree-2','park-pergola','tree-4','flowerbed'],step=21,setback=17)
    w.landmark_review=('inner-east',145,(555,300))
    return finish(w,'sky-park','하늘 놀이공원','Sky Amusement Park','Entrance gardens and a carousel open toward the observation wheel, coaster court and optional upper lane.',
        ['entrance plaza','carousel gardens','wheel terrace','coaster court'],['Observation wheel','Carousel pavilion','Coaster silhouette'],
        [('garden-road','arrival-road',100,60),('wheel-road','inner-east',145,100),('coaster-road','east-road',45,90),('distant','ridge-road',100,90)])
