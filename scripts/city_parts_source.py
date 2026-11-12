#!/usr/bin/env python3
"""Writes the built-in city parts (parts/*.json, city part file v1).

The geometry is authored here in-house (MIT, no OSM-derived data) in
real-scale source centimetres around each part's local origin: x east, y north,
heights above local ground. Run from the map-editor folder:

    python scripts/city_parts_source.py parts
"""
import json
import math
import sys
from pathlib import Path

LICENSE = "MIT"
ROAD_WIDTH = 700
SIDEWALK = 200
# Builtin furniture keeps its game size while the part divides by the map's 1:D
# (up to 1:8) and its collision squares turn with the part. Spacing below, in
# source cm, keeps furniture clear at 1:8 and any angle (×√2): city trees (120 cm
# half size) 2,720 apart and 1,360 from buildings, benches (40 cm) 1,810 from trees.


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def circle(radius, count, cx=0, cy=0):
    return [[round(cx + radius * math.cos(2 * math.pi * i / count)), round(cy + radius * math.sin(2 * math.pi * i / count))] for i in range(count)]


class Part:
    def __init__(self, part_id, name, footprint):
        self.part = {"format": "miniearthure-city-part", "version": 1, "id": part_id, "name": name,
                     "license": LICENSE, "attributions": [], "footprint": footprint, "mouths": [],
                     "records": {}}

    def add(self, field, record):
        self.part["records"].setdefault(field, []).append(record)
        return record["id"]

    def node(self, node_id, x, y):
        return self.add("nodes", {"id": node_id, "position": [x, 0, y], "level": 0})

    def road(self, road_id, start, end, points, crosswalk_start=False, crosswalk_end=False, sidewalk=SIDEWALK):
        nodes = {n["id"]: n for n in self.part["records"]["nodes"]}
        line = [nodes[start]["position"]] + [[x, 0, y] for x, y in points] + [nodes[end]["position"]]
        segments = len(line) - 1
        return self.add("roads", {"id": road_id, "from": start, "to": end, "points": line,
                                  "widths_cm": [ROAD_WIDTH] * segments, "surfaces": ["asphalt"] * segments,
                                  "kind": "ground", "clearance_cm": None, "sidewalk_cm": sidewalk,
                                  "markings": {"lanes": 2, "center_line": True, "edge_lines": True,
                                               "crosswalk_start": crosswalk_start, "crosswalk_end": crosswalk_end}})

    def mouth(self, node_id, heading):
        self.part["mouths"].append({"node": node_id, "heading_deg": heading, "width_cm": ROAD_WIDTH})

    def building(self, building_id, ring, height, usage, material="concrete", roof="flat"):
        return self.add("buildings", {"id": building_id, "footprint": ring, "base_cm": 0, "height_cm": height,
                                      "usage": usage, "material": material, "roof": roof})

    def area(self, area_id, ring, surface):
        return self.add("surface_areas", {"id": area_id, "polygon": ring, "surface": surface})

    def place(self, place_id, asset, x, y, turns=0):
        return self.add("placements", {"id": place_id, "asset_id": asset, "position": [x, 0, y], "quarter_turns": turns})

    def barrier(self, barrier_id, kind, line, height, thickness):
        return self.add("barriers", {"id": barrier_id, "kind": kind, "line": line, "height_cm": height, "thickness_cm": thickness})


def junction(part_id, name, arms, footprint):
    part = Part(part_id, name, footprint)
    part.node("centre", 0, 0)
    for arm, (x, y, heading) in arms.items():
        part.node(arm, x, y)
        part.road("road-" + arm, "centre", arm, [], crosswalk_start=True)
        part.mouth(arm, heading)
    for i, (x, y) in enumerate([(800, 800), (-800, 800), (-800, -800), (800, -800)]):
        part.place("light-%d" % (i + 1), "builtin:streetlight", x, y, i % 4)
    return part


def crossroads():
    return junction("crossroads", "Four-way crossing",
                    {"east": (3000, 0, 0), "north": (0, 3000, 90), "west": (-3000, 0, 180), "south": (0, -3000, 270)},
                    rect(-3000, -3000, 3000, 3000))


def t_junction():
    return junction("t-junction", "T junction",
                    {"east": (3000, 0, 0), "west": (-3000, 0, 180), "south": (0, -3000, 270)},
                    rect(-3000, -3000, 3000, 1200))


def roundabout():
    part = Part("roundabout", "Roundabout", rect(-3500, -3500, 3500, 3500))
    ring = 1500
    names = ["east", "north", "west", "south"]
    for i, arm in enumerate(names):
        angle = math.pi / 2 * i
        part.node("ring-" + arm, round(ring * math.cos(angle)), round(ring * math.sin(angle)))
    for i, arm in enumerate(names):
        start = math.pi / 2 * i
        arc = [(round(ring * math.cos(start + math.pi / 2 * k / 6)), round(ring * math.sin(start + math.pi / 2 * k / 6))) for k in range(1, 6)]
        part.road("ring-%d" % (i + 1), "ring-" + arm, "ring-" + names[(i + 1) % 4], arc, sidewalk=None)
    for i, arm in enumerate(names):
        angle = math.pi / 2 * i
        part.node(arm, round(3500 * math.cos(angle)), round(3500 * math.sin(angle)))
        part.road("road-" + arm, "ring-" + arm, arm, [])
        part.mouth(arm, 90 * i)
    part.area("island", circle(800, 16), "grass")
    return part


def apartment_block():
    part = Part("apartment-block", "Apartment block", rect(-4000, -4000, 4000, 4000))
    for i, (x0, y0, height) in enumerate([(-3200, 1600, 4500), (800, 1600, 3600), (-3200, -2800, 3600), (800, -2800, 4500)]):
        part.building("tower-%d" % (i + 1), rect(x0, y0, x0 + 2400, y0 + 1200), height, "residential")
    part.area("playground", rect(-1500, -800, 1500, 800), "gravel")
    for i, x in enumerate((-2000, 2000)):
        part.place("tree-%d" % (i + 1), "builtin:city_tree", x, 0)
    part.barrier("hedge", "hedge", rect(-3700, -3700, 3700, 3700) + [[-3700, -3700]], 120, 60)
    return part


def low_rise_block():
    part = Part("low-rise-block", "Low-rise block", rect(-4000, -3000, 4000, 3000))
    count = 0
    for y in (1800, -1800):
        for x in (-2700, -900, 900, 2700):
            count += 1
            part.building("house-%d" % count, rect(x - 500, y - 400, x + 500, y + 400), 700, "residential",
                          "brick" if count % 2 else "wood", "gable")
    part.barrier("fence", "fence", [[-3800, 0], [3800, 0]], 120, 10)
    return part


def shop_block():
    part = Part("shop-block", "Shopping block", rect(-4000, -4000, 4000, 4000))
    part.building("shops-north", rect(-3600, 2000, 3600, 3400), 1100, "commercial")
    part.building("shops-south", rect(-3600, -3400, 1600, -2000), 900, "commercial", "brick")
    part.building("corner-tower", rect(2000, -3400, 3600, -2000), 2400, "commercial")
    part.area("square", rect(-3600, -1600, 3600, 1600), "concrete")
    for i, x in enumerate((-2800, 0, 2800)):
        part.place("tree-%d" % (i + 1), "builtin:city_tree", x, 600)
    for i, x in enumerate((-1200, 1200)):
        part.place("bench-%d" % (i + 1), "builtin:bench", x, -900)
    return part


def park():
    part = Part("park", "Park", rect(-4000, -4000, 4000, 4000))
    half = 200
    for name, (sx, sy) in {"lawn-ne": (1, 1), "lawn-nw": (-1, 1), "lawn-sw": (-1, -1), "lawn-se": (1, -1)}.items():
        x0, x1 = sorted((sx * half, sx * 3800))
        y0, y1 = sorted((sy * half, sy * 3800))
        part.area(name, rect(x0, y0, x1, y1), "grass")
    part.area("path", [[-3800, -half], [-half, -half], [-half, -3800], [half, -3800], [half, -half], [3800, -half],
                       [3800, half], [half, half], [half, 3800], [-half, 3800], [-half, half], [-3800, half]], "gravel")
    for name, (x0, y0) in {"grove-ne": (800, 800), "grove-sw": (-3400, -3400)}.items():
        part.add("zones", {"id": name, "polygon": rect(x0, y0, x0 + 2600, y0 + 2600), "kind": "orchard",
                           "spacing_cm": 700, "density_per_mille": 800, "exclusions": []})
    for i, (x, y) in enumerate([(-1200, 600), (1200, -600), (-600, -1200), (600, 1200)]):
        part.place("bench-%d" % (i + 1), "builtin:bench", x, y, 0 if abs(y) < abs(x) else 1)
    part.barrier("hedge", "hedge", rect(-3900, -3900, 3900, 3900) + [[-3900, -3900]], 120, 60)
    return part


def parking():
    part = Part("parking-lot", "Parking lot", rect(-3200, -3000, 3200, 2200))
    part.area("lot", rect(-3000, -2000, 3000, 2000), "asphalt")
    for i, x in enumerate((-2400, 0, 2400)):
        part.place("light-%d" % (i + 1), "builtin:streetlight", x, 0)
    part.barrier("fence", "fence", [[-600, -2100], [-3100, -2100], [-3100, 2100], [3100, 2100], [3100, -2100], [600, -2100]], 150, 10)
    part.node("entrance", 0, -1400)
    part.node("street", 0, -3000)
    part.road("access", "entrance", "street", [], sidewalk=None)
    part.mouth("street", 270)
    return part


def plaza():
    part = Part("plaza", "Plaza", rect(-4000, -4000, 4000, 4000))
    part.area("paving", circle(2600, 12), "concrete")
    part.building("hall", rect(-2000, 3200, 2000, 3900), 1500, "public")
    for i, (x, y) in enumerate([(1697, 1697), (-1697, 1697), (-1697, -1697), (1697, -1697)]):
        part.place("tree-%d" % (i + 1), "builtin:city_tree", x, y)
    for i, (x, y) in enumerate([(-600, 0), (600, 0)]):
        part.place("bench-%d" % (i + 1), "builtin:bench", x, y, 1)
    for i, (x, y) in enumerate([(-3200, -3200), (3200, -3200)]):
        part.place("light-%d" % (i + 1), "builtin:streetlight", x, y)
    return part


BUILDERS = (crossroads, t_junction, roundabout, apartment_block, low_rise_block, shop_block, park, parking, plaza)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: city_parts_source.py OUTPUT_DIR")
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    for index, build in enumerate(BUILDERS):
        part = build().part
        (target / ("%02d-%s.json" % (index + 1, part["id"]))).write_text(json.dumps(part, indent=1) + "\n")


if __name__ == "__main__":
    main()
