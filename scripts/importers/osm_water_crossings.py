"""City road evidence against original water, before any road corridor subtraction."""
from shapely.geometry import LineString, Polygon, Point, shape
from shapely.ops import transform
import shapely
import math


def classify(ways, nodes, assembled, consumed=frozenset(), node_tags=None):
    node_tags = node_tags or {}
    water = [shape(f["geometry"]) for f in assembled
             if f["properties"].get("landuse") in ("water", "reservoir", "basin")]
    latitude = sum(p[1] for p in nodes.values()) / max(1, len(nodes))
    sx, sy = 111320 * math.cos(math.radians(latitude)), 110540
    project = lambda x, y: (x * sx, y * sy)
    inverse = lambda x, y: (x / sx, y / sy)
    for identity, kind, refs, tags in ways:
        if identity in consumed or not refs or not all(ref in nodes for ref in refs): continue
        points = [nodes[ref] for ref in refs]
        if kind == "region" and (tags.get("natural") == "water" or tags.get("landuse") in ("reservoir", "basin")) and len(points) >= 4 and refs[0] == refs[-1]:
            polygon = Polygon(points)
            if polygon.is_valid: water.append(polygon)
        elif kind == "waterway" and tags.get("tunnel", "no") in ("no", "0"):
            try: width = float(tags.get("width", 3))
            except ValueError: width = 3
            if math.isfinite(width) and 0 < width <= 1000:
                water.append(transform(inverse, transform(project, LineString(points)).buffer(width / 2)))
    if not water: return ways, None, {}
    original = shapely.union_all(water)
    metric = transform(project, original)
    shapely.prepare(metric)
    evidence, result = {}, []
    for identity, kind, refs, tags in ways:
        if kind != "road" or len(refs) < 2 or not all(ref in nodes for ref in refs):
            result.append((identity, kind, refs, tags)); continue
        line = transform(project, LineString([nodes[ref] for ref in refs]))
        if not shapely.intersects(metric, line):
            result.append((identity, kind, refs, tags)); continue
        meet = line.intersection(metric)
        wet = sum(p.length for p in getattr(meet, "geoms", [meet]) if p.geom_type == "LineString")
        if wet <= .1:
            result.append((identity, kind, refs, tags)); continue
        explicit = tags.get("bridge", "no") not in ("no", "0")
        ford = tags.get("ford", "no") not in ("no", "0") or tags.get("highway") == "ford" or any(node_tags.get(ref, {}).get("ford", "no") not in ("no", "0") or node_tags.get(ref, {}).get("highway") == "ford" for ref in refs)
        exception = (ford or tags.get("ford", "no") not in ("no", "0") or tags.get("highway") == "ford"
                     or tags.get("tunnel", "no") not in ("no", "0")
                     or tags.get("embankment", "no") not in ("no", "0")
                     or tags.get("man_made") in ("dyke", "embankment", "causeway"))
        record = dict(source_id="way/" + str(identity), water_length_m=round(wet, 2))
        if exception:
            record.update(reason="explicit ford, culvert/tunnel or embankment takes precedence", conflict=explicit, unresolved=explicit, ford=ford)
        elif explicit:
            record.update(reason="explicit bridge intersects original source water")
        else:
            # Both anchors must have actual source land beyond the water edge.
            # A tangent or a road ending in water never becomes an inferred bridge.
            ends = [Point(line.coords[0]), Point(line.coords[-1])]
            across = all(metric.distance(p) > 2 for p in ends) and wet >= 2
            if across:
                tags = dict(tags, bridge="yes")
                record.update(reason="inferred bridge: source water between two land anchors", inferred=True)
            else:
                record.update(reason="shore tangent or water dead end needs explicit crossing evidence", unresolved=True)
        evidence[identity] = record
        result.append((identity, kind, refs, tags))
    return result, original, evidence
