"""Offline administrative-name lookup and bounded boundary preview, not map generation."""
import argparse
import hashlib
import json
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


def lookup(source, query, directory, event=lambda *args: None):
    query = query.strip()
    if not query or len(query) > 128 or any(ord(c) < 32 for c in query):
        raise ValueError("Enter an administrative area name (1–128 characters)")
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
            if entity.tags.get("boundary") != "administrative": return
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
        return dict(profile="pbf-place-preview-v1", query=query, source_name=source.name, source_sha256=digest, source_bytes=size, places=places,
                    limit_warnings=[limit_text(entry) for entry in limit_entries()])
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
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    from geojson import watch_parent_lifetime
    watch_parent_lifetime()
    progress = Progress(args.request)
    def event(stage, completed, total):
        progress(stage, completed, total)
    value = lookup(args.source, args.query, args.output.parent, event)
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
