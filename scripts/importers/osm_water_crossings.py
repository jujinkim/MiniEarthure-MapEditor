"""City road evidence against original water, before any road corridor subtraction."""
from shapely.geometry import LineString, Polygon, Point, shape
from shapely.ops import transform
import shapely
import math
from collections import Counter, defaultdict


def exceptions(tags, refs, node_tags):
    ford = tags.get("ford", "no") not in ("no", "0") or tags.get("highway") == "ford" or any(
        node_tags.get(ref, {}).get("ford", "no") not in ("no", "0") or node_tags.get(ref, {}).get("highway") == "ford" for ref in refs)
    excluded = ford or tags.get("tunnel", "no") not in ("no", "0") or tags.get("embankment", "no") not in ("no", "0") or tags.get("man_made") in ("dyke", "embankment", "causeway")
    return excluded, ford


def classify(ways, nodes, assembled, consumed=frozenset(), node_tags=None):
    from osm_extract import CITY_WATERWAYS, metres
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
            width = CITY_WATERWAYS.get(tags.get("waterway"), 3.0)
            if "width" in tags:
                try: width = metres(tags, "width")
                except ValueError: pass
            width = min(max(width, 0.5), 200.0)
            if math.isfinite(width) and 0 < width <= 1000:
                water.append(transform(inverse, transform(project, LineString(points)).buffer(width / 2)))
    if not water: return ways, None, {}
    original = shapely.union_all(water)
    metric = transform(project, original)
    shapely.prepare(metric)
    roads = {identity: (refs, tags) for identity, kind, refs, tags in ways
             if kind == "road" and identity not in consumed and len(refs) >= 2 and all(ref in nodes for ref in refs)}
    arms, ends = Counter(), defaultdict(list)
    lines, wet, flags = {}, {}, {}
    for identity, (refs, tags) in roads.items():
        for i, ref in enumerate(refs): arms[ref] += 1 if i in (0, len(refs)-1) else 2
        for ref in (refs[0], refs[-1]): ends[ref].append(identity)
        line = transform(project, LineString([nodes[ref] for ref in refs]))
        lines[identity] = line
        meet = line.intersection(metric) if shapely.intersects(metric, line) else LineString()
        wet[identity] = sum(p.length for p in getattr(meet, "geoms", [meet]) if p.geom_type == "LineString")
        flags[identity] = exceptions(tags, refs, node_tags)
    # Follow original source incidence, independent of way segmentation. A
    # junction, loop or explicit exception stops inference; never guess a branch.
    used, inferred, chain_info = set(), set(), {}
    for identity in sorted(roads):
        if identity in used or flags[identity][0]: continue
        path = [(identity, False)]
        used.add(identity)
        for at_end in (False, True):
            while True:
                way, flipped = path[-1] if at_end else path[0]
                refs = roads[way][0][::-1] if flipped else roads[way][0]
                node = refs[-1] if at_end else refs[0]
                peers = [peer for peer in ends[node] if peer != way]
                if arms[node] != 2 or len(peers) != 1: break
                peer = peers[0]
                if peer in used or flags[peer][0]: break
                other = roads[peer][0]
                # Interior branches are also boundaries for a structural chain.
                if other[0] == other[-1] or any(arms[ref] != 2 for ref in other[1:-1]): break
                used.add(peer)
                entry = (peer, other[-1] == node if at_end else other[0] == node)
                if at_end: path.append(entry)
                else: path.insert(0, entry)
        refs = []
        for way, flipped in path:
            segment = roads[way][0][::-1] if flipped else roads[way][0]
            refs.extend(segment if not refs else segment[1:])
        wet_members = [i for i, (way, _) in enumerate(path) if wet[way] > .1]
        if not wet_members: continue
        anchors = [Point(project(*nodes[ref])) for ref in (refs[0], refs[-1])]
        across = len(set(refs)) == len(refs) and all(metric.distance(p) > 2 for p in anchors) and sum(wet[way] for way, _ in path) >= 2
        if not across: continue
        sources = ["way/" + str(way) for way, _ in path]
        for way, _ in path[min(wet_members):max(wet_members)+1]:
            inferred.add(way)
            chain_info[way] = dict(chain_sources=sources, land_anchor_nodes=[str(refs[0]), str(refs[-1])])
    evidence, result = {}, []
    for identity, kind, refs, tags in ways:
        if identity not in roads or (wet[identity] <= .1 and identity not in inferred):
            result.append((identity, kind, refs, tags)); continue
        explicit = tags.get("bridge", "no") not in ("no", "0")
        exception, ford = flags[identity]
        record = dict(source_id="way/" + str(identity), water_length_m=round(wet[identity], 2))
        if exception:
            record.update(reason="explicit ford, culvert/tunnel or embankment takes precedence", conflict=explicit, unresolved=explicit, ford=ford)
        elif explicit:
            record.update(reason="explicit bridge intersects original source water")
        elif identity in inferred:
            tags = dict(tags, bridge="yes")
            record.update(reason="inferred bridge: connected source chain crosses water between two land anchors", inferred=True, **chain_info[identity])
        else:
            record.update(reason="source chain has no two unambiguous land anchors (junction, shore tangent or water dead end)", unresolved=True)
        evidence[identity] = record
        result.append((identity, kind, refs, tags))
    return result, original, evidence
