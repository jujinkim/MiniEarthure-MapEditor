"""A compact neon frontage, warehouse lanes and two cargo quays, MIT."""
from shapely.geometry import Point, LineString, box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish,WALKS

def compose(w):
    terrain(w,8,[(80,100,16,100,80)],river=('y',730,2.2,28))
    w.doc['theme']='urban';w.doc['environment'].update(concept='metropolis',architecture='modern',settlement='urban',ground_color=[99,111,95],start_minutes=1200)
    nodes=dict(A=(90,560),B=(270,560),C=(650,560),D=(820,430),E=(820,210),F=(510,180),G=(280,300),H=(90,340),I=(380,410))
    network(w,nodes,levels={k:10 for k in nodes},bridges=('east-road','ridge-road','inner-east'),width=8,
        bends={'west-ridge':[(430,230)],'return-road':[(65,445)]})
    split_south(w,(390,560),(520,560),10,'grind_rail')
    w.water_body('harbor-channel',box(702,0,758,768),3.8)
    w.water_body('east-basin',box(758,590,960,768),3.8)
    w.pads.extend([(180,560,105,70,10),(645,450,56,126,10),(845,475,65,100,10),(530,390,90,100,10)])
    # Each commercial block is individually placed with service space behind it.
    for side in (-1,1):
        for i,x in enumerate((115,151,187,223,259)):
            facility(w,'high-street-'+str(side)+'-'+str(i),'urban-'+str((i+(2 if side==1 else 0))%6),(x,560+side*30),180 if side==-1 else 0,10,3,'concrete')
    for i,(x,y) in enumerate([(115,300),(160,305),(210,294),(285,255),(335,325)]):
        facility(w,'canal-block-'+str(i),'urban-'+str(i%6),(x,y),180,10,3,'concrete')
    w.frontage('west-lane',[38,77,116,154],-1,['urban-5','urban-0','urban-2','urban-1'],'waterside-blocks',29)
    w.frontage('inner-approach',[58,96,134],-1,['urban-1','urban-3','urban-5'],'sign-alley',27)
    for i,(x,y,turn) in enumerate([(490,365,0),(555,470,90),(610,330,180)]):
        facility(w,'warehouse-'+str(i),'warehouse-'+str(i),(x,y),turn,10,7,'concrete')
        w.place('delivery-'+str(i),'parked-truck',x-25,y+28,turn,10,solid=False)
    for quay,x in [('west',645),('east',815)]:
        for row in range(4):
            for col in range(3):
                w.place(quay+'-containers-'+str(row)+'-'+str(col),'container-stack-'+str((row+col)%4),x+col*15,480+row*17,90,10,True,False)
        facility(w,quay+'-crane','dock-crane',((650,390) if quay=='west' else (875,470)),0,10,0)
    for i,y in enumerate(range(330,566,24)):
        w.place('quay-bollard-'+str(i),'bollard',692,y,level=10,foundation=True,solid=False)
        w.place('quay-edge-'+str(i),'quay-wall',698,y,90,10,solid=False)
    for i,(x,y) in enumerate([(730,499),(730,202),(730,426)]):w.place('bridge-pier-'+str(i),'harbor-pier',x,y,90,-2.2,solid=False)
    for i,(x,y) in enumerate([(473,389),(535,440),(635,360)]):w.place('service-pipeline-'+str(i),'pipeline',x,y,90,10,foundation=True,solid=False)
    w.boundary('warehouse-fence','metal-fence',[(455,325),(455,449),(620,449),(620,390)],gates=[(455,390),(555,449)],level=10)
    grove(w,'canal-gardens',box(310,205,470,310),['tree-1','tree-4'],15)
    grove(w,'harbor-hill',box(20,20,250,210),['tree-0','tree-2'],20)
    verge(w,['arrival-road','west-lane','inner-approach'],['lamp','planter','tree-4'],23,12)
    import json,struct
    for asset in w.doc['assets']:
        if not asset['id'].startswith('authored-urban-'):continue
        data=w.payloads[asset['path']];size=struct.unpack_from('<I',data,12)[0]
        model=json.loads(data[20:20+size]);colors=[m['pbrMetallicRoughness']['baseColorFactor'] for m in model['materials']]
        w.doc['environment']['lights'].append(dict(asset_id=asset['id'],window_materials=[i for i,c in enumerate(colors) if c==[.17,.29,.31,1]],
            bulb_materials=[i for i,c in enumerate(colors) if c in ([.24,.88,.90,1],[.91,.32,.58,1],[.92,.77,.40,1])],
            position_cm=[0,320,-700],range_cm=1600,color=[181,217,231]))
    walks={k:list(v) for k,v in WALKS.items()}
    walks['technical']=['arrival-road','south-road','east-road','-inner-east','-inner-approach']
    w.paint('cargo-paving',box(565,310,700,575),'concrete')
    w.paint('east-quay-paving',box(780,375,930,575),'concrete')
    streetscape(w,'upper-road',['warehouse-0','container-stack-1','warehouse-2','container-stack-3'],step=43,setback=30,yard='concrete')
    streetscape(w,'south-road',['container-stack-0','parked-truck','pipeline','container-stack-2'],step=27,setback=22,sides=(1,),yard='concrete')
    streetscape(w,'west-ridge',['urban-0','urban-3','urban-5'],step=42,setback=29,sides=(-1,),yard='concrete')
    w.landmark_review=('east-road',70,(650,390))
    return finish(w,'neon-harbor','네온 항구','Neon Harbor','Warm neon streets turn through warehouse courts to container quays and the channel bridges.',
        ['sign street','warehouse alleys','west cargo quay','east channel quay'],['Neon corner blocks','Twin cargo cranes','Channel bridges'],
        [('day-street','arrival-road',55,100),('port-road','south-road',45,75),('coastal-road','upper-road',80,80),('distant','east-road',70,80)],walks,
        weather=dict(name='main-street',time_minutes=1200))
