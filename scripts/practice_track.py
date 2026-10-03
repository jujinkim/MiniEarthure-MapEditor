#!/usr/bin/env python3
"""Reproducible MIT practice track. Only writes a NEW output directory.
All geometry is authored Source; MapKit compiles and verifies the execution package.
No human completion evidence is created by this tool.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

NAMES = ["Drive, brake and reverse", "Gentle right turn", "Gentle left turn",
         "Right drift", "Left drift", "Jump", "Jump and glide", "Grind and balance",
         "Air turn", "Boost climb"]

def source():
    d = dict(original_seed=None, grounded_supports=False,
             settings=dict(seed=101, circuit=False, duration_seconds=120, difficulty="easy",
                           categories=["driving"], time_minutes=720),
             instances=[], connections=[], paths=[], checkpoints=[], actions=[], attachments=[],
             grind_lines=[], structures=[])
    pos = [0, 0, 0]
    heading = 0
    width = 800
    def add(name, points, flight=False, target_width=None):
        nonlocal pos, width
        w = width if target_width is None else target_width
        angle = math.radians(heading)
        def transform(p):
            return [round(p[0]*math.cos(angle)+p[2]*math.sin(angle)), p[1],
                    round(-p[0]*math.sin(angle)+p[2]*math.cos(angle))]
        cps = [transform(p) for p in points]
        d["instances"].append(dict(id=name, preset="flight_curve" if flight else "free_curve",
            position_cm=pos[:], rotation_mdeg=[0,0,0], width_cm=w, entry_width_cm=width,
            exit_width_cm=w, control_points=cps))
        if len(d["instances"])>1:
            d["connections"].append(dict(from_=d["instances"][-2]["id"], to=name))
            d["connections"][-1]["from"] = d["connections"][-1].pop("from_")
        pos = [a+b for a,b in zip(pos,cps[-1])]
        width = w
        return d["instances"][-1]
    def straight(name, length, **kw):
        return add(name, [[0,0,0],[0,0,round(length/3)],[0,0,round(length*2/3)],[0,0,length]], **kw)
    def start(number, target_width=None):
        # Three metres behind each gate is a quiet stopped-start apron.
        road=straight("course-%02d"%number, 2000 if number<=3 else 2800 if number==9 else 3000, target_width=target_width)
        d["checkpoints"].append(dict(piece=road["id"],sample=0))
        return road
    def turn(name, radius, right):
        nonlocal heading
        side=1 if right else -1
        k=round(radius*.55228475)
        add(name,[[0,0,0],[0,0,k],[side*(radius-k),0,radius],[side*radius,0,radius]])
        heading += 90*side
    def box(name, center, size, yaw=0):
        # Outward wound convex cuboid, centimetres. One solid beam, never fake interaction collision.
        w,h,l=size
        vertices=[[x*w//2,y*h//2,z*l//2] for x,y,z in
                  [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
               [3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
        radius=sum(size)//2
        d["structures"].append(dict(id="authored-"+name,position=center,rotation_mdeg=[0,yaw*1000,0],
            scale_per_mille=[1000]*3,parts=[dict(vertices=vertices,faces=faces)],
            surface="asphalt",color=[245,168,35,255],
            motion=dict(kind="static",delta_cm=[0,0,0],axis=1,period_ms=4000,phase_ms=0,impulse_cmps=[0,0,0],cooldown_ms=1500),
            safety_min_cm=[v-radius for v in center],safety_max_cm=[v+radius for v in center]))
    def flight(number, length, rise=0, beam=False, corner=False):
        launch = d["instances"][-1]
        start_point=pos[:]
        if corner:
            add("flight-%02d"%number,[[0,0,0],[0,0,500],[100,0,600],[400,0,600]],True)
        else:
            add("flight-%02d"%number,[[0,0,0],[0,0,length//3],[0,rise,2*length//3],[0,rise,length]],True)
        end_point=pos[:]
        nonlocal heading
        if corner: heading+=90
        landing=straight("landing-%02d"%number,2000)
        d["actions"].append(dict(id="manual-%02d"%number,kind="manual_flight",piece=launch["id"],
            sample=0,height_cm=800,landing=dict(piece=landing["id"],sample=0)))
        if beam:
            center=[(a+b)//2 for a,b in zip(start_point,end_point)]
            center[1]+=35
            box("single-beam",center,[20,20,length+100],heading)
            d["grind_lines"].append(dict(id="practice-beam",control_points=[[p[0],p[1]+45,p[2]] for p in [start_point,end_point]],
                up=[0,1000000,0],capture_width_cm=30,start_connections=[],end_connections=[]))
        if rise:
            center=end_point[:];center[1]-=rise//2
            box("high-wall",center,[width,rise,50],heading)
    box("start-wall",[0,50,-20],[width+40,100,40])
    start(1);straight("runout-01",1600)
    start(2);turn("right-wide",3200,True);straight("runout-02",1600)
    start(3);turn("left-wide",3200,False);straight("runout-03",1600)
    start(4);turn("right-sharp",600,True);straight("runout-04",2400)
    start(5);turn("left-sharp",600,False);straight("runout-05",2400)
    start(6)
    center=pos[:];center[1]+=18
    box("low-barrier",center,[width,36,24],heading)
    straight("runout-06",2400)
    start(7);flight(7,1200)
    start(8);flight(8,1800,beam=True)
    straight("narrow-approach",2000,target_width=400)
    start(9);flight(9,400,corner=True)
    straight("wide-approach",2500,target_width=800)
    start(10);flight(10,1000,rise=360)
    end=straight("completion",2000)
    d["checkpoints"].append(dict(piece=end["id"],sample=0))
    end_wall=[pos[0]+round(20*math.sin(math.radians(heading))),pos[1]+50,pos[2]+round(20*math.cos(math.radians(heading)))]
    box("finish-wall",end_wall,[width+40,100,40],heading)
    d["paths"]=[dict(id="practice",pieces=[i["id"] for i in d["instances"]])]
    return d

def build(destination, cli):
    destination.mkdir(parents=True,exist_ok=False)
    original=source()
    # Source references use compiler-owned tessellation. Resolve metres from its
    # actual samples instead of copying a generator's sample spacing constants.
    with tempfile.TemporaryDirectory(prefix="practice-reference-") as temp:
        preview=Path(temp)
        (preview/"source.json").write_text(json.dumps(original))
        subprocess.run([str(cli),"compile-track",str(preview/"source.json"),str(preview/"preview.memap")],check=True)
        subprocess.run([str(cli),"unpack",str(preview/"preview.memap"),str(preview/"project")],check=True)
        assembled=json.loads((preview/"project/document.json").read_text())["assembled_track"]
        paths={instance["id"]:piece["path"] for instance,piece in zip(original["instances"],assembled["pieces"])}
        def at_station(piece, station, from_end=False):
            path=paths[piece]
            distances=[0.0]
            for a,b in zip(path,path[1:]):
                distances.append(distances[-1]+math.dist(a["position_cm"],b["position_cm"]))
            target=distances[-1]-station if from_end else station
            return min(range(len(path)),key=lambda i:abs(distances[i]-target))
        for checkpoint in original["checkpoints"]:
            checkpoint["sample"]=at_station(checkpoint["piece"],300)
        for action in original["actions"]:
            action["sample"]=at_station(action["piece"],400,from_end=True)
            action["landing"]["sample"]=at_station(action["landing"]["piece"],0)
    (destination/"source.json").write_text(json.dumps(original,ensure_ascii=False,indent=2)+"\n")
    package=destination/"practice.memap"
    subprocess.run([str(cli),"compile-track",str(destination/"source.json"),str(package)],check=True)
    subprocess.run([str(cli),"unpack",str(package),str(destination/"project")],check=True)
    document=json.loads((destination/"project/document.json").read_text())
    assembly=document["assembled_track"]
    ids=[i["id"] for i in original["instances"]]
    checkpoints=[assembly["pieces"][ids.index(cp["piece"])]["path"][cp["sample"]] for cp in original["checkpoints"]]
    first=checkpoints[0]["position_cm"]
    request=dict(path="res://maps/practice/practice.memap",x_cm=first[0],y_cm=first[2],
                 surface_id="assembled-road-0",heading_degrees=0,
                 expected_hash=hashlib.sha256(package.read_bytes()).hexdigest())
    (destination/"entry.json").write_text(json.dumps(request,indent=2)+"\n")
    (destination/"courses.json").write_text(json.dumps(dict(names=NAMES,checkpoints=checkpoints,
        human_completion="unverified"),ensure_ascii=False,indent=2)+"\n")
    return destination

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination",type=Path)
    p.add_argument("--mapkit",type=Path,required=True)
    a=p.parse_args();build(a.destination,a.mapkit.resolve())
