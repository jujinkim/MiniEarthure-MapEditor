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
    for identity,(x,z) in positions.items():
        node = ET.SubElement(root,"node",id=str(identity),lon=str(9+x/64000),lat=str(55+z/111000))
        if mode == "height": ET.SubElement(node,"tag",k="ele",v="3")
    for identity, refs in [(1,[1,2,3,4,1]),(2,[5,1,6]),(3,[3,7,8]),(4,[10,11])]:
        way = ET.SubElement(root,"way",id=str(identity))
        for ref in refs: ET.SubElement(way,"nd",ref=str(ref))
        for k,v in dict(highway="residential",width="4",surface="asphalt").items(): ET.SubElement(way,"tag",k=k,v=v)
        if identity == 1:
            ET.SubElement(way,"tag",k="junction",v="roundabout")
            ET.SubElement(way,"tag",k="oneway",v="yes")
    return ET.tostring(root,encoding="unicode")


if __name__ == "__main__":
    pbf(Path(sys.argv[1]),xml(sys.argv[2] if len(sys.argv)>2 else "plain"))
