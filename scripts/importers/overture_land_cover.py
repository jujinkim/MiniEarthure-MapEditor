"""Bounded, reviewed forest-only Overture base/land_cover adapter (MIT)."""
import json
import sys
import overture_area as area
from import_layer import MAX_INPUT, number, text, strict_json
from polygon_geometry import Budget, group_rings

LICENSE = "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; ESA WorldCover (CC-BY-4.0); © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium; https://docs.overturemaps.org/attribution/#base"
SUBTYPES = ("barren", "crop", "forest", "grass", "mangrove", "moss", "shrub", "snow", "urban", "wetland")
MAX_FEATURES = 256
MAX_POINTS = 8192


def plan(release, bbox):
    query = area.plan(release, bbox)
    query.update(theme="base", type="land_cover", profile="forest-high-detail-v1", license=LICENSE)
    return query


def checked_plan(value):
    return plan(value.get("release"), value.get("bbox"))


def remote_features(query):
    yield from area.read_features(query, ["land_cover"])


def acquire(query, partial, destination, progress, features=remote_features):
    return area.acquire(query, partial, destination, progress, features,
                        checker=checked_plan, feature_limit=MAX_FEATURES)


def parse(raw):
    if len(raw) > MAX_INPUT: raise ValueError("Land cover snapshot exceeds 32 MiB")
    value = strict_json(raw)
    if not isinstance(value, dict) or value.get("snapshot_version") != 1:
        raise ValueError("Expected land cover snapshot version 1")
    query = checked_plan(value)
    if set(value) != set(query) | {"snapshot_version", "features"} or any(value[k] != v for k,v in query.items()):
        raise ValueError("Land cover review contract/license changed")
    features = value["features"]
    if not isinstance(features, list) or not 1 <= len(features) <= MAX_FEATURES:
        raise ValueError("Land cover supports 1..256 source features")
    output, records, seen = [], [], set()
    budget, points = Budget(), 0
    w,s,e,n = query["bbox"]
    for f in features:
        if not isinstance(f, dict) or f.get("type") != "Feature": raise ValueError("Expected land cover Feature")
        identity = text(f.get("id"), "Overture ID", 128)
        if identity in seen: raise ValueError("Duplicate land cover ID")
        seen.add(identity)
        p,g = f.get("properties"), f.get("geometry")
        if not isinstance(p, dict) or p.get("id") != identity or p.get("theme") != "base" or p.get("type") != "land_cover":
            raise ValueError("Invalid land cover identity/theme/type")
        if p.get("subtype") not in SUBTYPES: raise ValueError("Unknown land cover subtype; no inferred trees")
        cart = p.get("cartography")
        if not isinstance(cart, dict): raise ValueError("Explicit land cover cartography required")
        low, high = cart.get("min_zoom"), cart.get("max_zoom")
        if type(low) not in (int,float) or type(high) not in (int,float): raise ValueError("Invalid land cover zoom")
        number(low, "min zoom", 0, 15); number(high, "max zoom", 0, 15)
        if low != int(low) or high != int(high) or low > high: raise ValueError("Invalid land cover zoom range")
        # Published high-detail representation; never combine different resolutions.
        if (low,high) != (8,15) and high >= 8: raise ValueError("Unsupported overlapping land cover resolution")
        sources = p.get("sources")
        if not isinstance(sources,list) or not 1 <= len(sources) <= 128 or len(json.dumps(sources)) > 16384:
            raise ValueError("Missing/oversized land cover attribution")
        for source in sources:
            if not isinstance(source,dict): raise ValueError("Invalid source")
            text(source.get("dataset"), "source dataset")
            if source.get("license") is not None: text(source["license"], "source license")
        if not isinstance(g,dict) or g.get("type") not in ("Polygon","MultiPolygon"):
            raise ValueError("Land cover requires Polygon/MultiPolygon")
        polygons = [g.get("coordinates")] if g["type"] == "Polygon" else g.get("coordinates")
        if not isinstance(polygons,list) or not 1 <= len(polygons) <= 256: raise ValueError("Invalid land cover parts")
        positions = []
        for rings in polygons:
            if not isinstance(rings,list) or not 1 <= len(rings) <= 17: raise ValueError("At most 16 exclusion holes per part")
            for ring in rings:
                if not isinstance(ring,list) or len(ring) < 4 or ring[0] != ring[-1]: raise ValueError("Invalid closed land cover ring")
                points += len(ring)
                if points > MAX_POINTS: raise ValueError("Land cover point budget exceeded")
                for pos in ring:
                    if not isinstance(pos,list) or len(pos) != 2: raise ValueError("Expected 2D WGS84 position")
                    number(pos[0], "longitude", -180,180); number(pos[1], "latitude", -80,84)
                positions.extend(ring)
        if group_rings([r[0] for r in polygons], [h for r in polygons for h in r[1:]], budget) != polygons:
            raise ValueError("Land cover holes must belong to declared outer")
        if min(p[0] for p in positions) >= e or max(p[0] for p in positions) <= w or min(p[1] for p in positions) >= n or max(p[1] for p in positions) <= s:
            raise ValueError("Land cover feature outside query")
        selected = p["subtype"] == "forest" and (low,high) == (8,15)
        disposition = "forest" if selected else "other-subtype" if p["subtype"] != "forest" else "lower-detail"
        records.append(dict(id=identity, version=p.get("version"), sources=sources, subtype=p["subtype"],
                            min_zoom=low, max_zoom=high, disposition=disposition, part_count=len(polygons), hole_counts=[len(r)-1 for r in polygons], zone_ids=[]))
        if selected:
            geometry = dict(type="Polygon",coordinates=polygons[0]) if len(polygons) == 1 else dict(type="MultiPolygon",coordinates=polygons)
            output.append(dict(type="Feature",id=identity,geometry=geometry,properties=dict(landuse="forest")))
    if not output: raise ValueError("No high-detail forest in source; other land classes are not trees")
    output.sort(key=lambda f:f["id"])
    records.sort(key=lambda f:f["id"])
    return dict(type="FeatureCollection",features=output), dict(query, source_feature_count=len(features), source_point_count=points, feature_sources=records)


def finish(layer, metadata):
    index = 0
    for record in metadata["feature_sources"]:
        if record["disposition"] != "forest": continue
        prefix = f"import-{layer.layer_id}-{index}"
        count = record["part_count"]
        record["zone_ids"] = [prefix] if count == 1 else [f"{prefix}-part-{part}" for part in range(count)]
        index += 1
    budget = Budget()
    for patch in layer.patches:
        zone = patch["after"]
        rings = [r + [r[0]] for r in [zone["polygon"], *zone["exclusions"]]]
        group_rings([rings[0]], rings[1:], budget)
    layer.adapter = "overture-land-cover-v1"
    layer.coordinates["overture_land_cover"] = metadata
    layer.warning("Only forest at min_zoom=8/max_zoom=15 becomes vegetation. Other subtypes/lower detail are explicitly excluded in provenance; unknown profiles reject.")
    layer.warning("Whole polygons, holes and islands retained without clipping. 10m WorldCover raster-derived classification is not tree locations or centimetre accuracy; survey alignment before adoption.")
    layer.warning("Forest spacing 8m / density 750 per mille, tree species/size/placement and terrain attachment are generated estimates, not source observations. No crop-to-orchard or wetland/mangrove-to-forest inference.")
    layer.encode()
    return layer


if __name__ == "__main__":
    try: area.main(acquire)
    except Exception as exc:
        print(json.dumps({"error":str(exc)[:1024]}),file=sys.stderr)
        sys.exit(1)
