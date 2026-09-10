"""Hand-authored Village course studies; original geometry, no extracted assets.

Reference topology: KartRider Freeway and The Glove original minimaps.
Dimensions/grades are adapted to the compact town authoring profile; runtime uses actual metres.
"""
import math

REFERENCES = [
    {"title": "빌리지 고가의 질주 / Freeway", "url": "https://kartrider.fandom.com/zh/wiki/城镇_高速公路"},
    {"title": "빌리지 손가락 / The Glove", "url": "https://kartrider.fandom.com/zh/wiki/城镇_手指"},
]


def cylinder(t, name, x, y, radius, base=0, height=3):
    # Same authored 48-sided solid as the Editor Cylinder wall tool. MapKit
    # generates/clips the visible mesh and solid collision from these vertices.
    t.doc["buildings"].append(dict(id=name, footprint=[
        [round(100*(x+radius*math.cos(2*math.pi*i/48))),
         round(100*(y+radius*math.sin(2*math.pi*i/48)))] for i in range(48)],
        base_cm=round(base*100), height_cm=round(height*100),
        usage="industrial", material="concrete", roof="flat"))


class Course:
    def __init__(self, town, prefix, start, width):
        self.t, self.prefix, self.width = town, prefix, width
        self.points, self.ids, self.cylinders, self.openings = [start], [], [], []

    def add(self, name, points, kind=None, width=None):
        assert self.points[-1] == points[0], (name, self.points[-1], points[0])
        self.ids.append(self.t.path(self.prefix+"-"+name, points, width=width or self.width,
                                    kind=kind or ("elevated" if any(p[1]!=0 for p in points) else "ground")))
        self.points.extend(points[1:])

    def line(self, name, *points, **kwargs):
        self.add(name, [self.points[-1], *points], **kwargs)

    def turn(self, name, x, y, radius, start, end, height=0, solid=False):
        steps=max(4, round(abs(end-start)/15))
        points=[(round(x+radius*math.cos(math.radians(start+(end-start)*i/steps)),6), height,
                 round(y+radius*math.sin(math.radians(start+(end-start)*i/steps)),6)) for i in range(steps+1)]
        points[0]=self.points[-1]
        self.add(name, points)
        if solid:
            barrier_radius=radius-self.width/2-2.3
            cylinder(self.t, self.prefix+"-cylinder-"+name,x,y,barrier_radius,height-0.5,3.5)
            self.cylinders.append((x,y,barrier_radius))

    def walls(self):
        """Mitered narrow prisms, 8cm joints; no vehicle-sized bend gaps.

        Cylinder walls replace inner arc rails. Gate openings are explicit and
        limited to the side crossed by an access road. Grades use short spans.
        """
        sampled=[]
        for a,b in zip(self.points,self.points[1:]):
            dx,dy=b[0]-a[0],b[2]-a[2]
            length=math.hypot(dx,dy)
            cuts={0.0}
            for x,y,radius in self.openings:
                along=((x-a[0])*dx+(y-a[2])*dy)/(length*length)
                cross=abs((x-a[0])*dy-(y-a[2])*dx)/length
                if cross<radius+self.width:
                    for value in (along-radius/length,along,along+radius/length):
                        if 0<value<1: cuts.add(value)
            sampled.extend([tuple(a[j]+(b[j]-a[j])*v for j in range(3)) for v in sorted(cuts)])
        sampled.append(self.points[-1])
        points=[]
        for a,b in zip(sampled,sampled[1:]):
            count=max(1,math.ceil(abs(b[1]-a[1])/1.5))
            points.extend([tuple(a[j]+(b[j]-a[j])*k/count for j in range(3)) for k in range(count)])
        points.append(self.points[-1])
        closed=points[0] == points[-1]
        def normal(a,b):
            dx,dy=b[0]-a[0],b[2]-a[2]
            length=math.hypot(dx,dy)
            return (-dy/length,dx/length)
        normals=[normal(a,b) for a,b in zip(points,points[1:])]
        def offset(index,distance):
            if index in (0,len(points)-1):
                left,right=(normals[-1],normals[0]) if closed else (normals[max(0,index-1)],)*2
            else: left,right=normals[index-1],normals[index]
            denominator=1+left[0]*right[0]+left[1]*right[1]
            assert denominator>0.1, "Use an arc for a hairpin, not a zero-radius reversal"
            return ((left[0]+right[0])*distance/denominator,(left[1]+right[1])*distance/denominator)
        spans={-1:[],1:[]}
        for i,(a,b) in enumerate(zip(points,points[1:])):
            length=math.hypot(b[0]-a[0],b[2]-a[2])
            ux,uy=(b[0]-a[0])/length,(b[2]-a[2])/length
            for side in (-1,1):
                ring=[]
                for index,point,trim,dist in [(i,a,0.08,self.width/2+1),(i+1,b,-0.08,self.width/2+1),
                                             (i+1,b,-0.08,self.width/2+1.7),(i,a,0.08,self.width/2+1.7)]:
                    ox,oy=offset(index,dist*side)
                    ring.append((point[0]+ox+ux*trim,point[2]+oy+uy*trim))
                # Full circular collision closes each inside edge without seams.
                mid=(sum(p[0] for p in ring)/4,sum(p[1] for p in ring)/4)
                if any(math.hypot(mid[0]-cx,mid[1]-cy)<radius+1 for cx,cy,radius in self.cylinders): continue
                if any(math.hypot(mid[0]-x,mid[1]-y)<radius for x,y,radius in self.openings): continue
                spans[side].append(dict(id=f"{self.prefix}-rail-{i:03}-{side}",
                    footprint=[[round(x*100),round(y*100)] for x,y in ring],
                    base_cm=round((min(a[1],b[1])-0.6)*100),height_cm=round((abs(b[1]-a[1])+3.2)*100),
                    usage="industrial",material="concrete",roof="flat"))
        # Coalesce flat adjoining spans into one polygonal wall, preserving its
        # mitered outline. This lowers source validation work without relaxing
        # MapKit budgets or changing the generated collision contract.
        for records in spans.values():
            group=[]
            def flush():
                if not group: return
                first=group[0].copy()
                near=[group[0]["footprint"][0]]
                far=[group[0]["footprint"][3]]
                for j,r in enumerate(group):
                    if j<len(group)-1:
                        nxt=group[j+1]
                        near.append([round((r["footprint"][1][a]+nxt["footprint"][0][a])/2) for a in (0,1)])
                        far.append([round((r["footprint"][2][a]+nxt["footprint"][3][a])/2) for a in (0,1)])
                    else:
                        near.append(r["footprint"][1]);far.append(r["footprint"][2])
                first["footprint"]=near+far[::-1]
                self.t.doc["buildings"].append(first)
                group.clear()
            for record in records:
                if group and (len(group)>=12 or record["base_cm"]!=group[-1]["base_cm"] or record["height_cm"]!=group[-1]["height_cm"] or
                              math.dist(record["footprint"][0],group[-1]["footprint"][1])>30 or math.dist(record["footprint"][3],group[-1]["footprint"][2])>30): flush()
                group.append(record)
            flush()


def freeway(t):
    c=Course(t,"kart-freeway",(3750,0,4050),20)
    c.line("start",(3750,0,3930),(3750,0,3900))
    c.turn("first-right",3710,3900,40,0,-90)
    c.line("plaza",(3630,0,3860))
    c.turn("round-plaza",3630,3790,70,90,270,solid=True)
    c.line("ramp-approach",(3820,0,3720))
    c.turn("ramp-entry",3820,3670,50,90,0)
    # Structural junction aprons must meet flat terrain before the grade starts.
    c.line("climb",(3870,0,3650),(3870,20,3350))
    c.turn("highway-entry",3940,3350,70,180,270,height=20)
    c.line("highway-kink",(4010,20,3280),(4050,20,3330))
    c.line("highway-straight",(4700,20,3330))
    c.turn("highway-exit",4700,3430,100,-90,0,height=20)
    c.line("upper-approach",(4800,20,3750))
    c.turn("upper-left",4880,3750,80,180,90,height=20)
    c.line("upper-link",(5070,20,3830))
    c.turn("upper-right",5070,3750,80,90,0,height=20)
    c.line("hairpin-approach",(5150,20,3600))
    c.turn("upper-hairpin",5230,3600,80,180,360,height=20,solid=True)
    c.line("hairpin-exit",(5310,20,3900))
    c.turn("exit-left",5390,3900,80,180,90,height=20)
    c.line("exit-link",(5460,20,3980))
    c.turn("descent-entry",5460,4060,80,-90,0,height=20)
    # The outward dogleg leads into the signature downhill and last Z corners.
    c.line("descent",(5540,20,4080),(5540,0,4400),(5540,0,4420))
    c.turn("last-right",5500,4420,40,0,90)
    c.line("return-straight",(4150,0,4460))
    c.turn("z-first",4150,4420,40,90,180)
    c.line("z-link",(4110,0,4310))
    c.turn("z-second",4070,4310,40,0,-90)
    c.line("home-link",(3830,0,4270))
    c.turn("home-corner",3830,4190,80,90,180)
    c.line("home",(3750,0,4050))
    t.route("sky-kart","빌리지 고가의 질주 모방 코스",c.ids)
    # Split the western access at the course's start node.
    t.path("kart-freeway-access",[(3000,0,3300),(3350,0,3300),(3350,0,4050),(3750,0,4050)],width=14)
    c.openings.append((3750,4050,34))
    c.walls()
    t.building("kart-freeway-grandstand",4200,4140,600,70,12,"public")
    t.building("kart-freeway-paddock",3410,4080,170,90,10,"industrial")
    for i,x in enumerate(range(4110,4700,100)):
        t.building(f"kart-freeway-pier-{i}",x,3306,5,5,18,"industrial")
    t.location("kart-entry","고가의 질주 / 출발",(3750,0,4030),"kart-freeway-start","원형 광장 → 진입 램프 → 고가 직선 → 헤어핀 → 내리막 → Z자",180)
    t.location("kart-highway","고가의 질주 / 고가 직선",(4200,20,3330),"kart-freeway-highway-straight","높이 20m, 길이 650m의 고가 직선",-90)
    t.location("kart-downhill","고가의 질주 / 내리막",(5540,10,4240),"kart-freeway-descent","6.25% 내리막 뒤 감속과 Z자",0)


def finger(t):
    c=Course(t,"kart-finger",(4100,0,5540),16)
    # Four unequal fingers and three alternating inner U-turns: the glove outline.
    c.line("start",(5370,0,5540))
    c.turn("tip-1",5370,5495,45,90,-90,solid=True)
    c.line("finger-1-in",(4970,0,5450),(4860,0,5450))
    c.turn("inside-1",4860,5405,45,90,270,solid=True)
    c.line("finger-2-out",(5160,0,5360))
    c.turn("tip-2",5160,5315,45,90,-90,solid=True)
    c.line("finger-2-in",(4860,0,5270))
    c.turn("inside-2",4860,5225,45,90,270,solid=True)
    c.line("finger-3-out",(5100,0,5180),(5480,0,5180))
    c.turn("tip-3",5480,5135,45,90,-90,solid=True)
    c.line("finger-3-in",(5100,0,5090),(4860,0,5090))
    c.turn("inside-3",4860,5045,45,90,270,solid=True)
    c.line("finger-4-out",(4970,0,5000),(5220,0,5000))
    c.turn("tip-4",5220,4955,45,90,-90,solid=True)
    c.line("finger-4-in",(3980,0,4910))
    c.turn("wrist-entry",3980,5030,120,-90,-180)
    c.line("bridge-in",(3860,0,5070),(3860,4,5150),(3860,4,5170),(3860,0,5250),(3860,0,5270))
    c.line("clock-tower",(3860,0,5310),kind="tunnel",width=10)
    t.doc["roads"][-1]["clearance_cm"]=700
    c.line("bridge-out",(3860,0,5330),(3860,4,5410),(3860,4,5430),(3860,0,5500),(3860,0,5510))
    c.turn("wrist-return",3890,5510,30,180,90)
    c.line("home",(4100,0,5540))
    t.route("finger-kart","빌리지 손가락 모방 코스",c.ids)
    # Two narrow shortcut mouths use real graph nodes (never XY-only crossings).
    def split_at(ident,point):
        original=next(r for r in t.doc["roads"] if r["id"]==ident)
        index=original["points"].index([round(v*100) for v in point])
        assert 0<index<len(original["points"])-1
        t.doc["roads"].remove(original)
        first=t.path(ident+"-a",[tuple(v/100 for v in p) for p in original["points"][:index+1]],width=16,kind=original["kind"])
        second=t.path(ident+"-b",[tuple(v/100 for v in p) for p in original["points"][index:]],width=16,kind=original["kind"])
        route=next(r for r in t.routes if r["id"]=="finger-kart")
        i=route["roads"].index(ident)
        route["roads"][i:i+1]=[first,second]
    # Adjacent fingers shortcut: enough space to turn, but much narrower than main.
    split_at("kart-finger-finger-3-out",(5100,0,5180))
    split_at("kart-finger-finger-3-in",(5100,0,5090))
    t.path("kart-finger-shortcut-1",[(5100,0,5180),(5100,0,5090)],width=6)
    # First/fourth shortcut is unnecessary crossing; instead split tip-1's two arms.
    # A second tighter cut across the first fingertip follows the original rhythm.
    r=next(r for r in t.doc["roads"] if r["id"]=="kart-finger-start")
    r["points"].insert(1,[497000,0,554000]); r["widths_cm"].append(1600);r["surfaces"].append("asphalt")
    split_at("kart-finger-start",(4970,0,5540))
    split_at("kart-finger-finger-1-in",(4970,0,5450))
    t.path("kart-finger-shortcut-2",[(4970,0,5540),(4970,0,5450)],width=5)
    # Add the shortcut vertices to rail sampling so the small mouths open locally.
    for point in [(4970,0,5540)]:
        i=next(i for i,(a,b) in enumerate(zip(c.points,c.points[1:])) if a[2]==b[2]==point[2] and min(a[0],b[0])<point[0]<max(a[0],b[0]))
        c.points.insert(i+1,point)
    c.openings.extend([(5100,5180,24),(5100,5090,24),(4970,5540,24),(4970,5450,24),(4100,5540,32),(3860,5270,30),(3860,5310,30)])
    # The optional round thumb beside the wrist, entered through a real junction.
    thumb=Course(t,"kart-thumb",(3710,0,5270),12)
    thumb.turn("circle",3650,5270,60,0,360,solid=True)
    t.route("kart-thumb","손가락 엄지 원형 구간",thumb.ids)
    t.path("kart-finger-thumb-access",[(3860,0,5270),(3710,0,5270)],width=10)
    thumb.openings.append((3710,5270,30));thumb.walls()
    t.path("kart-finger-access",[(3000,0,5400),(3300,0,5680),(4100,0,5680),(4100,0,5540)],width=14)
    c.walls()
    # Clock tower is authored as two solid flanking towers; the tunnel road owns
    # the shared arch ceiling so the model and collision passage remain aligned.
    for side,x in [("west",3841),("east",3870)]:
        t.building("kart-finger-clock-"+side,x,5280,9,20,20,"public")
    t.building("kart-finger-paddock",4190,5600,240,70,8,"industrial")
    t.location("kart-finger","손가락 / 출발",(4300,0,5540),"kart-finger-start-a","길이가 다른 네 손가락, 7연속 U턴, 두 지름길",-90)
    t.location("kart-finger-hairpin","손가락 / 원통형 안쪽 벽",(5415,0,5495),"kart-finger-tip-1","반경 45m U턴 / 34.7m 원통형 충돌 벽",180)
    t.location("kart-finger-clock","손가락 / 시계탑",(3860,0,5290),"kart-finger-clock-tower","교량 → 폭 10m 시계탑 통로 → 교량")


def build_courses(t):
    freeway(t)
    finger(t)


def atlas(t, kind):
    """Detailed, reproducible plan from the authored road/wall coordinates."""
    from compact_town import atlas as compact_atlas
    return compact_atlas(t, kind)
