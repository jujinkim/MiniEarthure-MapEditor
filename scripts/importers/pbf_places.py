"""Offline administrative-name lookup and bounded boundary preview, not map generation."""
import argparse
import hashlib
import json
from pathlib import Path

from osm_extract import dependency
from osm_stream import _capture, _scan, OWNED_FILES, MAX_SCAN_ENTITIES

MAX_MATCHES = 32
MAX_REFS = 200_000
MAX_PREVIEW_POINTS = 20_000


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
                raise ValueError("PBF lookup scan entity budget exceeded")

        def relation(entity):
            nonlocal references
            counted(0)
            if entity.tags.get("boundary") != "administrative": return
            names = [entity.tags.get(key, "") for key in ("name", "name:ko", "name:en", "official_name")]
            if not any(query.casefold() in name.casefold() for name in names): return
            if len(places) >= MAX_MATCHES: raise ValueError("More than 32 matching areas; enter a more specific name")
            name = next((n for n in names if n), "")
            if len(name) > 256: raise ValueError("PBF place name exceeds 256 characters")
            refs, issue = [], ""
            for member in entity.members:
                if member.role not in ("outer", ""): continue
                if member.type != "w":
                    issue = "Nested outer boundary is unsupported; choose another area or enter coordinates."
                    continue
                refs.append(member.ref)
                references += 1
                if references > MAX_REFS: raise ValueError("PBF boundary reference budget exceeded")
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
            if references > MAX_REFS: raise ValueError("PBF boundary reference budget exceeded")
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
        preview_points = 0
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
            # Exact extent, simplified display only. Retain endpoints of each way.
            stride = max(1, (len(points)+1999)//2000)
            lines = []
            for ref in refs:
                line = [nodes[n] for n in ways[ref][::stride]]
                if line[-1] != nodes[ways[ref][-1]]: line.append(nodes[ways[ref][-1]])
                preview_points += len(line)
                if preview_points > MAX_PREVIEW_POINTS: raise ValueError("PBF boundary preview budget exceeded; use a more specific name")
                lines.append(line)
            place.update(bbox=box, outlines=lines)
        places.sort(key=lambda p: (p["rank"], int(p["admin_level"]) if p["admin_level"].isdigit() else 100, p["name"], p["source_id"]))
        for place in places: place.pop("rank")
        return dict(profile="pbf-place-preview-v1", query=query, source_name=source.name, source_sha256=digest, source_bytes=size, places=places)
    finally:
        for name in ("source.pbf.part", "source.pbf"):
            (directory / name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    from geojson import watch_parent_lifetime
    watch_parent_lifetime(900)
    sequence = 0
    def event(stage, completed, total):
        nonlocal sequence
        sequence += 1
        print(json.dumps(dict(request=args.request, seq=sequence, stage=stage, completed=completed, total=total, unit="bytes")), flush=True)
    value = lookup(args.source, args.query, args.output.parent, event)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > 4*1024**2: raise ValueError("Boundary preview exceeds 4 MiB")
    event("write", 0, len(raw))
    with args.output.open("xb") as output: output.write(raw)
    event("write", len(raw), len(raw))
    sequence += 1
    print(json.dumps(dict(request=args.request, seq=sequence, stage="complete", completed=len(raw), total=len(raw), unit="bytes", sha256=hashlib.sha256(raw).hexdigest())), flush=True)


if __name__ == "__main__":
    try: main()
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        raise SystemExit(str(exc))
