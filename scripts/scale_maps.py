#!/usr/bin/env python3
"""L02 fixed-density synthetic area experiments, in a NEW directory.

Public authoring only: MapKit still validates, partitions and generates geometry.
No downloads, user datasets, limit overrides or changes to the shipped town.
"""
import argparse
import copy
import json
import math
from collections import Counter
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib

from reference_maps import canonical, empty, rectangle, sha

PROFILE = "l02-area-density-v1"
TILE_CM = 6400
CELL_CM = 1600
FIELDS = ("nodes", "roads", "buildings", "zones", "assets", "placements",
          "repetitions", "heightmaps", "surface_areas")
QUALITY_ROADS = ("korea-ew-1-1", "korea-ew-2-1", "korea-ns-1-1",
                 "korea-ns-2-1", "korea-ns-1-1-q01-north",
                 "korea-ns-2-1-q01-north", "q01-service-lane")


def reference_town():
    # Read the versioned public synthetic source. Do not rebuild unrelated kart
    # geometry or require its optional Shapely dependency for an area experiment.
    root = Path(__file__).resolve().parents[1]/"examples/driving-school"
    doc = json.loads((root/"document.json").read_text())
    return SimpleNamespace(doc=doc,payloads={a["path"]:(root/a["path"]).read_bytes() for a in doc["assets"]})


def hill_png():
    """One 16m cell, 4m samples, exact zero edges and a 2m central hill."""
    values = [[min(x, y, 4-x, 4-y)*100 for x in range(5)] for y in range(5)]
    raw = b"".join(b"\0" + struct.pack(">5H", *row) for row in values)
    def chunk(kind, data):
        return struct.pack(">I", len(data))+kind+data+struct.pack(">I", zlib.crc32(kind+data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB",5,5,16,0,0,0,0))
            + chunk(b"IDAT", zlib.compress(raw,9)) + chunk(b"IEND", b""))


def quality_template(town):
    placements = [copy.deepcopy(p) for p in town.doc["placements"] if p["id"].startswith("q01-")]
    roads = [copy.deepcopy(r) for r in town.doc["roads"] if r["id"] in QUALITY_ROADS]
    used = {p["asset_id"] for p in placements}
    assets = [copy.deepcopy(a) for a in town.doc["assets"] if a["id"] in used]
    return placements, roads, assets


def make(profile="mixed", size_m=2000, town=None):
    if profile not in ("mixed", "dense") or size_m < 256 or size_m > 10000 or size_m % 16:
        raise ValueError("profile mixed/dense; size 256..10000m in complete 16m cells")
    town = town or reference_town()
    size = size_m*100
    # Constant density and block geometry at every size. Unfilled outer margin is
    # reported explicitly; it is never counted as occupied representative blocks.
    tiles = ((size-3200)//TILE_CM)//2*2
    origin = ((size-tiles*TILE_CM)//2//CELL_CM)*CELL_CM
    doc = empty(f"{PROFILE}-{profile}-{size_m}m", size, CELL_CM)
    doc.update(recipe_version=6, surface_areas=[])
    doc["provenance"].update(tool_id="mapeditor-scale-maps", build_id=PROFILE,
        first_created="2026-09-11T00:00:00Z", last_edited="2026-09-11T00:00:00Z")
    doc["attributions"] = [dict(source=PROFILE,license="MIT",notice=
        "Original synthetic density experiment; fixed 64m lots, exact Hanbit block assets and placements. Repetition is intentional stress, not surveyed geography or whole-city art acceptance.")]
    template, quality_roads, assets = quality_template(town)
    assets_by_id = {a["id"]: a for a in town.doc["assets"]}
    used_assets = {a["id"]: a for a in assets}
    payloads = {a["path"]: town.payloads[a["path"]] for a in assets}
    nodes = {}
    lots = []

    def add_road(ident, points, width=400, sidewalk=0, kind="ground", prototype=None):
        r = copy.deepcopy(prototype) if prototype else dict(clearance_cm=None,kind=kind,
            widths_cm=[width]*(len(points)-1), surfaces=["asphalt"]*(len(points)-1),sidewalk_cm=sidewalk)
        endpoints = []
        for p in (points[0], points[-1]):
            key = "n-"+"-".join(map(str,p))
            nodes[key] = dict(id=key,position=p,level=0 if p[1] == 0 else 1)
            endpoints.append(key)
        r.update(id=ident, points=points, **{"from":endpoints[0], "to":endpoints[1]})
        doc["roads"].append(r)

    def place(ident, asset, x, y, turns=0):
        a = assets_by_id[asset]
        used_assets[asset] = copy.deepcopy(a)
        payloads[a["path"]] = town.payloads[a["path"]]
        doc["placements"].append(dict(id=ident,asset_id=asset,position=[x,0,y],quarter_turns=turns))

    # Fully connected boundary grid: graph junctions are real shared endpoints.
    # Split each horizontal arm at x+16m to connect the Hanbit access street.
    for y in range(tiles+1):
        z = origin+y*TILE_CM
        for x in range(tiles):
            a = origin+x*TILE_CM
            add_road(f"grid-ew-{x}-{y}-a",[[a,0,z],[a+1600,0,z]])
            add_road(f"grid-ew-{x}-{y}-b",[[a+1600,0,z],[a+TILE_CM,0,z]])
    for x in range(tiles+1):
        a = origin+x*TILE_CM
        for y in range(tiles):
            z = origin+y*TILE_CM
            add_road(f"grid-ns-{x}-{y}",[[a,0,z],[a,0,z+TILE_CM]])
    for y in range(tiles):
        for x in range(tiles):
            ox, oy = origin+x*TILE_CM, origin+y*TILE_CM
            kind = "urban" if profile == "dense" else (
                "urban" if x < tiles//2 and y < tiles//2 else
                "residential" if y < tiles//2 else "rural" if x < tiles//2 else "forest")
            ident = f"{kind}-{x}-{y}"
            lots.append(dict(id=ident,kind=kind,bounds_cm=[ox,oy,ox+TILE_CM,oy+TILE_CM]))
            if kind == "urban":
                dx, dz = ox+1600-23800, oy+1600-4800
                for p in template:
                    translated = copy.deepcopy(p)
                    translated.update(id=ident+"-"+p["id"],position=[p["position"][0]+dx,p["position"][1],p["position"][2]+dz])
                    doc["placements"].append(translated)
                for r in quality_roads:
                    add_road(ident+"-"+r["id"], [[p[0]+dx,p[1],p[2]+dz] for p in r["points"]],prototype=r)
                add_road(ident+"-access-s",[[ox+1600,0,oy],[ox+1600,0,oy+1600]],sidewalk=120)
                add_road(ident+"-access-n",[[ox+1600,0,oy+4800],[ox+1600,0,oy+TILE_CM]],sidewalk=120)
                doc["surface_areas"].append(dict(id=ident+"-paving",polygon=rectangle(ox,oy,TILE_CM,TILE_CM),surface="concrete"))
            elif kind == "residential":
                for i,(px,py) in enumerate([(1800,1800),(4400,1800),(1800,4400),(4400,4400)]):
                    place(ident+f"-home-{i}","q03-home-"+str(i%2),ox+px,oy+py,i%2*2)
                for i,px in enumerate([2200,4200]):place(ident+f"-bench-{i}","city-bench",ox+px,oy+3200)
            elif kind == "rural":
                place(ident+"-home","q03-home-0",ox+1600,oy+1600)
                doc["zones"].append(dict(id=ident+"-orchard",kind="orchard",polygon=rectangle(ox+3000,oy+1600,2200,3600),spacing_cm=800,density_per_mille=800,exclusions=[]))
            else:
                doc["zones"].append(dict(id=ident+"-forest",kind="forest",polygon=rectangle(ox+800,oy+800,4800,4800),spacing_cm=600,density_per_mille=850,exclusions=[]))
                doc["heightmaps"].append(dict(cell=dict(x=(ox+3200)//CELL_CM,y=(oy+3200)//CELL_CM),path="terrain/hill.png",spacing_cm=400,offset_cm=0,step_cm=1,source_accuracy_cm=None))
    # Dedicated full-width speed/structure route in the margin, separate from
    # the block grid. Explicit surface spawn; no invented ground connections.
    add_road("speed-bridge",[[0,0,800],[1600,0,800],[4800,300,800],
        [size-4800,300,800],[size-1600,0,800],[size,0,800]],width=600,kind="bridge")
    doc["nodes"] = list(nodes.values())
    doc["assets"] = list(used_assets.values())
    if doc["heightmaps"]: payloads["terrain/hill.png"] = hill_png()
    for a in doc["assets"]:
        if a["attribution"] not in doc["attributions"]: doc["attributions"].append(a["attribution"])
    lot_counts = Counter(lot["kind"] for lot in lots)
    instance_counts = Counter(p["asset_id"] for p in doc["placements"])
    road_m = sum(math.dist(a,b)/100 for r in doc["roads"] for a,b in zip(r["points"],r["points"][1:]))
    quality_signature = sha(canonical(dict(placements=template,roads=quality_roads,assets=assets)))
    counts = {k:len(doc[k]) for k in FIELDS}
    building_count = 6*lot_counts["urban"]+4*lot_counts["residential"]+lot_counts["rural"]
    summary = dict(profile=PROFILE,condition=profile,size_m=size_m,area_km2=(size_m/1000)**2,
        execution_cell_m=16,execution_cells=(size_m//16)**2,tiles_per_side=tiles,
        occupied_lot_area_m2=tiles**2*4096,outer_margin_area_m2=size_m**2-tiles**2*4096,
        grid_origin_cm=origin,lot_pitch_m=64,lots=lots,lot_counts=dict(lot_counts),counts=counts,
        building_instances=building_count,building_instances_per_km2=building_count/(size_m/1000)**2,
        quality=dict(signature_sha256=quality_signature,placements_per_block=len(template),shops_per_block=6,
                     source="public driving-school v6 Hanbit block",assets_sha256={a["path"]:sha(payloads[a["path"]]) for a in assets}),
        road_centerline_spatial_m=road_m,road_m_per_km2=road_m/(size_m/1000)**2,
        placement_instances_by_asset=dict(instance_counts),unique_asset_count=len(doc["assets"]),
        unique_asset_bytes=sum(len(payloads[a["path"]]) for a in doc["assets"]),
        instance_asset_bytes_without_reuse=sum(len(payloads[used_assets[p["asset_id"]]["path"]]) for p in doc["placements"]),
        source_document_bytes=len(canonical(doc)),payload_bytes=sum(map(len,payloads.values())),
        terrain=dict(spacing_m=4,quantization_cm=1,peak_m=2,heightmap_cells=len(doc["heightmaps"]),
                     implicit_flat_cells=(size_m//16)**2-len(doc["heightmaps"]),accuracy=None),
        routes=[dict(id="speed-bridge",surface="speed-bridge",start_cm=[6400,300,800],end_cm=[size-6400,300,800],
                     target_speed_m_s=12,storage_sides_to_compare_m=[64,128,256],
                     purpose="real input, three storage crossings when extent permits; separate elevated surface"),
                dict(id="urban-street",surface="urban-0-0-access-s",start_cm=[origin+1600,0,origin+800],end_cm=[origin+1600,0,origin+tiles*TILE_CM-800],target_speed_m_s=8)],
        transfer=dict(target_bytes=50000000,all_declared_assets_bundled=True,preinstalled_common_asset_credit_bytes=0,
                      additional_common_pack_bytes=0,bundled_generated_cache_bytes=0),
        source_hashes={"document.json":sha(canonical(doc)),**{p:sha(b) for p,b in payloads.items()}},
        limits=["Repeated fictional lots are controlled stress, not whole-city art acceptance.",
                "All referenced public models are bundled; no assumed installed asset cache discount.",
                "No geometry, memory, document or work limit is raised. Expanded source and reservation differ from RSS/GPU.",
                "5/10km expansion is conditional on 2km native admission and driving; generation counts require native measurement."])
    return doc,payloads,summary


def create(destination,profile="mixed",size_m=2000):
    destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    doc,payloads,summary=make(profile,size_m)
    destination.mkdir(parents=True,exist_ok=False)
    for name,data in {"document.json":canonical(doc),**payloads,
                      "scale.json":(json.dumps(summary,indent=2,ensure_ascii=False)+"\n").encode()}.items():
        target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as output:output.write(data)
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path)
    parser.add_argument("--profile",choices=["mixed","dense"],default="mixed")
    parser.add_argument("--size-m",type=int,default=2000)
    args=parser.parse_args()
    report=create(args.destination,args.profile,args.size_m)
    print(json.dumps({k:report[k] for k in ["condition","size_m","counts","building_instances_per_km2","source_document_bytes","unique_asset_bytes"]},indent=2))
