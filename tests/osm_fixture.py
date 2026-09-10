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


def structural_xml(level_approaches=False):
    import xml.etree.ElementTree as ET
    root = ET.Element("osm", version="0.6", generator="mapeditor-synthetic")
    # Explicit approaches, elevated span and a depressed tunnel, spaced apart.
    for identity, (x, z, h) in enumerate([(0,0,0),(20,0,0),(50,0,6),(90,0,6),(120,0,0),(140,0,0),
                                            (0,80,0),(20,80,0),(50,80,-6),(90,80,-6),(120,80,0),(140,80,0)], 1):
        node = ET.SubElement(root, "node", id=str(identity), lon=str(9+x/64000), lat=str(55+z/111000))
        ET.SubElement(node, "tag", k="ele", v=str(h))
    for identity, refs, tags in [(1,[1,2],{}),(2,[2,3,4,5],{"bridge":"yes","layer":"1"}),(3,[5,6],{}),
                                 (4,[7,8],{}),(5,[8,9,10,11],{"tunnel":"yes","layer":"-1","maxheight:physical":"4.5"}),(6,[11,12],{})]:
        way = ET.SubElement(root, "way", id=str(identity))
        for ref in refs: ET.SubElement(way, "nd", ref=str(ref))
        for key,value in dict(highway="residential",width="4",**tags).items(): ET.SubElement(way,"tag",k=key,v=value)
    if level_approaches:
        # Recipe 2 requires terrain-level mouths before the independent grade.
        for identity, x, z, way_id, offset in [(13,24,0,2,1),(14,116,0,2,4),(15,24,80,5,1),(16,116,80,5,4)]:
            node = ET.Element("node", id=str(identity), lon=str(9+x/64000), lat=str(55+z/111000))
            ET.SubElement(node,"tag",k="ele",v="0")
            root.insert(0,node)
            root.find(f"way[@id='{way_id}']").insert(offset,ET.Element("nd",ref=str(identity)))
        root[:] = sorted(root,key=lambda e: ({"node":0,"way":1}[e.tag],int(e.get("id"))))
    return ET.tostring(root, encoding="unicode")


def pbf(path, xml=XML):
    import osmium
    # Tests own their temporary destination; never overwrite an existing file.
    with osmium.SimpleWriter(str(path)) as writer:
        for entity in osmium.FileProcessor(osmium.io.FileBuffer(xml.encode(), "osm")):
            writer.add(entity)
    return Path(path).read_bytes()


def connected_structures_xml():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(structural_xml(level_approaches=True))
    for identity, x in [(3,48), (4,96), (9,48), (10,96)]:
        root.find(f"node[@id='{identity}']").set("lon", str(9+x/64000))
    originals = list(root.findall("way"))
    for way in originals: root.remove(way)
    identity = 0
    for way in originals:
        refs = [n.get("ref") for n in way.findall("nd")]
        groups = [refs[:3],refs[2:4],refs[3:]] if len(refs) == 6 else [refs]
        for group in groups:
            identity += 1
            derived = ET.SubElement(root, "way", id=str(identity))
            for ref in group: ET.SubElement(derived, "nd", ref=ref)
            for tag in way.findall("tag"): derived.append(ET.fromstring(ET.tostring(tag)))
    return ET.tostring(root, encoding="unicode")


def structural_junctions_xml(interior=False):
    """Synthetic separated mouths, level ground approaches, no real dataset."""
    import xml.etree.ElementTree as ET
    root = ET.Element("osm", version="0.6")
    for base, x, z, kinds in [(1,96,96,["bridge"]*3), (100,256,96,["tunnel"]*3),
                              (200,416,96,["bridge","tunnel","tunnel"]),
                              (300,96,256,["bridge","tunnel"])]:
        height = -6 if base == 100 else 6
        def node(identity, px, pz, h):
            n = ET.SubElement(root,"node",id=str(identity),lon=str(9+px/64000),lat=str(55+pz/111000))
            ET.SubElement(n,"tag",k="ele",v=str(h))
        node(base,x,z,height)
        directions = [(-60,0),(30,52),(30,-52)] if len(kinds) == 3 else [(-60,0),(60,0)]
        for index, (kind,(dx,dz)) in enumerate(zip(kinds,directions)):
            refs = [base]
            for offset, (t,h) in enumerate([(0.2,height),(0.85,0),(1,0),(1.2,0)],1):
                identity = base+index*4+offset
                node(identity,x+dx*t,z+dz*t,h)
                refs.append(identity)
            for identity, sequence, tags in [(base+index*2,refs[:4],{kind:"yes",**({"maxheight:physical":"4.5"} if kind == "tunnel" else {})}),
                                              (base+index*2+1,refs[3:],{})]:
                way = ET.SubElement(root,"way",id=str(identity))
                for ref in sequence: ET.SubElement(way,"nd",ref=str(ref))
                for key,value in dict(highway="service",width="4",surface="gravel" if index == 0 else "asphalt",**tags).items():
                    ET.SubElement(way,"tag",k=key,v=value)
    if interior:
        a,b = root.find("way[@id='1']"),root.find("way[@id='3']")
        refs = list(reversed([n.get("ref") for n in a.findall("nd")])) + [n.get("ref") for n in b.findall("nd")][1:]
        for n in a.findall("nd"): a.remove(n)
        for index, ref in enumerate(refs): a.insert(index,ET.Element("nd",ref=ref))
        root.remove(b)
    root[:] = sorted(root,key=lambda e: ({"node":0,"way":1}[e.tag],int(e.get("id"))))
    return ET.tostring(root,encoding="unicode")


if __name__ == "__main__":
    xml = structural_junctions_xml(interior=True) if len(sys.argv) > 3 and sys.argv[3] == "junctions" else connected_structures_xml() if len(sys.argv) > 3 and sys.argv[3] == "chains" else structural_xml(level_approaches=True) if len(sys.argv) > 3 and sys.argv[3] == "structures" else multipolygon_xml() if len(sys.argv) > 3 else XML
    pbf(sys.argv[1], xml.replace("12 m", sys.argv[2] + " m") if len(sys.argv) > 2 else xml)
