"""A compact market, garden lanes, orchard farm and wooded river, metres/MIT."""
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish,WALKS

def compose(w):
    terrain(w,8,[(45,50,20,90,70),(595,45,18,75,65)],river=('x',145,2.2,5.5))
    nodes=dict(A=(60,350),B=(240,350),C=(440,350),D=(560,300),E=(550,85),F=(370,85),G=(200,190),H=(70,200),I=(340,250))
    network(w,nodes,levels=dict(D=11,E=11,F=11,G=11),bridges=('upper-road','west-ridge'),bends={'return-road':[(45,260)],'east-road':[(515,360)]})
    # The farm bypass curves around a field; its short lane offers a low ramp.
    split_south(w,(290,350),(390,350),9)
    w.river_y=lambda x:np.asarray(x)*0+145
    w.river_line=lambda:LineString([(0,145),(640,145)])
    w.river_distance=lambda x,y:np.abs(np.asarray(y)-145)
    w.water_body('willow-river',box(0,139.5,640,150.5),3.8)
    # Deck soffits remain supported while bases are embedded in the river bed.
    for i,(road,station) in enumerate([('upper-road',100),('west-ridge',60)]):
        line=w.routes[road];p=line.interpolate(station)
        r=next(r for r in w.doc['roads'] if r['id']==road)
        top=sum(v[1] for v in r['points'])/len(r['points'])/100
        w.place('bridge-support-'+str(i),'bridge-support-high',p.x,p.y,level=top-.2-17.8,solid=False)
    # The central opening exposes the clock and stalls directly from the road.
    w.frontage('arrival-road',[31,53,75,97,163],-1,['shop-0','home-3','shop-1','shop-3'],'market',18)
    w.frontage('arrival-road',[32,57,83,109,135,159],1,['home-0','shop-2','home-5'],'garden',18)
    w.paint('market-square',box(168,307,216,343),'concrete')
    facility(w,'clock-hall','market-hall',(190,294),180,9,7,'concrete')
    for i,x in enumerate([174,185,205]):w.place('market-stall-'+str(i),'market-stall',x,312,level=9,foundation=True)
    for i,x in enumerate([170,215]):w.place('market-planter-'+str(i),'planter',x,316,level=9,foundation=True)
    w.frontage('inner-approach',[35,65,100],-1,['home-4','home-2','home-0'],'garden-lane',20)
    w.frontage('inner-grove',[26,52,79,106],-1,['home-2','home-1','home-5'],'ridge-gardens',19)
    w.frontage('west-lane',[25,52,80,106],1,['home-1','home-5','home-2'],'river-homes',20)
    facility(w,'orchard-barn','barn',(447,422),0,9,6)
    facility(w,'farmhouse','home-4',(412,425),0,9,4)
    facility(w,'equipment-shed','shed',(478,422),0,9,3)
    w.place('farm-tractor','tractor',478,410,level=9,foundation=True)
    w.paint('farm-drive',LineString([(447,405),(442,375)]).buffer(3.6),'gravel')
    w.boundary('farm-boundary','timber-fence',[(396,402),(496,402),(496,446),(396,446),(396,402)],gates=[(447,402)],level=9)
    for row in range(3):
        for col in range(6):w.place('orchard-'+str(row)+'-'+str(col),'tree-3',290+col*12,425+row*13,col*29,solid=False)
    for row in range(3):
        for col in range(5):w.place('wheat-'+str(row)+'-'+str(col),'wheat',518+col*9,411+row*9,solid=False)
    w.paint('farm-soil',box(513,406,560,438),'dirt')
    grove(w,'hill-woods',box(18,18,620,75),['tree-0','tree-1','tree-2'],16)
    grove(w,'garden-copse',box(90,235,235,288),['tree-2','tree-4','tree-0'],12)
    grove(w,'river-willows',box(250,162,515,202),['tree-2','tree-3','tree-4'],13)
    grove(w,'east-grove',box(585,195,624,469),['tree-0','tree-2'],15)
    grove(w,'south-orchard-edge',box(25,470,610,495),['tree-4','tree-2'],14)
    for i,x in enumerate(range(20,630,13)):
        for side in (-1,1):w.place('river-reed-'+str(i)+'-'+str(side),'reeds',x,145+side*6,level=3.2,solid=False)
    verge(w,['inner-grove','east-road','ridge-road','return-road'],['tree-2','shrub','tree-4','grass'],15)
    walks={k:list(v) for k,v in WALKS.items()}
    walks['tour']+=['arrival-road','inner-approach']
    walks['technical']=['arrival-road','south-road','east-road','-inner-east','inner-grove','west-lane','return-road']
    streetscape(w,'ridge-road',['tree-2','tree-4','shrub'],step=14,setback=14)
    streetscape(w,'south-road',['tree-3','timber-fence','grass'],step=15,setback=15,sides=(1,))
    streetscape(w,'return-road',['tree-0','tree-2','shrub'],step=17,setback=16)
    w.landmark_review=('arrival-road',122,(190,294))
    return finish(w,'village','마을','Village Driving Park','Market stalls and garden cottages lead to an orchard farm and two wooded river crossings.',
        ['market square','garden homes','orchard farm','river ridge'],['Clock Hall and market','Orchard barn','Willow bridges'],
        [('main-street','arrival-road',80,75),('farm-road','south-road',22,65),('nature-road','west-ridge',45,65),('distant','ridge-road',36,95)],walks)
