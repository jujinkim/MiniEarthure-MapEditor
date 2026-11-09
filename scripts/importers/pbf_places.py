"""Offline administrative-name lookup and bounded boundary preview, not map generation.

Besides administrative areas whose names contain the query, the lookup lists named
features whose name is exactly the query (anchors: villages, stations, campuses …)
and, for every area centre and anchor, the administrative areas of the PBF that
contain it and its country, so callers can choose a map extent and a traffic
convention without guessing (`real_city_auto.gd`)."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from import_layer import BudgetExceeded, Progress, soft_limit, limit_entries, limit_text
from osm_extract import dependency
from osm_stream import _capture, _scan, OWNED_FILES, MAX_SCAN_ENTITIES

MAX_MATCHES = 32  # Results shown; further matches are counted in a warning.
MAX_REFS = 200_000  # Warn above.
REFS_CEILING = 10_000_000  # Memory guard.
MAX_PREVIEW_POINTS = 20_000  # Display only: the preview is thinned to fit.
MAX_NAME = 256  # Longer names are shortened for display.
MAX_PREVIEW_BYTES = 4 * 1024**2  # Warn above.
PREVIEW_CEILING = 16 * 1024**2


def _references(count):
    if count > REFS_CEILING: raise BudgetExceeded("PBF boundary references exceed 10,000,000")
    if count > MAX_REFS: soft_limit("place_references", count, MAX_REFS, "PBF boundary reference budget exceeded")


def _thin(places, ways, nodes):
    """Display outlines within MAX_PREVIEW_POINTS. Every way keeps its last point
    while it fits; the exact extent (bbox) is never thinned."""
    complete = [place for place in places if not place["issue"]]
    if not complete: return
    share = max(2, min(2000, MAX_PREVIEW_POINTS // len(complete)))
    for place in complete:
        refs = place["_refs"]
        stride = max(1, (sum(len(ways[ref]) for ref in refs) + share - 1) // share)
        lines = []
        for ref in refs:
            line = [nodes[n] for n in ways[ref][::stride]]
            if line[-1] != nodes[ways[ref][-1]]: line.append(nodes[ways[ref][-1]])
            lines.append(line)
        place["outlines"] = lines
    if sum(len(line) for place in complete for line in place["outlines"]) <= MAX_PREVIEW_POINTS: return
    # Too many boundary ways for the display: keep a regular subset of them.
    for place in complete:
        used = sum(len(line) for line in place["outlines"])
        if used > share:
            lines, kept = [], 0
            for line in place["outlines"][::(used + share - 1) // share]:
                if lines and kept + len(line) > share: break
                lines.append(line)
                kept += len(line)
            place["outlines"] = lines
            soft_limit("place_preview_ways", used, share, "Boundary preview shows a subset of boundary ways")


MAX_ANCHORS = 16  # Results shown; further anchors are counted in a warning.
MAX_CONTEXT_REFS = 8_000_000  # Containing-area context: warn and stop collecting above.
MAX_CONTEXT_AREAS = 16  # Containing areas listed per point (largest dropped first).
ANCHOR_KEYS = ("name", "name:ko", "name:en", "name:ja", "official_name", "alt_name", "int_name", "short_name", "loc_name")
SETTLEMENTS = ("city", "town", "village", "suburb", "quarter", "neighbourhood", "borough", "hamlet", "isolated_dwelling", "locality", "square")
KIND_KEYS = ("place", "amenity", "tourism", "historic", "leisure", "aeroway", "railway", "landuse", "natural", "waterway", "highway", "building", "shop")
CONTEXT_STAGES = ("context_relations", "context_ways", "context_named_ways", "context_nodes", "context_named_nodes")
KM_PER_DEGREE = 111.32


def _kind(tags):
    return next((f"{key}={tags.get(key)}"[:64] for key in KIND_KEYS if tags.get(key)), "")


def _tier(tags):
    """Settlements first (larger first), then landmarks, then other named features."""
    if tags.get("place") in SETTLEMENTS: return SETTLEMENTS.index(tags.get("place"))
    if any(tags.get(key) for key in ("amenity", "tourism", "historic", "leisure", "aeroway", "railway")): return 20
    return 30


def _iso(tags):
    return (tags.get("ISO3166-1:alpha2") or tags.get("ISO3166-1") or "")[:2].upper(), (tags.get("ISO3166-2") or "")[:16]


class _Context:
    """Every administrative boundary of a captured PBF and the exactly named
    features (anchors). `locate` lists the boundaries containing a point (only
    complete ones; nothing is guessed) and the country (`basis`: the containing
    country boundary, the ISO 3166-2 code of a containing subdivision, the one
    code of cut country/subdivision boundaries whose present points span the
    point, or the extract's only country)."""

    def __init__(self, path, size, osmium, event, query):
        self.boundaries, self.ways, self.nodes, self.anchors = {}, {}, {}, []
        self.complete = True
        refs = 0

        def budget(count):
            nonlocal refs
            refs += count
            if self.complete and refs > MAX_CONTEXT_REFS:
                soft_limit("place_context_references", refs, MAX_CONTEXT_REFS, "PBF boundary context budget exceeded; containing areas and country are not listed")
                self.complete = False
            return self.complete

        def named(tags):
            return query and any(tags.get(key) == query for key in ANCHOR_KEYS)

        def anchor(kind, identity, tags, ways=(), nodes=(), point=None):
            name = next((tags.get(key) for key in ANCHOR_KEYS if tags.get(key) == query), query)[:MAX_NAME]
            self.anchors.append(dict(name=name, source_id=f"{kind}/{identity}", kind=_kind(tags), _tier=_tier(tags), _ways=list(ways), _nodes=list(nodes), point=point))

        def relation(entity):
            tags = entity.tags
            if tags.get("boundary") == "administrative":
                outer = [m.ref for m in entity.members if m.type == "w" and m.role in ("outer", "")]
                inner = [m.ref for m in entity.members if m.type == "w" and m.role == "inner"]
                if not budget(len(outer) + len(inner)): return
                code, subdivision = _iso(tags)
                self.boundaries[entity.id] = dict(name=next((tags.get(k) for k in ("name", "name:ko", "name:en") if tags.get(k)), "")[:MAX_NAME],
                                                  admin_level=tags.get("admin_level", "")[:16], country=code, subdivision=subdivision,
                                                  driving_side=tags.get("driving_side", "") if tags.get("driving_side") in ("left", "right") else "",
                                                  outer=outer, inner=inner)
                self.ways.update((ref, None) for ref in outer + inner)
            elif named(tags):
                refs = [m.ref for m in entity.members if m.type == "w" and m.role in ("outer", "")]
                if not budget(len(refs)): return
                anchor("relation", entity.id, tags, ways=refs)
                self.ways.update((ref, None) for ref in refs)

        def way(entity):
            if entity.id not in self.ways or not budget(len(entity.nodes)): return
            self.ways[entity.id] = [node.ref for node in entity.nodes]
            self.nodes.update((node.ref, None) for node in entity.nodes)

        def named_way(entity):
            if not named(entity.tags) or not budget(len(entity.nodes)): return
            refs = [node.ref for node in entity.nodes]
            anchor("way", entity.id, entity.tags, nodes=refs)
            self.nodes.update((ref, None) for ref in refs)

        def node(entity):
            if entity.id in self.nodes and entity.location.valid(): self.nodes[entity.id] = (entity.lon, entity.lat)

        def named_node(entity):
            if named(entity.tags) and entity.location.valid() and budget(1):
                anchor("node", entity.id, entity.tags, point=[entity.lon, entity.lat])

        names = osmium.filter.TagFilter(*[(key, query) for key in ANCHOR_KEYS]) if query else None
        for stage, bits, callback, selected in (
                (CONTEXT_STAGES[0], osmium.osm.RELATION, relation, None),
                (CONTEXT_STAGES[1], osmium.osm.WAY, way, lambda: osmium.filter.IdFilter(self.ways)),
                (CONTEXT_STAGES[2], osmium.osm.WAY, named_way if query else (lambda entity: None), lambda: names or osmium.filter.IdFilter([])),
                (CONTEXT_STAGES[3], osmium.osm.NODE, node, lambda: osmium.filter.IdFilter(self.nodes)),
                (CONTEXT_STAGES[4], osmium.osm.NODE, named_node if query else (lambda entity: None), lambda: names or osmium.filter.IdFilter([]))):
            _scan(path, stage, event, size, osmium, bits, callback, selected() if selected else None)
        self._boxes, self._shapes = {}, {}
        for item in self.anchors:
            if item["point"] is None:
                refs = item["_nodes"] + [n for ref in item["_ways"] for n in (self.ways.get(ref) or [None])]
                points = [self.nodes.get(n) for n in refs]
                if points and all(p is not None for p in points):
                    item["point"] = [round((min(p[0] for p in points) + max(p[0] for p in points)) / 2, 7),
                                     round((min(p[1] for p in points) + max(p[1] for p in points)) / 2, 7)]
            item["issue"] = "" if item["point"] is not None and -180 <= item["point"][0] <= 180 and -80 <= item["point"][1] <= 84 else "Incomplete geometry in this PBF; its position was not guessed."
            if item["issue"]: item["point"] = []
        self.anchors.sort(key=lambda a: (bool(a["issue"]), a["_tier"], a["source_id"]))

    def _box(self, identity):
        if identity not in self._boxes:
            entry = self.boundaries[identity]
            points = [self.nodes.get(n) for ref in entry["outer"] for n in (self.ways.get(ref) or [None])]
            self._boxes[identity] = None if not points or any(p is None for p in points) else (
                min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
        return self._boxes[identity]

    def _partial_box_covers(self, identity, point):
        points = [self.nodes[n] for ref in self.boundaries[identity]["outer"] for n in (self.ways.get(ref) or []) if self.nodes.get(n)]
        return bool(points) and min(p[0] for p in points) <= point[0] <= max(p[0] for p in points) and min(p[1] for p in points) <= point[1] <= max(p[1] for p in points)

    def _shape(self, identity):
        if identity not in self._shapes:
            from shapely.geometry import LineString
            from shapely.ops import polygonize, unary_union
            entry = self.boundaries[identity]
            line = lambda ref: LineString([self.nodes[n] for n in self.ways[ref]])
            shape = unary_union(list(polygonize(unary_union([line(ref) for ref in entry["outer"]]))))
            inner = [ref for ref in entry["inner"] if self.ways.get(ref) and all(self.nodes.get(n) for n in self.ways[ref])]
            if inner and not shape.is_empty: shape = shape.difference(unary_union(list(polygonize(unary_union([line(ref) for ref in inner])))))
            self._shapes[identity] = shape
        return self._shapes[identity]

    def locate(self, point):
        if not self.complete or not point: return dict(areas=[], country={})
        from shapely.geometry import Point
        here, areas = Point(point), []
        for identity, entry in self.boundaries.items():
            box = self._box(identity)
            if box is None or not (box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]): continue
            shape = self._shape(identity)
            if shape.is_empty or not shape.covers(here): continue
            km2 = shape.area * KM_PER_DEGREE ** 2 * math.cos(math.radians((box[1] + box[3]) / 2))
            areas.append(dict(name=entry["name"], source_id=f"relation/{identity}", admin_level=entry["admin_level"],
                              bbox=[round(v, 7) for v in box], km2=round(km2, 6), _entry=entry))
        areas.sort(key=lambda a: (-a["km2"], a["source_id"]))
        country = {}
        named_countries = [e for e in self.boundaries.values() if e["admin_level"] == "2" and e["country"]]
        found = next((a["_entry"] for a in areas if a["_entry"]["admin_level"] == "2" and a["_entry"]["country"]), None)
        basis = "boundary"
        if found is None:
            subdivision = next((a["_entry"]["subdivision"] for a in reversed(areas) if "-" in a["_entry"]["subdivision"]), "")
            if subdivision:
                code, basis = subdivision.split("-")[0].upper()[:2], "subdivision"
                found = next((e for e in named_countries if e["country"] == code), dict(country=code, name="", driving_side=""))
            else:
                # Regional extracts cut country and state boundaries: their present
                # points still span the place. Every such code must agree.
                codes = {e["country"] or e["subdivision"].split("-")[0].upper()[:2]
                         for identity, e in self.boundaries.items() if (e["country"] or "-" in e["subdivision"]) and self._partial_box_covers(identity, point)}
                if len(codes) == 1:
                    code = codes.pop()
                    found, basis = next((e for e in named_countries if e["country"] == code), dict(country=code, name="", driving_side="")), "partial"
                elif len({e["country"] for e in named_countries}) == 1:
                    found, basis = named_countries[0], "extract"
        if found is not None: country = dict(code=found["country"], name=found["name"], driving_side=found["driving_side"], basis=basis)
        if len(areas) > MAX_CONTEXT_AREAS: areas = areas[len(areas) - MAX_CONTEXT_AREAS:]
        for area in areas: area.pop("_entry")
        return dict(areas=areas, country=country)


def lookup(source, query, directory, event=lambda *args: None, point=None):
    """Areas named like `query` plus anchors named exactly `query`, each with
    its containing areas and country; `point` ([lon, lat]) adds that point's
    context alone (`query` may then be empty)."""
    query = query.strip()
    if (not query and point is None) or len(query) > 128 or any(ord(c) < 32 for c in query):
        raise ValueError("Enter an administrative area name (1–128 characters)")
    if point is not None and (len(point) != 2 or not -180 <= point[0] <= 180 or not -80 <= point[1] <= 84):
        raise ValueError("Point must be [lon, lat] within -180..180 / -80..84")
    source, directory = Path(source), Path(directory)
    if any((directory / name).exists() for name in OWNED_FILES):
        raise ValueError("PBF lookup workspace already contains owned files")
    places, ways, nodes = [], {}, {}
    counts = [0, 0, 0]
    references = 0
    try:
        size, digest = _capture(source, directory, event)
        path, osmium = directory / "source.pbf", dependency()

        def counted(index):
            counts[index] += 1
            if sum(counts) > MAX_SCAN_ENTITIES:
                soft_limit("place_scan_entities", sum(counts), MAX_SCAN_ENTITIES, "PBF lookup scan entity budget exceeded; scanning takes longer")

        def relation(entity):
            nonlocal references
            counted(0)
            if not query or entity.tags.get("boundary") != "administrative": return
            names = [entity.tags.get(key, "") for key in ("name", "name:ko", "name:en", "official_name")]
            if not any(query.casefold() in name.casefold() for name in names): return
            name = next((n for n in names if n), "")
            if len(name) > MAX_NAME:
                soft_limit("place_name", len(name), MAX_NAME, "PBF place name is shortened for display")
                name = name[:MAX_NAME]
            refs, issue = [], ""
            for member in entity.members:
                if member.role not in ("outer", ""): continue
                if member.type != "w":
                    issue = "Nested outer boundary is unsupported; choose another area or enter coordinates."
                    continue
                refs.append(member.ref)
                references += 1
                _references(references)
            if not refs: issue = "No direct outer boundary ways in this source."
            places.append(dict(name=name, source_id=f"relation/{entity.id}", admin_level=entity.tags.get("admin_level", "")[:16], refs=refs, issue=issue,
                               rank=0 if any(query.casefold()==n.casefold() for n in names) else 1 if any(n.casefold().startswith(query.casefold()) for n in names) else 2))
            ways.update((ref, None) for ref in refs)

        def way(entity):
            nonlocal references
            counted(1)
            if entity.id not in ways: return
            if ways[entity.id] is not None: raise ValueError("Duplicate boundary way")
            references += len(entity.nodes)
            _references(references)
            refs = [node.ref for node in entity.nodes]
            ways[entity.id] = refs
            nodes.update((ref, None) for ref in refs)

        def node(entity):
            counted(2)
            if entity.id not in nodes: return
            if nodes[entity.id] is not None or not entity.location.valid(): raise ValueError("Invalid/duplicate boundary node")
            if not -180 <= entity.lon <= 180 or not -80 <= entity.lat <= 84:
                raise ValueError("Boundary is outside the supported latitude range")
            nodes[entity.id] = [entity.lon, entity.lat]

        for stage, bits, callback, ids in (("index_relations", osmium.osm.RELATION, relation, None), ("index_ways", osmium.osm.WAY, way, ways), ("index_nodes", osmium.osm.NODE, node, nodes)):
            # Filter in libosmium before creating Python entities. Framed byte
            # progress and the immutable capture still cover the whole source.
            selected_ids = None if ids is None else osmium.filter.IdFilter(ids)
            _scan(path, stage, event, size, osmium, bits, callback, selected_ids)
        for place in places:
            refs = place.pop("refs")
            place.update(bbox=[], outlines=[])
            if place["issue"]: continue
            if any(not ways[ref] or any(nodes[n] is None for n in ways[ref]) for ref in refs):
                place["issue"] = "Incomplete outer boundary in this PBF; no extent was guessed."
                continue
            points = [nodes[n] for ref in refs for n in ways[ref]]
            if len(points) < 3:
                place["issue"] = "Boundary has too few points."
                continue
            box = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
            if box[0] >= box[2] or box[1] >= box[3] or box[2]-box[0] > 180:
                place["issue"] = "Empty or dateline-crossing boundary is unsupported."
                continue
            # Exact extent; the outline is a thinned display only.
            place.update(bbox=box, _refs=refs)
        places.sort(key=lambda p: (p["rank"], int(p["admin_level"]) if p["admin_level"].isdigit() else 100, p["name"], p["source_id"]))
        if len(places) > MAX_MATCHES:
            # Display truncation only: the best matches are listed.
            soft_limit("place_matches", len(places), MAX_MATCHES, "More matching areas than shown; enter a more specific name")
            places = places[:MAX_MATCHES]
        for place in places: place.pop("rank")
        _thin(places, ways, nodes)
        for place in places: place.pop("_refs", None)
        context = _Context(path, size, osmium, event, query)
        for place in places:
            box = place["bbox"]
            place["context"] = context.locate([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2] if box else None)
        anchors = [a for a in context.anchors if not any(a["source_id"] == p["source_id"] for p in places)]
        if len(anchors) > MAX_ANCHORS:
            soft_limit("place_anchors", len(anchors), MAX_ANCHORS, "More named places than shown; enter a more specific name")
            anchors = anchors[:MAX_ANCHORS]
        for item in anchors:
            item["tier"] = item.pop("_tier")
            for key in ("_ways", "_nodes"): item.pop(key)
            item["context"] = context.locate(item["point"] or None)
        value = dict(profile="pbf-place-preview-v1", query=query, source_name=source.name, source_sha256=digest, source_bytes=size, places=places, anchors=anchors)
        if point is not None: value["point_context"] = context.locate(list(point))
        value["limit_warnings"] = [limit_text(entry) for entry in limit_entries()]
        return value
    finally:
        for name in ("source.pbf.part", "source.pbf"):
            (directory / name).unlink(missing_ok=True)


MAX_REGION_AREAS = 8  # Warn above.
REGION_AREAS_CEILING = 64


def region(path, relation_ids, osmium, event=lambda *args: None):
    """Exact union of selected administrative boundaries in an already captured PBF.

    Outer ways are polygonized as recorded; inner ways are removed. Missing or
    open boundaries reject the request instead of guessing an extent.
    """
    import shapely
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    wanted = [int(v) for v in relation_ids]
    if not wanted or len(wanted) > REGION_AREAS_CEILING or len(set(wanted)) != len(wanted) or any(v <= 0 for v in wanted):
        raise ValueError(f"Choose 1–{REGION_AREAS_CEILING} distinct administrative areas")
    if len(wanted) > MAX_REGION_AREAS:
        soft_limit("region_areas", len(wanted), MAX_REGION_AREAS, "Many administrative areas are combined; the import takes longer")
    path = Path(path)
    size = path.stat().st_size
    found, ways, nodes, references = {}, {}, {}, 0

    def relation(entity):
        nonlocal references
        if entity.id not in wanted: return
        if entity.tags.get("boundary") != "administrative": raise ValueError(f"relation/{entity.id} is not an administrative boundary")
        members = []
        for member in entity.members:
            if member.role not in ("outer", "inner", ""): continue
            if member.type != "w": raise ValueError(f"relation/{entity.id}: nested boundary members are unsupported")
            members.append((member.ref, member.role or "outer"))
            references += 1
            _references(references)
        found[entity.id] = dict(name=next((entity.tags.get(k) for k in ("name", "name:ko", "name:en") if entity.tags.get(k)), "")[:256], members=members)
        ways.update((ref, None) for ref, _ in members)

    def way(entity):
        nonlocal references
        if entity.id not in ways: return
        references += len(entity.nodes)
        _references(references)
        ways[entity.id] = [node.ref for node in entity.nodes]
        nodes.update((ref, None) for ref in ways[entity.id])

    def node(entity):
        if entity.id not in nodes: return
        if not entity.location.valid(): raise ValueError("Invalid boundary node")
        nodes[entity.id] = (entity.lon, entity.lat)

    for stage, bits, callback, ids in (("region_relations", osmium.osm.RELATION, relation, wanted), ("region_ways", osmium.osm.WAY, way, ways), ("region_nodes", osmium.osm.NODE, node, nodes)):
        _scan(path, stage, event, size, osmium, bits, callback, osmium.filter.IdFilter(ids) if ids else None)
    areas, parts = [], []
    for identity in wanted:
        if identity not in found: raise ValueError(f"relation/{identity} is missing from this PBF")
        entry = found[identity]
        lines = {"outer": [], "inner": []}
        for ref, role in entry["members"]:
            refs = ways.get(ref)
            if not refs or any(nodes.get(n) is None for n in refs): raise ValueError(f"relation/{identity}: incomplete boundary; no extent was guessed")
            lines[role].append(LineString([nodes[n] for n in refs]))
        outer = unary_union(list(polygonize(unary_union(lines["outer"])))) if lines["outer"] else None
        if outer is None or outer.is_empty: raise ValueError(f"relation/{identity}: boundary does not close")
        if lines["inner"]: outer = outer.difference(unary_union(list(polygonize(unary_union(lines["inner"])))))
        parts.append(outer)
        areas.append(dict(source_id=f"relation/{identity}", name=entry["name"]))
    union = shapely.make_valid(unary_union(parts))
    if union.is_empty or union.bounds[2] - union.bounds[0] > 180: raise ValueError("Selected areas form an empty or dateline-crossing region")
    return union, areas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--point", type=lambda text: [float(v) for v in text.split(",")], help="lon,lat whose containing areas and country are listed")
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    from geojson import watch_parent_lifetime
    watch_parent_lifetime()
    progress = Progress(args.request)
    def event(stage, completed, total):
        progress(stage, completed, total)
    value = lookup(args.source, args.query, args.output.parent, event, args.point)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > PREVIEW_CEILING: raise ValueError("Boundary preview exceeds 16 MiB")
    if len(raw) > MAX_PREVIEW_BYTES:
        soft_limit("place_preview_bytes", len(raw), MAX_PREVIEW_BYTES, "Boundary preview exceeds 4 MiB")
        value["limit_warnings"] = [limit_text(entry) for entry in limit_entries()]
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    event("write", 0, len(raw))
    with args.output.open("xb") as output: output.write(raw)
    event("write", len(raw), len(raw))
    progress("complete", len(raw), len(raw), sha256=hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    try: main()
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        raise SystemExit(str(exc))
