"""Synthetic source only; transport substitute for native process checks."""
import copy
import json
from pathlib import Path
import sys

QUERY = dict(provider="Overture", release="2026-08-19.0", bbox=[9,55,9.001,55.001], theme="buildings", type="building",
    license="ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings")
FEATURE = dict(type="Feature", id="synthetic-building", properties=dict(id="synthetic-building", version=1, height=12,
    sources=[dict(dataset="synthetic fixture", license="CC0-1.0", record_id="fixture:1")]),
    geometry=dict(type="MultiPolygon", coordinates=[[[[9.0001,55.0001],[9.0002,55.0001],[9.0002,55.0002],[9.0001,55.0002],[9.0001,55.0001]]]]))

def snapshot(height=12):
    feature=copy.deepcopy(FEATURE)
    feature["properties"]["height"]=height
    return dict(snapshot_version=1, **QUERY, features=[feature])

def multipart_snapshot():
    value = snapshot()
    def ring(x, y, size):
        return [[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]
    value["features"][0]["geometry"]["coordinates"] = [
        [ring(9.0001,55.0001,0.0006), ring(9.0002,55.0002,0.0004)],
        [ring(9.0003,55.0003,0.0001)],  # Complete island in the courtyard.
        [ring(9.0012,55.0001,0.0001)],  # Retained outside the query bbox.
    ]
    return value

def vertical_snapshot():
    value = snapshot()
    value.update(include_parts=True, ground_m=2)
    parent = value["features"][0]
    parent["properties"].update(type="building", has_parts=True)
    for name, base, height in [("lower", 0, 4), ("upper", 8, 3)]:
        part = copy.deepcopy(FEATURE)
        part["id"] = name
        part["properties"].update(id=name, type="building_part", building_id=parent["id"], min_height=base, height=height)
        value["features"].append(part)
    return value

if __name__ == "__main__":
    modes = {"--snapshot": snapshot, "--vertical": vertical_snapshot, "--multipart": multipart_snapshot}
    value = modes[sys.argv[1]]()
    Path(sys.argv[2]).write_text(json.dumps(value))
