"""Synthetic land-cover source; process transport substitute with no network."""
import copy
import json
from pathlib import Path
import sys
import time


def snapshot():
    from overture_land_cover import plan
    def ring(x,y,size): return [[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]
    def feature(fid,subtype,polys,low=8,high=15):
        return dict(type="Feature",id=fid,properties=dict(id=fid,theme="base",type="land_cover",subtype=subtype,
            version=1,cartography=dict(min_zoom=low,max_zoom=high),sources=[dict(dataset="synthetic fixture",license="CC0-1.0",record_id=fid)]),
            geometry=dict(type="MultiPolygon",coordinates=polys))
    features = [feature("a-forest","forest",[[ring(9.0001,55.0001,0.0008),ring(9.0003,55.0003,0.0004)],
        [ring(9.0004,55.0004,0.0002)],[ring(9.0012,55.0001,0.0003)]]),
        feature("b-crop","crop",[[ring(9.0001,55.0001,0.0002)]]),
        feature("c-low","forest",[[ring(9.0001,55.0001,0.0008)]],0,7)]
    return dict(snapshot_version=1,**plan("2026-08-19.0",[9,55,9.001,55.001]),features=features)


if __name__ == "__main__":
    entry = sys.argv.pop(1)
    sys.path.insert(0,str(Path(entry).parent))
    import overture_land_cover as adapter
    original = adapter.acquire
    def features(query):
        for feature in snapshot()["features"]:
            yield copy.deepcopy(feature)
            if query["release"] == "2026-08-19.1": time.sleep(30)
    def acquire(query,partial,destination,progress):
        return original(query,partial,destination,progress,features)
    adapter.area.main(acquire)
