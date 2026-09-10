"""Synthetic structural heights; no surveyed or user data."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from vertical_fixture import xml, grid
from osm_fixture import pbf
CRS = {"EGM96":"EPSG:5773 / EGM96 metres"}


def missing(source=None, ids=None):
    root = ET.fromstring(xml(level_approaches=True) if source is None else source)
    entries = []
    for node in root.findall("node"):
        ele = node.find("tag[@k='ele']")
        if ele is not None and (ids is None or node.get("id") in ids):
            entries.append(dict(node_id=node.get("id"),height_m=float(ele.get("v"))))
            node.remove(ele)
    return ET.tostring(root,encoding="unicode"), entries


def supplement(raw, entries):
    return dict(format="miniearthure-osm-node-heights-v1",osm_sha256=hashlib.sha256(raw).hexdigest(),
        source='Synthetic original node heights; braces {} and "quoted keys": stay text',
        license="CC0 synthetic fixture",accuracy="unknown; synthetic only",vertical_crs=CRS["EGM96"],nodes=entries)


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    text, entries = missing(ids={"1","2","3","7","9","13","15"})
    raw = pbf(directory/"source.pbf",text)
    (directory/"source.osm").write_text(text,encoding="utf-8")
    (directory/"heights.json").write_text(json.dumps(supplement(raw,entries),ensure_ascii=False),encoding="utf-8")
    (directory/"correction.json").write_text(json.dumps(grid()),encoding="utf-8")
    bad = supplement(raw,entries[:-1])
    (directory/"incomplete.json").write_text(json.dumps(bad),encoding="utf-8")
