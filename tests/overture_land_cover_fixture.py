"""Synthetic land-cover source; process transport substitute with no network."""
import json
from pathlib import Path
import sys


def snapshot():
    def ring(x,y,size): return [[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]
    def feature(fid,subtype,polys,low=8,high=15):
        return dict(type="Feature",id=fid,properties=dict(id=fid,theme="base",type="land_cover",subtype=subtype,
            version=1,cartography=dict(min_zoom=low,max_zoom=high),sources=[dict(dataset="synthetic fixture",license="CC0-1.0",record_id=fid)]),
            geometry=dict(type="MultiPolygon",coordinates=polys))
    features = [feature("a-forest","forest",[[ring(9.0001,55.0001,0.0008),ring(9.0003,55.0003,0.0004)],
        [ring(9.0004,55.0004,0.0002)],[ring(9.0012,55.0001,0.0003)]]),
        feature("b-crop","crop",[[ring(9.0001,55.0001,0.0002)]]),
        feature("c-low","forest",[[ring(9.0001,55.0001,0.0008)]],0,7)]
    return dict(snapshot_version=1, provider="Overture", release="2026-08-19.0", bbox=[9,55,9.001,55.001],
        theme="base", type="land_cover", profile="forest-high-detail-v1",
        license="ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; ESA WorldCover (CC-BY-4.0); © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium; https://docs.overturemaps.org/attribution/#base",
        features=features)


if __name__ == "__main__":
    value = snapshot()
    Path(sys.argv[2]).write_text(json.dumps(value))
