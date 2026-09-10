#!/usr/bin/env python3
"""Create original MIT P01 source fixtures in a NEW directory; no downloads.

Geometry is authored input, never a replacement for MapKit generation/packing.
The fixed profile is synthetic, not a calibrated real-region performance claim.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

PROFILE = "p01-synthetic-v1"
FIELDS = ("nodes", "roads", "buildings", "zones", "assets", "placements", "repetitions", "heightmaps")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rectangle(x, y, w, h):
    return [[x,y], [x+w,y], [x+w,y+h], [x,y+h]]


def empty(name, size, cell):
    return dict(map_id=name, revision=1, bounds={"min":[0,0], "max":[size,size]},
                cell_size_cm=cell, seed=9012026, recipe_version=4, theme="default", terrain_base_cm=0,
                **{field: [] for field in FIELDS},
                attributions=[dict(source=PROFILE, license="MIT", notice="Original synthetic geometry and terrain; no external datasets; not a surveyed region")],
                provenance=dict(tool_id="mapeditor-reference-maps", version="1", build_id=PROFILE,
                                fingerprint="synthetic-not-authentication", first_created="2026-09-09T00:00:00Z", last_edited="2026-09-09T00:00:00Z"))


def road(doc, name, points, kind="ground", width=800, surface="asphalt", start=None, end=None):
    ids = [start or name+"-from", end or name+"-to"]
    for ident, point in zip(ids, (points[0], points[-1])):
        if not any(n["id"] == ident for n in doc["nodes"]):
            doc["nodes"].append(dict(id=ident, position=point, level=0 if point[1] == 0 else 1))
    doc["roads"].append(dict(id=name, **{"from":ids[0], "to":ids[1]}, points=points,
        widths_cm=[width]*(len(points)-1), surfaces=[surface]*(len(points)-1), kind=kind,
        clearance_cm=300 if kind in ("tunnel", "underpass") else None, sidewalk_cm=0))


def building(doc, name, x, y, width, height, usage, roof="flat"):
    doc["buildings"].append(dict(id=name, footprint=rectangle(x,y,width,width), base_cm=0,
        height_cm=height, usage=usage, material="brick" if usage=="residential" else "concrete", roof=roof))


def terrain_png(hill=False):
    # Full 512 m cell, 2 m samples, all boundary heights exactly zero.
    # Integer-only tent with a plateau; partial outer cells use the flat payload.
    rows = b"".join(b"\0" + b"".join(struct.pack(">H", min(i,j,256-i,256-j,64)*20 if hill else 0)
                                     for i in range(257)) for j in range(257))
    def chunk(kind, data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",257,257,16,0,0,0,0))+chunk(b"IDAT",zlib.compress(rows,9))+chunk(b"IEND",b"")


def baseline():
    doc = empty(PROFILE+"-10km", 1000000, 51200)
    # Four exact 5x5 km quadrants, with connected 500 m streets.
    for y in range(21):
        for x in range(20):
            road(doc, f"ew-{x}-{y}", [[x*50000,0,y*50000],[(x+1)*50000,0,y*50000]],
                 start=f"n-{x}-{y}", end=f"n-{x+1}-{y}")
    for x in range(21):
        for y in range(20):
            road(doc, f"ns-{x}-{y}", [[x*50000,0,y*50000],[x*50000,0,(y+1)*50000]],
                 start=f"n-{x}-{y}", end=f"n-{x}-{y+1}")
    quadrants=[]
    for kind, ox, oy, count in [("urban",0,0,4),("residential",500000,0,2),("rural",0,500000,1),("forest",500000,500000,0)]:
        quadrants.append(dict(id=kind, bounds={"min":[ox,oy],"max":[ox+500000,oy+500000]}, buildings=100*count))
        for y in range(10):
            for x in range(10):
                bx,by=ox+x*50000,oy+y*50000
                for n in range(count):
                    building(doc,f"{kind}-{x}-{y}-{n}",bx+6000+(n%4)*10000,by+6000+(n//4)*10000,
                             3000 if kind=="urban" else 1800, 3000 if kind=="urban" else 800,
                             "commercial" if kind=="urban" else "residential", "flat" if kind=="urban" else "gable")
                if kind in ("rural","forest"):
                    doc["zones"].append(dict(id=f"{kind}-zone-{x}-{y}",kind="orchard" if kind=="rural" else "forest",
                        polygon=rectangle(bx+12000,by+12000,30000,30000),spacing_cm=5000 if kind=="rural" else 3000,
                        density_per_mille=800,exclusions=[]))
    for y in range(20):
        for x in range(20):
            # Roads conform to hills; source resolution is not survey accuracy.
            hill = 11 <= x <= 18 and 11 <= y <= 18
            doc["heightmaps"].append(dict(cell=dict(x=x,y=y),path="terrain/hill.png" if hill else "terrain/flat.png",
                                         spacing_cm=200,offset_cm=0,step_cm=1,source_accuracy_cm=None))
    routes=[dict(id="east-west", surface="ew-0-1", start_cm=[1000,0,50000],
                 waypoints_cm=[[1000,0,50000],[999000,0,50000]], purpose="continuous flat connected road; 19 x-cell boundaries each way"),
            dict(id="north-south", surface="ns-1-0", start_cm=[50000,0,1000],
                 waypoints_cm=[[50000,0,1000],[50000,0,999000]], purpose="continuous flat connected road; 19 y-cell boundaries each way")]
    return doc, {"terrain/flat.png":terrain_png(),"terrain/hill.png":terrain_png(True)}, dict(quadrants=quadrants,routes=routes)


def baseline_user():
    doc,payloads,extra=baseline()
    doc["map_id"] += "-user"
    # Original PNG16 used as a static black material; no external asset bytes.
    payloads["assets/white.png"]=terrain_png()
    doc["assets"].append(dict(id="white-marker",path="assets/white.png",
        attribution=copy.deepcopy(doc["attributions"][0]),
        collision=[dict(center=[0,150,0],size_cm=[600,300,600])]))
    doc["placements"].append(dict(id="marker",asset_id="white-marker",position=[2000,0,2000],quarter_turns=0))
    return doc,payloads,extra


def structures():
    doc=empty(PROFILE+"-structures",102400,51200)
    road(doc,"ground-west",[[0,0,10000],[51200,0,10000]],start="west",end="junction")
    road(doc,"ground-east",[[51200,0,10000],[102400,0,10000]],start="junction",end="east")
    road(doc,"branch",[[51200,0,10000],[51200,0,30000]],start="junction")
    # Crossings have distinct graph IDs and explicit heights. Deck endpoints are
    # surface-specific spawn sites, not invented connections to ground roads.
    road(doc,"bridge",[[25600,600,0],[25600,600,35000]],"bridge",600,"concrete")
    road(doc,"elevated",[[75000,500,0],[75000,1000,35000]],"elevated",600)
    for kind,y,depth in [("underpass",50000,-500),("tunnel",80000,-600)]:
        road(doc,kind,[[0,0,y],[10000,0,y],[25000,depth,y],[75000,depth,y],[92400,0,y],[102400,0,y]],kind,800)
    building(doc,"seam-gable",50000,36000,3000,1400,"residential","gable")
    building(doc,"flat-shop",60000,60000,5000,2000,"commercial")
    doc["zones"].append(dict(id="seam-orchard",kind="orchard",polygon=rectangle(47000,88000,12000,10000),spacing_cm=2000,density_per_mille=800,exclusions=[]))
    doc["repetitions"].append(dict(id="fence-line",asset_id="builtin:fence",points=[[40000,0,34000],[60000,0,34000]],spacing_cm=200))
    doc["placements"].append(dict(id="light",asset_id="builtin:streetlight",position=[49000,0,12000],quarter_turns=0))
    return doc, {}, dict(routes=[dict(id=kind,surface=kind,start_cm=[1000,0,y],waypoints_cm=doc["roads"][i]["points"],
                                    purpose="grade entrances, walls, seam; tunnel also ceiling") for kind,y,i in [("underpass",50000,5),("tunnel",80000,6)]],
                         limitations=["Bridge/elevated decks require explicit surface spawn; no connected ground approach is authored.","No real-world source accuracy or performance calibration."])


def summarize(doc, payloads, extra):
    planar=spatial=0.0
    for r in doc["roads"]:
        for a,b in zip(r["points"],r["points"][1:]):
            planar+=math.hypot(b[0]-a[0],b[2]-a[2])/100
            spatial+=math.dist(a,b)/100
    return dict(profile=PROFILE,map_id=doc["map_id"],bounds_cm=doc["bounds"],world_scale=1.0,
                cell_size_cm=doc["cell_size_cm"],cell_count=math.ceil(doc["bounds"]["max"][0]/doc["cell_size_cm"])**2,
                counts={f:len(doc[f]) for f in FIELDS},authored_object_count=sum(len(doc[f]) for f in FIELDS),
                road_centerline_planar_m=round(planar,6),road_centerline_spatial_m=round(spatial,6),
                terrain=dict(spacing_cm=200 if payloads else None,source_accuracy_cm=None,
                             description="synthetic PNG16, 1 cm quantization, zero shared edges" if payloads else "implicit flat terrain"),
                source_files={"document.json":sha(canonical(doc)),**{p:sha(data) for p,data in sorted(payloads.items())}},
                attributions=doc["attributions"],**extra)


def create(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    summaries={}
    for name,make in [("baseline",baseline),("baseline-user",baseline_user),("structures",structures)]:
        doc,payloads,extra=make()
        project=destination/name
        project.mkdir()
        for path,data in {"document.json":canonical(doc),**payloads}.items():
            target=project/path
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as output: output.write(data)
        summaries[name]=summarize(doc,payloads,extra)
    with (destination/"reference.json").open("x") as output:
        json.dump(summaries,output,indent=2,sort_keys=True)
        output.write("\n")
    return summaries


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path,help="new directory; existing paths are refused")
    args=parser.parse_args()
    create(args.destination)
