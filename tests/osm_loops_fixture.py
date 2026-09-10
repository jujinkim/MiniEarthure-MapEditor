"""Synthetic loop and incident highways; no external datasets."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from osm_fixture import pbf


def xml(mode="plain"):
    root = ET.Element("osm", version="0.6", generator="mapeditor-synthetic-loops")
    # Four-node ring, a through approach at node 1 and one at node 3. Node 10
    # coincides with 2 but is not a source graph connection.
    positions = {1:(40,40),2:(140,40),3:(140,140),4:(40,140),
                 5:(0,40),6:(60,60),7:(180,140),8:(220,160),
                 10:(140,40),11:(180,0)}
    if mode == "collapse": positions[2] = (40.001,40)
    structural_mode = mode in ("direct_bridge", "direct_tunnel", "closed_bridge", "closed_tunnel", "closed_join_bridge")
    if structural_mode:
        # Broad octagonal bends and separated incident mouths satisfy the
        # existing native apron contract; no implicit corner repair is claimed.
        positions.update({1:(40,80),12:(80,40),2:(140,40),13:(180,80),
                          3:(180,140),14:(140,180),4:(80,180),15:(40,140),
                          5:(0,60),7:(220,160),8:(260,180)})
    if mode == "closed_join_bridge": positions.update({16:(160,0),17:(180,-40),18:(190,-60),19:(175,-30)})
    if mode in ("direct_bridge", "direct_tunnel"):
        positions.update({9:(300,200),19:(190,145),20:(250,175)})
    for identity,(x,z) in positions.items():
        node = ET.SubElement(root,"node",id=str(identity),lon=str(9+x/64000),lat=str(55+z/111000))
        if mode == "height": ET.SubElement(node,"tag",k="ele",v="3")
        elif structural_mode:
            elevated = identity in (2,4) if mode.startswith("closed") else identity == 7
            height = (-6 if mode.endswith("tunnel") else 6) if elevated or (mode == "closed_join_bridge" and identity == 16) else 0
            ET.SubElement(node,"tag",k="ele",v=str(height))
    ways = [(1,[1,12,2,13,3,14,4,15,1] if structural_mode else [1,2,3,4,1]),
            (2,[5,1] if structural_mode else [5,1,6]),(3,[3,19,7,20,8] if mode.startswith("direct") else [3,7,8]),(4,[10,11])]
    for identity, refs in ways:
        way = ET.SubElement(root,"way",id=str(identity))
        for ref in refs: ET.SubElement(way,"nd",ref=str(ref))
        for k,v in dict(highway="residential",width="4",surface="asphalt").items(): ET.SubElement(way,"tag",k=k,v=v)
        if identity == 1:
            ET.SubElement(way,"tag",k="junction",v="roundabout")
            ET.SubElement(way,"tag",k="oneway",v="yes")
        if (mode.startswith("closed_") and identity == 1) or (mode.startswith("direct_") and identity == 3):
            kind = mode.split("_")[-1]
            ET.SubElement(way,"tag",k=kind,v="yes")
            if kind == "tunnel": ET.SubElement(way,"tag",k="maxheight:physical",v="4.5")
    if mode.startswith("direct_"):
        way = ET.SubElement(root,"way",id="5")
        for ref in [8,9]: ET.SubElement(way,"nd",ref=str(ref))
        for k,v in dict(highway="residential",width="4",surface="asphalt").items(): ET.SubElement(way,"tag",k=k,v=v)
    if mode == "closed_join_bridge":
        for identity, refs, extra in [(5,[2,16,19,17],{"bridge":"yes"}),(6,[17,18],{})]:
            way = ET.SubElement(root,"way",id=str(identity))
            for ref in refs: ET.SubElement(way,"nd",ref=str(ref))
            for k,v in dict(highway="residential",width="4",surface="asphalt",**extra).items(): ET.SubElement(way,"tag",k=k,v=v)
    return ET.tostring(root,encoding="unicode")


if __name__ == "__main__":
    pbf(Path(sys.argv[1]),xml(sys.argv[2] if len(sys.argv)>2 else "plain"))
