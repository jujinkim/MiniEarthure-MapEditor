"""Canopied forest lanes reveal a camp, lake and two gorge bridges, MIT."""
from shapely.geometry import Point,LineString,box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish

def compose(w):
    terrain(w,27,[(80,120,36,110,90),(810,100,40,90,90),(810,810,28,80,80)],river=('y',640,18,8))
    w.doc['environment'].update(concept='jungle',settlement='wilderness',ground_color=[70,101,65],start_minutes=840)
    nodes=dict(A=(80,670),B=(260,670),C=(580,670),D=(760,540),E=(720,300),F=(520,170),G=(280,360),H=(110,420),I=(340,500))
    network(w,nodes,levels={**{k:32 for k in nodes},'F':32,'G':34},bridges=('east-road','ridge-road','inner-east'),
        bends={'west-ridge':[(409,222),(337,283)],'return-road':[(82,535)],'inner-grove':[(308,437)]})
    split_south(w,(360,670),(465,670),32,'ramp_low',2)
    lake=Point(602,510).buffer(60,quad_segs=32)
    w.water_body('cedar-stream',box(632,0,648,896).union(lake),19.6)
    # The lake is a real basin; its shoreline joins the stream at the same level.
    base=w.base
    from default_worlds import smooth
    import numpy as np
    def basin(x,y):
        r=np.hypot(np.asarray(x)-602,np.asarray(y)-510);weight=smooth((r-60)/14)
        return 18*(1-weight)+base(x,y)*weight
    w.base=basin
    facility(w,'ranger-station','ranger-lodge',(190,636),180,32,7)
    facility(w,'trail-shelter','picnic-shelter',(370,548),90,32,5)
    for i,(x,y) in enumerate([(494,522),(520,535),(518,568),(485,568)]):
        facility(w,'camp-tent-'+str(i),'camp-tent',(x,y),i*80,30,3,'dirt')
    facility(w,'camp-shelter','picnic-shelter',(478,540),90,30,4)
    w.paint('camp-walk',LineString([(448,510),(483,540),(541,540)]).buffer(2.5),'gravel')
    w.boundary('camp-palisade','timber-fence',[(466,505),(535,505),(545,582),(466,582),(466,505)],gates=[(466,540),(535,520)],level=30)
    for i,(x,y) in enumerate([(515,500),(550,540),(336,480)]):w.place('trail-marker-'+str(i),'trail-sign',x,y,i*65,solid=False)
    for i,(x,y) in enumerate([(640,627),(640,248),(600,525)]):w.place('forest-pier-'+str(i),'forest-pier',x,y,90,7.0,solid=False)
    habitats=[('old-growth',box(20,20,610,330),['beech','cedar-2','cedar-0'],14),
        ('fern-hollow',box(24,330,425,620),['cedar-0','beech','sapling-0'],12),
        ('east-cedars',box(675,30,872,858),['cedar-2','cedar-1','sapling-1'],14),
        ('south-woods',box(24,705,630,872),['beech','cedar-0','cedar-1'],14),
        ('lake-groves',box(420,320,605,625),['beech','sapling-0','cedar-1'],13)]
    for name,area,kinds,spacing in habitats:grove(w,name,area,kinds,spacing,'fern-patch',8)
    verge(w,['inner-grove','west-ridge','return-road','upper-road'],['fern-patch','sapling-0','cedar-1','beech'],11,10)
    for i,y in enumerate(range(35,870,19)):
        w.place('stream-reeds-'+str(i),'reeds',631,y,level=19,solid=False)
        if i%3==0:w.place('stream-boulder-'+str(i),'rock-'+str(i%3),654,y,i*31,solid=False)
    for i,(x,y) in enumerate([(440,257),(390,264),(278,450),(737,390)]):w.place('fallen-cedar-'+str(i),'fallen-cedar',x,y,i*45,solid=False)
    streetscape(w,'arrival-road',['tree-0','tree-2','tree-1','tree-4'],step=16,setback=17)
    w.landmark_review=('inner-east',115,(500,545))
    return finish(w,'deep-forest','깊은 숲','Deep Forest','A close canopy opens onto the ranger clearing, fern hollow, quiet lakeside camp and cedar gorge.',
        ['ranger clearing','old-growth canopy','fern hollow','lake camp','river gorge'],['Ranger lodge','Lakeside camp','Cedar gorge bridges'],
        [('forest-road','inner-grove',35,80),('ranger-road','arrival-road',85,65),('camp-road','inner-east',95,90),('distant','east-road',80,80)])
