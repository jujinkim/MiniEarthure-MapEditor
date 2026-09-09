"""Bounded offline OSM snapshot adapter; no private modules or source writes."""
from importlib.metadata import version, PackageNotFoundError
import re

from import_layer import MAX_INPUT, MAX_POINTS

LICENSE = "ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
MAX_ENTITIES = 250_000
MAX_REFS = 200_000
MAX_FEATURES = 20_000


def dependency():
    try:
        if version("osmium") != "4.3.1":
            raise ValueError("OSM requires osmium 4.3.1; install requirements-import.txt in the selected Python")
        import osmium
        return osmium
    except (ImportError, PackageNotFoundError) as exc:
        raise ValueError("OSM requires osmium 4.3.1; install requirements-import.txt in the selected Python") from exc


def category(tags):
    kinds = []
    if tags.get("highway"):
        kinds.append("road")
    if tags.get("building", "no") != "no" or "building:part" in tags:
        kinds.append("building")
    if tags.get("landuse") in ("forest", "orchard") or tags.get("natural") == "wood":
        kinds.append("zone")
    if len(kinds) > 1:
        raise ValueError("ambiguous OSM feature categories; prepare an explicit extract")
    return kinds[0] if kinds else None


def metres(tags, name):
    raw = tags[name]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?: m)?", raw):
        raise ValueError(f"OSM {name}: only a positive decimal metre value is supported")
    value = float(raw.removesuffix(" m"))
    if not 0 < value <= 1000:
        raise ValueError(f"OSM {name}: expected 0 < metres <= 1000")
    return value


def parse(raw, input_format):
    """Capture scalars only: osmium entities expire at the next iteration.

    Bounds include ignored entities/references, so filtering cannot evade admission.
    No implicit libosmium location/area cache or unbounded sparse ID array is used.
    """
    if not raw or len(raw) > MAX_INPUT or input_format not in ("pbf", "osm"):
        raise ValueError("expected a nonempty OSM PBF/XML snapshot up to 32 MiB")
    if input_format == "osm":
        xml = raw.decode("utf-8-sig")
        if "\x00" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper() or "<osmChange" in xml:
            raise ValueError("OSM XML must be UTF-8 without entities, DTDs or change records")
    osmium = dependency()
    nodes, ways, seen, area_members = {}, [], set(), set()
    counts = dict(nodes=0, ways=0, relations=0, ignored_ways=0, ignored_relations=0, tagged_nodes=0)
    refs = 0
    try:
        processor = osmium.FileProcessor(osmium.io.FileBuffer(raw, input_format))
        if processor.header.has_multiple_object_versions:
            raise ValueError("OSM history input is unsupported; use a current snapshot")
        for entity in processor:
            kind = entity.type_str()
            identity = (kind, entity.id)
            if len(seen) >= MAX_ENTITIES or identity in seen or entity.id <= 0 or not entity.visible:
                raise ValueError("OSM entity budget, duplicate/history ID or deleted object")
            seen.add(identity)
            if len(entity.tags) > 128:
                raise ValueError("OSM tag budget exceeded")
            tags = {}
            for tag in entity.tags:
                if tag.k in tags or len(tag.k) > 512 or len(tag.v) > 512:
                    raise ValueError("OSM duplicate/oversized tag")
                tags[tag.k] = tag.v
            if kind == "n":
                counts["nodes"] += 1
                counts["tagged_nodes"] += bool(tags)
                if len(nodes) >= MAX_POINTS or not entity.location.valid():
                    raise ValueError("OSM node budget or invalid location")
                nodes[entity.id] = [entity.lon, entity.lat]
            elif kind == "w":
                counts["ways"] += 1
                refs += len(entity.nodes)
                if refs > MAX_REFS:
                    raise ValueError("OSM reference budget exceeded")
                selected = category(tags)
                if selected:
                    if len(ways) >= MAX_FEATURES:
                        raise ValueError("OSM selected feature budget exceeded")
                    ways.append((entity.id, selected, [n.ref for n in entity.nodes], tags))
                else:
                    counts["ignored_ways"] += 1
            elif kind == "r":
                counts["relations"] += 1
                refs += len(entity.members)
                if refs > MAX_REFS:
                    raise ValueError("OSM reference budget exceeded")
                if category(tags):
                    raise ValueError("OSM feature relations/multipolygons need explicit assembly; no silent flattening")
                if tags.get("type") in ("multipolygon", "boundary"):
                    area_members.update(m.ref for m in entity.members if m.type == "w")
                counts["ignored_relations"] += 1
            else:
                raise ValueError("unsupported OSM entity")
    except RuntimeError as exc:
        raise ValueError("invalid OSM snapshot: " + str(exc)[:300]) from exc
    features = []
    for identity, kind, references, tags in sorted(ways):
        if identity in area_members:
            raise ValueError("selected OSM way belongs to an area relation; no silent holes/flattening")
        if any(ref not in nodes for ref in references):
            raise ValueError(f"OSM way {identity}: missing referenced node; use a complete extract")
        if any(tags.get(key, "no") not in ("no", "0") for key in ("bridge", "tunnel")) or tags.get("layer", "0") != "0":
            raise ValueError(f"OSM way {identity}: bridge/tunnel/nonzero layer requires explicit vertical geometry")
        if any(key in tags for key in ("building:part", "min_height", "building:min_level", "incline", "ele", "level")):
            raise ValueError(f"OSM way {identity}: unsupported vertical semantics")
        points = [nodes[ref] for ref in references]
        properties = {}
        if kind == "road":
            if tags["highway"] not in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "track", "path", "footway", "cycleway", "pedestrian") or tags.get("area", "no") != "no":
                raise ValueError(f"OSM way {identity}: unsupported highway/area profile")
            if len(references) < 2 or references[0] == references[-1]:
                raise ValueError(f"OSM way {identity}: closed/short road requires explicit segmentation")
            if "width" in tags: properties["width_m"] = metres(tags, "width")
            if "surface" in tags: properties["surface"] = tags["surface"]
            geometry = dict(type="LineString", coordinates=points)
        else:
            if len(references) < 4 or references[0] != references[-1]:
                raise ValueError(f"OSM way {identity}: polygon must be a closed way")
            if kind == "building":
                if "height" in tags: properties["height_m"] = metres(tags, "height")
                if tags["building"] != "yes": properties["usage"] = tags["building"]
            else:
                properties["landuse"] = "orchard" if tags.get("landuse") == "orchard" else "forest"
            geometry = dict(type="Polygon", coordinates=[points])
        features.append(dict(type="Feature", properties=properties, geometry=geometry))
    if not features:
        raise ValueError("OSM extract contains no supported road/building/forest/orchard ways")
    return dict(type="FeatureCollection", features=features), counts


def finish(layer, counts):
    layer.adapter = "osm-extract-v1"
    previous = layer.warnings
    layer.warnings = []
    layer.warning("OSM snapshot via osmium 4.3.1; © OpenStreetMap contributors; ODbL-1.0; https://www.openstreetmap.org/copyright")
    layer.warning("OSM input counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    layer.warning("Only selected way geometry is imported; POIs, other ways/relations and other tags are omitted. No routing/access/oneway semantics.")
    layer.warning("Ground elevation/base, missing width/height/surface, vegetation and materials are estimates; building levels/roof tags are not interpreted.")
    # Put source-level omissions before per-road warning samples, even at the cap.
    layer.warnings = (layer.warnings + previous)[:50]
    layer.encode()
    return layer
