#!/usr/bin/env python3
"""Author a tiny MIT terrain-only vehicle tuning map in a NEW directory.

MapKit owns packing, generation and collision. Coordinates are authored metres;
the consuming game's 1:8 presentation makes this a 128 m square test area.
"""
import argparse
import json
from pathlib import Path
import struct
import zlib

from reference_maps import canonical, empty, summarize

PROFILE = "physics-test-v1"
SIZE_M = 1024
SPACING_M = 32
HILLS = [(704, 640, 192, 16), (320, 768, 128, 8)]


def height_cm(x, y):
    # Compact smooth bumps: exactly flat outside each radius, zero edge slope.
    value = 0.0
    for cx, cy, radius, height in HILLS:
        r2 = ((x - cx) ** 2 + (y - cy) ** 2) / radius ** 2
        if r2 < 1:
            value += height * (1 - r2) ** 3
    return round(value * 100)


def terrain_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    side = SIZE_M // SPACING_M + 1
    rows = b"".join(b"\0" + b"".join(struct.pack(">H", height_cm(x * SPACING_M, y * SPACING_M))
                                  for x in range(side)) for y in range(side))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 16, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def create(destination):
    doc = empty(PROFILE, SIZE_M * 100, SIZE_M * 100)
    doc["recipe_version"] = 5
    doc["attributions"] = [dict(source=PROFILE, license="MIT", notice="Original synthetic terrain for vehicle tuning; no external data or assets.")]
    doc["provenance"].update(tool_id="mapeditor-physics-test", build_id=PROFILE,
                             first_created="2026-09-11T00:00:00Z", last_edited="2026-09-11T00:00:00Z")
    doc["heightmaps"] = [dict(cell=dict(x=0, y=0), path="terrain/hills.png",
                              spacing_cm=SPACING_M * 100, offset_cm=0, step_cm=1, source_accuracy_cm=None)]
    payloads = {"terrain/hills.png": terrain_png()}
    locations = [dict(id="start", title="Flat ground", position_cm=[51200, 0, 25600],
                      surface_id="terrain", heading_degrees=0),
                 dict(id="hill", title="Gentle hill approach", position_cm=[70400, height_cm(704, 512), 51200],
                      surface_id="terrain", heading_degrees=0)]
    report = summarize(doc, payloads, dict(locations=locations, routes=[],
        start=dict(x_cm=51200, y_cm=25600, surface_id="terrain", heading_degrees=0),
        limitations=["Terrain material only; no paved friction comparison or scenery.",
                     "Finite test area; existing runtime boundary recovery remains active."]))
    report["profile"] = PROFILE
    report["terrain"] = dict(spacing_cm=SPACING_M * 100, source_accuracy_cm=None,
        description="Single 33x33 PNG16 heightfield, flat ground and two compact smooth hills",
        hills=[dict(center_m=[x, y], radius_m=r, height_m=h) for x, y, r, h in HILLS])
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in {"document.json": canonical(doc), **payloads,
                       "driving.json": (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()}.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    report = create(parser.parse_args().destination)
    print(json.dumps({k: report[k] for k in ("map_id", "cell_count", "counts")}, indent=2))
