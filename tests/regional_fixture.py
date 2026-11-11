"""Creates only synthetic local-source inputs for the native regional worker test."""
from pathlib import Path
import json
import sys
from shapely.geometry import box, mapping, MultiPolygon, Polygon
from shapely.ops import transform
from test_regional import Regional, shapely_scale

case=Regional();case.setUp()
try:
    case.root=Path(sys.argv[1]);case.root.mkdir(parents=True,exist_ok=True)
    request=case.request
    case.cover(request)
    def geo(g):return json.loads(json.dumps(mapping(transform(case.inverse,shapely_scale(g,3/100,-300,-300)))))
    parent=dict(id="synthetic-parent",height=12,has_parts=True,parts_complete=True,sources=[],**{"class":"school"})
    parent["parts"]=[dict(id="left",building_id=parent["id"],height=6,geometry=geo(box(1000,15000,2200,18000))),dict(id="right",building_id=parent["id"],height=9,geometry=geo(box(2400,15000,4000,18000)))]
    request["buildings"]=case.snapshot([
        dict(type="Feature",geometry=geo(box(1000,15000,4000,18000)),properties=parent),
        dict(type="Feature",geometry=geo(MultiPolygon([box(1000,3000,2000,4000),box(2000,4000,3000,5000)])),properties=dict(id="touching-components",height=6,sources=[])),
        dict(type="Feature",geometry=geo(Polygon([(13000,14000),(15000,14000),(15000,16000),(13000,16000),(13000,15000)],
            [[(13000,15000),(14000,14500),(14000,15500)]])),properties=dict(id="touching-courtyard",height=6,sources=[]))])
    (case.root/"request.json").write_text(json.dumps(request))
    (case.root/"document.json").write_text(json.dumps(case.document(request)))
finally:case.doCleanups()
