"""Q03: original MIT neighbourhoods using the Q01 modelling vocabulary.

Actual metres; public authoring only. The Hanbit lot, practice courses and all
spawns stay fixed. Shared source assets do not imply shared renderer resources.
"""
import copy
from driving_school_map import cm, glb
from shop_block import ShopModel, SHOPS, BRICK, CREAM, CONCRETE, GLASS, WOOD, GREEN, RED, GOLD, DARK

PROFILE = 'driving-school-town-v6'
ATTRIBUTION = dict(source='mapeditor-q03-city-themes', license='MIT', notice=
    'Original fictional residential lanes, covered market, offices, hotels and civic plazas. Procedural geometry and materials; no external models, fonts, textures or user datasets.')


class ThemeModel(ShopModel):
    def publish(self, town, name):
        path = 'assets/' + name + '.glb'
        town.payloads[path] = glb([(vertices, dict(baseColorFactor=color,
            roughnessFactor=.23 if color == GLASS else .85,
            metallicFactor=.25 if color == GLASS else 0), faces)
            for color, (vertices, faces) in self.groups.items()], indexed=True, generator=ATTRIBUTION['source'])
        town.doc['assets'].append(dict(id=name, path=path, attribution=ATTRIBUTION, collision=self.collision))

    def mass(self, w, d, h, tone, x=0, y=0, base=0):
        self.solid((x, base+h/2, y), (w, h, d), tone, True)
        self.solid((x, base+.16, y), (w+.04, .32, d+.04), CONCRETE)
        self.solid((x, base+h+.08, y), (w+.18, .16, d+.18), CREAM)
        self.solid((x, base+h+.18, y), (w-.25, .025, d-.25), DARK)

    def windows(self, w, d, h, x=0, y=0, base=0, balcony=False):
        # Full four-sided recessed window frames, sill shadows and street doors.
        for side in range(4):
            span = w if side < 2 else d
            columns = max(2, int(span/2.2))
            sign = -1 if side % 2 == 0 else 1
            def panel(u, z, depth, size, color):
                if side < 2:
                    self.solid((x+u, z, y+sign*(d/2+depth)), size, color)
                else:
                    self.solid((x+sign*(w/2+depth), z, y+u), (size[2], size[1], size[0]), color)
            for level in range(max(1, int(h/2.6))):
                z = base+1.45+level*2.6
                for col in range(columns):
                    u = (col+.5)*span/columns-span/2
                    panel(u,z,.02,(1.3,1.65,.035),DARK)
                    panel(u,z+.03,.045,(1.12,1.4,.025),GLASS)
                    panel(u,z,.062,(.045,1.4,.02),CREAM)
                    panel(u,z-.86,.12,(1.44,.12,.22),CREAM)
                if balcony and side == 0 and level > 0:
                    self.solid((x,z-.96,y-d/2-.35),(w-.4,.12,.72),CONCRETE)
                    self.solid((x,z-.28,y-d/2-.68),(w-.5,.055,.045),DARK)
                    for n in range(9):
                        self.solid((x-w/2+.3+n*(w-.6)/8,z-.60,y-d/2-.68),(.04,.65,.04),DARK)
            panel(span*.24,base+1.0,.065,(.85,1.95,.07),WOOD)
            panel(span*.24,base+1.17,.105,(.66,1.3,.02),GLASS)

    def services(self, w, d, h):
        self.solid((w*.2,h+.55,d*.22),(1.5,1.1,1.8),CONCRETE,True)
        self.solid((w*.2,h+1.15,d*.22),(1.65,.13,1.95),DARK)
        self.solid((-w*.22,h+.25,d*.20),(1.1,.5,1.25),CREAM,True)
        for n in range(5):
            self.solid((-w*.22-.42+n*.21,h+.52,d*.20),(.055,.035,1),DARK)


def library(town):
    specs = {}
    def publish(m, name, w, d, h):
        name = 'q03-'+name
        m.publish(town,name)
        specs[name] = dict(w=w,d=d,h=h)
        return name
    for index,(w,d,h,tone) in enumerate([(6.6,8.4,5.5,BRICK),(7.0,8.0,8.1,CREAM)]):
        m=ThemeModel();m.mass(w,d,h,tone);m.windows(w,d,h,balcony=True);m.services(w,d,h)
        # Eye-level brick/tile joints, repairs, side conduits and separate entry.
        for row in range(8):
            for side in [-1,1]:
                m.solid((side*(w/2+.01),.3+row*.24,0),(.016,.014,d),CREAM if index==0 else CONCRETE)
        m.solid((w/2+.04,h*.4,d*.25),(.07,h*.8,.07),DARK)
        m.solid((-.8,2.28,-d/2-.25),(2.3,.12,.6),GREEN)
        publish(m,'home-'+str(index),w,d,h)
    m=ThemeModel();w,d,h=10,8,3.4
    m.mass(w,d,h,BRICK);m.windows(w,d,h)
    # Three pitched roof bays with actual stepped roof collision, not a box
    # proxy filling the outdoor aisle. Loading doors and clerestory glazing.
    for bay in [-1,0,1]:
        cx=bay*3.3
        m.panel([(cx-1.65,h,-4.2),(cx,h+1.5,-4.2),(cx,h+1.5,4.2),(cx-1.65,h,4.2)],(-1,1,0),GREEN)
        m.panel([(cx,h+1.5,-4.2),(cx+1.65,h,-4.2),(cx+1.65,h,4.2),(cx,h+1.5,4.2)],(1,1,0),GREEN)
        for step in range(2):m.solid((cx,h+.25+step*.5,0),(2.2-step*1.1,.5,8),GREEN,True)
        m.solid((cx,2,-4.025),(2.6,2.5,.035),DARK)
        m.solid((cx,3,-4.05),(2.35,.40,.02),GLASS)
    m.solid((0,3.55,-4.25),(7,.62,.15),RED)
    m.text('한빛시장',-1.1,3.34,-4.34,.47)
    publish(m,'market-hall',w,d,4.9)
    for name,w,d,h,tone in [('office',13,11,21,CONCRETE),('hotel',13,10,17,CREAM)]:
        m=ThemeModel();m.mass(w,d,3,tone);m.windows(w,d,3)
        tw,td=w-3,d-2
        m.mass(tw,td,h-3,tone,base=3);m.windows(tw,td,h-3,base=3,balcony=name=='hotel')
        m.services(tw,td,h)
        for x in [-w/2+.2,w/2-.2]:m.solid((x,1.5,-d/2-.32),(.22,3,.45),tone,True)
        m.solid((0,2.9,-d/2-.45),(w+.15,.18,1.15),GREEN if name=='hotel' else DARK)
        if name=='office':
            for x in [-4,-2,0,2,4]:m.solid((x,12,-td/2-.09),(.10,18,.18),CREAM)
            m.mass(5,5,1.5,CONCRETE,base=h)
        else:
            m.solid((tw/2-.25,h-1,-td/2-.15),(.75,3,.18),RED)
            for z in range(3):m.solid((tw/2-.25,h-2+z,-td/2-.25),(.44,.35,.025),GOLD)
        publish(m,name,w,d,h)
    m=ThemeModel();m.mass(13,7,5.4,CREAM);m.windows(13,7,5.4)
    for x in [-5.7,-2.85,0,2.85,5.7]:m.solid((x,1.4,-4.25),(.18,2.8,.18),CONCRETE,True)
    m.solid((0,2.82,-3.95),(13.4,.18,1.2),GREEN)
    m.solid((0,5.65,0),(8,.35,4),BRICK,True)
    m.services(13,7,5.4)
    publish(m,'arcade',13,7,5.9)
    # Original market produce stand: individual legs are its real collision.
    m=ThemeModel()
    for x in [-.7,.7]:
        for y in [-.4,.4]:m.solid((x,.48,y),(.08,.96,.08),WOOD,True)
    m.solid((0,.98,0),(1.55,.12,.95),WOOD,True)
    for x in [-.5,0,.5]:
        m.solid((x,1.13,0),(.43,.18,.7),WOOD)
        for y in [-.18,.18]:m.solid((x,1.29,y),(.25,.18,.24),GOLD if x==0 else RED)
    for x in [-.76,.76]:m.solid((x,1.05,.45),(.055,2.1,.055),DARK,True)
    for n in range(8):m.solid((-.7+n*.2,2.15,0),(.2,.08,1.1),CREAM if n%2 else GREEN)
    publish(m,'stall',1.6,1.1,2.2)
    m=ThemeModel();m.mass(.9,.9,4.7,BRICK)
    for y in [-.47,.47]:
        m.solid((0,4.03,y),(.72,.72,.035),CREAM)
        m.solid((0,4.12,y*1.05),(.035,.3,.018),DARK)
        m.solid((.12,4.03,y*1.05),(.27,.035,.018),DARK)
    m.solid((0,4.9,0),(1.5,.2,1.5),GREEN)
    publish(m,'clock',1.5,1.5,5)
    m=ThemeModel()
    # Raised stone basin; opaque shallow blue stone suggests water without a
    # new water shader, transparency contract, or floating collision cover.
    m.solid((0,.12,0),(3.6,.24,2.6),CONCRETE,True)
    for x in [-1.7,1.7]:m.solid((x,.38,0),(.2,.52,2.6),CREAM,True)
    for y in [-1.2,1.2]:m.solid((0,.38,y),(3.4,.52,.2),CREAM,True)
    m.solid((0,.26,0),(3.1,.025,2.1),GLASS)
    m.solid((0,1,0),(.35,1.5,.35),GOLD,True)
    publish(m,'fountain',3.6,2.6,1.75)
    return specs


def connect_lane(town, lot, lane_y):
    """Split actual existing street segments, including a previously split edge."""
    district,i,j=lot['id'].split('-');i=int(i);j=int(j)
    xs=[204,238,272,306,340,376]
    left=xs[i]+(2.25 if xs[i]==272 else 0)
    right=xs[i+1]-(2.25 if xs[i+1]==272 else 0)
    for x in [left,right]:
        point=cm((x,0,lane_y))
        node='n-'+'-'.join(map(str,point))
        if any(n['id']==node for n in town.doc['nodes']):continue
        road=next(r for r in town.doc['roads'] if r['id'].startswith('korea-ns-') and
            r['points'][0][0]==point[0] and r['points'][0][2]<point[2]<r['points'][-1][2])
        remainder=copy.deepcopy(road)
        remainder.update(id=road['id']+'-q03-'+str(point[2]),points=[point,road['points'][-1]],**{'from':node})
        remainder['markings']['crosswalk_start']=False
        road.update(points=[road['points'][0],point],to=node)
        road['markings']['crosswalk_end']=False
        town.doc['nodes'].append(dict(id=node,position=point,level=0))
        town.doc['roads'].append(remainder)
    town.path('q03-lane-'+lot['id'],[(left,0,lane_y),(right,0,lane_y)],width=2,sidewalk=0)
    return dict(y_m=lane_y,x_m=[left,right],width_m=2)


def refine(town):
    d=town.doc
    specs=library(town)
    specs.update({'q01-'+s['id']:{k:s[k] for k in ['w','d','h']} for s in SHOPS})
    d['map_id']=PROFILE;d['provenance']['build_id']=PROFILE;d['attributions'].append(ATTRIBUTION)
    removed=[p['id'] for p in d['placements'] if p['id'].startswith(('korea-block-','sky-block-'))]
    d['placements']=[p for p in d['placements'] if p['id'] not in removed]
    lots=[]
    for lot in town.city_report['lots']:
        if lot['id']=='korea-1-1':continue
        district,i,j=lot['id'].split('-');i=int(i);j=int(j)
        x0,y0,x1,y1=lot['bounds'];cx=(x0+x1)/2;cy=(y0+y1)/2
        theme=('shopping' if j<2 else 'market' if j==2 else 'residential') if district=='korea' else ['office','hotel','plaza'][(i+j)%3]
        buildings=[];details=[]
        def place(asset,x,y,turn=0,detail=False):
            target=details if detail else buildings
            ident='q03-'+lot['id']+('-detail-' if detail else '-building-')+str(len(target))
            town.place(ident,asset,(cx+x,0,cy+y),turn)
            target.append(dict(id=ident,asset=asset,x=cx+x,y=cy+y,turn=turn,**specs.get(asset,{})))
        def row(assets,y,turn):
            width=sum(specs[a]['w'] for a in assets)+.55*(len(assets)-1)
            x=-width/2
            for col,asset in enumerate(assets):
                w=specs[asset]['w']
                place(asset,x+w/2,y+(col%2)*(.2 if y>0 else -.2),turn)
                x+=w+.55
        if theme in ['shopping','residential']:
            for side in range(2):
                count=3 if side==0 or i%2==0 else 2
                models=[('q01-'+SHOPS[(i+side*3+col)%6]['id']) if theme=='shopping' else 'q03-home-'+str((i+side+col)%2) for col in range(count)]
                row(models,-6.8 if side==0 else 6.8,2 if side==0 else 0)
            place('q01-planter',-3,1.6,detail=True)
            if theme=='shopping' and i%2:
                place('q01-cafe-table',-10.7,6.8,detail=True)
            else:
                place('q01-menu' if theme=='shopping' else 'city-bench',3,1.6,detail=True)
        elif theme=='market':
            row(['q01-'+SHOPS[(i+col)%6]['id'] for col in range(3)],-6.8,2)
            place('q03-market-hall',-6,6.5)
            place('q01-workshop',6,6.8)
            for x in [-9,-6,-3]:place('q03-stall',x,1.8,detail=True)
            place('q01-planter',8,1.8,detail=True)
        elif theme=='office':
            place('q03-office',-9,6.5,i%2*2)
            place('q03-office',8,-7,(i+1)%2*2)
            place('q01-cafe',-10,-9.5,2)
            place('q01-pharmacy',9,9.5)
            place('q03-clock',0,2,detail=True)
            place('city-bench',0,5,detail=True)
        elif theme=='hotel':
            place('q03-hotel',-9,6)
            place('q03-arcade',6.5,8.5)
            place('q01-book',-9,-9,2)
            place('q01-diner',8,-9,2)
            place('q03-fountain',4,0,detail=True)
            for x in [0,8]:place('q01-planter',x,2,detail=True)
        else:
            place('q03-arcade',7,10)
            place('q03-office',-9,-5,2)
            place('q01-cafe',9,-8,2)
            place('q03-fountain',6,3,detail=True)
            place('q03-clock',0,5,detail=True)
            for x in [3,9]:place('city-bench',x,4.8,detail=True)
        lane=connect_lane(town,lot,cy) if theme in ['market','residential'] else None
        lot.update(buildings=len(buildings),footprint_m2=sum(b['w']*b['d'] for b in buildings),theme=theme)
        lots.append(dict(id=lot['id'],theme=theme,center_m=[cx,cy],bounds_m=lot['bounds'],buildings=buildings,details=details,lane=lane))
    # Remove only old street furniture intersecting explicit new lane openings.
    # Other v5 furniture and its collision remain exactly as authored.
    from shapely.geometry import box as rectangle
    lanes=[rectangle(*[l['lane']['x_m'][0],l['lane']['y_m']-1.05,l['lane']['x_m'][1],l['lane']['y_m']+1.05]) for l in lots if l['lane']]
    assets={a['id']:a for a in d['assets']}
    from shapely.affinity import rotate,translate
    retained=[]
    for p in d['placements']:
        conflict=False
        if p['id'].startswith('city-'):
            for shape in assets[p['asset_id']].get('collision',[]):
                x,_,y=[v/100 for v in shape['center']];w,_,depth=[v/100 for v in shape['size_cm']]
                poly=translate(rotate(rectangle(x-w/2,y-depth/2,x+w/2,y+depth/2),90*p['quarter_turns'],origin=(0,0)),p['position'][0]/100,p['position'][2]/100)
                conflict |= any(poly.intersects(lane) for lane in lanes)
        if conflict:removed.append(p['id'])
        else:retained.append(p)
    d['placements']=retained
    # Retire the v4 library from the active package only after every placement
    # has been replaced. The frozen v5 source/package retains its exact bytes.
    used={p['asset_id'] for p in d['placements']}
    retired_assets=[a for a in d['assets'] if a['id'] not in used]
    d['assets']=[a for a in d['assets'] if a['id'] in used]
    for asset in retired_assets:town.payloads.pop(asset['path'])
    town.city_report['buildings']=6+sum(len(l['buildings']) for l in lots)
    town.city_report['props']={asset:sum(p['asset_id']==asset for p in d['placements']) for asset in town.city_report['props']}
    town.city_report['themes']=dict(profile=PROFILE,baseline='driving-school-town-v5',lots=lots,
        replaced_placements=removed,retired_assets=[a['id'] for a in retired_assets],attribution=ATTRIBUTION)
