#!/usr/bin/env python3
"""Seven fixed, editable fictional regions. MIT; only detail variation uses a seed.
MapKit owns geometry, package serialization and reusable assets. This file owns
terrain, districts, connected street plans and suggested route waypoints only.
"""
import argparse
import copy
import json
import math
import random
import struct
import zlib
from pathlib import Path
from reference_maps import canonical, empty, road, sha

# Metres; independent plans deliberately follow different land-use boundaries.
PLANS = [
 dict(id="haeon",name="해온항",en="Haeon Harbour",theme="metropolis",size=[384,288],relief=18,
 description="산비탈 주거지와 시장 골목 아래로 항만 대로와 고가도로가 이어지는 동아시아 항구도시.",
 districts=["업무지구","구도심 시장","산비탈 주거지","창고 부두"],landmarks=["항만 크레인","전망 시계탑","고가 교차부"],
 outer=[[40,220],[140,220],[260,220],[346,206],[346,136],[320,88],[250,48],[160,40],[76,68],[38,128],[40,220]],
 inner=[[140,220],[132,174],[91,163],[84,121],[137,108],[180,126],[207,94],[250,48]],
 link=[[132,174],[203,182],[254,155],[280,112],[320,88]],
 sprint=[[346,206],[304,190],[260,180],[214,151],[174,106],[160,40]],
 courses=["항만 대로 순환","구도심 골목 순환","고가·산비탈 스프린트"]),
 dict(id="belmont",name="벨몽 계곡",en="Belmont Valley",theme="countryside",size=[448,256],relief=12,
 description="북프랑스에서 착안한 농촌. 밭 경계를 따르는 농로와 돌다리가 읍내·과수원·구릉 마을을 잇습니다.",
 districts=["작은 읍내","곡물 농지","과수원","구릉 마을"],landmarks=["돌다리","풍차 언덕","물레방앗간"],
 outer=[[36,192],[132,208],[244,215],[357,199],[405,160],[395,100],[340,55],[242,40],[140,58],[60,98],[36,192]],
 inner=[[132,208],[153,151],[119,121],[140,58]],link=[[153,151],[217,130],[267,150],[316,112],[340,55]],
 sprint=[[242,40],[270,67],[267,105],[217,130],[198,176],[244,215]],
 courses=["읍내·농장 순환","돌담 농로 순환","능선·물레방앗간 스프린트"]),
 dict(id="nord",name="노르드 항구",en="Nord Harbour",theme="polar",size=[512,224],relief=15,
 description="극지 항구의 창고와 색색의 주택, 연구 시설을 연결합니다. 열린 해안에서 암석 절개지로 올라갑니다.",
 districts=["항구 창고","색채 주택군","연구 시설","눈 언덕"],landmarks=["부두 크레인","관측소","암석 절개지"],
 outer=[[36,169],[148,176],[287,179],[433,168],[475,131],[437,83],[347,50],[237,42],[127,68],[54,109],[36,169]],
 inner=[[148,176],[154,125],[207,118],[211,82],[237,42]],link=[[154,125],[287,135],[345,113],[347,50]],
 sprint=[[36,169],[92,156],[116,122],[127,68],[176,52],[237,42]],
 courses=["항구 순환","창고·주택 기술 코스","관측소 오르막 스프린트"]),
 dict(id="safra",name="사프라 구릉",en="Safra Hills",theme="middle-eastern",size=[384,288],relief=20,
 description="레반트 석조 구도심. 중정 주택과 그늘진 시장, 테라스가 신시가지 대로와 올리브 과수원에 맞닿습니다.",
 districts=["신시가지","중정 시장","경사 테라스","올리브 과수원"],landmarks=["시장 시계탑","언덕 전망대","중정 광장"],
 outer=[[38,222],[149,232],[283,226],[343,182],[327,115],[280,65],[202,38],[112,61],[53,127],[38,222]],
 inner=[[149,232],[143,183],[111,166],[124,125],[163,111],[186,143],[220,121],[280,65]],
 link=[[143,183],[211,191],[255,164],[283,226]],
 sprint=[[38,222],[63,186],[95,193],[111,166],[124,125],[163,111],[144,84],[202,38]],
 courses=["신시가지 순환","시장·중정 골목 순환","언덕 전망대 스프린트"]),
 dict(id="red-wadi",name="붉은 와디",en="Red Wadi",theme="desert",size=[512,224],relief=22,
 description="사암 협곡과 마른 하천 바닥이 경로를 만드는 사막. 암벽 협로를 지나 넓은 분지와 정비소로 나옵니다.",
 districts=["열린 분지","사암 협곡","모래 능선","정비소 정착지"],landmarks=["쌍둥이 사암벽","능선 전망대","정비소"],
 outer=[[42,159],[150,183],[272,185],[387,173],[466,135],[429,78],[336,49],[240,36],[136,60],[68,98],[42,159]],
 inner=[[150,183],[169,138],[202,157],[232,113],[274,125],[307,84],[336,49]],
 link=[[232,113],[228,68],[240,36]],
 sprint=[[429,78],[382,91],[354,122],[307,84],[274,125],[232,113],[202,157],[150,183]],
 courses=["분지 순환","협곡 기술 코스","능선·정착지 스프린트"]),
 dict(id="kanupi",name="카누피 강 계곡",en="Kanupi River Valley",theme="jungle",size=[448,256],relief=24,
 description="보르네오 열대림에서 착안한 강 계곡. 층진 수관 아래의 흙길과 다리가 연구 캠프와 폭포 능선을 잇습니다.",
 districts=["연구 캠프","강변 정착지","울창한 숲","폭포 능선"],landmarks=["강 위 교량","폭포 절벽","연구 관측탑"],
 outer=[[42,190],[132,211],[227,203],[341,215],[404,169],[388,111],[329,69],[231,38],[137,54],[63,115],[42,190]],
 inner=[[132,211],[115,165],[159,137],[174,94],[231,38]],
 link=[[159,137],[213,159],[257,121],[299,152],[388,111]],
 sprint=[[231,38],[245,79],[221,110],[257,121],[299,152],[278,178],[341,215]],
 courses=["캠프·강변 순환","숲속 굽잇길 순환","폭포 능선 스프린트"]),
 dict(id="bansai",name="반사이 수변마을",en="Bansai Waterfront",theme="southeast-asian",size=[448,256],relief=7,
 description="태국 수변 생활권에서 착안했습니다. 처마 상점가와 고상 주택, 소교량, 논과 제방길이 이어집니다.",
 districts=["수변 상점가","운하 주택","시장 마당","논·제방"],landmarks=["시장 회관","운하 소교량","수변 종탑"],
 outer=[[42,193],[151,217],[261,214],[377,199],[411,144],[367,87],[274,51],[169,40],[87,83],[46,135],[42,193]],
 inner=[[151,217],[149,171],[102,149],[123,112],[172,119],[204,92],[274,51]],
 link=[[149,171],[215,162],[250,131],[316,150],[377,199]],
 sprint=[[169,40],[190,66],[204,92],[172,119],[215,162],[261,214]],
 courses=["제방·마을 순환","시장·소교량 순환","외곽 농지·상점가 스프린트"]),
]


def river_x(plan,z):
    return {"belmont":280,"kanupi":306,"bansai":310}.get(plan["id"],-1000)+4*math.sin(z/25)


def height(plan,x,z):
    w,h=plan["size"]
    # Independent landforms, all easing into a broad southern start apron.
    # Deterministic global coordinates keep adjacent 2m sample edges identical.
    def raw(a,b):
        u=a/w;v=b/h;n=max(0,(.64-v)/.64)
        land=plan["id"]
        if land=="haeon":profile=n**1.25*(.55+.45*math.exp(-((u-.30)/.28)**2))
        elif land=="belmont":profile=n*(.48+.20*math.sin(u*math.tau*1.8)+.16*math.sin(v*math.tau*2.1))
        elif land=="nord":profile=n**1.5*(.58+.42*math.exp(-((u-.60)/.18)**2))
        elif land=="safra":profile=n*(.75+.18*math.sin(u*math.pi))+.035*math.sin(n*math.pi*6)*min(1,n*8)
        elif land=="red-wadi":profile=n*(.32+.65*abs(math.sin((u-.48)*math.pi*1.7)))
        elif land=="kanupi":profile=n*(.48+.50*math.exp(-((u-.52)/.20)**2))+.10*math.sin(u*math.pi*3)**2*math.sin(n*math.pi)**2
        else:profile=n**2*(.38+.60*math.exp(-((u-.32)/.13)**2))
        return max(0,profile)*plan["relief"]*100
    value=raw(x,z)
    if plan["id"]=="haeon":
        distance=math.hypot(x-174,z-106)
        weight=max(0,min(1,(distance-24)/16))
        value=raw(174,106)*(1-weight)+value*weight
    if plan["id"] in ["belmont","kanupi","bansai"] and z>h*.66:
        bank=max(0,min(1,(8-abs(x-river_x(plan,z)))/5))
        entrance=max(0,min(1,(z-h*.66)/12))
        value-=180*bank*entrance
    return round(value)


def terrain(plan,cx,cz):
    samples=[[height(plan,cx*16+i*2,cz*16+j*2) for i in range(9)] for j in range(9)]
    raw=b"".join(b"\0"+b"".join(struct.pack(">H",v+200) for v in row) for row in samples)
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",9,9,16,0,0,0,0))+chunk(b"IDAT",zlib.compress(raw,9))+chunk(b"IEND",b"")


def distance(p,a,b):
    dx,dz=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dz)/(dx*dx+dz*dz)))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dz)


def build(plan,library):
    w,h=plan["size"];doc=empty("regional-"+plan["id"],w*100,1600)
    doc["bounds"]["max"]=[w*100,h*100];doc["surface_areas"]=[]
    theme=plan["theme"]
    environment_source=Path(__file__).resolve().parents[1]/"examples/world-themes-atmosphere"/theme/"document.json"
    doc["environment"]=json.loads(environment_source.read_text())["environment"]
    doc["environment"]["lights"]=[]
    doc["provenance"].update(tool_id="mapeditor-regional-maps",build_id="regional-miniatures",first_created="2026-09-20T00:00:00Z",last_edited="2026-09-20T00:00:00Z")
    doc["attributions"]=[dict(source="mapeditor-regional-maps",license="MIT",notice="Original fictional region: "+plan["en"]+". No surveyed data or external game assets.")]
    payloads={};assets={a["id"]:a for a in json.loads((library/"library.json").read_text())["assets"]};used=set();footprints=[]
    for cz in range(h//16):
        for cx in range(w//16):
            path=f"terrain/{cx}-{cz}.png";payloads[path]=terrain(plan,cx,cz)
            doc["heightmaps"].append(dict(cell=dict(x=cx,y=cz),path=path,spacing_cm=200,offset_cm=-200,step_cm=1,source_accuracy_cm=None))
    paths={};segments=[]
    surface="dirt" if plan["theme"]=="jungle" else "gravel" if plan["theme"]=="desert" else "asphalt"
    def network(name,points,width,kind="ground"):
        result=[]
        for i,(a,b) in enumerate(zip(points,points[1:])):
            ident=f"{name}-{i}";pa=[round(a[0]*100),height(plan,*a),round(a[1]*100)];pb=[round(b[0]*100),height(plan,*b),round(b[1]*100)]
            if kind=="elevated":
                pa[1]+=round(max(0,math.sin((i-1)/(len(points)-3)*math.pi))*800);pb[1]+=round(max(0,math.sin(i/(len(points)-3)*math.pi))*800)
            segment_kind=kind
            if plan["id"] in ["belmont","kanupi","bansai"] and min(a[1],b[1])>h*.66 and (a[0]-river_x(plan,a[1]))*(b[0]-river_x(plan,b[1]))<0:
                segment_kind="bridge";pa[1]=0;pb[1]=0
            node=lambda p:"n-"+"-".join(map(str,p))
            points_cm=[pa,pb]
            if kind=="elevated" and i in [1,len(points)-2]:
                points_cm.insert(1,[round(pa[0]+(pb[0]-pa[0])*.40),pa[1],round(pa[2]+(pb[2]-pa[2])*.40)])
            if kind=="elevated" and i==len(points)-3:
                points_cm.insert(-1,[round(pa[0]+(pb[0]-pa[0])*.60),pb[1],round(pa[2]+(pb[2]-pa[2])*.60)])
            if segment_kind=="bridge":
                left=[round(pa[j]+(pb[j]-pa[j])*.1) for j in range(3)]
                right=[round(pa[j]+(pb[j]-pa[j])*.9) for j in range(3)]
                road(doc,ident+"-approach-a",[pa,left],"ground",width*100,surface,start=node(pa),end=node(left))
                road(doc,ident,[left,right],"bridge",width*100,surface,start=node(left),end=node(right))
                road(doc,ident+"-approach-b",[right,pb],"ground",width*100,surface,start=node(right),end=node(pb))
            else:
                road(doc,ident,points_cm,"ground" if kind=="elevated" and i in [0,len(points)-2] else segment_kind,width*100,surface,start=node(pa),end=node(pb))
            result.append(ident);segments.append((a,b,width,ident))
        paths[name]=result
    network("artery",plan["outer"],10)
    network("lanes",plan["inner"],5)
    network("cross",plan["link"],6)
    network("ridge",plan["sprint"],8,"elevated" if plan["id"]=="haeon" else "ground")
    serial=0
    def place(asset,x,z,turn=0,base=None,ident=None,clearance=True):
        nonlocal serial
        serial+=1
        key="regional-"+asset;record=assets[key]
        # Conservative road and neighbour clearance uses actual proxy extents.
        proxies=record.get("collision",[])
        radius=max([math.hypot((abs(c["center"][0])+c["size_cm"][0]/2)/100,(abs(c["center"][2])+c["size_cm"][2]/2)/100) for c in proxies] or [8 if asset=="water" else 7])
        for proxy in record.get("convex_collision",[]):
            radius=max(radius,max(math.hypot(v[0],v[2])/100 for v in proxy["vertices"]))
        if any(asset.startswith(style+"-") for style in ["tower","shop","stone","farm","polar","warehouse"]):radius=max(radius,6)
        if clearance and plan["id"] in ["belmont","kanupi","bansai"] and z>h*.66-8 and abs(x-river_x(plan,z))<12+radius:return False
        if clearance and plan["theme"] in ["metropolis","polar","southeast-asian","jungle","countryside"] and z+radius>h-26:return False
        if clearance and any(distance((x,z),a,b)<width/2+radius+1.2 for a,b,width,_ in segments):return False
        if clearance and any(math.hypot(x-a,z-b)<radius+r+1 for a,b,r in footprints):return False
        edge_extent=8 if asset=="water" else radius
        if min(x,z)<edge_extent or x+edge_extent>w or z+edge_extent>h:return False
        used.add(key)
        # Foundational base is buried in the highest nearby terrain. Shared kit
        # plinths plus authored retaining blocks close any exposed slope side.
        base=height(plan,x,z)+(25 if asset in ["field","rice"] else 0) if base is None else base
        doc["placements"].append(dict(id=ident or "detail-"+str(serial),asset_id=key,position=[round(x*100),round(base),round(z*100)],quarter_turns=turn))
        if clearance:footprints.append((x,z,radius))
        return True
    rng=random.Random(20260920+PLANS.index(plan))
    theme=plan["theme"]
    styles={"metropolis":["tower","shop","shop","warehouse"],"countryside":["farm","farm","farm","stone"],"polar":["warehouse","polar","warehouse","polar"],"middle-eastern":["shop","stone","stone","farm"],"desert":["warehouse","stone","warehouse","stone"],"jungle":["stilt","stilt","warehouse","stilt"],"southeast-asian":["shop","stilt","shop","farm"]}[theme]
    # Districts follow terrain/coast bands, with dense market versus loose outskirts.
    district_counts=[0]*4
    for a,b,width,ident in segments:
        if ident.startswith("ridge") and theme=="metropolis":continue
        length=math.dist(a,b);dx=(b[0]-a[0])/length;dz=(b[1]-a[1])/length
        for d in range(16,int(length)-8,15 if theme in ["metropolis","middle-eastern","southeast-asian"] else 27):
            for side in [-1,1]:
                x=a[0]+dx*d-dz*side*(width/2+9+rng.random()*3);z=a[1]+dz*d+dx*side*(width/2+9+rng.random()*3)
                district=0 if x>w*.60 else 1 if z>h*.42 and z<h*.72 else 2 if z<=h*.42 else 3
                if theme in ["desert","jungle"] and (x>w*.45 or z<h*.60):continue
                variant=rng.randrange(4)
                if place(styles[district]+"-"+str(variant),x,z,(round(math.atan2(-dz,-dx)/(math.pi/2)))%4):district_counts[district]+=1
    # Infill parcels concentrate city blocks around the market/business streets;
    # gardens, fields and forest clearings retain deliberately different density.
    if theme in ["metropolis","middle-eastern","southeast-asian"]:
        for _ in range(1800):
            x=rng.uniform(18,w-18);z=rng.uniform(24,h-30)
            if theme=="metropolis" and x<w*.22 and z<h*.35:continue
            if theme=="southeast-asian" and x>w*.62:continue
            if theme=="middle-eastern" and x>w*.72:continue
            district=0 if x>w*.60 else 1 if h*.42<z<h*.72 else 2 if z<=h*.42 else 3
            style=styles[district]
            if theme=="middle-eastern" and district==1 and rng.random()<.5:style="courtyard"
            if place(style if style=="courtyard" else style+"-"+str(rng.randrange(4)),x,z,rng.randrange(4)):district_counts[district]+=1
    nature={"polar":"snow","desert":"sandstone","jungle":"canopy","southeast-asian":"palm","middle-eastern":"canopy","countryside":"canopy","metropolis":"canopy"}[theme]
    for _ in range(650 if theme=="jungle" else 300):
        x=rng.uniform(12,w-12);z=rng.uniform(12,h-12)
        if theme=="metropolis" and z>h*.38:continue
        if theme=="countryside" and x>w*.5:
            place("field",x,z)
        elif theme=="southeast-asian" and x>w*.6 and z<h*.5:place("rice",x,z)
        else:
            asset=nature if rng.random()<.8 else "rock"
            if asset=="sandstone":asset=["sandstone","sandstone-1","sandstone-2","sandstone-3"][rng.randrange(4)]
            place(asset,x,z,rng.randrange(4))
    landmarks=[]
    landmark_assets={"metropolis":["crane","bell-tower","observatory"],"polar":["crane","observatory","rock"],"countryside":["bell-tower","windmill","watermill"],"middle-eastern":["bell-tower","observatory","courtyard"],"desert":["sandstone","observatory","service-canopy"],"jungle":["observatory","waterfall","observatory"],"southeast-asian":["shop-3","quay","bell-tower"]}[theme]
    for i,(asset,point) in enumerate(zip(landmark_assets,[(w*.82,h*.88),(w*.47,20),(w*.13,h*.78)])):
        # Explicit landmark reserve, remove detail placements nearby before adding.
        if (theme=="metropolis" and i==2) or (theme in ["countryside","jungle"] and i==0) or (theme=="southeast-asian" and i==1):
            structure=next(r for r in doc["roads"] if r["kind"] in ["bridge","elevated"])
            aa,bb=structure["points"][0],structure["points"][-1]
            landmarks.append(dict(name=plan["landmarks"][i],position_m=[(aa[0]+bb[0])/200,(aa[2]+bb[2])/200],road_id=structure["id"]))
            continue
        if theme=="countryside" and i==2:point=(river_x(plan,h*.90)+15,h*.90)
        x,z=point
        candidates=[(x+dx,z+dz) for dx in range(-24,25,4) for dz in range(-24,25,4)]
        x,z=min((p for p in candidates if 14<p[0]<w-14 and 14<p[1]<h-14 and all(distance(p,a,b)>width/2+15 for a,b,width,_ in segments)),key=lambda p:math.dist(p,point))
        doc["placements"]=[p for p in doc["placements"] if math.hypot(p["position"][0]/100-x,p["position"][2]/100-z)>20]
        place(asset,x,z,ident="landmark-"+str(i),clearance=False)
        landmarks.append(dict(name=plan["landmarks"][i],position_m=[x,z],asset=asset))
    if theme in ["metropolis","polar"]:
        # Static water is contained behind the shoreline road; no live fluid physics.
        for x in range(16,w-15,16):place("water",x,h-8,base=35,clearance=False)
        for x in range(28,w-20,48):place("quay",x,h-21,base=0,clearance=False)
    if plan["id"] in ["belmont","kanupi","bansai"]:
        for z in range(round(h*.66)+16,h-8,16):
            x=river_x(plan,z)
            place("water",x,z,base=-85,clearance=False)
    # Ground buildings get slope foundations extending to their lowest corner.
    for p in list(doc["placements"]):
        if any(p["asset_id"].startswith("regional-"+s+"-") for s in ["tower","shop","stone","farm","polar","warehouse"]):
            x,z=p["position"][0]/100,p["position"][2]/100
            low=min(height(plan,x+dx,z+dz) for dx in [-6,6] for dz in [-6,6]);high=max(height(plan,x+dx,z+dz) for dx in [-6,6] for dz in [-6,6])
            p["position"][1]=high

    # Outboard piers and guards leave the road collision strip unobstructed.
    # Crossings omit columns at ground-road corridors; the deck spans them.
    if theme=="metropolis":
        for r in doc["roads"]:
            if r["kind"]!="elevated":continue
            for a,b in zip(r["points"],r["points"][1:]):
                length=math.hypot(b[0]-a[0],b[2]-a[2])/100;dx=(b[0]-a[0])/100/length;dz=(b[2]-a[2])/100/length
                for step in range(1,int(length/2.6)):
                    t=step*2.6/length;x=(a[0]+(b[0]-a[0])*t)/100;z=(a[2]+(b[2]-a[2])*t)/100;deck=a[1]+(b[1]-a[1])*t
                    for side in [-1,1]:
                        px=x-dz*side*4.3;pz=z+dx*side*4.3
                        if any(distance((px,pz),aa,bb)<ww/2+1.5 for aa,bb,ww,rid in segments if rid!=r["id"]):continue
                        doc["placements"]=[p for p in doc["placements"] if math.hypot(p["position"][0]/100-px,p["position"][2]/100-pz)>2.5]
                        place("rail-"+str(round(math.degrees(math.atan2(dz,dx))/15)*15%180),px,pz,base=deck,clearance=False)
                        if step%5==0 and len(r["points"])==2:
                            bottom=height(plan,px,pz);gap=math.ceil(abs(b[1]-a[1])/length*.5)+2;steps=math.ceil((deck-bottom-gap)/50)
                            if 1<=steps<=40:
                                # Separate rail and pier in the plane, per existing
                                # conservative public placement validation.
                                qx=x-dz*side*3;qz=z+dx*side*3
                                if all(distance((qx,qz),aa,bb)>ww/2+.7 for aa,bb,ww,rid in segments if not rid.startswith("ridge")):place("support-"+str(steps),qx,qz,base=deck-gap-steps*50,clearance=False)
    # Reuse baked regional writing; complete PNG/GLB/font attribution travels
    # with this map, independent of recipient UI language and installed fonts.
    sign_source=Path(__file__).resolve().parents[1]/"examples/world-themes-atmosphere"/theme
    sign_doc=json.loads((sign_source/"document.json").read_text())
    sign=copy.deepcopy(next(a for a in sign_doc["assets"] if a["id"]=="map-writing"))
    sign["id"]="regional-writing";assets[sign["id"]]=sign
    for path in (sign_source/"signs").iterdir():payloads["signs/"+path.name]=path.read_bytes()
    a,b=plan["outer"][:2];length=math.dist(a,b);dx=(b[0]-a[0])/length;dz=(b[1]-a[1])/length
    sx=a[0]+dx*30-dz*9;sz=a[1]+dz*30+dx*9
    doc["placements"]=[p for p in doc["placements"] if math.hypot(p["position"][0]/100-sx,p["position"][2]/100-sz)>6]
    place("writing",sx,sz,base=height(plan,sx,sz)+80,clearance=False,ident="district-sign")
    place("sign-post",sx,sz+.2,base=height(plan,sx,sz),clearance=False,ident="district-sign-post")
    for key in sorted(used):
        record=copy.deepcopy(assets[key]);doc["assets"].append(record);payloads[record["path"]]=(sign_source/record["path"] if key=="regional-writing" else library/record["path"]).read_bytes()
    # Route topology is authored, not a game codec. Technical loop uses inner
    # roads + part of the artery, while sprint has a separately authored ridge.
    inner_end=plan["outer"].index(plan["inner"][-1]);inner_start=plan["outer"].index(plan["inner"][0])
    technical=paths["lanes"]+paths["artery"][inner_end:]+paths["artery"][:inner_start]
    routes=[]
    # Each recommendation starts on a long shared avenue with room for 8 slots.
    byid={r["id"]:r for r in doc["roads"]}
    longest=max(range(len(technical)),key=lambda j:math.dist(byid[technical[j]]["points"][0],byid[technical[j]]["points"][-1]))
    technical=technical[longest:]+technical[:longest]
    sprint_start=plan["outer"].index(plan["sprint"][0])
    sprint=[paths["artery"][(sprint_start-1)%len(paths["artery"])]]+paths["ridge"]
    preceding=(sprint_start-1)%len(paths["artery"])
    while math.dist(byid[sprint[0]]["points"][0],byid[sprint[0]]["points"][-1])<8000:
        preceding=(preceding-1)%len(paths["artery"])
        sprint.insert(0,paths["artery"][preceding])
    for i,ids in enumerate([paths["artery"],technical,sprint]):
        waypoints=[]
        for ident in ids:
            r=byid[ident];a,b=r["points"][0],r["points"][-1]
            # Mid-segment gates avoid ambiguous junction surface labels.
            waypoints.append(dict(structural=r["kind"]!="ground",surface_id=ident,x_cm=round((a[0]+b[0])/2),y_cm=round((a[2]+b[2])/2)))
        first=byid[ids[0]]["points"];a,b=first[0],first[-1];dx=b[0]-a[0];dz=b[2]-a[2];length=math.hypot(dx,dz)
        assert length>=8000,(plan["id"],i,length)
        waypoints[:1]=[dict(structural=False,surface_id=ids[0],x_cm=round(a[0]+dx/length*d),y_cm=round(a[2]+dz/length*d)) for d in [4000,6500]]
        start=dict(x_cm=round(a[0]+dx/length*2000),y_cm=round(a[2]+dz/length*2000),surface_id=ids[0],heading_radians=math.atan2(-dx,-dz))
        routes.append(dict(id=["intro","technical","ridge"][i],name=plan["courses"][i],mode="sprint" if i==2 else "circuit",laps=1 if i==2 else 2,waypoints=waypoints,start=start))
    start=copy.deepcopy(routes[0]["start"])
    metadata={k:copy.deepcopy(v) for k,v in plan.items() if k not in ["outer","inner","link","sprint","courses"]}
    elevations=[height(plan,x,z) for x in range(0,w+1,2) for z in range(0,h+1,2)]
    metadata["elevation_range_m"]=[min(elevations)/100,max(elevations)/100]
    metadata["relief"]=round((max(elevations)-min(elevations))/100,2)
    metadata.update(version=1,cell_size_cm=1600,surface=surface,routes=routes,start=start,locations=[dict(id="start",title=plan["name"],**start)],landmark_records=landmarks,district_buildings=district_counts,source_files={"document.json":sha(canonical(doc)),**{p:sha(v) for p,v in payloads.items()}})
    return doc,payloads,metadata


def create(destination,library):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    (destination/".gdignore").write_text("")
    for plan in PLANS:
        doc,payloads,metadata=build(plan,Path(library));folder=destination/plan["id"];folder.mkdir()
        for path,data in {"document.json":canonical(doc),"region.json":canonical(metadata),**payloads}.items():
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return destination

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("destination",type=Path);p.add_argument("--library",type=Path,required=True);a=p.parse_args();create(a.destination,a.library)
