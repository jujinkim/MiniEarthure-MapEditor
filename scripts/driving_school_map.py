#!/usr/bin/env python3
"""Author an original MIT driving school town; only create NEW output directories.

Metres below are authoring conveniences. MapKit remains the sole compiler,
collision generator and package writer. No downloaded data or game dependency.
"""
import argparse
import html
import json
import math
from pathlib import Path
import struct
import zlib

from reference_maps import canonical, empty, rectangle, road, sha, summarize

PROFILE = "driving-school-town-v4"
SIZE_M = 6144
TERRAIN_GRID_M = 128
FACES = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
         (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2),
         (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]


def cm(point):
    return [round(value * 100) for value in point]


def arc(cx, cy, radius, start, end, steps=12, height=0):
    return [(cx + radius * math.cos(math.radians(start + (end-start)*i/steps)),
             height, cy + radius * math.sin(math.radians(start + (end-start)*i/steps)))
            for i in range(steps + 1)]


def oriented_faces(vertices):
    """Outward integer triangles, including after reflection into glTF axes."""
    center = [sum(p[a] for p in vertices) / len(vertices) for a in range(3)]
    result = []
    for face in FACES:
        a, b, c = [vertices[i] for i in face]
        u, v = [[p[i]-a[i] for i in range(3)] for p in (b, c)]
        normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        result.append(list(face if sum(normal[i]*(a[i]-center[i]) for i in range(3)) > 0
                           else (face[0], face[2], face[1])))
    return result


def box(center, size):
    x, h, y = center
    w, t, d = [v/2 for v in size]
    return [(x-w,h-t,y-d),(x+w,h-t,y-d),(x+w,h-t,y+d),(x-w,h-t,y+d),
            (x-w,h+t,y-d),(x+w,h+t,y-d),(x+w,h+t,y+d),(x-w,h+t,y+d)]


def glb(solids, indexed=False, generator=None):
    """Small static flat-shaded meshes, in glTF metres, with embedded materials."""
    binary, views, accessors, primitives, materials = bytearray(), [], [], [], []
    for solid in solids:
        vertices, color = solid[:2]
        vertices = [(x, h, -y) for x, h, y in vertices]
        positions, normals = [], []
        faces = oriented_faces(vertices) if len(solid) == 2 else [(a,c,b) for a,b,c in solid[2]]
        for face in faces:
            a, b, c = [vertices[i] for i in face]
            u, v = [[p[i]-a[i] for i in range(3)] for p in (b,c)]
            n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            length = math.sqrt(sum(x*x for x in n))
            positions.extend((a,b,c))
            normals.extend([tuple(x/length for x in n)]*3)
        element_indices = []
        if indexed:
            unique = {}
            for position, normal in zip(positions, normals):
                key = (position, normal)
                if key not in unique: unique[key] = len(unique)
                element_indices.append(unique[key])
            positions = [p for p, _ in unique]
            normals = [n for _, n in unique]
        indices = []
        for values in (positions, normals):
            offset = len(binary)
            binary.extend(b"".join(struct.pack("<fff", *v) for v in values))
            views.append(dict(buffer=0, byteOffset=offset, byteLength=len(binary)-offset, target=34962))
            accessors.append(dict(bufferView=len(views)-1, componentType=5126, count=len(values), type="VEC3",
                                  min=[min(p[i] for p in values) for i in range(3)],
                                  max=[max(p[i] for p in values) for i in range(3)]))
            indices.append(len(accessors)-1)
        pbr = color if isinstance(color, dict) else dict(baseColorFactor=color, metallicFactor=0, roughnessFactor=0.85)
        materials.append(dict(pbrMetallicRoughness=pbr))
        primitive = dict(attributes=dict(POSITION=indices[0], NORMAL=indices[1]), material=len(materials)-1, mode=4)
        if indexed:
            offset = len(binary)
            binary.extend(b"".join(struct.pack("<H", i) for i in element_indices))
            views.append(dict(buffer=0, byteOffset=offset, byteLength=len(binary)-offset, target=34963))
            accessors.append(dict(bufferView=len(views)-1, componentType=5123, count=len(element_indices), type="SCALAR"))
            primitive['indices'] = len(accessors)-1
            binary.extend(b"\0" * (-len(binary) % 4))
        primitives.append(primitive)
    doc = dict(asset=dict(version="2.0", generator=generator or PROFILE), scene=0, scenes=[dict(nodes=[0])],
               nodes=[dict(mesh=0)], meshes=[dict(primitives=primitives)], materials=materials,
               accessors=accessors, bufferViews=views, buffers=[dict(byteLength=len(binary))])
    data = canonical(doc)
    data += b" " * (-len(data) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28+len(data)+len(binary)) +
            struct.pack("<I4s", len(data), b"JSON") + data + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def flat_terrain():
    # Exact flat 128m grid. Local triangles prevent a whole-cell terrain polygon
    # from fragmenting combinatorially around the dense S curves and skidpad.
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    side=512//TERRAIN_GRID_M+1
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",side,side,16,0,0,0,0))+
            chunk(b"IDAT",zlib.compress(b"\0"*(side*(1+side*2)),9))+chunk(b"IEND",b""))


class Town:
    def __init__(self):
        self.doc = empty(PROFILE, SIZE_M*100, 51200)
        self.doc["attributions"] = [dict(source=PROFILE, license="MIT", notice=
            "Original driving school, city and static models. Kart circuits study the topology of KartRider Village Freeway and The Glove; dimensions are adapted. No extracted assets or surveyed exam layout.")]
        self.doc["provenance"].update(tool_id="mapeditor-driving-school", build_id=PROFILE,
            first_created="2026-09-10T00:00:00Z", last_edited="2026-09-11T00:00:00Z")
        self.payloads, self.routes, self.locations = {}, [], []
        self.payloads["terrain/flat.png"] = flat_terrain()
        self.doc["heightmaps"] = [dict(cell=dict(x=x,y=y),path="terrain/flat.png",spacing_cm=TERRAIN_GRID_M*100,
            offset_cm=0,step_cm=1,source_accuracy_cm=None) for y in range(12) for x in range(12)]

    def path(self, name, points, width=12, kind="ground", surface="asphalt", sidewalk=0):
        points = [cm(p) for p in points]
        # Shared endpoint coordinates are deliberate graph connections. Heights
        # are part of identity: the two kart crossing levels never share a node.
        node = lambda p: "n-" + "-".join(map(str, p))
        road(self.doc, name, points, kind, round(width*100), surface, node(points[0]), node(points[-1]))
        self.doc["roads"][-1]["sidewalk_cm"] = round(sidewalk*100)
        return name

    def chain(self, name, points, **kwargs):
        return [self.path(f"{name}-{i:02}", [a,b], **kwargs) for i,(a,b) in enumerate(zip(points,points[1:]))]

    def building(self, name, x, y, w, d, height, usage="residential", base=0):
        self.doc["buildings"].append(dict(id=name, footprint=rectangle(*cm((x,y,w,d))),
            base_cm=round(base*100), height_cm=round(height*100), usage=usage,
            material="brick" if usage=="residential" else "concrete", roof="gable" if usage=="residential" else "flat"))

    def trees(self, name, x, y, w, d, spacing=25, density=700):
        self.doc["zones"].append(dict(id=name, kind="orchard", polygon=rectangle(*cm((x,y,w,d))),
            spacing_cm=round(spacing*100), density_per_mille=density, exclusions=[]))

    def asset(self, name, solids, origin=(0,0,0), collision=True):
        path = f"assets/{name}.glb"
        self.payloads[path] = glb(solids)
        self.doc["assets"].append(dict(id=name, path=path, attribution=self.doc["attributions"][0], collision=[],
            convex_collision=[dict(vertices=[cm(v) for v in vertices], faces=oriented_faces([cm(v) for v in vertices]))
                              for vertices, _ in solids] if collision else []))
        self.place(name+"-instance", name, origin)

    def place(self, name, asset, position, turns=0):
        self.doc["placements"].append(dict(id=name, asset_id=asset, position=cm(position), quarter_turns=turns))

    def location(self, ident, title, point, surface, purpose, heading=0):
        self.locations.append(dict(id=ident, title=title, position_cm=cm(point), surface_id=surface,
                                   heading_degrees=heading, purpose=purpose))

    def route(self, ident, title, roads, closed=True):
        self.routes.append(dict(id=ident, title=title, roads=roads, closed=closed))


def streets(t):
    # The arterial grid is split at every gate; all districts are reachable by road.
    ys = [600,1100,1500,2100,2600,3000,3300,3900,4250,5400,5500]
    for side, x in [("west",300),("east",5800)]:
        t.chain("belt-"+side, [(x,0,y) for y in ys], width=24)
    for side,y in [("north",300),("south",5800)]:
        t.chain("belt-"+side, [(x,0,y) for x in [600,1800,3000,3300,4400,5500]], width=24)
    for name,cx,cy,a,b in [("nw",600,600,180,270),("ne",5500,600,270,360),
                            ("se",5500,5500,0,90),("sw",600,5500,90,180)]:
        t.path("belt-"+name, arc(cx,cy,300,a,b), width=24)
    t.chain("central-spine", [(3000,0,y) for y in [300,400,1100,1500,2100,2600,3000,3300,3900,4250,5400,5800]], width=24)
    t.chain("crosstown", [(x,0,3000) for x in [300,500,2650,3000,3300,4400,5500,5800]], width=24)
    # Through traffic uses the school perimeter; never cut across exam lanes.
    t.doc["roads"] = [r for r in t.doc["roads"] if r["id"] != "crosstown-01"]
    t.location("boulevard", "중앙 대로", (3000,0,1550), "central-spine-03", "장거리 자유 주행과 도시/스쿨 연결")


def city_and_village(t):
    for label,xs,ys,width in [("city",range(3300,5501,220),range(400,2601,220),20),
                              ("village",range(600,2401,300),range(500,1701,300),10)]:
        xs,ys=list(xs),list(ys)
        for j,y in enumerate(ys):
            t.chain(f"{label}-ew-{j:02}",[(x,0,y) for x in xs],width=width)
        for i,x in enumerate(xs):
            t.chain(f"{label}-ns-{i:02}",[(x,0,y) for y in ys],width=width)
        for j,y in enumerate(ys[:-1]):
            for i,x in enumerate(xs[:-1]):
                park = (i+3*j)%13==0
                if park:
                    t.trees(f"{label}-park-{i}-{j}",x+30,y+30,xs[1]-xs[0]-60,ys[1]-ys[0]-60,20)
                    continue
                if label=="city":
                    for k,(ox,oy) in enumerate([(35,35),(125,35),(35,125),(125,125)]):
                        height=18+(i*17+j*11+k*13)%65
                        t.building(f"city-block-{i}-{j}-{k}",x+ox,y+oy,50,50,height,
                                   "commercial" if (i+j+k)%3 else "residential")
                else:
                    for k in range(4):
                        t.building(f"village-home-{i}-{j}-{k}",x+35+(k%2)*160,y+35+(k//2)*160,30,36,7+(k%3)*2)
                    t.trees(f"village-garden-{i}-{j}",x+40,y+100,220,70,25)
    for j,y in [(0,400),(5,1500),(10,2600)]:
        t.path(f"city-west-gate-{j}",[(3000,0,y),(3300,0,y)],width=20)
        # North-east belt begins at Y=600; avoid inventing a crossing above it.
        if y>=600: t.path(f"city-east-gate-{j}",[(5500,0,y),(5800,0,y)],width=20)
    for x in [3300,4400,5500]:
        t.path(f"city-north-gate-{x}",[(x,0,300),(x,0,400)],width=20)
        t.path(f"city-south-gate-{x}",[(x,0,2600),(x,0,3000)],width=20)
    t.path("village-west-gate",[(300,0,1100),(600,0,1100)],width=12)
    t.path("village-east-gate",[(2400,0,1100),(3000,0,1100)],width=12)
    t.path("village-north-gate",[(1800,0,300),(1800,0,500)],width=12)
    t.location("city", "신도시 / 100개 블록", (4400,0,1550), "city-ns-05-05", "2.2 × 2.2km 도시, 큰 교차로와 고층 건물")
    t.location("village", "드라이빙 스쿨 마을", (1800,0,1150), "village-ns-04-02", "주택가·골목·공원·생활 도로")


def school(t):
    perimeter=[(650,0,2050),(800,0,2050),(2500,0,2050),(2650,0,2200),(2650,0,3000),
               (2650,0,3500),(2500,0,3650),(650,0,3650),(500,0,3500),(500,0,3000),(500,0,2200),(650,0,2050)]
    t.route("school-perimeter","스쿨 외곽",t.chain("school-loop",perimeter,width=16))
    t.path("school-gate",[(3000,0,2100),(2800,0,2100),(2650,0,2200)],width=16)
    t.path("license-gate",[(800,0,2050),(800,0,2200)],width=8)
    t.building("school-academy",1700,1820,280,110,18,"public")
    t.building("school-workshop",2150,1850,160,90,12,"industrial")
    t.building("school-control",670,2150,55,40,8,"public")
    ids=[]
    ids.append(t.path("license-start",[(800,0,2200),(800,0,2350)],width=6))
    ids.append(t.path("license-hill",[(800,0,2350),(800,0,2380),(800,2,2410),(800,2,2440),(800,0,2470),(800,0,2500)],width=6,kind="elevated"))
    ids+=t.chain("license-stop",[(800,0,2500),(800,0,2550),(800,0,2620),(800,0,2700)],width=6)
    ids.append(t.path("license-right-angle",[(800,0,2700),(950,0,2700),(950,0,2830),(1100,0,2830),(1100,0,3000)],width=6))
    ids.append(t.path("license-s",[(1100+65*math.sin(2*math.pi*i/32),0,3000+300*i/32) for i in range(33)],width=6))
    ids.append(t.path("license-exit",[(1100,0,3300),(1300,0,3300),(1450,0,3150),(1450,0,2700)],width=7))
    ids.append(t.path("license-acceleration",[(1450,0,2700),(1450,0,2200)],width=8))
    ids.append(t.path("license-return",[(1450,0,2200),(800,0,2200)],width=8))
    t.route("license","한국식 기능시험 연습 코스",ids)
    t.path("license-t-parking-approach",[(800,0,2620),(900,0,2620)],width=6)
    t.path("license-t-parking-bay",[(900,0,2620),(900,0,2580)],width=4)
    t.path("license-parallel-parking",[(800,0,2550),(835,0,2550),(835,0,2590)],width=4)
    t.path("school-inner-gate",[(1450,0,2200),(1700,0,2200),(1700,0,2350)],width=10)
    technical=[(1700,0,2350),(2300,0,2350),(2300,0,2460),(1900,0,2460),(1900,0,2580),
               (2360,0,2580),(2360,0,2800),(2050,0,2800),(2050,0,2950),(1700,0,2950),(1700,0,2350)]
    t.route("technical","급코너 / 더블 시케인",[t.path("technical-corners",technical,width=10)])
    t.path("s-gate",[(1700,0,2350),(1570,0,2350),(1570,0,3050),(1800,0,3050)],width=10)
    ss=[(1800+100*math.sin(4*math.pi*i/48),0,3050+470*i/48) for i in range(49)]
    t.route("slalom","더블 S자",[t.path("double-s",ss,width=10),
        t.path("double-s-return",[(1800,0,3520),(1570,0,3520),(1570,0,3050),(1800,0,3050)],width=10)])
    skid=arc(2250,3320,170,180,540,48)
    t.path("skidpad-gate",[(1800,0,3520),(1980,0,3520),(2080,0,3320)],width=10)
    t.route("skidpad","원선회",[t.path("skidpad",skid,width=20)])
    t.location("start","출발 / 기능시험장",(800,0,2250),"license-start","기본 진행 방향 +Y: 경사로 정지 → 주차 → 직각 → S자")
    t.location("technical","급코너와 시케인",(1700,0,2400),"technical-corners","90도 급회전과 연속 방향 전환")
    t.location("s-curves","연속 S자",(1800,0,3050),"double-s","470m, 두 번의 S자와 별도 복귀로")
    t.location("skidpad","원선회 패드",(2080,0,3320),"skidpad","반경 170m / 폭 20m",180)
    # Mark the stop plateau and parking surfaces using the road's own material;
    # no overlapping decorative collision or unsupported decal footprint.
    for r in t.doc["roads"]:
        if r["id"] == "license-hill": r["surfaces"][2] = "concrete"
        if r["id"] in ("license-t-parking-bay", "license-parallel-parking", "license-stop-02"):
            r["surfaces"] = ["concrete"] * len(r["surfaces"])
    t.asset("school-pylon",[(box((0,3,0),(2,6,2)),(1,0.66,0.08,1))],(791,0,2220))
    t.place("school-pylon-right","school-pylon",(809,0,2220))


def straights_and_hairpins(t):
    t.path("straight-west-gate",[(300,0,3900),(600,0,3900)],width=20)
    t.path("straight-east-gate",[(2600,0,3900),(3000,0,3900)],width=20)
    t.path("school-straight-gate",[(2650,0,3500),(2800,0,3700),(2600,0,3900)],width=16)
    ids=[t.path("two-km-straight",[(600,0,3900),(2600,0,3900)],width=20)]
    ids.append(t.path("straight-return",[(2600,0,3900),(2730,0,4000),(2600,0,4120),(600,0,4120),(470,0,4000),(600,0,3900)],width=14))
    t.route("straight","2km 가속 / 제동",ids)
    t.location("straight","2km 가속 직선",(650,0,3900),"two-km-straight","가속·최고속·제동, 4개 셀 경계",-90)
    t.asset("distance-marker",[(box((0,1,0),(1,2,1)),(0.95,0.6,0.08,1))],(700,0,3914))
    for distance in range(200,2000,100): t.place(f"distance-{distance}","distance-marker",(600+distance,0,3914))
    # Seven straights joined by six true semicircular 180° hairpins.
    ids=[t.path("hairpin-entry",[(650,0,4250),(800,0,4300)],width=12)]
    for row in range(7):
        y=4300+row*180
        a,b=(800,2300) if row%2==0 else (2300,800)
        ids.append(t.path(f"hairpin-straight-{row}",[(a,0,y),(b,0,y)],width=12))
        if row<6:
            ids.append(t.path(f"hairpin-turn-{row+1}",arc(b,y+90,90,-90,90 if row%2==0 else -270,20),width=12))
            t.trees(f"hairpin-garden-{row}",950,y+35,1200,110,40,800)
    ids.append(t.path("hairpin-return",[(2300,0,5380),(2580,0,5380),(2720,0,5500),(2600,0,5630),
                                      (600,0,5630),(450,0,5480),(450,0,4410),(650,0,4250)],width=12))
    t.route("hairpins","6연속 헤어핀",ids)
    t.path("hairpin-west-gate",[(300,0,4250),(650,0,4250)],width=14)
    t.path("hairpin-central-gate",[(3000,0,4250),(2820,0,4190),(650,0,4190),(650,0,4250)],width=12)
    t.location("hairpins","6연속 180° 헤어핀",(850,0,4300),"hairpin-straight-0","반경 90m, 폭 12m, 연속 감속과 탈출 가속",-90)


def kart(t):
    from kart_village_courses import build_courses
    build_courses(t)


def build():
    t=Town()
    streets(t)
    city_and_village(t)
    school(t)
    straights_and_hairpins(t)
    kart(t)
    from compact_town import compact
    compact(t)
    from city_expansion import expand
    expand(t)
    from shop_block import refine
    refine(t)
    from city_themes import refine as refine_city
    refine_city(t)
    return t


def atlas(t):
    """An overview drawn from the exact authoring coordinates, not a mockup."""
    from compact_town import atlas as compact_atlas
    return compact_atlas(t)


def create(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    t=build()
    report=summarize(t.doc,t.payloads,dict(routes=t.routes,locations=t.locations,
        start=dict(x_cm=2500,y_cm=7031,surface_id="license-start",heading_degrees=0),
        limitations=["Fictional Korean-style practice layout, not an official examination replica or scoring system.",
                     "Static city; traffic AI, race rules and vehicle selection belong to the consuming application.",
                     "KartRider Village layout studies: adapted dimensions and original models; not extracted game assets.",
                     "Geometry verification is separate from human driving feel and platform performance acceptance."]))
    from kart_village_courses import REFERENCES
    report["references"] = REFERENCES
    report["world_scale"] = 1.0
    report["profile"]=t.doc['map_id']
    report["city"]=t.city_report
    report["landmarks"]=dict(city_blocks=41,
        city_buildings=sum(b["id"].startswith("city-block-") for b in t.doc["buildings"]),
        village_homes=sum(b["id"].startswith("village-home-") for b in t.doc["buildings"]),
        guardrail_sections=sum("-rail-" in b["id"] for b in t.doc["buildings"]),
        hairpin_turns=6,straight_m=62.5,kart_highway_height_m=0.625, finger_u_turns=7,
        cylinder_walls=sum("-cylinder-" in b["id"] for b in t.doc["buildings"]))
    report["terrain"]=dict(description="exact synthetic flat PNG16, 4m grid; compact practice hill, elevated freeway and two vehicle-clearance bridges",
                           spacing_cm=400,source_accuracy_cm=None)
    from kart_village_courses import atlas as course_atlas
    files={"document.json":canonical(t.doc), **t.payloads,
           "driving.json":(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode(),
           "overview.svg":atlas(t).encode(),
           "village-freeway.svg":course_atlas(t,"freeway").encode(),
           "village-finger.svg":course_atlas(t,"finger").encode()}
    for name,data in files.items():
        target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as stream: stream.write(data)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path,help="new project directory; existing paths are refused")
    result=create(parser.parse_args().destination)
    print(json.dumps({k:result[k] for k in ("map_id","cell_count","counts","road_centerline_planar_m")},indent=2))
