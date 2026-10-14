"""Production halls, process tanks, service alleys and shipping, MIT."""
from shapely.geometry import LineString,box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish

def compose(w):
    terrain(w,8,[(55,80,12,65,65)])
    w.doc['theme']='urban';w.doc['environment'].update(concept='metropolis',architecture='modern',settlement='urban',ground_color=[113,115,98])
    nodes=dict(A=(80,600),B=(260,600),C=(560,600),D=(660,440),E=(620,190),F=(410,140),G=(250,300),H=(90,350),I=(350,430))
    network(w,nodes,levels={k:10 for k in nodes},width=8,bends={'inner-approach':[(260,550)],'upper-road':[(682,315)],'west-ridge':[(330,201)]})
    split_south(w,(350,600),(470,600),10,'grind_rail',5)
    w.pads.extend([(320,542,210,82,10),(467,280,108,75,10),(602,595,73,132,10)])
    w.paint('production-campus',box(110,460,530,575),'concrete')
    w.paint('process-campus',box(365,215,570,345),'concrete')
    w.paint('shipping-campus',box(540,465,665,725),'concrete')
    for i,(x,y,a) in enumerate([(170,510,0),(400,540,180),(485,490,90)]):
        facility(w,'production-hall-'+str(i),'production-'+str(i),(x,y),a,10,8,'concrete')
    facility(w,'factory-admin','factory-admin',(175,640),0,10,7,'concrete')
    facility(w,'boiler-bank','boiler-bank',(525,285),0,10,5,'concrete')
    facility(w,'chimney','factory-stack',(552,269),0,10,3)
    for i,(x,y) in enumerate([(423,245),(465,245),(464,300),(423,300)]):
        facility(w,'process-tank-'+str(i),'process-tank-'+str(i%3),(x,y),0,10,4,'concrete')
    for i,(x,y,a) in enumerate([(420,275,0),(465,275,0),(495,287,90),(505,343,0),(360,485,90)]):
        w.place('pipe-connection-'+str(i),'pipe-rack',x,y,a,10,solid=False)
    for i,(x,y) in enumerate([(375,265),(365,310)]):facility(w,'transformer-'+str(i),'transformer',(x,y),0,10,2,'concrete')
    for i,(x,y) in enumerate([(560,505),(596,514),(580,543)]):
        w.place('shipping-truck-'+str(i),'parked-truck',x,y,90,10,solid=False)
    for row in range(3):
        for col in range(3):w.place('shipping-container-'+str(row)+'-'+str(col),'container-'+str((row+col)%4),563+col*18,660+row*16,90,10,True,False)
    w.boundary('process-safety','safety-barrier',[(385,217),(520,217),(520,327),(385,327),(385,217)],gates=[(385,275),(520,285)],level=10)
    for i,(x,y) in enumerate([(210,480),(280,485),(478,449),(507,377)]):
        w.place('service-compressor-'+str(i),'compressor',x,y,90,10,foundation=True,solid=False)
    grove(w,'factory-screen',box(20,20,350,130),['tree-1','tree-4'],18)
    grove(w,'shipping-screen',box(25,685,480,747),['tree-4','tree-2'],17)
    verge(w,['arrival-road','inner-approach','west-lane'],['lamp','planter','safety-barrier'],24,12)
    streetscape(w,'arrival-road',['compressor','pipe-rack','transformer','safety-barrier'],step=24,setback=20,yard='concrete')
    streetscape(w,'ridge-road',['process-tank-0','pipe-rack','process-tank-2','boiler-bank'],step=36,setback=30,yard='concrete')
    streetscape(w,'upper-road',['production-1','pipe-rack','transformer','production-0'],step=52,setback=34,yard='concrete')
    streetscape(w,'east-road',['container-0','parked-truck','container-2'],step=26,setback=23,sides=(1,),yard='concrete')
    streetscape(w,'inner-grove',['pipe-rack','compressor','transformer'],step=28,setback=23,yard='concrete')
    w.landmark_review=('ridge-road',80,(525,285))
    return finish(w,'machine-factory','기계 공장','Machine Factory','Sawtooth halls, connected pipe racks and tanks give way to maintenance lanes and a shipping court.',
        ['production halls','process equipment','maintenance lanes','shipping court'],['Boiler chimneys','Tank and pipe yard','Sawtooth production halls'],
        [('production-road','arrival-road',105,55),('process-road','ridge-road',40,90),('shipping-road','east-road',35,90),('distant','upper-road',100,90)])
