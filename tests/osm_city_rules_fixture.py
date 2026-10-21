"""Synthetic city sites, ground and barriers (metre layout near 9°E 55°N)."""
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from osm_fixture import pbf

LON_M = 111320 * math.cos(math.radians(55))
LAT_M = 110540
BBOX = (8.9995, 54.9995, 9.0135, 55.004)


def xml():
    root = ET.Element("osm", version="0.6", generator="mapeditor-city-rules-test")
    nodes, ways, relations, next_id = [], [], [], [1]
    def node(x, y, **tags):
        identity = next_id[0]; next_id[0] += 1
        element = ET.Element("node", id=str(identity), lon=f"{9 + x / LON_M:.9f}", lat=f"{55 + y / LAT_M:.9f}")
        for k, v in tags.items(): ET.SubElement(element, "tag", k=k, v=str(v))
        nodes.append(element)
        return identity
    def way(identity, refs, **tags):
        w = ET.Element("way", id=str(identity))
        for ref in refs: ET.SubElement(w, "nd", ref=str(ref))
        for k, v in tags.items(): ET.SubElement(w, "tag", k=k.replace("__", ":"), v=str(v))
        ways.append(w)
    def rectangle(identity, x0, y0, x1, y1, **tags):
        refs = [node(x0, y0), node(x1, y0), node(x1, y1), node(x0, y1)]
        way(identity, refs + [refs[0]], **tags)
    def line(identity, points, **tags):
        way(identity, [node(x, y) for x, y in points], **tags)
    # Apartment complex: 20 % coverage, two named towers, a footway gate and an
    # explicit fence on its top edge.
    rectangle(1, 0, 0, 120, 100, landuse="residential", name="Synthetic Apartments")
    rectangle(2, 10, 10, 50, 30, building="apartments", name="101", height=30)
    rectangle(3, 60, 10, 100, 30, building="apartments", name="102", height=30)
    rectangle(4, 10, 50, 50, 70, building="apartments", building__levels=9)
    line(5, [(60, -20), (60, 40)], highway="footway")
    line(6, [(0, 101), (120, 101)], barrier="fence", height="1.8")
    # School ground with its school building (a landmark record).
    rectangle(10, 200, 0, 300, 80, amenity="school", name="Synthetic School")
    rectangle(11, 220, 20, 260, 40, building="school")
    # Park with a pond, parking, hedge, wall and a waist-high fence.
    rectangle(20, 0, 150, 100, 250, leisure="park")
    rectangle(21, 30, 180, 50, 200, natural="water")
    rectangle(22, 150, 150, 180, 170, amenity="parking")
    line(23, [(150, 200), (190, 200)], barrier="hedge")
    line(24, [(150, 220), (190, 220)], barrier="wall")
    way(25, [node(150, 240), node(170, 240, barrier="lift_gate"), node(190, 240)], barrier="fence", fence_type="chain_link")  # A lift gate opens it.
    # Ordinary houses (one record), a historic house and a named house apart.
    rectangle(30, 350, 10, 360, 20, building="house")
    rectangle(31, 365, 10, 375, 20, building="house")
    rectangle(32, 380, 10, 390, 20, building="house", historic="yes")
    rectangle(33, 400, 10, 410, 20, building="house", name="Named House")
    # Industrial ground (inferred wall).
    rectangle(40, 350, 100, 450, 180, landuse="industrial")
    # Two sheds of one type=site relation in different 256 m tiles.
    rectangle(50, 520, 10, 530, 20, building="shed")
    rectangle(51, 800, 10, 810, 20, building="shed")
    rel = ET.Element("relation", id="900")
    for ref in (50, 51): ET.SubElement(rel, "member", type="way", ref=str(ref), role="")
    ET.SubElement(rel, "tag", k="type", v="site")
    relations.append(rel)
    # A road so the city has a road network.
    line(60, [(-10, -10), (500, -10)], highway="residential", width=6)
    root.extend(nodes + sorted(ways, key=lambda w: int(w.attrib["id"])) + relations)
    return ET.tostring(root, encoding="unicode")


if __name__ == "__main__": pbf(Path(sys.argv[1]), xml())
