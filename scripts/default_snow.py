"""Alpine lodges, fir valley, frozen lake and a summit outlook, MIT."""
from shapely.geometry import Point,LineString,box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish

def compose(w):
    terrain(w,20,[(125,115,100,130,100),(735,110,110,90,110),(740,950,45,70,75)])
    w.doc['environment'].update(concept='polar',climate='polar',settlement='village',ground_color=[171,180,181])
    nodes=dict(A=(90,800),B=(270,800),C=(580,800),D=(660,620),E=(650,340),F=(460,240),G=(260,460),H=(100,550),I=(340,640))
    levels={k:24 for k in nodes};levels.update(D=30,E=42,F=40,G=30,H=26,I=26)
    network(w,nodes,levels=levels,bends={'upper-road':[(700,488)],'west-ridge':[(376,301),(304,376)]})
    split_south(w,(365,800),(485,800),24,'ramp_low')
    # The ice lake is an actual bounded solid; its margin is separate scenery.
    facility(w,'frozen-lake','frozen-lake',(496,690),0,22,0)
    w.pads.append((496,690,48,33,21.3))
    w.paint('lake-margin',Point(496,690).buffer(57,quad_segs=20),'gravel')
    for i,(x,y,a) in enumerate([(171,765,180),(220,758,180),(305,856,0),(363,855,0),(155,840,0),(220,840,0)]):
        facility(w,'alpine-lodge-'+str(i),'alpine-lodge-'+str(i%2),(x,y),a,24,6)
    facility(w,'summit-lodge','alpine-lodge-1',(545,225),160,41,7)
    for i,(x,y) in enumerate([(145,752),(248,752),(525,266),(565,280)]):w.place('lodge-bench-'+str(i),'bench',x,y,level=24 if i<2 else 41,solid=False)
    w.boundary('lodge-fence','snow-fence',[(142,740),(245,740),(245,778),(142,778),(142,740)],gates=[(195,778)],level=24)
    grove(w,'fir-valley',box(30,380,240,730),['snow-fir-0','snow-fir-1','snow-fir-2'],14,'snowbank')
    grove(w,'lake-firs',box(386,405,603,736),['snow-fir-2','snow-fir-0'],16,'snowbank')
    grove(w,'east-snowline',box(724,270,806,870),['snow-fir-1','alpine-crag-2'],20,'snowbank')
    grove(w,'south-forest',box(30,900,700,1028),['snow-fir-0','snow-fir-1'],18,'snowbank')
    for i,(x,y,a) in enumerate([(115,156,20),(206,185,40),(692,171,20),(735,232,65),(747,573,10)]):
        w.place('summit-crag-'+str(i),'alpine-crag-'+str(i%3),x,y,a,solid=False)
    verge(w,['inner-approach','inner-grove','west-ridge','upper-road'],['snowbank','snow-fir-1','snow-fir-2'],17,13)
    streetscape(w,'arrival-road',['snow-fir-1','snow-fir-2','snowbank'],step=18,setback=19)
    streetscape(w,'ridge-road',['alpine-crag-0','snow-fir-0','alpine-crag-2'],step=24,setback=25)
    streetscape(w,'upper-road',['snow-fir-0','snow-fir-2','alpine-crag-1'],step=24,setback=21)
    streetscape(w,'west-ridge',['snow-fir-0','snow-fir-1','snowbank'],step=19,setback=17)
    w.landmark_review=('inner-east',130,(496,690))
    return finish(w,'snow-mountain','설산','Snow Mountain','Lodge gardens and fir bends climb past a frozen lake to the summit terrace.',
        ['lodge village','fir valley','frozen lake','summit road'],['Summit lodge','Frozen lake','Twin mountain silhouettes'],
        [('valley-road','inner-grove',45,95),('lodge-road','arrival-road',90,60),('snow-road','west-ridge',80,80),('distant','ridge-road',70,90)],
        weather=dict(name='snow-state',weather='snow',snow=1.0))
