"""Offline regional classification; source facts, auxiliary evidence and estimates stay distinct.

Only authoring code reads snapshots. Style IDs are shared MapKit v1 identifiers.
A regional request is opt-in: absent requests keep existing v1 import semantics.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from shapely.geometry import Point, Polygon, shape
from shapely.strtree import STRtree

AXES = {"architecture": "architectures", "climate": "climates", "settlement": "settlements", "terrain": "terrains"}
DEFAULT = dict(architecture="modern", climate="temperate", settlement="city", terrain="plain")
SURFACES = {"asphalt":"asphalt", "concrete":"concrete", "concrete:plates":"concrete", "paving_stones":"pavers",
    "sett":"stone_paving", "cobblestone":"stone_paving", "pebblestone":"gravel", "gravel":"gravel", "fine_gravel":"gravel",
    "compacted":"compacted_earth", "dirt":"compacted_earth", "earth":"compacted_earth", "ground":"compacted_earth",
    "sand":"sand", "rock":"rock", "grass":"managed_lawn", "grass_paver":"pavers", "snow":"snow", "ice":"ice"}
BUILDINGS = {"house":"detached", "detached":"detached", "bungalow":"detached", "villa":"detached", "cabin":"detached",
    "terrace":"terraced", "semidetached_house":"terraced", "apartments":"apartment", "dormitory":"apartment",
    "residential":"lowrise", "retail":"shop", "shop":"shop", "kiosk":"shop", "commercial":"mixed_use", "office":"office",
    "hotel":"hotel", "supermarket":"shopping", "mall":"shopping", "school":"school", "kindergarten":"school",
    "university":"university", "college":"university", "hospital":"hospital", "clinic":"hospital",
    "public":"civic", "civic":"civic", "government":"civic", "library":"civic", "museum":"civic", "fire_station":"civic",
    "church":"religious", "cathedral":"religious", "chapel":"religious", "mosque":"religious", "temple":"religious",
    "synagogue":"religious", "shrine":"religious", "train_station":"station", "transportation":"station",
    "industrial":"factory", "factory":"factory", "manufacture":"factory", "warehouse":"warehouse", "hangar":"warehouse",
    "farm":"farmhouse", "farmhouse":"farmhouse", "barn":"barn", "cowshed":"barn", "stable":"barn",
    "farm_auxiliary":"barn", "greenhouse":"utility", "service":"utility", "shed":"utility", "garage":"utility",
    "garages":"utility", "research":"research"}
AMENITIES = {**BUILDINGS, "place_of_worship":"religious", "townhall":"civic", "police":"civic", "courthouse":"civic",
    "community_centre":"civic", "public_building":"civic", "research_institute":"research"}
MATERIALS = {"timber_framing":"wood", "reinforced_concrete":"concrete", "cement_block":"concrete", "steel":"metal",
    "limestone":"stone", "sandstone":"stone", "render":"plaster"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def catalogue(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "addons/mapkit/godot/regional_catalog.json"
    value = json.loads(path.read_text())
    if value.get("version") != 1: raise ValueError("regional catalogue must be v1")
    return value


def profile(value, catalog, base=None):
    if not isinstance(value, dict) or set(value) - AXES.keys(): raise ValueError("regional profile has unknown axes")
    result = dict(DEFAULT if base is None else base)
    for axis, option in value.items():
        if not isinstance(option, str) or option not in catalog[AXES[axis]]: raise ValueError("unknown regional " + axis)
        result[axis] = option
    return result


def snapshot(descriptor, kind):
    required = {"path", "sha256", "release", "bbox", "source_url", "license"}
    if not isinstance(descriptor, dict) or set(descriptor) != required: raise ValueError(kind + " needs path, sha256, release, bbox, source_url and license")
    if not re.fullmatch(r"[0-9a-f]{64}", str(descriptor["sha256"])): raise ValueError("invalid " + kind + " SHA-256")
    if not isinstance(descriptor["path"], str) or not Path(descriptor["path"]).is_file(): raise ValueError("missing requested " + kind + " snapshot")
    for key in ("release", "source_url", "license"):
        if not isinstance(descriptor[key], str) or not descriptor[key].strip(): raise ValueError("missing " + kind + " " + key)
    bbox = descriptor["bbox"]
    if (not isinstance(bbox, list) or len(bbox) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox)
        or not -180 <= bbox[0] < bbox[2] <= 180 or not -80 <= bbox[1] < bbox[3] <= 84): raise ValueError("invalid " + kind + " coverage")
    if Path(descriptor["path"]).stat().st_size > 512 * 1024 * 1024: raise ValueError(kind + " local snapshot exceeds 512 MiB")
    data = Path(descriptor["path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != descriptor["sha256"]: raise ValueError(kind + " snapshot SHA-256 mismatch")
    if kind == "worldcover" and descriptor["release"] != "2021-v200": raise ValueError("WorldCover release must be 2021-v200")
    if kind == "buildings" and not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]+", descriptor["release"]): raise ValueError("invalid fixed Overture release")
    return data


def validate(request, catalog, source_sha=None, bounds=None, read_sources=True):
    if not isinstance(request, dict) or request.get("version") != 1 or set(request) - {"version", "profile", "regions", "overrides", "worldcover", "buildings"}:
        raise ValueError("regional request must use v1 keys")
    profile(request.get("profile", {}), catalog)
    regions = request.get("regions", [])
    if not isinstance(regions, list) or len(regions) > 64: raise ValueError("regional regions must contain at most 64 records")
    ids = set()
    for region in regions:
        if not isinstance(region, dict) or set(region) != {"id", "polygon", "profile"} or not isinstance(region["id"], str) or not region["id"] or region["id"] in ids: raise ValueError("invalid or duplicate regional region")
        ids.add(region["id"])
        points = region["polygon"]
        if not isinstance(points, list) or not 3 <= len(points) <= 64: raise ValueError("regional polygon needs 3..64 vertices")
        if any(not isinstance(p, list) or len(p) != 2 or any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) for x in p) or not -180 <= p[0] <= 180 or not -80 <= p[1] <= 84 for p in points): raise ValueError("regional polygon must be WGS84 longitude/latitude")
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= 0: raise ValueError("invalid regional polygon")
        profile(region["profile"], catalog)
    overrides = request.get("overrides", {})
    if overrides:
        if not isinstance(overrides, dict) or set(overrides) != {"osm_sha256", "objects"} or overrides["osm_sha256"] != source_sha: raise ValueError("regional overrides need the exact OSM snapshot hash")
        if not isinstance(overrides["objects"], list) or not 1 <= len(overrides["objects"]) <= 10000: raise ValueError("invalid regional override count")
        ids = set()
        for row in overrides["objects"]:
            if not isinstance(row, dict) or set(row) - {"source_id", "architecture", "building_type", "material", "ground", "height_m"} or len(row) < 2: raise ValueError("invalid regional override")
            sid = row.get("source_id", "")
            if not re.fullmatch(r"(?:way|relation)/[1-9][0-9]*", sid) or sid in ids: raise ValueError("invalid/duplicate regional override source")
            ids.add(sid)
            for key, table in (("architecture", "architectures"), ("building_type", "building_types"), ("material", "materials"), ("ground", "ground")):
                if key in row and row[key] not in catalog[table]: raise ValueError("unknown regional override " + key)
            if "height_m" in row and (isinstance(row["height_m"], bool) or not isinstance(row["height_m"], (int,float)) or not math.isfinite(row["height_m"]) or not .1 <= row["height_m"] <= 1000): raise ValueError("invalid regional height override")
    for key in ("worldcover", "buildings"):
        if key not in request: continue
        desc = request[key]
        if read_sources: snapshot(desc, key)
        if bounds and (desc["bbox"][0] > bounds[0] or desc["bbox"][1] > bounds[1] or desc["bbox"][2] < bounds[2] or desc["bbox"][3] < bounds[3]): raise ValueError(key + " snapshot does not cover requested extent")
    return deepcopy(request)


def input_receipt(request):
    result = deepcopy(request)
    for key in ("worldcover", "buildings"):
        if key in result: result[key].pop("path", None)
    return result


def selected_profile(request, point, catalog):
    result = profile(request.get("profile", {}), catalog)
    region_id = "default"
    for region in request.get("regions", []):
        if Polygon(region["polygon"]).covers(point):
            result = profile(region["profile"], catalog, result)
            region_id = region["id"]
            break
    return result, region_id


def ground(tags):
    if tags.get("surface") in SURFACES: return SURFACES[tags["surface"]], "source:surface"
    natural, use = tags.get("natural"), tags.get("landuse")
    for values, style in (({"bare_rock", "scree", "shingle"}, "rock"), ({"sand", "beach"}, "sand"), ({"scrub", "heath"}, "scrub"), ({"wood"}, "forest_floor"), ({"wetland", "mud"}, "wetland"), ({"glacier"}, "ice"), ({"grassland"}, "grassland")):
        if natural in values: return style, "source:natural"
    styles = {"forest":"forest_floor", "orchard":"orchard", "vineyard":"orchard", "farmland":"cropland", "farmyard":"compacted_earth", "meadow":"grassland", "grass":"managed_lawn", "flowerbed":"managed_lawn", "recreation_ground":"managed_lawn", "village_green":"managed_lawn"}
    if use in styles: return styles[use], "source:landuse"
    if tags.get("leisure") in ("park", "garden", "golf_course"): return "managed_lawn", "source:leisure"
    if tags.get("amenity") == "parking": return "asphalt", "context:parking"
    if tags.get("highway") in ("pedestrian", "footway", "steps", "cycleway"): return "pavers", "context:walking"
    return None, None


def building_type(tags, height, settlement):
    for field, table in (("amenity", AMENITIES), ("building", BUILDINGS)):
        if tags.get(field) in table:
            kind = table[tags[field]]
            if kind == "apartment" and height >= 40: kind = "residential_tower"
            if tags.get("shop") and kind in ("lowrise", "apartment", "residential_tower"): kind = "mixed_use"
            return kind, "source:" + field
    if tags.get("shop"): return "shop", "source:shop"
    if tags.get("office"): return "office", "source:office"
    if tags.get("tourism") == "hotel": return "hotel", "source:tourism"
    if tags.get("industrial"): return "factory", "source:industrial"
    if settlement in ("rural", "village", "sparse", "wilderness"): return "detached", "context:profile"
    if settlement == "industrial": return "utility", "context:profile"
    return "lowrise", "context:profile"


def read_buildings(descriptor):
    value = json.loads(snapshot(descriptor, "buildings"))
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or value.get("release") != descriptor["release"] or value.get("bbox") != descriptor["bbox"] or not isinstance(value.get("features"), list): raise ValueError("invalid pinned Overture building snapshot")
    rows, ids = [], set()
    for feature in value["features"]:
        props = feature.get("properties", {})
        sid = props.get("id")
        if not isinstance(sid, str) or not sid or sid in ids: raise ValueError("missing/duplicate Overture building ID")
        ids.add(sid)
        geometry = shape(feature["geometry"])
        if not geometry.is_valid or geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"): raise ValueError("invalid Overture building footprint " + sid)
        for key in ("height", "min_height", "num_floors"):
            number = props.get(key)
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int,float)) or not math.isfinite(number) or number < 0 or number > 1000): raise ValueError("invalid Overture " + key)
        if props.get("has_parts") and not props.get("parts_complete"): raise ValueError("requested Overture building parts missing for " + sid)
        part_ids = set()
        for part in props.get("parts") or []:
            if not isinstance(part, dict) or not isinstance(part.get("id"), str) or part["id"] in part_ids or part.get("building_id") != sid: raise ValueError("invalid Overture building part identity " + sid)
            part_ids.add(part["id"])
            footprint = shape(part["geometry"])
            if not footprint.is_valid or footprint.is_empty or footprint.geom_type not in ("Polygon", "MultiPolygon"): raise ValueError("invalid Overture building part geometry " + sid)
            for key in ("height", "min_height"):
                number = part.get(key)
                if number is not None and (isinstance(number, bool) or not isinstance(number, (int,float)) or not math.isfinite(number) or not 0 <= number <= 1000): raise ValueError("invalid Overture part " + key)
        rows.append((props, geometry))
    return sorted(rows, key=lambda row: row[0]["id"])


def source_ids(props):
    result = set()
    for source in props.get("sources") or []:
        if not isinstance(source, dict): continue
        value = str(source.get("record_id", ""))
        match = re.search(r"(?:^|/)(way|relation)/([0-9]+)$", value)
        if match: result.add(match.group(1) + "/" + match.group(2))
        compact = re.fullmatch(r"([wr])([1-9][0-9]*)(?:@[1-9][0-9]*)?", value)
        if compact: result.add(("way/" if compact.group(1) == "w" else "relation/") + compact.group(2))
    return result


def annotate(collection, request, source_sha, catalog, bounds=None):
    """Annotate original polygons before generalization; no network or source mutation."""
    validate(request, catalog, source_sha, bounds)
    result = deepcopy(collection)
    overrides = {row["source_id"]: row for row in request.get("overrides", {}).get("objects", [])}
    present = {f["properties"].get("osm_source_id") for f in result["features"]}
    if set(overrides) - present: raise ValueError("regional override source absent from selected extent: " + ", ".join(sorted(set(overrides) - present)))
    auxiliaries = read_buildings(request["buildings"]) if "buildings" in request else []
    tree = STRtree([g for p,g in auxiliaries])
    by_id = {}
    for i, (p,g) in enumerate(auxiliaries):
        for sid in source_ids(p): by_id.setdefault(sid, []).append(i)
    report = {"request": input_receipt(request), "counts": {}, "objects": []}
    counts = Counter()
    for feature in result["features"]:
        p = feature["properties"]
        geometry = shape(feature["geometry"])
        selected, region_id = selected_profile(request, geometry.representative_point(), catalog)
        tags = p.get("_city_source_tags", p.get("_city_road_tags", {}))
        sid = p.get("osm_source_id", "")
        author = overrides.get(sid, {})
        evidence = {}
        p["_city_regional"] = dict(profile=selected, region=region_id, evidence=evidence)
        if geometry.geom_type in ("Polygon", "MultiPolygon") and not (p.get("osm_region") or p.get("landuse") in ("forest", "orchard")):
            candidates = set(by_id.get(sid, [])) | set(int(i) for i in tree.query(geometry))
            matches = []
            for i in candidates:
                aux, footprint = auxiliaries[i]
                if aux.get("is_underground"): continue
                overlap = geometry.intersection(footprint).area
                iou = overlap / max(geometry.union(footprint).area, 1e-20)
                if sid in source_ids(aux) or iou >= .5: matches.append((sid in source_ids(aux), iou, aux["id"], aux))
            aux = sorted(matches, key=lambda x: (-x[0], -x[1], x[2]))[0][3] if matches else {}
            if "height_m" in author:
                p["height_m"] = author["height_m"]; evidence["height"] = "author"
            elif "height_m" in p: evidence["height"] = "source:height"
            elif "_city_levels" in p: evidence["height"] = "source:levels"
            elif aux.get("height"):
                p["height_m"] = aux["height"]; evidence["height"] = "auxiliary:height"
            elif aux.get("num_floors"):
                p["height_m"] = aux["num_floors"] * 3; evidence["height"] = "auxiliary:floors"
            kind, basis = building_type(tags or {"building": p.get("_city_building", "yes")}, float(p.get("height_m", 0)), selected["settlement"])
            if basis == "context:profile" and aux.get("class") in BUILDINGS: kind, basis = BUILDINGS[aux["class"]], "auxiliary:class"
            if "building_type" in author: kind, basis = author["building_type"], "author"
            evidence["type"] = basis
            arch = author.get("architecture", selected["architecture"])
            evidence["architecture"] = "author" if "architecture" in author else "context:profile"
            material = tags.get("building:material", "")
            material = MATERIALS.get(material, material)
            if "material" in author: material, basis = author["material"], "author"
            elif material in catalog["materials"]: basis = "source:material"
            elif aux.get("facade_material") in catalog["materials"]: material, basis = aux["facade_material"], "auxiliary:material"
            else: material, basis = catalog["architectures"][arch]["material"], "context:profile"
            evidence["material"] = basis
            p["style_id"] = f"building/{arch}/{kind}/{material}"
            p["_city_regional"]["type"] = kind
            p["_city_regional"]["roof_shape"] = tags.get("roof:shape") or aux.get("roof_shape") or catalog["architectures"][arch]["roof"]
            if aux: p["_city_regional"]["auxiliary_id"] = aux["id"]
        else:
            style, basis = ground(tags)
            if "ground" in author: style, basis = author["ground"], "author"
            if geometry.geom_type in ("LineString", "MultiLineString") and p.get("_city_road_tags"):
                highway = tags.get("highway", "street")
                road_type = highway if highway in catalog["road_types"] else "street"
                if highway == "service": road_type = tags.get("service") if tags.get("service") in ("alley", "driveway", "parking_aisle") else "driveway"
                if highway in ("track", "path"): road_type = "unpaved"
                if p.get("road_kind") in ("bridge", "tunnel"): road_type = p["road_kind"]
                if not style: style, basis = ("compacted_earth" if road_type == "unpaved" else "asphalt"), "context:road"
                p["style_id"] = f"road/{road_type}/{style}"
                p["sidewalk_style_id"] = "ground/pavers"
                p["_city_ground_style"] = "ground/" + style
            elif style:
                p["_city_ground_style"] = "ground/" + style
                if p.get("osm_region") or p.get("landuse") in ("forest", "orchard"):
                    p["_city_ground"] = dict(kind="explicit" if basis in ("author", "source:surface") else "natural", surface=catalog["ground"][style]["surface"])
            if p.get("landuse") in ("forest", "orchard"):
                vegetation = "orchard" if p["landuse"] == "orchard" else "conifer" if selected["climate"] in ("cold", "polar") else "deciduous"
                p["style_id"] = "vegetation/" + vegetation
            if basis: evidence["ground"] = basis
        if p.get("_city_barrier"):
            kind = tags.get("barrier", p["_city_barrier"]["kind"])
            kind = {"guard_rail":"rail"}.get(kind, kind)
            if kind not in catalog["barrier_types"]: kind = "fence"
            material = tags.get("material", "metal" if kind in ("fence", "rail") else "stone")
            material = MATERIALS.get(material, material)
            if material not in catalog["materials"]: material = "concrete"
            p["_city_barrier"]["style_id"] = f"barrier/{kind}/{material}"
        for dimension, basis in evidence.items(): counts[dimension + ":" + basis] += 1
        if p.get("style_id") or p.get("_city_ground_style"):
            report["objects"].append(dict(source_id=sid, style_id=p.get("style_id", p.get("_city_ground_style")), region=region_id, evidence=deepcopy(evidence)))
    report["counts"] = dict(sorted(counts.items()))
    return result, report


def finish_building(p, site_kind, near):
    """Conservative height fallback. Randomness never chooses type or storeys."""
    info = p["_city_regional"]
    if "height_m" not in p and "_city_levels" not in p:
        heights = sorted(height for height, usage in near)
        if len(heights) >= 3:
            middle = len(heights) // 2
            p["height_m"] = heights[middle] if len(heights) % 2 else sum(heights[middle-1:middle+1]) / 2
            info["evidence"]["height"] = "context:neighbour_median"
        else:
            kind = info["type"]
            floors = 4 if kind in ("apartment", "residential_tower", "office", "hotel", "hospital") else 1 if kind in ("barn", "utility", "warehouse", "research") else 2
            p["height_m"] = 3 * floors
            info["evidence"]["height"] = "context:type_profile"
        p["_city_levels_height"] = True
        p["_city_neighbour_height"] = True
    material = p["style_id"].split("/")[-1]
    p["material"] = material if material in ("brick", "wood") else "concrete"
    kind = info["type"]
    p["usage"] = "industrial" if kind in ("factory", "warehouse", "barn", "utility") else "public" if kind in ("school", "university", "hospital", "civic", "religious", "station", "research") else "commercial" if kind in ("shop", "mixed_use", "office", "hotel", "shopping") else "residential"
    p["roof"] = "gable" if info["roof_shape"] in ("gabled", "gable") else "flat"
    p["_city_usage_inferred"] = info["evidence"]["type"].startswith("context:")
