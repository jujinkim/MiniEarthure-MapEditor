"""Disk-indexed, three-pass selected-area PBF input. Public MIT adapter.

The original is read only. A private captured PBF and a quota-limited disposable
SQLite index belong to the import worker; no libosmium location/area cache.
PBF framing makes progress actual bytes, not an estimate of parser position.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import struct
import zlib
from collections import deque

from import_layer import MAX_INPUT, MAX_POINTS
from osm_area import bounds
from osm_extract import dependency, category, build_features, MAX_ENTITIES, MAX_REFS, MAX_FEATURES

MAX_SOURCE = 2 * 1024**3
MAX_INDEX = 2 * 1024**3
MAX_SCAN_ENTITIES = 20_000_000
MAX_SCAN_REFS = 80_000_000
MAX_ENTITY_REFS = 20_000
MAX_BLOB = 32 * 1024**2
MAX_HEADER = 64 * 1024
COPY_BLOCK = 1024**2
PROFILE = "pbf-area-stream-v1"
OWNED_FILES = ("source.pbf.part", "source.pbf", "source-index.sqlite")


def _varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _fields(raw):
    """Only the scalar/bytes wire types used by PBF Blob/BlobHeader envelopes."""
    offset, values = 0, {}
    def integer():
        nonlocal offset
        result = 0
        for shift in range(0, 70, 7):
            if offset >= len(raw): raise ValueError("truncated PBF envelope")
            byte = raw[offset]
            offset += 1
            result |= (byte & 127) << shift
            if not byte & 128: return result
        raise ValueError("oversized PBF envelope integer")
    while offset < len(raw):
        key = integer()
        number, wire = key >> 3, key & 7
        if number == 0 or number in values: raise ValueError("duplicate/invalid PBF envelope field")
        if wire == 0:
            value = integer()
        elif wire == 2:
            length = integer()
            if length > len(raw)-offset: raise ValueError("truncated PBF envelope bytes")
            value = raw[offset:offset+length]
            offset += length
        else:
            raise ValueError("unsupported PBF envelope wire type")
        values[number] = value
    return values


def _frame(kind, payload):
    blob = b"\x0a" + _varint(len(payload)) + payload
    header = b"\x0a" + _varint(len(kind)) + kind + b"\x18" + _varint(len(blob))
    return struct.pack(">I", len(header)) + header + blob


def _blocks(path, stage, event, size):
    event(stage, 0, size)
    completed, last_report = 0, 0
    with path.open("rb") as stream:
        while completed < size:
            prefix = stream.read(4)
            if len(prefix) != 4: raise ValueError("truncated PBF frame")
            length = struct.unpack(">I", prefix)[0]
            if not 0 < length <= MAX_HEADER: raise ValueError("PBF header budget exceeded")
            header_raw = stream.read(length)
            if len(header_raw) != length: raise ValueError("truncated PBF header")
            header = _fields(header_raw)
            kind, amount = header.get(1), header.get(3)
            if kind not in (b"OSMHeader", b"OSMData") or type(amount) is not int or not 0 < amount <= MAX_BLOB:
                raise ValueError("unsupported PBF block or blob budget exceeded")
            raw = stream.read(amount)
            if len(raw) != amount: raise ValueError("truncated PBF blob")
            blob = _fields(raw)
            if set(blob) == {1} and isinstance(blob[1], bytes):
                payload = blob[1]
            elif set(blob) == {2, 3} and type(blob[2]) is int and isinstance(blob[3], bytes) and 0 < blob[2] <= MAX_BLOB:
                inflater = zlib.decompressobj()
                payload = inflater.decompress(blob[3], MAX_BLOB+1)
                if len(payload) != blob[2] or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
                    raise ValueError("PBF decompressed size/budget mismatch")
            else:
                raise ValueError("PBF stream requires raw or zlib blobs with bounded raw_size")
            if not 0 < len(payload) <= MAX_BLOB: raise ValueError("PBF expanded blob budget exceeded")
            completed += 4 + length + amount
            yield kind, payload
            if completed-last_report >= 8*COPY_BLOCK or completed == size:
                event(stage, completed, size)
                last_report = completed
        if completed != size or stream.read(1): raise ValueError("PBF snapshot size changed")


def _scan(path, stage, event, size, osmium, entity_bits, callback):
    header, blocks = None, 0
    # One worker/one queued task: input size does not create a growing read queue.
    pool = osmium.io.ThreadPool(1, 1)
    try:
        for kind, payload in _blocks(path, stage, event, size):
            if kind == b"OSMHeader":
                if header is not None or blocks: raise ValueError("duplicate/misplaced PBF header")
                header = _frame(kind, payload)
                processor = osmium.FileProcessor(osmium.io.FileBuffer(header, "pbf"), thread_pool=pool)
                if processor.header.has_multiple_object_versions:
                    raise ValueError("OSM history input is unsupported")
            else:
                if header is None: raise ValueError("PBF data before header")
                blocks += 1
                processor = osmium.FileProcessor(osmium.io.FileBuffer(header + _frame(kind, payload), "pbf"), entities=entity_bits, thread_pool=pool)
                iterator = iter(processor)
                try:
                    for entity in iterator: callback(entity)
                finally:
                    iterator.close()
    finally:
        del pool
    if header is None or not blocks: raise ValueError("empty PBF snapshot")


def _signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _capture(source, directory, event):
    with source.open("rb") as reader:
        before = os.fstat(reader.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE:
            raise ValueError("PBF stream requires a regular nonempty source up to 2 GiB")
        size = before.st_size
        if shutil.disk_usage(directory).free < size + MAX_INDEX + 64*COPY_BLOCK:
            raise ValueError("PBF stream needs source bytes + 2 GiB index + 64 MiB free workspace")
        digest, completed, last_report = hashlib.sha256(), 0, 0
        event("read", 0, size)
        with (directory / "source.pbf.part").open("xb") as writer:
            while completed < size:
                raw = reader.read(min(COPY_BLOCK, size-completed))
                if not raw: raise ValueError("source truncated during capture; retry")
                writer.write(raw)
                digest.update(raw)
                completed += len(raw)
                if completed-last_report >= 8*COPY_BLOCK or completed == size:
                    event("read", completed, size)
                    last_report = completed
            if reader.read(1) or _signature(before) != _signature(os.fstat(reader.fileno())) or _signature(before) != _signature(source.stat()):
                raise ValueError("source changed during capture; retry")
        # Hard-link publishes without overwriting an existing owned filename.
        os.link(directory / "source.pbf.part", directory / "source.pbf")
        (directory / "source.pbf.part").unlink()
    return size, digest.hexdigest()


def _potential(tags):
    return bool(tags.get("highway") or tags.get("building", "no") != "no" or "building:part" in tags or tags.get("landuse") in ("forest", "orchard") or tags.get("natural") == "wood")


def _structure_closure(db, event, size):
    """Visit every incident highway at structural source nodes, transit structures.

    Ground roads are included whole but are never traversal edges. A separate
    operation cap bounds dense incidence, in addition to payload/index quotas.
    """
    if db.execute("SELECT count(*) FROM chosen").fetchone()[0] > MAX_ENTITIES:
        raise ValueError("OSM selected entity budget exceeded")
    pending, admitted = deque(), set()
    for (way,) in db.execute("SELECT s.id FROM structural_ways s JOIN chosen c ON c.id=s.id ORDER BY s.id"):
        if len(admitted) >= MAX_FEATURES: raise ValueError("OSM selected approach/feature budget exceeded")
        admitted.add(way)
        pending.append(way)
    nodes, payload_bytes, references, visits, structures = set(), 0, 0, 0, 0
    event("index_relations", size, size)
    while pending:
        way = pending.popleft()
        raw = db.execute("SELECT data FROM ways WHERE id=?", (way,)).fetchone()[0]
        payload_bytes += len(raw.encode("utf-8"))
        if payload_bytes > MAX_INPUT: raise ValueError("OSM structure closure payload budget exceeded")
        refs, _ = json.loads(raw)
        references += len(refs)
        if references > MAX_REFS: raise ValueError("OSM structure closure reference budget exceeded")
        structures += 1
        for ref in refs:
            if ref in nodes: continue
            nodes.add(ref)
            for (peer,) in db.execute("SELECT way FROM road_nodes WHERE node=? ORDER BY way", (ref,)):
                visits += 1
                if visits > MAX_REFS: raise ValueError("OSM structure closure incidence budget exceeded")
                if visits % 100 == 0: event("index_relations", size, size)
                if peer in admitted: continue
                if len(admitted) >= MAX_FEATURES: raise ValueError("OSM selected approach/feature budget exceeded")
                admitted.add(peer)
                db.execute("INSERT OR IGNORE INTO chosen VALUES(?)", (peer,))
                if db.execute("SELECT 1 FROM structural_ways WHERE id=?", (peer,)).fetchone():
                    pending.append(peer)
        event("index_relations", size, size)
    if db.execute("SELECT count(*) FROM chosen").fetchone()[0] > MAX_ENTITIES:
        raise ValueError("OSM selected entity budget exceeded")
    return dict(profile="structural-incidence-v1", ways=len(admitted), structures=structures, nodes=len(nodes), visits=visits)


def extract(source, selected, directory, event=lambda *a: None):
    selected = bounds(selected)
    source, directory = Path(source), Path(directory)
    # Refuse before claiming ownership. Cleanup may only remove files created here.
    if any((directory / name).exists() for name in OWNED_FILES):
        raise ValueError("PBF stream workspace already contains owned filenames")
    db = None
    try:
        size, digest = _capture(source, directory, event)
        path = directory / "source.pbf"
        osmium = dependency()
        db = sqlite3.connect(directory / "source-index.sqlite")
        db.executescript(f"""
            PRAGMA page_size=4096;
            PRAGMA max_page_count={MAX_INDEX//4096};
            PRAGMA cache_size=-8192;
            PRAGMA mmap_size=0;
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE nodes(id INTEGER PRIMARY KEY, x REAL, y REAL, tags TEXT);
            CREATE TABLE ways(id INTEGER PRIMARY KEY, west REAL, south REAL, east REAL, north REAL, data TEXT, feature INTEGER);
            CREATE TABLE relations(id INTEGER PRIMARY KEY, data TEXT, candidate INTEGER);
            CREATE TABLE owners(way INTEGER, relation INTEGER, blocked INTEGER, PRIMARY KEY(way,relation));
            CREATE TABLE chosen(id INTEGER PRIMARY KEY);
            CREATE TABLE road_nodes(node INTEGER, way INTEGER, PRIMARY KEY(node,way)) WITHOUT ROWID;
            CREATE TABLE structural_ways(id INTEGER PRIMARY KEY);

        """)
        totals = dict(nodes=0, ways=0, relations=0, references=0)
        def scalar(entity):
            key = {"n":"nodes", "w":"ways", "r":"relations"}[entity.type_str()]
            totals[key] += 1
            if sum(totals[k] for k in ("nodes","ways","relations")) > MAX_SCAN_ENTITIES or entity.id <= 0 or not entity.visible:
                raise ValueError("OSM scan entity budget/deleted or invalid ID")
            if len(entity.tags) > 128: raise ValueError("OSM tag budget exceeded")
            tags = {}
            for tag in entity.tags:
                if tag.k in tags or len(tag.k) > 512 or len(tag.v) > 512: raise ValueError("OSM duplicate/oversized tag")
                tags[tag.k] = tag.v
            return tags
        def references(count):
            totals["references"] += count
            if count > MAX_ENTITY_REFS or totals["references"] > MAX_SCAN_REFS:
                raise ValueError("OSM scan reference budget exceeded")
        def intersects(box):
            return box is not None and box[0] <= selected[2] and box[2] >= selected[0] and box[1] <= selected[3] and box[3] >= selected[1]
        def envelope(box, x, y, east=None, north=None):
            other = [x,y,x if east is None else east,y if north is None else north]
            return other if box is None else [min(box[0],other[0]),min(box[1],other[1]),max(box[2],other[2]),max(box[3],other[3])]
        def node(entity):
            tags = scalar(entity)
            if not entity.location.valid() or not -180 <= entity.lon <= 180 or not -90 <= entity.lat <= 90: raise ValueError("OSM invalid node location")
            db.execute("INSERT INTO nodes VALUES(?,?,?,?)", (entity.id,entity.lon,entity.lat,json.dumps(tags)))
        def way(entity):
            tags = scalar(entity)
            references(len(entity.nodes))
            refs, box = [], None
            if _potential(tags) and not len(entity.nodes): raise ValueError("OSM feature way has no referenced geometry")
            for n in entity.nodes:
                row = db.execute("SELECT x,y FROM nodes WHERE id=?", (n.ref,)).fetchone()
                if row is None: raise ValueError("OSM way missing referenced node; use a complete snapshot")
                box = envelope(box,*row)
                refs.append(n.ref)
            db.execute("INSERT INTO ways VALUES(?,?,?,?,?,?,?)", (entity.id,*(box or [None]*4),json.dumps([refs,tags]),int(_potential(tags))))
            if "highway" in tags:
                # Only source graph evidence, never an inferred positional join.
                # Disk/index/deadline/reference caps also cover this adjacency.
                db.executemany("INSERT OR IGNORE INTO road_nodes VALUES(?,?)", ((ref,entity.id) for ref in refs))
                if any(tags.get(k, "no") not in ("no", "0") for k in ("bridge", "tunnel")):
                    db.execute("INSERT INTO structural_ways VALUES(?)", (entity.id,))
            if _potential(tags) and intersects(box):
                db.execute("INSERT INTO chosen VALUES(?)", (entity.id,))
        def relation(entity):
            tags = scalar(entity)
            references(len(entity.members))
            members, box = [], None
            area = tags.get("type") in ("multipolygon", "boundary")
            potential = _potential(tags)
            if potential and not len(entity.members): raise ValueError("OSM feature relation has no referenced geometry")
            for m in entity.members:
                if len(m.role) > 512 or m.ref <= 0: raise ValueError("OSM invalid relation reference/role")
                members.append((m.type,m.ref,m.role))
                if m.type == "r":
                    if area or potential: raise ValueError("OSM nested area/feature relation is unsupported by streaming selection")
                    continue  # Non-area/non-feature relation semantics are disclosed omissions.
                if m.type == "w":
                    row = db.execute("SELECT west,south,east,north FROM ways WHERE id=?", (m.ref,)).fetchone()
                elif m.type == "n":
                    xy = db.execute("SELECT x,y FROM nodes WHERE id=?", (m.ref,)).fetchone()
                    row = None if xy is None else (*xy,*xy)
                else: raise ValueError("OSM unsupported relation member type")
                if row is None: raise ValueError("OSM relation missing member; use a complete snapshot")
                if row[0] is not None: box = envelope(box,*row)
            candidate = potential and intersects(box)
            if candidate and (tags.get("type") != "multipolygon" or category(tags) == "road"):
                raise ValueError("OSM selected relation requires supported multipolygon semantics")
            db.execute("INSERT INTO relations VALUES(?,?,?)", (entity.id,json.dumps([members,tags]) if candidate else None,int(candidate)))
            for kind,ref,role in members:
                if area and kind == "w":
                    # Duplicate membership must not disappear in INSERT OR IGNORE.
                    db.execute("INSERT INTO owners VALUES(?,?,?)", (ref,entity.id,int(not candidate)))
                if candidate and kind == "w": db.execute("INSERT OR IGNORE INTO chosen VALUES(?)", (ref,))
        for stage, bits, callback in [("index_nodes",osmium.osm.NODE,node),("index_ways",osmium.osm.WAY,way),("index_relations",osmium.osm.RELATION,relation)]:
            _scan(path, stage, event, size, osmium, bits, callback)
            db.commit()
        closure = _structure_closure(db, event, size)
        event("index_relations", size, size)
        nodes, node_tags, all_ways, ways, relations, blocked = {}, {}, {}, [], [], set()
        counts = dict(nodes=0,ways=0,relations=0,ignored_ways=0,ignored_relations=0,tagged_nodes=0,assembled_relations=0,outer_rings=0,inner_rings=0,member_ways=0)
        selection_bytes, selected_refs = 0, 0
        total = db.execute("SELECT count(*) FROM chosen").fetchone()[0] + db.execute("SELECT count(*) FROM relations WHERE candidate=1").fetchone()[0]
        if total > MAX_ENTITIES: raise ValueError("OSM selected entity budget exceeded")
        event("select", 0, total, "entities")
        def admit(raw, refs=0):
            nonlocal selection_bytes, selected_refs
            selection_bytes += len(raw.encode("utf-8"))
            selected_refs += refs
            if selection_bytes > MAX_INPUT or selected_refs > MAX_REFS or len(nodes)+len(all_ways)+len(relations) > MAX_ENTITIES:
                raise ValueError("OSM selected payload/reference/entity budget exceeded")
        completed = 0
        # Iterate the integer primary key, then lookup one payload. Avoid a SQL
        # join/sorter that could materialize all payloads before byte admission.
        for (identity,) in db.execute("SELECT id FROM chosen ORDER BY id"):
            raw = db.execute("SELECT data FROM ways WHERE id=?", (identity,)).fetchone()[0]
            admit(raw)
            refs,tags = json.loads(raw)
            admit("",len(refs))
            all_ways[identity] = (refs,tags)
            kind = category(tags)
            if kind: ways.append((identity,kind,refs,tags))
            else: counts["ignored_ways"] += 1
            if len(ways) > MAX_FEATURES: raise ValueError("OSM selected feature budget exceeded")
            for ref in refs:
                if ref in nodes: continue
                if len(nodes) >= MAX_POINTS: raise ValueError("OSM selected node budget exceeded")
                x,y,raw_tags = db.execute("SELECT x,y,tags FROM nodes WHERE id=?", (ref,)).fetchone()
                tags_at_node = json.loads(raw_tags)
                admit(json.dumps([ref,x,y,tags_at_node]))
                nodes[ref] = [x,y]
                if tags_at_node: node_tags[ref] = tags_at_node
            if db.execute("SELECT 1 FROM owners WHERE way=? AND blocked=1 LIMIT 1", (identity,)).fetchone(): blocked.add(identity)
            completed += 1
            if completed % 100 == 0: event("select",completed,total,"entities")
        for identity,raw in db.execute("SELECT id,data FROM relations WHERE candidate=1 ORDER BY id"):
            admit(raw)
            members,tags = json.loads(raw)
            admit("",len(members))
            relations.append((identity,category(tags),members,tags))
            if len(ways)+len(relations) > MAX_FEATURES: raise ValueError("OSM selected feature budget exceeded")
            completed += 1
            if completed % 100 == 0: event("select",completed,total,"entities")
        event("select",completed,total,"entities")
        # Count the completed selection too (the last insertion follows admit()).
        admit("")
        counts.update(nodes=len(nodes),ways=len(all_ways),relations=len(relations),tagged_nodes=len(node_tags))
        event("parse",0,selection_bytes)
        value, counts = build_features(nodes,node_tags,ways,all_ways,relations,blocked,counts)
        meta = dict(profile=PROFILE,passes=3,source_bytes=size,source_sha256=digest,
                    scan=totals,structure_closure=closure,selected=dict(nodes=len(nodes),ways=len(all_ways),relations=len(relations),references=selected_refs,bytes=selection_bytes))
        return value, counts, meta
    except (sqlite3.Error, RuntimeError, zlib.error) as exc:
        raise ValueError("invalid/budget-exceeding PBF stream: " + str(exc)[:300]) from exc
    finally:
        if db is not None: db.close()
        for name in OWNED_FILES:
            (directory / name).unlink(missing_ok=True)
