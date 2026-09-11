#!/usr/bin/env python3
"""Original MIT airborne/ground vehicle test course; NEW directory only."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from reference_maps import canonical, empty, road, rectangle, summarize

def post_glb(width, height):
    # Original untextured cuboid; glTF metres, collision proxy centimetres.
    vertices = [(x, y, z) for x in [-width/2, width/2] for y in [0, height] for z in [-width/2, width/2]]
    indices = [0,1,3,0,3,2, 4,6,7,4,7,5, 0,4,5,0,5,1, 2,3,7,2,7,6, 0,2,6,0,6,4, 1,5,7,1,7,3]
    blob = struct.pack('<24f', *(c for v in vertices for c in v)) + struct.pack('<36H', *indices)
    doc = dict(asset=dict(version='2.0'), scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0), indices=1, material=0)])],
        materials=[dict(pbrMetallicRoughness=dict(baseColorFactor=[1,.55,.1,1],metallicFactor=0,roughnessFactor=1))],
        buffers=[dict(byteLength=len(blob))], bufferViews=[dict(buffer=0,byteOffset=0,byteLength=96),dict(buffer=0,byteOffset=96,byteLength=72)],
        accessors=[dict(bufferView=0,componentType=5126,count=8,type='VEC3',min=[-width/2,0,-width/2],max=[width/2,height,width/2]),dict(bufferView=1,componentType=5123,count=36,type='SCALAR')])
    encoded=canonical(doc); encoded+=b' '*(-len(encoded)%4)
    return struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob


def create(destination):
    doc = empty("fleet-playground-v1", 12800, 12800)
    doc["recipe_version"] = 6
    doc["attributions"] = [dict(source="fleet-playground-v1", license="MIT", notice="Original synthetic ramps, obstacles and ground bypass. No external data.")]
    doc["provenance"].update(tool_id="mapeditor-fleet-test", build_id="fleet-playground-v1",
                             first_created="2026-09-11T00:00:00Z", last_edited="2026-09-11T00:00:00Z")
    # Eastbound ascending ramp, 3 m launch elevation, then an actual deck gap.
    road(doc, "launch", [[400, 0, 4000], [800, 0, 4000], [7800, 300, 4000], [8400, 300, 4000]], "elevated", 300)
    road(doc, "landing", [[9600, 230, 4000], [10400, 180, 4000], [12000, 0, 4000]], "elevated", 500)
    road(doc, "bypass", [[1200, 0, 5200], [8500, 0, 5200]], "ground", 400, "asphalt")
    road(doc, "rough", [[1200, 0, 7600], [2000, 20, 7600], [2200, 0, 7600], [2400, 25, 7600], [2600, 0, 7600], [3000, 0, 7600]], "elevated", 300, "gravel")
    for z in [9400, 10200]: road(doc, f"slalom-edge-{z}", [[1200,0,z],[8000,0,z]], "ground", 100)
    payloads = {"assets/post.glb": post_glb(.12,.70), "assets/probe.glb": post_glb(.08,.80)}
    for name,w,h in [("post",12,70),("probe",8,80)]:
        doc["assets"].append(dict(id=name,path=f"assets/{name}.glb", attribution=doc["attributions"][0],collision=[dict(center=[0,h//2,0],size_cm=[w,h,w])]))
    for i in range(6):
        doc["placements"].append(dict(id=f"slalom-post-{i}",asset_id="post", position=[2300+i*750,0,9800+(70 if i%2 else -70)],quarter_turns=0))
    # Thin freestanding probe in a separate flat clearance lane (x=42,z=60).
    doc["placements"].append(dict(id="wing-probe",asset_id="probe",position=[4230,0,6031],quarter_turns=0))
    locations = [dict(id="start", title="Ramp approach", position_cm=[600,0,4000], surface_id="launch", heading_degrees=270),
                 dict(id="bypass", title="Ground bypass", position_cm=[1600,0,5200], surface_id="bypass", heading_degrees=270),
                 dict(id="rough", title="Uneven test lane", position_cm=[1600,0,7600], surface_id="rough", heading_degrees=270)]
    report = summarize(doc, payloads, dict(locations=locations, routes=[], start=dict(x_cm=600,y_cm=4000,surface_id="launch",heading_degrees=270),
        limitations=["Synthetic development course, not a calibrated performance benchmark.", "Ground under the 12 m deck gap is a safe return route; this is not an infinite pit."]))
    destination.mkdir(parents=True, exist_ok=False)
    report["profile"] = "fleet-playground-v1"
    report["terrain"] = dict(spacing_cm=None,source_accuracy_cm=None,description="Implicit flat terrain beneath elevated ramps")
    for name, data in payloads.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    document_bytes = canonical(doc) + b"\n"
    report["source_files"]["document.json"] = hashlib.sha256(document_bytes).hexdigest()
    (destination / "document.json").write_bytes(document_bytes)
    (destination / "driving.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    print(json.dumps(create(parser.parse_args().destination), indent=2))
