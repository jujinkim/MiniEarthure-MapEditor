"""Bounded, offline, user-declared EGM96 -> EGM2008 height differences.

The grid is a prepared local correction surface, not a geoid model inferred from
terrain. Original UTF-8 bytes are retained in the reviewed layer provenance.
"""
import copy
import hashlib
import math
from import_layer import number, text, strict_json, MAX_POINTS

MAX_GRID_BYTES = 64 * 1024
CRS = {"EGM96": "EPSG:5773 / EGM96 metres", "EGM2008": "EPSG:3855 / EGM2008 metres"}
ORDER = "source vertices before crop; target heights linearly interpolated at cuts; round once to cm"


def read_options(path):
    # CLI inputs are ordinary local files, never URLs/GDAL virtual paths.
    if not path.is_file(): raise ValueError("vertical request must be a local file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_GRID_BYTES * 2 + 1)
    if len(raw) > MAX_GRID_BYTES * 2: raise ValueError("vertical request exceeds 128 KiB")
    return strict_json(raw)


class Vertical:
    def __init__(self, options):
        if not isinstance(options, dict) or set(options) != {"target", "zero_m", "grid"}:
            raise ValueError("vertical requires target, zero_m and grid")
        target = options["target"]
        if target not in CRS: raise ValueError("unsupported vertical datum")
        zero = number(options["zero_m"], "vertical zero", -10000, 10000)
        if zero * 100 != round(zero * 100) and abs(zero * 100 - round(zero * 100)) > 1e-8:
            raise ValueError("vertical zero must be whole centimetres")
        self.zero = zero
        self.grid = None
        self.metadata = dict(profile="osm-vertical-v1", source_crs=CRS["EGM96"],
            target_crs=CRS[target], vertical_zero_m=zero, order=ORDER,
            method="offset" if target == "EGM96" else "bilinear-local-delta-grid-v1",
            grid_source=None, explicit_points=0, explicit_roads=0, delta_range_m=None)
        if target == "EGM96":
            if options["grid"] is not None: raise ValueError("EGM96 offset must not specify a correction grid")
            return
        raw = options["grid"]
        if not isinstance(raw, str) or not 0 < len(raw.encode("utf-8")) <= MAX_GRID_BYTES:
            raise ValueError("EGM2008 requires a local UTF-8 correction grid of at most 64 KiB")
        grid = strict_json(raw)
        required = {"format", "source", "license", "accuracy", "horizontal_crs", "source_crs", "target_crs", "quantity", "bbox", "columns", "rows", "values_m"}
        if not isinstance(grid, dict) or set(grid) != required:
            raise ValueError("invalid local correction grid fields")
        for key, expected in dict(format="miniearthure-height-delta-v1", horizontal_crs="EPSG:4326",
                source_crs=CRS["EGM96"], target_crs=CRS["EGM2008"], quantity="H_EGM2008-minus-H_EGM96").items():
            if grid[key] != expected: raise ValueError("invalid correction grid " + key)
        for key in ("source", "license", "accuracy"): text(grid[key], "correction " + key)
        for key in ("columns", "rows"):
            n = number(grid[key], "grid " + key, 2, 33)
            if int(n) != n: raise ValueError("grid dimensions must be integers")
            grid[key] = int(n)
        bbox = grid["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4: raise ValueError("grid bbox requires west/south/east/north")
        for i, n in enumerate(bbox): number(n, "grid bbox", -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84)
        if not 0 < bbox[2]-bbox[0] <= 1 or not 0 < bbox[3]-bbox[1] <= 1:
            raise ValueError("grid bbox must be ordered, at most one degree per side, without dateline crossing")
        values = grid["values_m"]
        if not isinstance(values, list) or len(values) != grid["columns"] * grid["rows"]:
            raise ValueError("grid samples must fill every row and column")
        for n in values: number(n, "grid delta (no nodata)", -200, 200)
        self.grid = grid
        payload = raw.encode("utf-8")
        self.metadata["grid_source"] = dict(json=raw, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())

    def delta(self, point):
        if self.grid is None: return 0
        lon, lat = point
        g = self.grid
        west, south, east, north = g["bbox"]
        if not west <= lon <= east or not south <= lat <= north:
            raise ValueError("explicit source vertex outside correction grid; include complete ways and approaches")
        x = (lon-west)/(east-west)*(g["columns"]-1)
        y = (lat-south)/(north-south)*(g["rows"]-1)
        ix, iy = min(math.floor(x), g["columns"]-2), min(math.floor(y), g["rows"]-2)
        fx, fy = x-ix, y-iy
        offset = iy*g["columns"]+ix
        a,b = g["values_m"][offset:offset+2]
        c,d = g["values_m"][offset+g["columns"]:offset+g["columns"]+2]
        return (a*(1-fx)+b*fx)*(1-fy)+(c*(1-fx)+d*fx)*fy

    def apply(self, value):
        result = copy.deepcopy(value)
        points, roads, low, high = 0, 0, None, None
        for feature in result["features"]:
            properties = feature["properties"]
            if "elevations_m" not in properties: continue
            coordinates = feature["geometry"]["coordinates"]
            if len(coordinates) != len(properties["elevations_m"]): raise ValueError("vertical profile size mismatch")
            roads += 1
            converted = []
            for point, height in zip(coordinates, properties["elevations_m"]):
                points += 1
                if points > MAX_POINTS: raise ValueError("vertical point budget exceeded")
                delta = self.delta(point)
                low = delta if low is None else min(low, delta)
                high = delta if high is None else max(high, delta)
                converted.append(number(number(height, "source elevation", -10000, 10000)+delta-self.zero,
                    "converted local elevation", -10000, 10000))
            properties["elevations_m"] = converted
        self.metadata.update(explicit_points=points, explicit_roads=roads, delta_range_m=[low, high] if points else None)
        if not points and (self.grid is not None or self.zero != 0):
            raise ValueError("vertical conversion requires explicit OSM node heights; no estimated heights are converted")
        return result
