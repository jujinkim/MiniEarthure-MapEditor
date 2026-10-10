"""Synthetic overlapping city footprints and compatible source road chains."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from osm_fixture import pbf


def xml():
    root=ET.Element("osm",version="0.6",generator="mapeditor-city-test")
    nodes, ways, next_id = [], [], 1
    def node(x,y):
        nonlocal next_id
        identity=next_id; next_id+=1
        nodes.append(ET.Element("node",id=str(identity),lon=str(9+x*.00001),lat=str(55+y*.00001)))
        return identity
    def way(identity,refs,tags):
        w=ET.Element("way",id=str(identity))
        for ref in refs: ET.SubElement(w,"nd",ref=str(ref))
        for k,v in tags.items(): ET.SubElement(w,"tag",k=k,v=str(v))
        ways.append(w)
    def rectangle(identity,x,y,width,height,tags):
        refs=[node(x,y),node(x+width,y),node(x+width,y+height),node(x,y+height)]
        way(identity,refs+[refs[0]],tags)
    for i in range(6): rectangle(i+1,10+i*6,20,8,8,{"building":"yes"})
    rectangle(10,80,20,8,8,{"building":"yes","name":"한글 도서관"})
    rectangle(11,100,20,8,8,{"building":"yes","height":"80"})
    a,b,c=node(0,0),node(40,0),node(80,0)
    way(20,[a,b],{"highway":"residential","width":"4"})
    way(21,[b,c],{"highway":"residential","width":"4"})
    rectangle(30,20,60,20,20,{"landuse":"forest"})
    rectangle(31,30,60,20,20,{"landuse":"forest"})
    root.extend(nodes+sorted(ways,key=lambda w:int(w.attrib["id"])))
    return ET.tostring(root,encoding="unicode")


if __name__=="__main__": pbf(Path(sys.argv[1]),xml())
