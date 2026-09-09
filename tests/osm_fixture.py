"""Synthetic OSM snapshots only; no downloaded or private data."""
from pathlib import Path
import sys

XML = '''<osm version="0.6" generator="mapeditor-synthetic">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.0002" lat="55"/>
<node id="3" lon="9.0002" lat="55.0002"/><node id="4" lon="9" lat="55.0002"/>
<node id="5" lon="9.0005" lat="55"/><node id="6" lon="9.001" lat="55"/>
<node id="7" lon="9.002" lat="55"/><node id="8" lon="9.0022" lat="55"/>
<node id="9" lon="9.0022" lat="55.0002"/><node id="10" lon="9.002" lat="55.0002"/>
<node id="11" lon="9.003" lat="55"><tag k="amenity" v="bench"/></node>
<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
<tag k="building" v="yes"/><tag k="height" v="12 m"/></way>
<way id="2"><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="width" v="4.5"/></way>
<way id="3"><nd ref="7"/><nd ref="8"/><nd ref="9"/><nd ref="10"/><nd ref="7"/><tag k="landuse" v="forest"/></way>
<way id="4"><nd ref="10"/><nd ref="11"/><tag k="barrier" v="fence"/></way>
</osm>'''


def multipolygon_xml():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(XML)
    next_node = 100
    def ring(way_id, x, y, size, split=False):
        nonlocal next_node
        ids = list(range(next_node, next_node+4))
        next_node += 4
        for identity, (dx, dy) in zip(ids, [(0,0),(size,0),(size,size),(0,size)]):
            ET.SubElement(root, "node", id=str(identity), lon=str(9+x+dx), lat=str(55+y+dy))
        segments = [ids[:3], [ids[0],ids[3],ids[2]]] if split else [ids+[ids[0]]]
        for i, segment in enumerate(segments):
            way = ET.SubElement(root, "way", id=str(way_id+i))
            for identity in segment: ET.SubElement(way, "nd", ref=str(identity))
        return list(range(way_id,way_id+len(segments)))
    def relation(identity, rings, kind):
        rel = ET.SubElement(root, "relation", id=str(identity))
        for role, ways in rings:
            for way in reversed(ways): ET.SubElement(rel, "member", type="way", ref=str(way), role=role)
        ET.SubElement(rel, "tag", k="type", v="multipolygon")
        ET.SubElement(rel, "tag", k=kind, v="yes" if kind == "building" else "forest")
    relation(100, [("outer",ring(100,0,0.001,0.0002,True)),("outer",ring(102,0.001,0.001,0.0002))], "building")
    relation(101, [("outer",ring(110,0.003,0.001,0.002,True)),("inner",ring(112,0.0034,0.0014,0.0012,True)),("outer",ring(114,0.0038,0.0018,0.0004))], "landuse")
    # Snapshot order need not match traversal or relation membership order.
    root[:] = sorted(root, key=lambda e: ({"node":0,"way":1,"relation":2}[e.tag], int(e.get("id"))))
    return ET.tostring(root, encoding="unicode")


def pbf(path, xml=XML):
    import osmium
    # Tests own their temporary destination; never overwrite an existing file.
    with osmium.SimpleWriter(str(path)) as writer:
        for entity in osmium.FileProcessor(osmium.io.FileBuffer(xml.encode(), "osm")):
            writer.add(entity)
    return Path(path).read_bytes()


if __name__ == "__main__":
    xml = multipolygon_xml() if len(sys.argv) > 3 else XML
    pbf(sys.argv[1], xml.replace("12 m", sys.argv[2] + " m") if len(sys.argv) > 2 else xml)
