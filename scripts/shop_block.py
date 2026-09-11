"""Q01: one original MIT Korean shopping block, in actual metres.

Keep the v4 course streets and other lots byte-identical; split two local
streets only at the new service-lane junctions. Geometry, lettering and palette
are authored here: no fonts, downloaded textures, extracted models or game code.
The public GLB/PBR and placement collision contracts are sufficient for this unit.
"""
import math
from city_assets import Model, DARK, WHITE
from driving_school_map import glb, cm

PROFILE = 'driving-school-town-v5'
ATTRIBUTION = dict(source='mapeditor-q01-hanbit-block', license='MIT', notice=
    'Original fictional Hanbit shopping block; buildings, Hangul stroke lettering, street furniture and wall relief authored procedurally. No external models, fonts, textures or surveyed data.')
BRICK = (0.48, 0.22, 0.14, 1)
MORTAR = (0.63, 0.48, 0.36, 1)
TILE = (0.72, 0.78, 0.69, 1)
CREAM = (0.86, 0.80, 0.66, 1)
CONCRETE = (0.55, 0.56, 0.52, 1)
GLASS = (0.14, 0.29, 0.32, 1)
WOOD = (0.39, 0.24, 0.13, 1)
GREEN = (0.18, 0.32, 0.23, 1)
RED = (0.58, 0.18, 0.12, 1)
GOLD = (0.83, 0.61, 0.28, 1)

# Local building front is -Y. Source placement quarter-turns rotates around up.
# The two rows face the 4m+ service lane, with varied setbacks and narrow passages.
SHOPS = [
    dict(id='book', title='한빛서점', x=245.4, y=57.3, w=6.4, d=8.6, h=6.9, turn=2, wall=BRICK, sign=GREEN),
    dict(id='cafe', title='골목커피', x=253.1, y=57.0, w=7.0, d=7.8, h=4.9, turn=2, wall=CREAM, sign=RED),
    dict(id='pharmacy', title='봄약국', x=261.7, y=57.4, w=7.8, d=8.4, h=5.8, turn=2, wall=TILE, sign=GREEN),
    dict(id='diner', title='은하식당', x=246.2, y=71.4, w=8.0, d=9.0, h=5.6, turn=0, wall=CREAM, sign=RED),
    dict(id='workshop', title='온유공방', x=254.9, y=72.0, w=7.0, d=8.0, h=7.6, turn=0, wall=CONCRETE, sign=GREEN),
    dict(id='stationer', title='다온문구', x=262.6, y=71.8, w=6.0, d=9.0, h=4.1, turn=0, wall=BRICK, sign=GOLD),
]


class ShopModel(Model):
    def solid(self, center, size, color, physical=False):
        # Shallow applied panels need one outward face, not five hidden faces
        # embedded in the wall. Actual solid masses keep their full geometry.
        axis=min(range(3),key=lambda i:size[i])
        other=[i for i in range(3) if i!=axis]
        if not physical and size[axis]<=.05 and min(size[i] for i in other)>size[axis]*3:
            sign=1 if center[axis]>=0 else -1
            vertices=[]
            for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:
                p=list(center)
                p[axis]+=sign*size[axis]/2
                p[other[0]]+=a*size[other[0]]/2
                p[other[1]]+=b*size[other[1]]/2
                vertices.append(tuple(p))
            normal=[0,0,0];normal[axis]=sign
            self.panel(vertices,normal,color)
        else:
            super().solid(center,size,color,physical)

    def publish(self, town, name):
        path = 'assets/' + name + '.glb'
        solids = []
        for color, (vertices, faces) in self.groups.items():
            roughness, metallic = (0.23, 0.25) if color == GLASS else ((0.42, 0.65) if color == DARK else (0.88, 0))
            solid = (vertices, dict(baseColorFactor=color, roughnessFactor=roughness,
                                   metallicFactor=metallic), faces)
            solids.append(solid)
        town.payloads[path] = glb(solids, indexed=True, generator='mapeditor-q01-hanbit-block')
        town.doc['assets'].append(dict(id=name, path=path, attribution=ATTRIBUTION, collision=self.collision))

    def stroke(self, a, b, thickness, y, color):
        dx, dh = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dh)
        nx, nh = -dh/length*thickness/2, dx/length*thickness/2
        self.panel([(a[0]+nx,a[1]+nh,y),(b[0]+nx,b[1]+nh,y),
                    (b[0]-nx,b[1]-nh,y),(a[0]-nx,a[1]-nh,y)], (0,0,-1), color)

    def text(self, text, x, h, y, size, color=WHITE):
        for index, char in enumerate(text):
            for a, b in hangul(char):
                self.stroke((x+(index*1.15+a[0])*size,h+(1-a[1])*size),
                            (x+(index*1.15+b[0])*size,h+(1-b[1])*size),0.075*size,y,color)


def jamo(char):
    """Original geometric strokes in a unit square; every syllable is decomposed."""
    paths = {
        'ㄱ': [[(.1,.1),(.9,.1),(.9,.9)]], 'ㄴ': [[(.1,.1),(.1,.9),(.9,.9)]],
        'ㄷ': [[(.9,.1),(.1,.1),(.1,.9),(.9,.9)]],
        'ㄹ': [[(.1,.1),(.9,.1),(.9,.5),(.1,.5),(.1,.9),(.9,.9)]],
        'ㅁ': [[(.1,.1),(.9,.1),(.9,.9),(.1,.9),(.1,.1)]],
        'ㅂ': [[(.1,.1),(.1,.9),(.9,.9),(.9,.1)],[(.1,.48),(.9,.48)]],
        'ㅅ': [[(.5,.1),(.1,.9)],[(.5,.1),(.9,.9)]],
        'ㅈ': [[(.1,.1),(.9,.1)],[(.5,.1),(.1,.9)],[(.5,.1),(.9,.9)]],
        'ㅊ': [[(.35,.04),(.65,.04)],[(.1,.25),(.9,.25)],[(.5,.25),(.1,.9)],[(.5,.25),(.9,.9)]],
        'ㅋ': [[(.1,.1),(.9,.1),(.9,.9)],[(.1,.5),(.9,.5)]],
        'ㅍ': [[(.1,.1),(.9,.1)],[(.1,.9),(.9,.9)],[(.3,.1),(.3,.9)],[(.7,.1),(.7,.9)]],
        'ㅏ': [[(.4,.04),(.4,.96)],[(.4,.5),(.95,.5)]],
        'ㅑ': [[(.4,.04),(.4,.96)],[(.4,.35),(.95,.35)],[(.4,.65),(.95,.65)]],
        'ㅓ': [[(.6,.04),(.6,.96)],[(.05,.5),(.6,.5)]],
        'ㅗ': [[(.05,.8),(.95,.8)],[(.5,.1),(.5,.8)]],
        'ㅜ': [[(.05,.2),(.95,.2)],[(.5,.2),(.5,.9)]],
        'ㅠ': [[(.05,.2),(.95,.2)],[(.3,.2),(.3,.9)],[(.7,.2),(.7,.9)]],
        'ㅡ': [[(.05,.5),(.95,.5)]], 'ㅣ': [[(.5,.04),(.5,.96)]],
    }
    if char in ['ㅇ','ㅎ']:
        cy, ry = (.66,.28) if char == 'ㅎ' else (.5,.4)
        paths[char] = [[(.5+.4*math.cos(i*math.tau/16),cy+ry*math.sin(i*math.tau/16)) for i in range(17)]]
        if char == 'ㅎ': paths[char] += [[(.35,.05),(.65,.05)],[(.08,.25),(.92,.25)]]
    return [(a,b) for path in paths[char] for a,b in zip(path,path[1:])]


def hangul(char):
    value = ord(char)-0xAC00
    first = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'[value//588]
    vowel = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'[(value//28)%21]
    last = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'[value%28]
    height = .65 if last != ' ' else 1.0
    boxes = [(first,(0,0,.55,height)),(vowel,(.6,0,.4,height))] if vowel in 'ㅏㅑㅓㅣ' else [(first,(.15,0,.7,height*.62)),(vowel,(0,height*.64,1,height*.34))]
    if last != ' ': boxes.append((last,(.1,.73,.8,.27)))
    result = []
    for component,(x,y,w,h) in boxes:
        result.extend([((x+a[0]*w,y+a[1]*h),(x+b[0]*w,y+b[1]*h)) for a,b in jamo(component)])
    return result


def shop(town, spec):
    m = ShopModel()
    w,d,h = spec['w'],spec['d'],spec['h']
    front = -d/2
    # Mass is physically solid. Facade relief, recess shading and lettering are visual.
    m.solid((0,h/2,0),(w,h,d),spec['wall'],True)
    m.solid((0,.16,0),(w+.03,.32,d+.03),CONCRETE)
    m.solid((0,h+.10,0),(w+.20,.20,d+.20),CREAM)
    m.solid((0,h+.20,0),(w-.35,.02,d-.35),DARK)
    for x in [-w/2+.1,w/2-.1]: m.solid((x,h+.31,0),(.16,.35,d),spec['wall'])
    for y in [-d/2+.1,d/2-.1]: m.solid((0,h+.31,y),(w,.35,.16),spec['wall'])
    # Dark recessed ground floor plus display panes, timber mullions and a door.
    m.solid((0,1.1,front-.018),(w-.48,1.82,.028),DARK)
    for index in range(3):
        x = -w/2+.90+index*(w-1.8)/2
        m.solid((x,1.12,front-.038),((w-2.0)/3,1.55,.025),GLASS)
        m.solid((x,1.12,front-.058),(.045,1.58,.025),WOOD)
        # A warm interior band and display shelf read as depth without alpha sorting.
        m.solid((x,.57,front-.056),((w-2.0)/3,.07,.018),GOLD)
        for n in range(4):
            m.solid((x-.32+n*.2,.69,front-.069),(.10,.17+.04*(n%2),.025),[CREAM,RED,GREEN,GOLD][n])
    m.solid((w/2-.84,1.0,front-.082),(.7,1.8,.05),WOOD)
    m.solid((w/2-.84,1.17,front-.113),(.53,1.26,.015),GLASS)
    m.solid((w/2-.61,1.0,front-.13),(.025,.25,.025),GOLD)
    # Legible, individually authored shop signs and a blade sign on the corner.
    m.solid((0,2.23,front-.10),(w-.3,.62,.18),spec['sign'])
    size = .39 if len(spec['title']) == 4 else .43
    m.text(spec['title'],-len(spec['title'])*1.15*size/2,2.03,front-.197,size)
    m.solid((-w/2+.25,3.0,front-.52),(.12,.9,.9),spec['sign'])
    m.solid((-w/2+.17,3.0,front-.52),(.025,.48,.62),CREAM)
    # Angled canvas awning with alternating sewn panels and a scalloped valance.
    for i in range(10):
        x0 = -w/2+.12+(w-.24)*i/10
        x1 = -w/2+.12+(w-.24)*(i+1)/10
        color = spec['sign'] if i%2 else CREAM
        m.panel([(x0,2.0,front-.2),(x1,2.0,front-.2),(x1,1.85,front-.80),(x0,1.85,front-.80)],(0,1,0),color)
        m.solid(((x0+x1)/2,1.78,front-.80),(x1-x0,.14,.035),color)
    # Upper windows have sills, lintels, recessed shadows and thin sash frames.
    for level in range(max(1,int((h-2.7)/1.65))):
        height = 3.25+level*1.65
        for column in range(3):
            x = -w/2+.95+column*(w-1.9)/2
            m.solid((x,height,front-.018),(1.12,1.14,.035),DARK)
            m.solid((x,height+.02,front-.042),(.92,.94,.025),GLASS)
            m.solid((x,height,front-.058),(.045,.98,.02),CREAM)
            m.solid((x,height-.03,front-.063),(.94,.035,.02),CREAM)
            m.solid((x,height-.59,front-.13),(1.27,.10,.24),CREAM)
            m.solid((x,height+.61,front-.06),(1.27,.09,.10),CREAM)
        if spec['id'] in ['book','workshop']:
            m.solid((0,height-.64,front-.32),(w-.4,.12,.55),CONCRETE)
            m.solid((0,height-.13,front-.58),(w-.45,.045,.04),DARK)
            for n in range(13): m.solid((-w/2+.3+n*(w-.6)/12,height-.36,front-.58),(.028,.55,.028),DARK)
    # Avenue-facing side windows and service windows on the rear break up blank
    # walls while retaining the physical mass. Mortar relief is concentrated at eye level.
    for height in [1.25,3.35]:
        if height+0.6>h: continue
        for y in [-d*.24,d*.24]:
            for side in [-1,1]:
                x=side*(w/2+.02)
                m.solid((x,height,y),(.035,1.10,1.20),DARK)
                m.solid((x+side*.028,height,y),(.022,.90,1.02),GLASS)
                m.solid((x+side*.045,height,y),(.018,.93,.04),CREAM)
                m.solid((x+side*.05,height-.58,y),(.20,.09,1.30),CREAM)
        for x in [-w*.25,w*.25]:
            m.solid((x,height,d/2+.025),(1.1,1.05,.04),DARK)
            m.solid((x,height,d/2+.055),(.9,.85,.02),GLASS)
    # Fine horizontal coursing remains visible above the shops. Staggered brick
    # joints are concentrated in the lower side-wall band instead of spending
    # thousands of triangles on distant upper walls (Q01 package admission).
    step=.25 if spec['wall']==BRICK else .75
    for row in range(int(h/step)):
        z=.25+row*step
        if z>h-.1: break
        if z>2.65: m.solid((0,z,front-.008),(w,.014,.016),MORTAR if spec['wall']==BRICK else CONCRETE)
        for side in [-1,1]:
            x=side*(w/2+.009)
            m.panel([(x,z,-d/2),(x,z,d/2),(x,z+.013,d/2),(x,z+.013,-d/2)],(side,0,0),MORTAR if spec['wall']==BRICK else CONCRETE)
            if z<=1.0 and spec['wall']==BRICK:
                for col in range(int(d/.5)):
                    y=-d/2+(col+.5*(row%2))*.5
                    m.panel([(x,z,y),(x,z,y+.012),(x,z+step-.01,y+.012),(x,z+step-.01,y)],(side,0,0),MORTAR)
    # Roof stair enclosure, service ducts and ventilation fins; physical roof masses.
    m.solid((w*.22,h+.65,d*.20),(1.6,1.3,2),CONCRETE,True)
    m.solid((w*.22,h+1.35,d*.20),(1.75,.12,2.15),DARK)
    for x in [-w*.28,-w*.02]:
        m.solid((x,h+.34,d*.28),(1,.55,1.1),CREAM,True)
        for n in range(5): m.solid((x-.38+n*.19,h+.63,d*.28),(.045,.025,.85),DARK)
    # Utility conduit and faded lower-wall repairs, kept out of the driving lane.
    for side in [-1,1]:
        m.solid((side*(w/2+.05),h*.45,d*.30),(.07,h*.85,.07),DARK)
        m.solid((side*(w/2+.018),.65,d*.1),(.028,.52,1.1),CONCRETE)
    name = 'q01-'+spec['id']
    m.publish(town,name)
    town.place(name+'-instance',name,(spec['x'],0,spec['y']),spec['turn'])


def street_details(town):
    # Small separate objects retain spatial culling and collision ownership.
    m=ShopModel()
    m.solid((0,.30,0),(.72,.60,.72),CONCRETE,True)
    m.solid((0,.61,0),(.62,.02,.62),WOOD)
    for x,y,z in [(-.18,.85,-.12),(.19,1.02,.1),(-.02,1.13,.0)]:
        m.solid((x,y,z),(.38,.45,.38),GREEN)
    m.publish(town,'q01-planter')
    for i,(x,y) in enumerate([(249.3,61.5),(257.1,61.5),(250.65,67.65),(258.9,67.5)]):
        town.place('q01-planter-'+str(i),'q01-planter',(x,0,y))
    m=ShopModel()
    for x in [-.42,.42]: m.solid((x,.38,0),(.055,.76,.055),WOOD,True)
    m.solid((0,.72,0),(.94,.07,.64),WOOD,True)
    for i in [-1,1]:
        m.solid((0,.38,i*.65),(.75,.08,.32),WOOD,True)
        for x in [-.3,.3]:m.solid((x,.18,i*.65),(.06,.36,.25),DARK,True)
    m.publish(town,'q01-cafe-table')
    town.place('q01-cafe-table-instance','q01-cafe-table',(253.0,0,61.95))
    m=ShopModel()
    m.solid((0,.47,0),(.55,.94,.08),WOOD,True)
    m.solid((0,.50,-.047),(.46,.72,.01),DARK)
    for row in range(4):m.solid((0,.30+row*.12,-.054),(.28-row*.025,.012,.006),CREAM)
    m.solid((0,.04,0),(.65,.08,.45),WOOD,True)
    m.publish(town,'q01-menu')
    town.place('q01-cafe-menu','q01-menu',(255.6,0,61.65),2)
    # Local asphalt repair/cover plates sit outside the clear traffic lane. Their
    # centimetre-thin proxies declare the true footprint required by MapKit.
    m=ShopModel()
    m.solid((0,.008,0),(2.4,.012,1.35),(.24,.25,.24,1),True)
    for n in range(4):m.solid((-.8+n*.48,.016,0),(.035,.003,.9),(.30,.30,.28,1))
    m.publish(town,'q01-asphalt-repair')
    for i,(x,y) in enumerate([(243.6,62.6),(260.2,62.6)]):town.place('q01-asphalt-repair-'+str(i),'q01-asphalt-repair',(x,0,y))
    m=ShopModel()
    for i in range(32):
        a,b=i*math.tau/32,(i+1)*math.tau/32
        m.faces([(0,.027,0),(.32*math.cos(a),.027,.32*math.sin(a)),(.32*math.cos(b),.027,.32*math.sin(b))],[(0,2,1)],DARK)
    for n in range(5):m.solid((0,.031,-.21+n*.105),(.42,.004,.023),CONCRETE)
    m.collision.append(dict(center=[0,1,0],size_cm=[64,3,64]))
    m.publish(town,'q01-manhole')
    for i,(x,y) in enumerate([(248.5,66.1),(265.0,66.1)]):town.place('q01-manhole-'+str(i),'q01-manhole',(x,0,y))
    m=ShopModel()
    m.solid((0,.015,0),(.30,.025,.75),DARK,True)
    for n in range(7):m.solid((0,.032,-.30+n*.10),(.25,.01,.034),CONCRETE)
    m.publish(town,'q01-drain')
    for i,(x,y) in enumerate([(267.75,58),(267.75,69),(241.3,62.8)]):town.place('q01-drain-'+str(i),'q01-drain',(x,0,y))
    # A pair of compact loading/parking bays beside the courtyard, off the lane.
    m=ShopModel()
    for x in [-1.05,1.05]:m.solid((x,.018,0),(.06,.01,1.35),CREAM)
    m.solid((0,.018,.65),(2.16,.01,.06),CREAM)
    m.collision.append(dict(center=[0,1,0],size_cm=[216,1,135]))
    m.publish(town,'q01-parking')
    for i,x in enumerate([251.5,254]):town.place('q01-parking-'+str(i),'q01-parking',(x,0,66.45))
    m=ShopModel()
    m.solid((0,.019,0),(.10,.01,.85),CREAM)
    m.panel([(-.30,.025,-.2),(0,.025,-.63),(.30,.025,-.2),(0,.025,-.32)],(0,1,0),CREAM)
    m.collision.append(dict(center=[0,1,-10],size_cm=[60,2,107]))
    m.publish(town,'q01-arrow')
    town.place('q01-courtyard-arrow','q01-arrow',(263.2,0,66.1),1)


def connect_alley(town):
    import copy
    d=town.doc
    # Retain each original ID on its southern half (including the city spawn),
    # split exactly at the new junction, and preserve width/grade/material.
    for ident in ['korea-ns-1-1','korea-ns-2-1']:
        road=next(r for r in d['roads'] if r['id']==ident)
        point=[road['points'][0][0],0,6450]
        node='n-'+'-'.join(map(str,point))
        d['nodes'].append(dict(id=node,position=point,level=0))
        remainder=copy.deepcopy(road)
        remainder.update(id=ident+'-q01-north',points=[point,road['points'][-1]],**{'from':node})
        remainder['markings']['crosswalk_start']=False
        road.update(points=[road['points'][0],point],to=node)
        road['markings']['crosswalk_end']=False
        d['roads'].append(remainder)
    town.path('q01-service-lane',[(238,0,64.5),(269.75,0,64.5)],width=2,sidewalk=0)


def refine(town):
    d=town.doc
    d['map_id']=PROFILE
    d['provenance']['build_id']=PROFILE
    d['attributions'].append(ATTRIBUTION)
    removed={f'korea-block-1-1-{i}' for i in range(4)}
    # Only v4 furniture inside this lot/its immediate sidewalk is replaced.
    retained=[]
    replaced=[]
    for p in d['placements']:
        x,_,y=[v/100 for v in p['position']]
        if p['id'] in removed or (p['asset_id'].startswith('city-') and 240<=x<=268 and 51<=y<=77):
            replaced.append(p['id'])
        else:retained.append(p)
    d['placements']=retained
    connect_alley(town)
    for spec in SHOPS:shop(town,spec)
    street_details(town)
    # Keep public sidewalks/road markings, and retain a shelter clear of the lane.
    town.place('q01-bus-stop','city-bus-stop',(266.9,.12,73),3)
    town.place('q01-lamp','city-lamp',(266.9,.12,55))
    town.place('q01-bin','city-bin',(266.9,.12,75))
    town.city_report['buildings']+=len(SHOPS)-4
    town.city_report['props']={asset:sum(p['asset_id']==asset for p in d['placements']) for asset in town.city_report['props']}
    lot=next(lot for lot in town.city_report['lots'] if lot['id']=='korea-1-1')
    lot['buildings']=len(SHOPS)
    lot['footprint_m2']=sum(s['w']*s['d'] for s in SHOPS)
    town.city_report['quality_block']=dict(id='korea-1-1',name='한빛 골목',bounds_m=[238,48,272,80],
        alley=dict(center_y_m=64.5,clear_width_m=2.0,through_x_m=[240,268]),
        shops=[{k:s[k] for k in ['id','title','x','y','w','d','h','turn']} for s in SHOPS],
        replaced_placements=replaced,attribution=ATTRIBUTION,
        materials='Geometry mortar/tile joints and recess shading with glass/metal PBR; no image decode, external textures or baked shadow maps.',
        baseline='driving-school-town-v4')
