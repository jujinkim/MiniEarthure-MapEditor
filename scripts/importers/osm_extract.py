"""Bounded offline OSM snapshot adapter; no private modules or source writes."""
from importlib.metadata import version, PackageNotFoundError
import re
from collections import Counter

from import_layer import MAX_INPUT, MAX_POINTS
from polygon_geometry import Budget, group_rings

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


def vertical(tags):
    if any(tags.get(key, "no") not in ("no", "0") for key in ("bridge", "tunnel")) or tags.get("layer", "0") != "0":
        raise ValueError("OSM bridge/tunnel/nonzero layer requires explicit vertical geometry")
    if any(key in tags for key in ("building:part", "min_height", "building:min_level", "incline", "ele", "level")):
        raise ValueError("OSM unsupported vertical semantics")


def road_vertical(tags, references, node_tags):
    """Explicit EGM96 node heights; layer is ordering, never metres."""
    bridge, tunnel = tags.get("bridge", "no"), tags.get("tunnel", "no")
    if bridge not in ("no", "0", "yes") or tunnel not in ("no", "0", "yes") or bridge == tunnel == "yes":
        raise ValueError("OSM unsupported/ambiguous bridge or tunnel type")
    kind = "bridge" if bridge == "yes" else "tunnel" if tunnel == "yes" else "ground"
    if not re.fullmatch(r"-?[0-9]+", tags.get("layer", "0")) or not -5 <= int(tags.get("layer", "0")) <= 5:
        raise ValueError("OSM layer requires an integer from -5 to 5; it is not elevation")
    if kind == "ground" and int(tags.get("layer", "0")) != 0:
        raise ValueError("OSM nonzero ground layer requires explicit supported structure")
    forbidden = ("building:part", "min_height", "building:min_level", "incline", "ele", "level", "height", "covered", "location")
    if any(k in tags for k in forbidden) or any(k.startswith("ele:") for k in tags):
        raise ValueError("OSM unsupported vertical semantics on road")
    elevations = []
    for ref in references:
        tags_at_node = node_tags.get(ref, {})
        if any(k in tags_at_node for k in ("layer", "level", "incline", "bridge", "tunnel")) or any(k.startswith("ele:") for k in tags_at_node):
            raise ValueError("OSM unsupported road-node vertical semantics")
        if "ele" in tags_at_node:
            raw = tags_at_node["ele"]
            if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?(?: m)?", raw):
                raise ValueError("OSM node ele requires signed decimal metres (EGM96)")
            value = float(raw.removesuffix(" m"))
            if not -10000 <= value <= 10000:
                raise ValueError("OSM node elevation outside native range")
            elevations.append(value)
    if elevations and len(elevations) != len(references) or kind != "ground" and not elevations:
        raise ValueError("OSM explicit vertical geometry requires ele on every road node; no interpolation of missing heights")
    if not elevations:
        if "maxheight:physical" in tags:
            raise ValueError("OSM physical clearance requires an explicit supported tunnel")
        return {}
    result = dict(elevations_m=elevations, road_kind=kind, osm_node_refs=references,
                  osm_way_layer=int(tags.get("layer", "0")))
    if kind == "tunnel":
        if "maxheight:physical" not in tags:
            raise ValueError("OSM tunnel requires maxheight:physical; legal maxheight is not geometry")
        clearance = metres(tags, "maxheight:physical")
        if not 2 <= clearance <= 50:
            raise ValueError("OSM tunnel physical clearance requires 2..50 metres")
        result["clearance_m"] = clearance
    elif "maxheight:physical" in tags:
        raise ValueError("OSM physical clearance only supported on tunnel ways")
    return result


def split_vertical_roads(features):
    """Join only shared source node IDs; split explicit roads at graph junctions."""
    roads = [f for f in features if "osm_node_refs" in f["properties"]]
    uses = Counter(ref for f in roads for ref in f["properties"]["osm_node_refs"])
    ground = set(ref for f in roads if f["properties"]["road_kind"] == "ground" for ref in f["properties"]["osm_node_refs"])
    output = []
    for feature in features:
        p = feature["properties"]
        if "osm_node_refs" not in p:
            output.append(feature)
            continue
        refs = p["osm_node_refs"]
        if len(set(refs)) != len(refs):
            raise ValueError("OSM explicit road repeats nodes; prepare unambiguous segments")
        if p["road_kind"] != "ground" and (refs[0] not in ground or refs[-1] not in ground):
            raise ValueError("OSM structure endpoints require explicit-height ground connections; prepare complete approaches")
        cuts = [0] + [i for i in range(1, len(refs)-1) if uses[refs[i]] > 1] + [len(refs)-1]
        for a,b in zip(cuts,cuts[1:]):
            if len(output) >= MAX_FEATURES:
                raise ValueError("OSM split feature budget exceeded")
            properties = dict(p, osm_node_refs=refs[a:b+1], elevations_m=p["elevations_m"][a:b+1])
            output.append(dict(type="Feature", properties=properties, geometry=dict(type="LineString", coordinates=feature["geometry"]["coordinates"][a:b+1])))
    return output


def canonical_ring(ring):
    values = ring[:-1]
    smallest = values.index(min(values))
    forward = values[smallest:] + values[:smallest]
    reverse = [forward[0]] + list(reversed(forward[1:]))
    result = min(forward, reverse)
    return result + [result[0]]


def assemble(segments):
    """Join complete way endpoints in either direction, never infer missing edges."""
    endpoints, remaining, rings = {}, {}, []
    for identity, refs in segments:
        if len(refs) < 2 or len(set(refs[:-1] if refs[0] == refs[-1] else refs)) != len(refs)-(refs[0] == refs[-1]):
            raise ValueError("OSM multipolygon short/repeated way nodes")
        if refs[0] == refs[-1]:
            if len(refs) < 4:
                raise ValueError("OSM multipolygon short closed ring")
            rings.append(canonical_ring(refs))
            continue
        remaining[identity] = refs
        for endpoint in (refs[0], refs[-1]):
            endpoints.setdefault(endpoint, []).append(identity)
    if any(len(ways) != 2 for ways in endpoints.values()):
        raise ValueError("OSM multipolygon incomplete or ambiguous endpoint joins")
    for identity in sorted(remaining):
        if identity not in remaining:
            continue
        ring = remaining.pop(identity)[:]
        while ring[-1] != ring[0]:
            following = [key for key in endpoints[ring[-1]] if key in remaining]
            if len(following) != 1:
                raise ValueError("OSM multipolygon incomplete or ambiguous ring")
            refs = remaining.pop(following[0])
            ring.extend((refs if refs[0] == ring[-1] else refs[::-1])[1:])
        if len(set(ring[:-1])) != len(ring)-1:
            raise ValueError("OSM multipolygon repeats a ring node")
        rings.append(canonical_ring(ring))
    return sorted(rings)


def relation_features(relations, all_ways, nodes, blocked_members, counts, budget):
    features, consumed = [], set()
    semantic = {"building", "building:part", "height", "landuse", "natural", "highway", "width", "surface"}
    for identity, kind, members, tags in sorted(relations):
        vertical(tags)
        selected = {"outer": [], "inner": []}
        local = set()
        for member_type, ref, role in members:
            if member_type != "w" or role not in selected or ref in local or ref in consumed or ref in blocked_members:
                raise ValueError("OSM multipolygon requires unique explicit outer/inner ways without shared area ownership")
            if ref not in all_ways:
                raise ValueError("OSM multipolygon missing member way; use a complete extract")
            refs, member_tags = all_ways[ref]
            vertical(member_tags)
            if any(key in member_tags and member_tags[key] != tags.get(key) for key in semantic) or (role == "inner" and category(member_tags)):
                raise ValueError("OSM multipolygon member feature tags conflict; prepare explicit relation geometry")
            if any(node not in nodes for node in refs):
                raise ValueError("OSM multipolygon missing referenced node; use a complete extract")
            local.add(ref)
            selected[role].append((ref, refs))
        outers = [[nodes[n] for n in ring] for ring in assemble(selected["outer"])]
        inners = [[nodes[n] for n in ring] for ring in assemble(selected["inner"])]
        polygons = group_rings(outers, inners, budget)
        properties = {}
        if kind == "building":
            if "height" in tags: properties["height_m"] = metres(tags, "height")
            if tags["building"] != "yes": properties["usage"] = tags["building"]
        else:
            properties["landuse"] = "orchard" if tags.get("landuse") == "orchard" else "forest"
        features.append(dict(type="Feature", properties=properties, geometry=dict(type="MultiPolygon", coordinates=polygons)))
        consumed.update(local)
        counts["assembled_relations"] += 1
        counts["outer_rings"] += len(outers)
        counts["inner_rings"] += len(inners)
    counts["member_ways"] = len(consumed)
    return features, consumed


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
    node_tags = {}
    all_ways, relations = {}, []
    counts = dict(nodes=0, ways=0, relations=0, ignored_ways=0, ignored_relations=0, tagged_nodes=0, assembled_relations=0, outer_rings=0, inner_rings=0, member_ways=0)
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
                if tags: node_tags[entity.id] = tags
            elif kind == "w":
                counts["ways"] += 1
                refs += len(entity.nodes)
                if refs > MAX_REFS:
                    raise ValueError("OSM reference budget exceeded")
                all_ways[entity.id] = ([n.ref for n in entity.nodes], tags)
                selected = category(tags)
                if selected:
                    if len(ways) + len(relations) >= MAX_FEATURES:
                        raise ValueError("OSM selected feature budget exceeded")
                    ways.append((entity.id, selected, [n.ref for n in entity.nodes], tags))
                else:
                    counts["ignored_ways"] += 1
            elif kind == "r":
                counts["relations"] += 1
                refs += len(entity.members)
                if refs > MAX_REFS:
                    raise ValueError("OSM reference budget exceeded")
                selected = category(tags)
                if selected:
                    if tags.get("type") != "multipolygon" or selected == "road":
                        raise ValueError("OSM selected relation requires a building/forest/orchard multipolygon")
                    if len(ways) + len(relations) >= MAX_FEATURES:
                        raise ValueError("OSM selected feature budget exceeded")
                    relations.append((entity.id, selected, [(m.type, m.ref, m.role) for m in entity.members], tags))
                else:
                    if tags.get("type") in ("multipolygon", "boundary"):
                        area_members.update(m.ref for m in entity.members if m.type == "w")
                    counts["ignored_relations"] += 1
            else:
                raise ValueError("unsupported OSM entity")
    except RuntimeError as exc:
        raise ValueError("invalid OSM snapshot: " + str(exc)[:300]) from exc
    return build_features(nodes, node_tags, ways, all_ways, relations, area_members, counts)


def build_features(nodes, node_tags, ways, all_ways, relations, area_members, counts):
    """Normalize a complete bounded selection from either snapshot reader."""
    assembled, consumed = relation_features(relations, all_ways, nodes, area_members, counts, Budget())
    counts["ignored_ways"] -= sum(category(all_ways[ref][1]) is None for ref in consumed)
    features = []
    for identity, kind, references, tags in sorted(ways):
        if identity in consumed:
            continue
        if identity in area_members:
            raise ValueError("selected OSM way belongs to an area relation; no silent holes/flattening")
        if any(ref not in nodes for ref in references):
            raise ValueError(f"OSM way {identity}: missing referenced node; use a complete extract")
        if kind != "road": vertical(tags)
        points = [nodes[ref] for ref in references]
        properties = {}
        if kind == "road":
            if tags["highway"] not in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "track", "path", "footway", "cycleway", "pedestrian") or tags.get("area", "no") != "no":
                raise ValueError(f"OSM way {identity}: unsupported highway/area profile")
            if len(references) < 2 or references[0] == references[-1]:
                raise ValueError(f"OSM way {identity}: closed/short road requires explicit segmentation")
            properties.update(road_vertical(tags, references, node_tags))
            if "osm_node_refs" in properties: properties["osm_way_id"] = identity
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
    features = split_vertical_roads(features)
    counts["explicit_height_roads"] = sum("elevations_m" in f["properties"] for f in features)
    counts["bridge_segments"] = sum(f["properties"].get("road_kind") == "bridge" for f in features)
    counts["tunnel_segments"] = sum(f["properties"].get("road_kind") == "tunnel" for f in features)
    features.extend(assembled)
    if len(features) > MAX_FEATURES:
        raise ValueError("OSM selected feature budget exceeded")
    if not features:
        raise ValueError("OSM extract contains no supported road/building/forest/orchard features")
    return dict(type="FeatureCollection", features=features), counts


def finish(layer, counts):
    layer.adapter = "osm-extract-v1"
    previous = layer.warnings
    layer.warnings = []
    layer.warning("OSM snapshot via osmium 4.3.1; © OpenStreetMap contributors; ODbL-1.0; https://www.openstreetmap.org/copyright")
    layer.warning("OSM input counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    layer.warning("Selected ways and explicit multipolygons are imported; POIs, other ways/relations and other tags are omitted. No routing/access/oneway semantics.")
    layer.warning("Ground elevation/base, missing width/height/surface, vegetation and materials are estimates; building levels/roof tags are not interpreted.")
    if counts.get("explicit_height_roads"):
        layer.warning("Explicit OSM node ele metres use EGM96 sea level as map Y=0; no vertical offset/datum conversion or terrain alignment. Verify against your map before adoption.")
        layer.warning("Explicit-height roads join only shared OSM node IDs (including split interior junctions); original source structure ends require explicit ground approaches before crop. Layer is ordering only, never height. Bridges add no invented supports or under-deck clearance; tunnel ceiling uses maxheight:physical, not legal maxheight.")
        layer.warning("Only bridge=yes/tunnel=yes with complete node elevations supported. Road grades interpolate between supplied nodes; tunnel cross-section is rectangular and physical clearance is constant (shape estimate). Access/oneway/vehicle limits remain omitted.")
        if counts.get("tunnel_segments"): layer.estimate("rectangular_tunnel_cross_section")
    # Put source-level omissions before per-road warning samples, even at the cap.
    layer.warnings = (layer.warnings + previous)[:50]
    layer.encode()
    return layer
