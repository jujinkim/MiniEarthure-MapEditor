"""Synthetic road graph and process transport substitute; never calls Internet."""
import json
from pathlib import Path
import sys


def snapshot():
    from pyproj import Geod
    coords = {"a":[9.0001,55.0002], "b":[9.0005,55.0002], "c":[9.0009,55.0002], "d":[9.0005,55.0008]}
    def feature(fid,kind,geometry,**properties):
        return dict(type="Feature",id=fid,geometry=geometry,properties=dict(id=fid,theme="transportation",type=kind,version=1,
            sources=[dict(dataset="synthetic fixture",license="CC0-1.0",record_id=fid)],**properties))
    features = [feature(cid,"connector",dict(type="Point",coordinates=point)) for cid,point in coords.items()]
    geod = Geod(ellps="WGS84")
    for fid,ids,width,surface in [("east",["a","b","c"],6,"paved"),("north",["b","d"],4,"gravel")]:
        positions = [coords[cid] for cid in ids]
        lengths = [0.0]
        for a,b in zip(positions,positions[1:]): lengths.append(lengths[-1]+geod.inv(*a,*b)[2])
        refs = [dict(connector_id=cid,at=length/lengths[-1]) for cid,length in zip(ids,lengths)]
        features.append(feature(fid,"segment",dict(type="LineString",coordinates=positions),subtype="road",**{"class":"residential"},
            connectors=refs,width_rules=[dict(value=width)],road_surface=[dict(value=surface)],level_rules=[dict(value=0)]))
    return dict(snapshot_version=1,provider="Overture",release="2026-08-19.0",bbox=[9,55,9.001,55.001],theme="transportation",type="segment",
        profile="ground-graph-v1",ground_m=0.2,license="ODbL-1.0; © OpenStreetMap contributors; TomTom; Overture Maps Foundation; https://docs.overturemaps.org/attribution/#transportation",features=features)


def scoped_snapshot():
    value = snapshot()
    props = value["features"][4]["properties"]
    props["width_rules"] = [dict(value=6,between=[0,0.25]), dict(value=4,between=[0.25,1])]
    props["road_surface"] = [dict(value="paved",between=[0,0.75]), dict(value="dirt",between=[0.75,1])]
    return value


def off_vertex_snapshot():
    value = scoped_snapshot()
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    coords = value["features"][4]["geometry"]["coordinates"]
    a,b = coords[0],coords[-1]
    azimuth,_,distance = geod.inv(*a,*b)
    lon,lat,_ = geod.fwd(*a,azimuth,distance/2)
    shared = [lon,lat]
    value["features"][1]["geometry"]["coordinates"] = shared
    value["features"][4]["geometry"]["coordinates"] = [a,b]
    value["features"][4]["properties"]["connectors"][1]["at"] = 0.5
    value["features"][5]["geometry"]["coordinates"][0] = shared
    return value


if __name__ == "__main__":
    value = off_vertex_snapshot()
    Path(sys.argv[2]).write_text(json.dumps(value))
