"""Synthetic heights only; this is not a geographic correction model."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from osm_fixture import structural_xml, pbf


def grid(values=None):
    return dict(format="miniearthure-height-delta-v1", source="Synthetic difference surface; no survey accuracy",
        license="CC0 synthetic fixture", accuracy="unknown; synthetic only", horizontal_crs="EPSG:4326",
        source_crs="EPSG:5773 / EGM96 metres", target_crs="EPSG:3855 / EGM2008 metres",
        quantity="H_EGM2008-minus-H_EGM96", bbox=[9.5,55.5,9.504,55.504], columns=2, rows=2,
        values_m=[2,2,2,2] if values is None else values)


def xml(level_approaches=False):
    root = ET.fromstring(structural_xml(level_approaches))
    for node in root.findall("node"):
        node.set("lon",str(float(node.get("lon")) + 0.5))
        node.set("lat",str(float(node.get("lat")) + 0.5))
        ele = node.find("tag")
        ele.set("v",str(float(ele.get("v")) + 100))
    return ET.tostring(root, encoding="unicode")


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    (directory / "correction.json").write_text(json.dumps(grid(),ensure_ascii=False),encoding="utf-8")
    (directory / "source.osm").write_text(xml(level_approaches=True),encoding="utf-8")
    pbf(directory / "source.osm.pbf", xml(level_approaches=True))
    import numpy as np
    import rasterio
    from rasterio.transform import Affine
    with rasterio.open(directory / "terrain.tif", "w", driver="GTiff", width=3600, height=3600,
            count=1, dtype="float32", crs="EPSG:4326", transform=Affine(1/3600,0,9-0.5/3600,0,-1/3600,56+0.5/3600),
            tiled=True, blockxsize=1024, blockysize=1024, compress="deflate", predictor=3, nodata=-9999) as out:
        out.write(np.full((3600,3600),102,dtype=np.float32),1)
