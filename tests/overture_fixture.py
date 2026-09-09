"""Synthetic source only; transport substitute for native process checks."""
import copy
import json
from pathlib import Path
import sys
import time

QUERY = dict(provider="Overture", release="2026-08-19.0", bbox=[9,55,9.001,55.001], theme="buildings", type="building",
    license="ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings")
FEATURE = dict(type="Feature", id="synthetic-building", properties=dict(id="synthetic-building", version=1, height=12,
    sources=[dict(dataset="synthetic fixture", license="CC0-1.0", record_id="fixture:1")]),
    geometry=dict(type="MultiPolygon", coordinates=[[[[9.0001,55.0001],[9.0002,55.0001],[9.0002,55.0002],[9.0001,55.0002],[9.0001,55.0001]]]]))

def snapshot(height=12):
    feature=copy.deepcopy(FEATURE)
    feature["properties"]["height"]=height
    return dict(snapshot_version=1, **QUERY, features=[feature])

if __name__ == "__main__":
    entry = sys.argv.pop(1)
    sys.path.insert(0,str(Path(entry).parent))
    import overture_area as adapter
    original = adapter.acquire
    def features(query):
        yield copy.deepcopy(FEATURE)
        if query["release"] == "2026-08-19.1": time.sleep(30)
    def acquire(query,partial,destination,progress):
        return original(query,partial,destination,progress,features)
    adapter.acquire=acquire
    adapter.main()
