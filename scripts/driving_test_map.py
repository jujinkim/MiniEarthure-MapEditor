#!/usr/bin/env python3
"""Create the fixed G01 offline driving project in a new directory."""
import argparse
import json
from pathlib import Path
from reference_maps import canonical, empty, road, building, sha

PROFILE = "g01-driving-v1"


def document():
    doc = empty(PROFILE, 102400, 51200)
    doc["attributions"] = [dict(source=PROFILE, license="MIT", notice="Original offline driving test geometry; no external data")]
    doc["provenance"].update(tool_id="mapeditor-driving-test-map", build_id=PROFILE)
    # Closed circuit: straight, broad corners, connected bridge grades and tunnel.
    road(doc, "straight", [[10000,0,16000],[51200,0,16000],[88000,0,16000]], width=1600, start="nw", end="ne")
    road(doc, "east-corner", [[88000,0,16000],[94000,0,22000],[94000,0,72000],[88000,0,78000]], width=1600, start="ne", end="se")
    road(doc, "tunnel", [[88000,0,78000],[80000,0,78000],[68000,-600,78000],[34000,-600,78000],[22000,0,78000],[10000,0,78000]], "tunnel",1600,start="se",end="sw")
    road(doc, "west-bridge", [[10000,0,78000],[4000,0,72000],[4000,0,64000],[4000,600,56000],[4000,600,40000],[4000,0,32000],[4000,0,22000],[10000,0,16000]], "bridge",1600,start="sw",end="nw")
    # Separate repeatable pad: terrain-conforming road with explicit small grades.
    road(doc, "surface-lane", [[20000,0,36000],[42000,0,36000],[62000,0,36000],[82000,0,36000]],width=1400)
    doc["roads"][-1]["surfaces"] = ["asphalt","gravel","dirt"]
    road(doc, "bumps", [[20000,100,52000],[28000,100,52000],[30000,140,52000],[32000,100,52000],[34000,140,52000],[36000,100,52000],[42000,100,52000]],"elevated",1400)
    building(doc,"occlusion-wall",90000,40000,2000,2400,"commercial")
    return doc


def create(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    data=canonical(document())
    (destination/"document.json").write_bytes(data)
    manifest=dict(profile=PROFILE,document_sha256=sha(data),revision=1,
        start=dict(x_cm=94000,y_cm=30000,surface_id="east-corner",heading_degrees=0),
        circuit=["straight","east-corner","tunnel","west-bridge"],
        sections=[dict(id="straight",purpose="acceleration/braking, x cell seam",start_cm=[14000,16000]),
                  dict(id="east-corner",purpose="corners, y seam and building occlusion",start_cm=[94000,30000]),
                  dict(id="tunnel",purpose="connected descent, ceiling and ascent",start_cm=[84000,78000]),
                  dict(id="west-bridge",purpose="connected ascent/deck/descent and y seam",start_cm=[4000,65000]),
                  dict(id="surface-lane",purpose="asphalt/gravel/dirt transitions",start_cm=[22000,36000]),
                  dict(id="bumps",purpose="two 40 cm bumps on a 100 cm deck with 20 m ramps",start_cm=[22000,52000])],
        sprint_points_cm=[[94000,35000],[94000,40000],[94000,45000]])
    (destination/"driving.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path)
    create(parser.parse_args().destination)
