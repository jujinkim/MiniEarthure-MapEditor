#!/usr/bin/env python3
"""Offline local-source regional composition; prepares one ordinary Editor command."""
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np
import pyproj
import rasterio
from rasterio.features import shapes
from rasterio.io import MemoryFile
import shapely
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.affinity import scale as geometry_scale
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

try:
    import regional
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).parent / "importers"))
    import regional

OWNER = "mapeditor-regional-v1"
WORLDCOVER = {10:"forest_floor", 20:"scrub", 30:"grassland", 40:"cropland", 50:"pavers", 60:"rock", 70:"snow", 80:None, 90:"wetland", 95:"wetland", 100:"scrub"}
FIELDS = ("buildings", "surface_areas", "attributions")


def polygons(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "Polygon": return [geometry]
    return [p for g in getattr(geometry, "geoms", []) for p in polygons(g)]


def parts(geometry, cell=6400):
    """Bound polygon complexity and remove holes by exact integer-lattice cuts."""
    geometry = shapely.set_precision(geometry, 1)
    def divide(polygon, depth=0):
        if not polygon.interiors and len(polygon.exterior.coords) <= 513:
            return [polygon] if polygon.area >= 4 else []
        if depth > 24: raise ValueError("regional polygon partition exceeded")
        bounds = Polygon(polygon.interiors[0]).bounds if polygon.interiors else polygon.bounds
        axis = 0 if bounds[2]-bounds[0] >= bounds[3]-bounds[1] else 1
        middle = round((bounds[axis]+bounds[axis+2])/2)
        x,y,X,Y = polygon.bounds
        halves = (box(x-1,y-1,middle,Y+1),box(middle,y-1,X+1,Y+1)) if axis == 0 else (box(x-1,y-1,X+1,middle),box(x-1,middle,X+1,Y+1))
        out = []
        for half in halves:
            for p in polygons(shapely.intersection(polygon,half,grid_size=1)):
                out.extend(divide(p,depth+1))
        return out
    result = []
    for polygon in polygons(geometry):
        x,y,X,Y = polygon.bounds
        for i in range(math.floor(x/cell), math.floor(X/cell)+1):
            for j in range(math.floor(y/cell), math.floor(Y/cell)+1):
                for p in polygons(shapely.intersection(polygon,box(i*cell,j*cell,(i+1)*cell,(j+1)*cell),grid_size=1)):
                    result.extend(divide(p))
    return sorted(result, key=lambda p: (p.bounds, p.wkb))


def ring(polygon): return [[round(x),round(y)] for x,y in polygon.exterior.coords[:-1]]


def cover_clearance(geometry):
    # Buffering narrow gaps may return individually valid components whose
    # shells overlap. The exclusion is their union; keep its holes and combine
    # the components before subsequent overlays consume it.
    return unary_union(polygons(geometry.buffer(2,join_style="mitre")))


def building_parts(geometry):
    """Keep exact lattice outlines when a courtyard touches another ring.

    GEOS permits a point contact; a native courtyard requires separated rings.
    Constrained triangles share one building owner and use existing vertices,
    preserving both the outline and the void without a clearance cut.
    """
    result=[]
    for polygon in polygons(shapely.set_precision(geometry,1)):
        rings=[polygon.exterior,*polygon.interiors]
        touching=any(a.intersects(b) for i,a in enumerate(rings) for b in rings[:i])
        if not touching:
            result.append(polygon)
            continue
        triangles=polygons(shapely.constrained_delaunay_triangles(polygon))
        if not triangles or unary_union(triangles).symmetric_difference(polygon).area != 0:
            raise ValueError("regional courtyard partition changed the source outline")
        result.extend(triangles)
    return sorted(result,key=lambda p:(p.bounds,p.wkb))


class Frame:
    def __init__(self, notice):
        c = notice["coordinates"]
        if c.get("mode") != "wgs84-utm" or c.get("axis_order") != "longitude-latitude": raise ValueError("regional sources require an adopted explicit WGS84 frame")
        self.origin, self.local = c["origin"], c["local_origin_m"]
        self.scale = int(c["osm_city"]["scale_denominator"])
        if not 1 <= self.scale <= 8: raise ValueError("invalid regional scale")
        self.bbox = c["osm_crop"]["bbox"]
        pyproj.network.set_network_enabled(False)
        self.project = pyproj.Transformer.from_crs("EPSG:4326", c["target_crs"], always_xy=True, allow_ballpark=False, only_best=True)
        self.xy = self.project.transform(*self.origin, errcheck=True)
    def to_map(self, x, y, z=None):
        a,b = self.project.transform(x,y,errcheck=True)
        return (np.asarray(a)-self.xy[0]+self.local[0])*100/self.scale, (np.asarray(b)-self.xy[1]+self.local[1])*100/self.scale
    def geometry(self, value): return shapely.set_precision(transform(self.to_map, value),1)


def osm_notice(document):
    found = []
    for attribution in document.get("attributions", []):
        try: notice = json.loads(attribution["notice"])
        except (ValueError, KeyError, TypeError): continue
        if notice.get("adapter") == "osm-extract-v1" and notice.get("coordinates", {}).get("osm_city"): found.append(notice)
    if len(found) != 1: raise ValueError("regional composition needs exactly one adopted city OSM source")
    return found[0]


def solids(document):
    result = []
    for b in document.get("buildings", []):
        for p in [b] + b.get("parts", []):
            result.append((b, Polygon(p["footprint"], p.get("holes", []))))
    return result


def cover(request, frame, boundary):
    """WorldCover's native cells supply broad cover only, never sidewalk evidence."""
    data = regional.snapshot(request, "worldcover")
    result = []
    with MemoryFile(data) as memory, memory.open() as src:
        if src.crs != rasterio.crs.CRS.from_epsg(4326) or src.count != 1 or src.width * src.height > 4000000: raise ValueError("WorldCover must be a bounded single-band WGS84 crop")
        if src.transform.a <= 0 or src.transform.e >= 0 or src.transform.b or src.transform.d or not .00007 <= src.transform.a <= .0001 or not .00007 <= -src.transform.e <= .0001: raise ValueError("WorldCover must retain its native 10 m grid")
        west,south,east,north = frame.bbox
        if src.bounds.left > west or src.bounds.bottom > south or src.bounds.right < east or src.bounds.top < north: raise ValueError("WorldCover raster does not cover the requested region")
        values = src.read(1)
        if set(np.unique(values)) - set(WORLDCOVER): raise ValueError("WorldCover has missing or unsupported classes")
        for geometry, value in shapes(values, transform=src.transform, connectivity=4):
            local = frame.geometry(shape(geometry)).intersection(boundary)
            if not local.is_empty: result.append((int(value), local))
    return result


class AddedIndex:
    """Incremental cell index keeps supplemental overlap checks local."""
    def __init__(self): self.shapes=[]; self.cells={}
    def keys(self, geometry):
        x,y,X,Y=geometry.bounds
        for i in range(math.floor(x/6400),math.floor(X/6400)+1):
            for j in range(math.floor(y/6400),math.floor(Y/6400)+1): yield i,j
    def add(self, geometry):
        index=len(self.shapes);self.shapes.append(geometry)
        for key in self.keys(geometry):self.cells.setdefault(key,[]).append(index)
    def query(self, geometry):
        indices={i for key in self.keys(geometry) for i in self.cells.get(key,[])}
        return [self.shapes[i] for i in sorted(indices) if self.shapes[i].intersects(geometry)]


def part_solids(props, local, frame, boundary):
    """Keep visible source part heights and parent remainder without double solids."""
    if not props.get("parts"): return [(local,props)]
    result=[];claimed=Polygon()
    ordered=sorted(props["parts"],key=lambda p:(-float(p.get("height") or props.get("height") or 6),str(p["id"])))
    for part in ordered:
        geometry=frame.geometry(shape(part["geometry"])).intersection(local).intersection(boundary)
        remainder=geometry.difference(claimed.buffer(2,join_style="mitre"))
        if not remainder.is_empty:result.append((remainder,part))
        claimed=claimed.union(geometry)
    remainder=local.difference(claimed.buffer(2,join_style="mitre"))
    if not remainder.is_empty:result.append((remainder,props))
    return result


def building_road_space(roads):
    """The same rounded carriageway/junction and bridge envelope as OSM review.

    Native document centimetres become working metres at scale one, so this
    helper's heights and 50 cm under-deck clearance stay in map dimensions.
    """
    from regional_road_conflicts import corridors
    features=[]
    for road in roads:
        properties=dict(road_kind=road.get("kind","ground"),
            clearance_m=(road.get("clearance_cm") or 450)/100,
            _city_widths_m=[w/100 for w in road["widths_cm"]],
            elevations_m=[p[1]/100 for p in road["points"]],
            osm_node_refs=[road["from"],road["to"]])
        features.append((dict(id=road["id"],properties=properties),LineString([(p[0]/100,p[2]/100) for p in road["points"]])))
    return corridors(features,1,lambda f:[f["id"]])


def compose(document, request, catalog):
    original = document
    doc = deepcopy(document)
    notice = osm_notice(doc)
    frame = Frame(notice)
    regional.validate(request, catalog, notice["source"]["sha256"], frame.bbox)
    adopted = notice["coordinates"].get("regional", {}).get("request")
    if adopted != regional.input_receipt(request): raise ValueError("regional source/profile request differs from the adopted OSM classification")
    for attribution in doc.get("attributions", []):
        try: existing = json.loads(attribution.get("notice", ""))
        except (ValueError, TypeError): continue
        if isinstance(existing, dict) and existing.get("adapter") == OWNER:
            raise ValueError("regional sources already applied; regenerate from the pinned recipe to replace them")
    boundary = unary_union([Polygon(p) for p in doc.get("play_area", [])]) if doc.get("play_area") else box(*doc["bounds"]["min"], *doc["bounds"]["max"])
    counts, diagnostics = Counter(), []
    rows = solids(doc)
    occupied = [g for b,g in rows]
    tree = STRtree(occupied)
    ground_roads = [r for r in doc.get("roads", []) if r.get("kind", "ground") == "ground"]
    roads = [LineString([(p[0],p[2]) for p in r["points"]]).buffer(max(r["widths_cm"])/2 + (r.get("sidewalk_cm") or 0),quad_segs=2) for r in ground_roads]
    road_tree = STRtree(roads)
    road_space = building_road_space(doc.get("roads", []))
    osm_ids = set(notice["coordinates"]["osm_city"]["source_ids"])
    auxiliary = regional.read_buildings(request["buildings"]) if "buildings" in request else []
    added = AddedIndex()
    added_shapes = added.shapes
    for props, geographic in auxiliary:
        sid = props["id"]
        if props.get("is_underground"):
            counts["building_underground"] += 1
            diagnostics.append(dict(source_id=sid, reason="source underground building has no above-ground facade"))
            continue
        local = frame.geometry(geographic).intersection(boundary)
        if local.is_empty: continue
        matches = [int(i) for i in tree.query(local)]
        if regional.source_ids(props) & osm_ids:
            counts["building_duplicate_source_id"] += 1; continue
        duplicate = any(local.intersection(occupied[i]).area / max(local.union(occupied[i]).area,1) >= .5 for i in matches)
        if duplicate:
            counts["building_duplicate_overlap"] += 1; continue
        conflicts = [occupied[i] for i in matches if occupied[i].intersects(local)] + added.query(local)
        if conflicts:
            # OSM owns conflicts. Never silently shave a supplemental footprint.
            counts["building_conflict"] += 1
            diagnostics.append(dict(source_id=sid, reason="overlap with retained building; OSM geometry wins")); continue
        selected, region_id = regional.selected_profile(request, geographic.representative_point(), catalog)
        tags = {"building":props.get("class") or "yes"}
        height = props.get("height") or ((props.get("num_floors") or 0)*3)
        kind, basis = regional.building_type(tags, height, selected["settlement"], regional.source_area_m2(geographic))
        if not height:
            nearby = [float(rows[i][0]["height_cm"])*frame.scale/100 for i in tree.query(local.centroid, predicate="dwithin", distance=6000/frame.scale)]
            height = float(np.median(nearby)) if len(nearby) >= 3 else regional.profile_height(kind, selected["settlement"])
            height_basis = "context:neighbour_median" if len(nearby) >= 3 else "context:profile"
        else: height_basis = "auxiliary:height" if props.get("height") else "auxiliary:floors"
        from regional_road_conflicts import trim
        local_metres=geometry_scale(local,xfact=.01,yfact=.01,origin=(0,0))
        top=max([height]+[part.get("height") or height for part in props.get("parts",[])])
        base=min([props.get("min_height") or 0]+[part.get("min_height") or 0 for part in props.get("parts",[])])
        _,road_hits,removed=trim(local_metres,road_space,top/frame.scale,base/frame.scale)
        sidewalk_hits=[ground_roads[int(i)]["id"] for i in road_tree.query(local.buffer(2)) if roads[int(i)].distance(local)<2]
        road_hits=sorted(set(road_hits+sidewalk_hits))
        if road_hits:
            counts["building_road_conflict"] += 1
            diagnostics.append(dict(source_id=sid, reason="auxiliary footprint conflicts with retained OSM road; detailed road wins", road_ids=road_hits))
            continue
        arch = selected["architecture"]
        material = props.get("facade_material")
        material_basis = "auxiliary:material" if material in catalog["materials"] else "context:profile"
        if material not in catalog["materials"]: material = regional.use_style(catalog, arch, kind)["material"]
        shapes_to_add = part_solids(props,local,frame,boundary)
        for part_index, (geometry, part) in enumerate(shapes_to_add):
            part_roof, _, part_evidence = regional.roof_style({},dict(props,**part),{},arch,kind,catalog)
            part_style = f"building/{arch}/{kind}/{material}"+part_roof
            record_ids = []
            record = None
            for polygon_index, polygon in enumerate(building_parts(geometry)):
                if polygon.area <= 0: raise ValueError("Overture footprint collapsed at map scale: " + sid)
                if len(polygon.interiors) > 16 or sum(len(r.coords)-1 for r in [polygon.exterior, *polygon.interiors]) > 512: raise ValueError("Overture footprint exceeds native polygon budget: " + sid)
                h = part.get("height") or height
                base = part.get("min_height") or 0
                if base >= h: raise ValueError("Overture part has nonpositive solid height: " + sid)
                solid = dict(footprint=ring(polygon), base_cm=round(base*100/frame.scale), height_cm=max(1,round((h-base)*100/frame.scale)))
                if polygon.interiors: solid["holes"] = [[[round(x),round(y)] for x,y in r.coords[:-1]] for r in polygon.interiors]
                if record is None:
                    record = dict(id=f"regional-ov-{sid}-{part_index}-0", **solid, roof="flat",
                        usage="industrial" if kind in ("factory", "warehouse", "barn", "utility") else "public" if kind in ("school", "university", "hospital", "civic", "religious", "station", "research") else "commercial" if kind in ("shop", "mixed_use", "office", "hotel", "shopping") else "residential",
                        material=material if material in ("brick", "wood") else "concrete", style_id=part_style)
                    doc.setdefault("buildings", []).append(record)
                    record_ids.append(record["id"])
                    counts["building_added"] += 1
                else:
                    # Point-touching components of one source part are one
                    # native owner. Their outlines and style remain unchanged.
                    record.setdefault("parts",[]).append(solid)
                added.add(polygon)
            source_bases=[s.get("base_cm",record["base_cm"]) for s in [record]+record.get("parts",[])] if record else []
            diagnostics.append(dict(source_id=sid, part_id=part.get("id",sid), style_id=part_style, region=region_id, record_ids=record_ids, source_bases_cm=source_bases, evidence=dict(type=basis.replace("source:", "auxiliary:"), height="auxiliary:height" if part.get("height") else height_basis, material=material_basis, architecture="context:profile", **part_evidence)))
    existing = [Polygon(p["polygon"]) for p in doc.get("surface_areas", [])]
    water = [Polygon(p["polygon"], p.get("islands", [])) for p in doc.get("water_bodies", [])]
    vegetation = [Polygon(z["polygon"], z.get("exclusions", [])) for z in doc.get("zones", [])]
    blocked = unary_union(existing + water + roads + occupied + added_shapes + vegetation)
    # Integer cuts can move an oblique edge by a fraction of a centimetre.
    # Keep the same two-map-centimetre clearance as city paint so raster cover
    # cannot overlap a detailed source area after quantization and partitioning.
    cover_blocked = cover_clearance(blocked)
    coverage = cover(request["worldcover"], frame, boundary) if "worldcover" in request else []
    by_style = {}
    for code, polygon in coverage:
        style = WORLDCOVER[code]
        if style is None: continue  # WorldCover water is not an inferred traversable surface.
        selected = regional.profile(request.get("profile", {}), catalog)
        if code == 60 and selected["terrain"] != "canyon" and selected["climate"] == "arid": style = "sand"
        by_style.setdefault(style, []).append(polygon)
    generated = []
    for style, geometries in sorted(by_style.items()):
        residual = unary_union(geometries).difference(cover_blocked)
        emitted = parts(residual)
        for polygon in emitted:
            record = dict(id="regional-cover-"+hashlib.sha256(style.encode()+polygon.wkb).hexdigest()[:24], polygon=ring(polygon), surface=catalog["ground"][style]["surface"], style_id="ground/"+style)
            generated.append(record)
        counts["cover:"+style] = sum(p.area for p in emitted) / 10000
        if emitted: cover_blocked = cover_blocked.union(cover_clearance(unary_union(emitted)))
    # Sidewalk candidates require a retained building/fence within ten source
    # metres of a road, and built-up cover. Coarse cover alone creates no ribbon.
    built = unary_union(by_style.get("pavers", []))
    natural = unary_union([p for style, gs in by_style.items() if style != "pavers" for p in gs] + water + vegetation + [Polygon(p["polygon"]) for p in doc.get("surface_areas", []) if p.get("surface") in ("grass", "dirt", "gravel")])
    anchors = occupied + added_shapes + [LineString(b["line"]) for b in doc.get("barriers", [])]
    candidate = unary_union([road.buffer(1000/frame.scale,quad_segs=2) for road in roads]).intersection(unary_union([g.buffer(1000/frame.scale,quad_segs=2) for g in anchors])).intersection(built).difference(blocked.union(natural)) if roads and anchors else Polygon()
    # Broad built-up cover already paints these points; record the qualified
    # sidewalk area distinctly in the production report for author review.
    counts["sidewalk_candidate_m2"] = candidate.area/10000
    doc.setdefault("surface_areas", []).extend(generated)
    selected = regional.profile(request.get("profile", {}), catalog)
    environment = deepcopy(doc.get("environment") or dict(version=1,concept="metropolis",latitude_mdeg=round(frame.origin[1]*1000),longitude_mdeg=round(frame.origin[0]*1000),utc_offset_minutes=0,sunrise_minutes=360,sunset_minutes=1080,regions=[],lights=[],start_minutes=720))
    environment.update(selected)
    environment["concept"] = "polar" if selected["climate"] in ("cold", "polar") else "desert" if selected["climate"] == "arid" else "countryside" if selected["settlement"] in ("rural", "village", "sparse", "wilderness") else "metropolis"
    environment["regions"] = []
    for region in request.get("regions", []):
        local = frame.geometry(Polygon(region["polygon"])).intersection(boundary)
        for index, polygon in enumerate(polygons(local)):
            if polygon.interiors or len(polygon.exterior.coords) > 65: raise ValueError("regional environment zone exceeds 64 vertices after clipping")
            environment["regions"].append(dict(id=region["id"]+f"-{index}",concept=environment["concept"],polygon=ring(polygon),**regional.profile(region["profile"],catalog,selected)))
    if len(environment["regions"]) > 64: raise ValueError("too many regional environment zones after clipping")
    doc["environment"] = environment
    base_style = "snow" if selected["climate"] == "polar" else "rock" if selected["terrain"] == "canyon" else "sand" if selected["climate"] == "arid" else "grassland"
    doc["ground_style_id"] = "ground/"+base_style
    distribution = {field: dict(sorted(Counter(record.get("style_id", "unspecified") for record in doc.get(field, [])).items())) for field in ("buildings", "roads", "surface_areas", "zones", "barriers")}
    evidence = Counter()
    for group in regional.receipt_rows(notice["coordinates"]["osm_city"],"groups"):
        for dimension, basis in group.get("regional", {}).get("evidence", {}).items(): evidence[dimension+":"+basis] += 1
    receipt = dict(adapter=OWNER,version=1,inputs=regional.input_receipt(request),counts=dict(sorted(counts.items())),distribution=distribution,evidence=dict(sorted(evidence.items())),objects=diagnostics)
    names, licenses = [], []
    for key, name in (("worldcover", "ESA WorldCover"), ("buildings", "Overture Buildings")):
        if key in request:
            names.append(name + " " + request[key]["release"])
            licenses.append(request[key]["license"])
    stored_receipt=deepcopy(receipt)
    regional.pack_rows(stored_receipt,"objects")
    attribution = dict(source=" + ".join(names) or "Regional appearance profiles",
                       license="; ".join(licenses) or "MIT; generated appearance classification",
                       notice=regional.canonical(stored_receipt))
    doc.setdefault("attributions", []).append(attribution)
    patches = []
    for field in FIELDS:
        key = lambda r: regional.canonical(r) if field == "attributions" else r["id"]
        a={key(r):r for r in original.get(field,[])}; b={key(r):r for r in doc.get(field,[])}
        for identity in sorted(a.keys()|b.keys()):
            if a.get(identity) != b.get(identity): patches.append(dict(field=field,id=identity,before=a.get(identity),after=b.get(identity)))
    for field in ("environment", "ground_style_id"):
        if original.get(field) != doc.get(field): patches.append(dict(field=field,id="",before=original.get(field),after=doc.get(field)))
    costs = Counter()
    size = int(doc["cell_size_cm"])
    for record in doc.get("buildings", []) + generated:
        p = record.get("footprint", record.get("polygon"))
        x,y = np.mean(p,axis=0)
        costs[(math.floor((x-doc["bounds"]["min"][0])/size),math.floor((y-doc["bounds"]["min"][1])/size))] += 1
    cells = [dict(x=x,y=y) for (x,y), count in sorted(costs.items(),key=lambda item:(-item[1],item[0]))[:16]]
    report = dict(patches=patches,payloads={},diagnostics=dict(errors=[],metrics=dict(cost_cells=cells),limit_warnings=[],regional=receipt))
    return doc, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path); parser.add_argument("destination", type=Path); parser.add_argument("--kit", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.request.read_text())
    parent = os.getppid()
    def watch():
        while os.getppid() == parent: time.sleep(.1)
        os._exit(3)
    threading.Thread(target=watch,daemon=True).start()
    doc, report = compose(raw["document"], raw["generation"]["regional"], regional.catalogue(args.kit/"godot/regional_catalog.json"))
    args.destination.mkdir(parents=True,exist_ok=False)
    (args.destination/"document.json").write_text(regional.canonical(doc))
    (args.destination/"generation.json").write_text(regional.canonical(report))
    print(regional.canonical(report["diagnostics"]["regional"]["counts"]))


if __name__ == "__main__": main()
