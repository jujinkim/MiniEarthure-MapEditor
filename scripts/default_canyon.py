"""Layered cliffs, a natural arch, dry wash and a working quarry, MIT."""
from shapely.geometry import LineString,box
from compact_worlds import terrain,network,facility,grove,verge,split_south,streetscape,finish

def compose(w):
    terrain(w,18,[(70,70,45,90,70),(1090,110,60,90,100),(1080,550,42,90,65),(540,50,20,180,50)])
    w.doc['environment'].update(concept='desert',climate='arid',settlement='sparse',ground_color=[168,116,76])
    nodes=dict(A=(100,450),B=(280,450),C=(660,450),D=(900,380),E=(900,200),F=(610,140),G=(300,240),H=(110,260),I=(410,350))
    levels={k:22 for k in nodes};levels.update(E=31,F=30,G=25)
    network(w,nodes,levels=levels,bends={'east-road':[(782,483),(858,432)],'upper-road':[(938,287)],'west-ridge':[(480,177),(376,202)]})
    split_south(w,(420,450),(550,450),22,'jump_panel',2.5)
    facility(w,'redstone-arch','natural-arch',(535,230),20,25,0)
    for i,(x,y,a) in enumerate([(165,220,20),(220,187,65),(590,100,15),(730,150,60),(956,330,10),(875,450,30),(620,485,40)]):
        w.place('road-cliff-'+str(i),'sandstone-'+str(i%4),x,y,a,solid=False)
    facility(w,'quarry-crusher','quarry-crusher',(723,315),90,22,8)
    facility(w,'quarry-office','quarry-office',(670,300),0,22,5)
    facility(w,'quarry-conveyor','quarry-conveyor',(747,330),90,22,0)
    facility(w,'quarry-stockpile','canyon-stockpile',(787,325),0,22,3,'dirt')
    w.place('quarry-loader','quarry-loader',753,354,90,22)
    w.paint('quarry-access',LineString([(670,315),(700,358),(738,379)]).buffer(3.8),'gravel')
    w.boundary('quarry-boundary','stone-wall',[(645,279),(808,279),(808,360),(645,360),(645,279)],gates=[(690,360)],level=22)
    w.paint('dry-riverbed',LineString([(340,24),(365,140),(485,280),(560,395),(590,600)]).buffer(14),'gravel')
    grove(w,'western-mesa',box(18,18,235,200),['sandstone-0','sandstone-2','sandstone-3'],26,'desert-scrub')
    grove(w,'eastern-walls',box(970,30,1125,602),['sandstone-1','sandstone-2','sandstone-0'],28,'canyon-rubble')
    grove(w,'south-scree',box(25,520,940,615),['cactus','desert-scrub','canyon-rubble'],21,'desert-scrub')
    verge(w,['inner-grove','west-ridge','upper-road','return-road'],['canyon-rubble','desert-scrub','cactus'],17,13)
    # Close layered rock walls reveal the next bend and frame the arch.
    streetscape(w,'west-ridge',['sandstone-0','sandstone-2','sandstone-1'],step=24,setback=23)
    streetscape(w,'inner-grove',['sandstone-3','sandstone-1','canyon-rubble'],step=23,setback=24)
    streetscape(w,'ridge-road',['sandstone-0','sandstone-2','cactus'],step=25,setback=27)
    streetscape(w,'arrival-road',['sandstone-3','cactus','canyon-rubble','desert-scrub'],step=22,setback=19)
    streetscape(w,'upper-road',['sandstone-0','sandstone-1','canyon-rubble'],step=26,setback=26)
    streetscape(w,'inner-east',['canyon-stockpile','canyon-rubble','quarry-conveyor'],start=245,step=31,setback=24,sides=(-1,),yard='gravel')
    w.landmark_review=('west-ridge',60,(535,230))
    return finish(w,'red-canyon','붉은 협곡','Red Canyon','Ochre cliff layers frame the natural arch, a dry river wash and quarry service bends.',
        ['strata corridor','arch overlook','dry wash','quarry yard'],['Redstone arch','Quarry crusher','Layered mesa'],
        [('canyon-road','west-ridge',45,90),('quarry-road','inner-east',230,90),('wash-road','inner-grove',55,75),('distant','ridge-road',80,100)])
