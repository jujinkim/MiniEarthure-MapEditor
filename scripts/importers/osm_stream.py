"""Disk-indexed, three-pass selected-area PBF input. Public MIT adapter.

The original is read only. A private captured PBF and a quota-limited disposable
coordinate arrays and SQLite metadata belong to the import worker; no libosmium
location/area cache. Their combined disk allocation stays within MAX_INDEX.
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
from itertools import chain

from import_layer import MAX_INPUT, MAX_POINTS, BudgetExceeded, soft_limit
from osm_review import Review
from osm_disk_nodes import DiskNodes, SharedRoadNodes, MissingNode, FILES as NODE_FILES, MAX_LOOKUP
from osm_area import bounds
from osm_extract import dependency, category, build_features, city_area, CITY_BARRIERS, MAX_ENTITIES, MAX_REFS, MAX_FEATURES, MAX_TAGS, TAG_CEILING, TAG_TEXT

# Source-work budgets warn (soft_limit) and the import continues. The CEILING
# values and the disk-sized index quota are memory/disk guards and still refuse.
MAX_SOURCE = 2 * 1024**3  # Warn above.
SOURCE_CEILING = 64 * 1024**3  # u64 block pointers, uint32 node positions.
MAX_INDEX = 2 * 1024**3  # Minimum index quota; warn when the index grows beyond it.
INDEX_PER_SOURCE = 3  # The quota grows with the source, within free disk.
MAX_SCAN_ENTITIES = 100_000_000  # CPU time only: warn.
MAX_SCAN_REFS = 80_000_000  # CPU time only: warn.
MAX_ENTITY_REFS = 20_000  # Warn above.
ENTITY_REFS_CEILING = 1_000_000  # Memory guard per entity.
MAX_BLOB = 32 * 1024**2
MAX_HEADER = 64 * 1024
COPY_BLOCK = 1024**2
PROFILE = "pbf-area-stream-v1"
OWNED_FILES = ("source.pbf.part", "source.pbf", "source-index.sqlite", *NODE_FILES)
WAY_BATCH_ROWS = 128
WAY_BATCH_BYTES = 4 * 1024**2  # Batch flush size; a single way warns above it.
WAY_PAYLOAD_CEILING = 64 * 1024**2  # Memory guard for one way payload.

# Only the explicit city-generalization path can stage more original geometry.
# Final ImportLayer/Undo/native limits are unchanged. These are source-work caps,
# never output admission limits or permission to discard source objects.
CITY_INPUT = 256 * 1024**2
CITY_POINTS = 2_000_000
CITY_REFS = 4_000_000
CITY_ENTITIES = 2_000_000
CITY_FEATURES = 250_000


def _payload(raw):
    """Private scratch compression, bounded to the existing per-way allowance."""
    if not isinstance(raw, bytes): return raw
    inflater = zlib.decompressobj()
    decoded = inflater.decompress(raw, WAY_PAYLOAD_CEILING + 1)
    if len(decoded) > WAY_PAYLOAD_CEILING or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise BudgetExceeded("OSM index payload ceiling exceeded")
    return decoded.decode("utf-8")


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


def _uvarint(raw, offset, end):
    value = shift = 0
    while True:
        if offset >= end or shift > 63: raise ValueError("truncated/oversized PBF integer")
        byte = raw[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128: return value, offset
        shift += 7


def _message(raw, offset, end):
    """(number, wire, value) of one protobuf message; bytes values are (start, stop)."""
    while offset < end:
        # One-byte keys and values are the common case in every PBF block.
        key = raw[offset]
        if key < 128: offset += 1
        else: key, offset = _uvarint(raw, offset, end)
        wire = key & 7
        if wire == 0 or wire == 2:
            if offset < end and raw[offset] < 128:
                value = raw[offset]
                offset += 1
            else:
                value, offset = _uvarint(raw, offset, end)
            if wire == 0:
                yield key >> 3, 0, value
                continue
            if value > end-offset: raise ValueError("truncated PBF bytes")
            yield key >> 3, 2, (offset, offset+value)
            offset += value
        elif wire == 1 or wire == 5:
            offset += 8 if wire == 1 else 4
            if offset > end: raise ValueError("truncated PBF field")
        else:
            raise ValueError("unsupported PBF wire type")


MAX_DECODED_BLOCK = 2 * 1024**2


class _Unsupported(Exception):
    """Block left to libosmium's per-entity path (which accepts or rejects it)."""


def _uvarints(np, data):
    """Packed unsigned varints, vectorized; temporaries scale with the value count."""
    ends = np.flatnonzero(data < 128)
    if not ends.size or ends[-1] != data.size-1: raise _Unsupported
    starts = np.empty_like(ends)
    starts[0] = 0
    starts[1:] = ends[:-1]+1
    lengths = ends-starts+1
    longest = int(lengths.max())
    # A tenth byte may only carry bit 63; anything else is left to libosmium.
    if longest > 10 or (longest == 10 and np.any(data[starts[lengths == 10]+9] > 1)): raise _Unsupported
    values = (data[starts] & 127).astype(np.uint64)
    for shift in range(1, longest):
        more = np.flatnonzero(lengths > shift)
        values[more] |= (data[starts[more]+shift] & 127).astype(np.uint64) << np.uint64(7*shift)
    return values, ends


def _sint64(np, data, offsets=None):
    """Zigzag packed varints. With byte offsets of packed runs, also each run's count."""
    if not data.size: return np.empty(0, np.int64), np.zeros(0 if offsets is None else len(offsets)-1, np.int64)
    values, ends = _uvarints(np, data)
    values = (values >> np.uint64(1)).astype(np.int64) ^ -(values & np.uint64(1)).astype(np.int64)
    if offsets is None: return values, None
    if np.any(data[offsets[1:]-1] >= 128): raise _Unsupported
    return values, np.diff(np.searchsorted(ends, offsets))


def _deltas(np, values, counts=None):
    """Delta-coded runs in wrapping int64 arithmetic, as libosmium sums them."""
    total = np.cumsum(values)
    if counts is None: return total
    first = np.concatenate(([0], np.cumsum(counts)[:-1]))
    return total-np.repeat(np.concatenate(([0], total))[first], counts)


def _signed(value, bits):
    value &= (1 << bits)-1
    return value-(1 << bits) if value >> (bits-1) else value


def _decode_block(np, raw, *, nodes=False, ways=False):
    """Dense node IDs/locations and way IDs/refs of one PrimitiveBlock, as libosmium decodes them.

    Returns None for anything but the canonical encoding (plain nodes, repeated or
    mismatched fields, oversized blocks...): those blocks stay on the per-entity path.
    """
    if len(raw) > MAX_DECODED_BLOCK: return None
    try:
        with np.errstate(over="ignore"):
            return _decode_canonical(np, raw, nodes, ways)
    except (_Unsupported, ValueError, IndexError):
        return None


def _decode_canonical(np, raw, nodes, ways):
    granularity, lat_offset, lon_offset, groups = 100, 0, 0, []
    for number, wire, value in _message(raw, 0, len(raw)):
        if number == 2 and wire == 2: groups.append(value)
        elif number == 17 and wire == 0: granularity = _signed(value, 32)
        elif number == 19 and wire == 0: lat_offset = _signed(value, 64)
        elif number == 20 and wire == 0: lon_offset = _signed(value, 64)
    data = np.frombuffer(raw, dtype=np.uint8)
    dense, way_ids, way_refs = [], [], []
    for start, stop in groups:
        for number, wire, value in _message(raw, start, stop):
            if number == 1: raise _Unsupported
            if number == 2 and nodes and wire == 2:
                fields = {}
                for inner, kind, span in _message(raw, *value):
                    if inner in (1, 5, 8, 9):
                        if inner in fields or kind != 2: raise _Unsupported
                        fields[inner] = span
                ids, lat, lon = (_deltas(np, _sint64(np, data[slice(*fields[k])] if k in fields else data[:0])[0]) for k in (1, 8, 9))
                if not len(ids) == len(lat) == len(lon): raise _Unsupported
                visible = None
                if 5 in fields:
                    for inner, kind, span in _message(raw, *fields[5]):
                        if inner == 6:
                            if visible is not None or kind != 2: raise _Unsupported
                            visible = _uvarints(np, data[slice(*span)])[0] if span[1] > span[0] else np.zeros(0, np.uint64)
                    # Only canonical 0/1 bools; libosmium reads wider values as int32.
                    if visible is not None and (len(visible) != len(ids) or np.any(visible > 1)): raise _Unsupported
                    if visible is not None: visible = visible == 1
                # libosmium: int32_t((c * granularity + offset) / 100) in int64, truncating toward zero.
                xy = np.empty((len(ids), 2), np.int32)
                for column, coordinate, offset in ((0, lon, lon_offset), (1, lat, lat_offset)):
                    scaled = coordinate*np.int64(granularity)+np.int64(offset)
                    quotient, remainder = np.divmod(scaled, np.int64(100))
                    xy[:, column] = (quotient+((remainder != 0) & (scaled < 0))).astype(np.int32)
                dense.append((ids, xy, visible))
            elif number == 3 and ways and wire == 2:
                # Inline field walk: millions of ways, only the ID and refs are needed.
                identity, refs, (offset, stop) = None, None, value
                while offset < stop:
                    key = raw[offset]
                    if key < 128: offset += 1
                    else: key, offset = _uvarint(raw, offset, stop)
                    kind = key & 7
                    if kind == 0 or kind == 2:
                        if offset < stop and raw[offset] < 128:
                            span = raw[offset]
                            offset += 1
                        else:
                            span, offset = _uvarint(raw, offset, stop)
                        if kind == 2:
                            if span > stop-offset: raise _Unsupported
                            offset += span
                    elif kind == 1 or kind == 5:
                        offset += 8 if kind == 1 else 4
                        if offset > stop: raise _Unsupported
                    else:
                        raise _Unsupported
                    if key == 0x08 and identity is None: identity = _signed(span, 64)
                    elif key == 0x42 and refs is None: refs = (offset-span, offset)
                    elif key >> 3 in (1, 8): raise _Unsupported
                if identity is None: raise _Unsupported
                way_ids.append(identity)
                way_refs.append(refs or (0, 0))
    if not way_ids: return dense, None
    spans = np.asarray(way_refs, dtype=np.int64)
    lengths = spans[:, 1]-spans[:, 0]
    offsets = np.concatenate(([0], np.cumsum(lengths)))
    packed = data[np.repeat(spans[:, 0]-offsets[:-1], lengths)+np.arange(offsets[-1])]
    values, counts = _sint64(np, packed, offsets)
    return dense, (way_ids, counts.tolist(), _deltas(np, values, counts))


def _frame(kind, payload):
    blob = b"\x0a" + _varint(len(payload)) + payload
    header = b"\x0a" + _varint(len(kind)) + kind + b"\x18" + _varint(len(blob))
    return struct.pack(">I", len(header)) + header + blob


def _read_block(stream):
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
    return kind, payload


def _blocks(path, stage, event, size, *, offsets=False):
    event(stage, 0, size)
    completed, last_report = 0, 0
    with path.open("rb") as stream:
        while completed < size:
            offset = stream.tell()
            kind, payload = _read_block(stream)
            completed = stream.tell()
            yield (kind, payload, offset) if offsets else (kind, payload)
            if completed-last_report >= 8*COPY_BLOCK or completed == size:
                event(stage, completed, size)
                last_report = completed
        if completed != size or stream.read(1): raise ValueError("PBF snapshot size changed")


def _scan(path, stage, event, size, osmium, entity_bits, callback, entity_filter=None, block_callback=None):
    header, blocks = None, 0
    # One worker/one queued task: input size does not create a growing read queue.
    pool = osmium.io.ThreadPool(1, 1)
    try:
        for kind, payload, offset in _blocks(path, stage, event, size, offsets=True):
            if kind == b"OSMHeader":
                if header is not None or blocks: raise ValueError("duplicate/misplaced PBF header")
                header = _frame(kind, payload)
                processor = osmium.FileProcessor(osmium.io.FileBuffer(header, "pbf"), thread_pool=pool)
                if processor.header.has_multiple_object_versions:
                    raise ValueError("OSM history input is unsupported")
            else:
                if header is None: raise ValueError("PBF data before header")
                blocks += 1
                # A block callback may narrow this block's Python entities (e.g. to tagged nodes).
                block_filter = block_callback(offset, payload) if block_callback is not None else None
                processor = osmium.FileProcessor(osmium.io.FileBuffer(header + _frame(kind, payload), "pbf"), entities=entity_bits, thread_pool=pool)
                if block_filter is not None or entity_filter is not None: processor.with_filter(block_filter or entity_filter)
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
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= SOURCE_CEILING:
            raise ValueError("PBF stream requires a regular nonempty source up to 64 GiB")
        size = before.st_size
        if size > MAX_SOURCE:
            soft_limit("stream_source_bytes", size, MAX_SOURCE, "PBF source exceeds 2 GiB; indexing takes longer and needs more disk")
        free = shutil.disk_usage(directory).free
        if free < size + MAX_INDEX + 64*COPY_BLOCK:
            # A real out-of-space error during capture or indexing still fails.
            soft_limit("stream_free_disk", size + MAX_INDEX + 64*COPY_BLOCK, free, "Little free workspace disk for the PBF copy and index; the import stops if the disk fills")
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


def _potential(tags, city=False, relation=False):
    # Index envelopes without interpreting unsupported features outside the
    # selection. Full semantic validation still follows bounded admission.
    # The city profile also selects green/parking/site areas and barrier ways.
    if bool(tags.get("highway") or tags.get("building", "no") != "no" or "building:part" in tags or tags.get("landuse") or tags.get("natural") in ("wood","water","wetland","bare_rock","scrub","grassland") or tags.get("leisure") in ("park","nature_reserve") or tags.get("boundary")=="protected_area"):
        return True
    if not city or relation and tags.get("type") != "multipolygon": return False
    return city_area(tags) or not relation and tags.get("barrier") in CITY_BARRIERS


def _structure_closure(db, event, size, read_way=None, limits=None):
    """Visit all incident highways at structural/loop nodes; transit both kinds.

    Open ground approaches are included whole but are not traversal edges. Work
    above the budgets (city-sized in city mode) records limit warnings.
    """
    input_limit, ref_limit, entity_limit, feature_limit = limits or (MAX_INPUT, MAX_REFS, MAX_ENTITIES, MAX_FEATURES)
    def entities():
        chosen = db.execute("SELECT count(*) FROM chosen").fetchone()[0]
        if chosen > entity_limit:
            soft_limit("stream_selected_entities", chosen, entity_limit, "OSM selected entity budget exceeded")
    def feature(count):
        if count > feature_limit:
            soft_limit("stream_closure_features", count, feature_limit, "OSM selected approach/feature budget exceeded")
    entities()
    pending, admitted = deque(), set()
    # Probe only admitted IDs. A whole-source UNION could build an unbudgeted
    # temporary set containing millions of unrelated ways before first yield.
    for (way,) in db.execute("SELECT c.id FROM chosen c WHERE EXISTS (SELECT 1 FROM structural_ways s WHERE s.id=c.id) OR EXISTS (SELECT 1 FROM loop_ways l WHERE l.id=c.id) ORDER BY c.id"):
        feature(len(admitted) + 1)
        admitted.add(way)
        pending.append(way)
    nodes, payload_bytes, references, visits, structures, loops = set(), 0, 0, 0, 0, 0
    event("index_relations", size, size)
    while pending:
        way = pending.popleft()
        raw = read_way(way) if read_way is not None else _payload(db.execute("SELECT data FROM ways WHERE id=?", (way,)).fetchone()[0])
        payload_bytes += len(raw.encode("utf-8"))
        if payload_bytes > input_limit: soft_limit("stream_closure_bytes", payload_bytes, input_limit, "OSM structure closure payload budget exceeded")
        refs, _ = json.loads(raw)
        references += len(refs)
        if references > ref_limit: soft_limit("stream_closure_references", references, ref_limit, "OSM structure closure reference budget exceeded")
        structures += bool(db.execute("SELECT 1 FROM structural_ways WHERE id=?", (way,)).fetchone())
        loops += bool(db.execute("SELECT 1 FROM loop_ways WHERE id=?", (way,)).fetchone())
        for ref in refs:
            if ref in nodes: continue
            nodes.add(ref)
            # A node without rows touches only this highway (shared-node index).
            rows = db.execute("SELECT way FROM road_nodes WHERE node=? ORDER BY way", (ref,))
            first = rows.fetchone()
            for (peer,) in (chain((first,), rows) if first is not None else ((way,),)):
                visits += 1
                if visits > ref_limit: soft_limit("stream_closure_visits", visits, ref_limit, "OSM structure closure incidence budget exceeded")
                if visits % 100 == 0: event("index_relations", size, size)
                if peer in admitted: continue
                feature(len(admitted) + 1)
                admitted.add(peer)
                db.execute("INSERT OR IGNORE INTO chosen VALUES(?)", (peer,))
                if db.execute("SELECT 1 FROM structural_ways WHERE id=? UNION ALL SELECT 1 FROM loop_ways WHERE id=?", (peer,peer)).fetchone():
                    pending.append(peer)
        event("index_relations", size, size)
    entities()
    return dict(profile="loop-structural-incidence-v1" if loops else "structural-incidence-v1",
                ways=len(admitted), structures=structures, nodes=len(nodes), visits=visits, **(dict(loops=loops) if loops else {}))


def extract(source, selected, directory, event=lambda *a: None, supplement=None, review=None, *, city=False, areas=None):
    """`areas` (relation IDs) resolve their exact boundary union from the same captured
    bytes; it is returned as `meta["_region"]` for the crop and never stored."""
    review = review or Review()
    selected = bounds(selected)
    source, directory = Path(source), Path(directory)
    input_limit, point_limit, ref_limit, entity_limit, feature_limit = (
        (CITY_INPUT, CITY_POINTS, CITY_REFS, CITY_ENTITIES, CITY_FEATURES) if city else
        (MAX_INPUT, MAX_POINTS, MAX_REFS, MAX_ENTITIES, MAX_FEATURES))
    # Refuse before claiming ownership. Cleanup may only remove files created here.
    if any((directory / name).exists() for name in OWNED_FILES):
        raise ValueError("PBF stream workspace already contains owned filenames")
    db, locations, shared, lazy_pool = None, None, None, None
    try:
        size, digest = _capture(source, directory, event)
        path = directory / "source.pbf"
        osmium = dependency()
        region = None
        if areas:
            from pbf_places import region as boundary_region
            region, area_meta = boundary_region(path, areas, osmium, event)
            w, s_, e, n = region.bounds
            if w < selected[0] or s_ < selected[1] or e > selected[2] or n > selected[3]:
                raise ValueError("Selected areas extend beyond the crop rectangle; use their combined extent")
        # The disk quota grows with the source, within the free workspace disk.
        quota = max(MAX_INDEX, min(INDEX_PER_SOURCE * size, shutil.disk_usage(directory).free - 64*COPY_BLOCK))
        db = sqlite3.connect(directory / "source-index.sqlite")
        db.executescript(f"""
            PRAGMA page_size=4096;
            PRAGMA max_page_count={quota//4096};
            PRAGMA cache_size=-8192;
            PRAGMA mmap_size=0;
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE nodes(id INTEGER PRIMARY KEY, x INTEGER, y INTEGER);
            CREATE TABLE node_tags(id INTEGER PRIMARY KEY, tags TEXT);
            CREATE TABLE ways(id INTEGER PRIMARY KEY, west REAL, south REAL, east REAL, north REAL, data TEXT, feature INTEGER);
            CREATE TABLE relations(id INTEGER PRIMARY KEY, data TEXT, candidate INTEGER);
            CREATE TABLE owners(way INTEGER, relation INTEGER, blocked INTEGER, PRIMARY KEY(way,relation));
            CREATE TABLE chosen(id INTEGER PRIMARY KEY);
            CREATE TABLE road_nodes(node INTEGER, way INTEGER, PRIMARY KEY(node,way)) WITHOUT ROWID;
            CREATE TABLE structural_ways(id INTEGER PRIMARY KEY);
            CREATE TABLE loop_ways(id INTEGER PRIMARY KEY);
            CREATE TABLE sites(id INTEGER PRIMARY KEY, members TEXT);

        """)
        locations = DiskNodes(directory, db, quota)
        totals = dict(nodes=0, ways=0, relations=0, references=0)
        scanned = 0
        def scalar(entity, key, *, counted=True):
            nonlocal scanned
            if counted:
                scanned += 1
                totals[key] += 1
            if entity.id <= 0 or not entity.visible:
                raise ValueError("OSM deleted or invalid ID")
            if scanned > MAX_SCAN_ENTITIES:
                soft_limit("stream_scan_entities", scanned, MAX_SCAN_ENTITIES, "OSM scan entity budget exceeded; scanning takes longer")
            tag_count = len(entity.tags)
            # Most geographic nodes have no tags. In pyosmium, exhausting a tag
            # iterator crosses a C++ exception boundary even for an empty list.
            # Do not pay that cost millions of times in a national snapshot:
            # take exactly tag_count items instead of iterating to the end.
            if tag_count == 0: return {}
            if tag_count > MAX_TAGS:
                soft_limit("osm_tags", tag_count, MAX_TAGS, "OSM object has many source tags")
            failure = "more than 1024 source tags are unsupported" if tag_count > TAG_CEILING else ""
            tags, iterator = {}, iter(entity.tags)
            for _ in range(tag_count):
                key, value = next(iterator)
                oversized = len(key) > TAG_TEXT or len(value) > TAG_TEXT
                if oversized or key in tags:
                    failure = "duplicate or oversized source tag"
                if not oversized and len(tags) < TAG_CEILING:
                    tags[key] = value
            if failure:
                # Unselected labels (e.g. multilingual country nodes) do not
                # consume the selected-object tag quota. Retain an error marker:
                # any geometry referencing this object must reject or review it.
                keys = {"type", "highway", "building", "building:part", "landuse", "natural", "leisure", "boundary", "bridge", "tunnel"}
                tags = {t.k:t.v[:TAG_TEXT] for t in entity.tags if t.k in keys}
                tags["_source_error"] = f"{entity.type_str()}/{entity.id}: {failure}"
            return tags
        def references(count):
            totals["references"] += count
            if count > ENTITY_REFS_CEILING:
                raise BudgetExceeded("OSM source object exceeds 1,000,000 references")
            if count > MAX_ENTITY_REFS:
                soft_limit("stream_entity_references", count, MAX_ENTITY_REFS, "OSM source object has many references")
            if totals["references"] > MAX_SCAN_REFS:
                soft_limit("stream_scan_references", totals["references"], MAX_SCAN_REFS, "OSM scan reference budget exceeded; scanning takes longer")
        def intersects(box):
            return box is not None and box[0] <= selected[2] and box[2] >= selected[0] and box[1] <= selected[3] and box[3] >= selected[1]
        def envelope(box, x, y, east=None, north=None):
            other = [x,y,x if east is None else east,y if north is None else north]
            return other if box is None else [min(box[0],other[0]),min(box[1],other[1]),max(box[2],other[2]),max(box[3],other[3])]
        tag_insert = db.cursor()
        np, tagged_only = locations.np, osmium.filter.EmptyTagFilter()
        # Dense blocks index IDs/locations without Python entities; ways take refs
        # from the same decoded block, checked against libosmium's ID and length.
        decoded = dict(dense=False, ids=None, counts=None, refs=None, way=0, ref=0)
        def node_block(offset, payload):
            nonlocal scanned
            blocks = _decode_block(np, payload, nodes=True)
            decoded["dense"] = blocks is not None
            if blocks is None: return None
            for ids, xy, visible in blocks[0]:
                if not len(ids): continue
                scanned += len(ids)
                totals["nodes"] += len(ids)
                if ids.min() <= 0 or (visible is not None and not visible.all()):
                    raise ValueError("OSM deleted or invalid ID")
                if scanned > MAX_SCAN_ENTITIES:
                    soft_limit("stream_scan_entities", scanned, MAX_SCAN_ENTITIES, "OSM scan entity budget exceeded; scanning takes longer")
                if xy[:,0].min() < -1800000000 or xy[:,0].max() > 1800000000 or xy[:,1].min() < -900000000 or xy[:,1].max() > 900000000:
                    raise ValueError("OSM invalid node location")
                locations.add_many(ids, xy)
            return tagged_only
        def node(entity):
            if decoded["dense"]:
                tags = scalar(entity, "nodes", counted=False)
                if tags: tag_insert.execute("INSERT INTO node_tags VALUES(?,?)", (entity.id,json.dumps(tags)))
                return
            tags = scalar(entity, "nodes")
            location = entity.location
            if not location.valid(): raise ValueError("OSM invalid node location")
            x, y = location.x, location.y
            if not -1800000000 <= x <= 1800000000 or not -900000000 <= y <= 900000000: raise ValueError("OSM invalid node location")
            locations.add(entity.id,x,y)
            if tags: tag_insert.execute("INSERT INTO node_tags VALUES(?,?)", (entity.id,json.dumps(tags)))
        pending_ways, pending_refs, pending_bytes = [], 0, 0
        block_offset = 0
        def decoded_rest():
            if decoded["ids"] is not None and decoded["way"] != len(decoded["ids"]): raise ValueError("PBF way decoding mismatch")
        def way_block(offset, payload):
            nonlocal block_offset
            decoded_rest()
            block_offset = offset
            blocks = _decode_block(np, payload, ways=True)
            ids, counts, refs = blocks[1] if blocks is not None and blocks[1] is not None else (None, None, None)
            decoded.update(ids=ids, counts=counts, refs=refs, way=0, ref=0)
        def block_start(offset, payload):
            nonlocal block_offset
            block_offset = offset
        def payload_size(size):
            if size > WAY_PAYLOAD_CEILING: raise BudgetExceeded("OSM way buffer byte ceiling exceeded")
            if size > WAY_BATCH_BYTES: soft_limit("stream_way_bytes", size, WAY_BATCH_BYTES, "OSM way buffer byte budget exceeded")
        def city_payload(refs, tags):
            raw = json.dumps([refs,tags])
            payload_size(len(raw.encode("utf-8")))
            return zlib.compress(raw.encode("utf-8"), 1)
        def flush_ways():
            nonlocal pending_refs, pending_bytes
            if not pending_ways: return
            boxes = locations.bounds_many([row[1] for row in pending_ways])
            # City mode stores only selected payloads; the rest are source block pointers.
            db.executemany("INSERT INTO ways VALUES(?,?,?,?,?,?,?)",
                [(identity,*(box or [None]*4),
                  (city_payload(refs, tags) if potential and intersects(box) else b"L"+struct.pack(">Q",offset)) if city else raw,int(potential))
                 for (identity,refs,tags,raw,potential,offset),box in zip(pending_ways,boxes)])
            # Only source graph evidence, never an inferred positional join.
            # Batches obey the same aggregate reference/disk/deadline caps.
            if shared is not None:
                shared.add([(identity,refs) for identity,refs,tags,raw,potential,offset in pending_ways if "highway" in tags])
            else:
                db.executemany("INSERT OR IGNORE INTO road_nodes VALUES(?,?)",
                    ((ref,identity) for identity,refs,tags,raw,potential,offset in pending_ways
                     if "highway" in tags for ref in refs))
            for (identity,refs,tags,raw,potential,offset),box in zip(pending_ways,boxes):
                if "highway" in tags:
                    if any(tags.get(k, "no") not in ("no", "0") for k in ("bridge", "tunnel")):
                        db.execute("INSERT INTO structural_ways VALUES(?)", (identity,))
                    elif len(refs) > 1 and refs[0] == refs[-1]:
                        db.execute("INSERT INTO loop_ways VALUES(?)", (identity,))
                if potential and intersects(box):
                    db.execute("INSERT INTO chosen VALUES(?)", (identity,))
            pending_ways.clear(); pending_refs = pending_bytes = 0
        def way(entity):
            nonlocal pending_refs, pending_bytes
            tags = scalar(entity, "ways")
            count = len(entity.nodes)
            references(count)
            if decoded["ids"] is None:
                refs = [n.ref for n in entity.nodes]
            else:
                index, start = decoded["way"], decoded["ref"]
                if index >= len(decoded["ids"]) or decoded["ids"][index] != entity.id or decoded["counts"][index] != count:
                    raise ValueError("PBF way decoding mismatch")
                refs = decoded["refs"][start:start+count].tolist()
                decoded["way"], decoded["ref"] = index+1, start+count
            potential = _potential(tags, city)
            if potential and not count: raise ValueError("OSM feature way has no referenced geometry")
            raw, size = None, 0
            if not city:
                raw = json.dumps([refs,tags]); size = len(raw.encode("utf-8"))
                payload_size(size)
            if len(pending_ways) >= WAY_BATCH_ROWS or pending_refs + len(refs) > MAX_LOOKUP or pending_bytes + size > WAY_BATCH_BYTES:
                flush_ways()
            pending_ways.append((entity.id,refs,tags,raw,potential,block_offset))
            pending_refs += len(refs); pending_bytes += size
        def relation(entity):
            tags = scalar(entity, "relations")
            references(len(entity.members))
            members, box, unsupported = [], None, ""
            member_ways = set()
            area = tags.get("type") in ("multipolygon", "boundary")
            potential = _potential(tags, city, relation=True)
            if potential and not len(entity.members): raise ValueError("OSM feature relation has no referenced geometry")
            for m in entity.members:
                if m.ref <= 0: raise ValueError("OSM invalid relation reference")
                role = m.role
                if len(role) > TAG_TEXT:
                    # As with oversized tags: geometry using this relation rejects
                    # (or is reviewed); an unselected relation does not refuse the import.
                    role = role[:TAG_TEXT]
                    tags.setdefault("_source_error", f"relation/{entity.id}: oversized relation member role")
                members.append((m.type,m.ref,role))
                if area and m.type == "w":
                    if m.ref in member_ways:
                        unsupported = "area relation repeats a way member; original topology is not repaired"
                        review.reject("relation/" + str(entity.id), unsupported)
                    member_ways.add(m.ref)
                if m.type == "r":
                    if potential: unsupported = "nested feature relation has unlocated geometry and is unsupported"
                    continue  # Non-area/non-feature relation semantics are disclosed omissions.
                if m.type == "w":
                    row = db.execute("SELECT west,south,east,north FROM ways WHERE id=?", (m.ref,)).fetchone()
                elif m.type == "n":
                    try: xy = locations.point(m.ref)
                    except MissingNode: xy = None
                    row = None if xy is None else (*xy,*xy)
                else: raise ValueError("OSM unsupported relation member type")
                if row is None:
                    if potential: unsupported = "relation missing member; use a complete snapshot"
                    continue
                if row[0] is not None: box = envelope(box,*row)
            candidate = potential and intersects(box)
            if potential and unsupported:
                review.reject("relation/" + str(entity.id), unsupported)
                candidate = False
            if candidate:
                try:
                    kind = category(tags, city)
                    if (tags.get("type") != "multipolygon" and not (kind=="region" and tags.get("type")=="boundary")) or kind in ("road", "barrier"):
                        raise ValueError("selected relation requires supported multipolygon semantics")
                except ValueError as exc:
                    review.reject("relation/" + str(entity.id), exc)
                    candidate = False
            db.execute("INSERT INTO relations VALUES(?,?,?)", (entity.id,json.dumps([members,tags]) if candidate else None,int(candidate)))
            if city and tags.get("type") == "site":
                # City building records group by site relation membership only.
                db.execute("INSERT INTO sites VALUES(?,?)", (entity.id,json.dumps([[kind,ref] for kind,ref,role in members if kind in ("w","r")])))
            owned_members = set()
            for kind,ref,role in members:
                if area and kind == "w":
                    # Repeated source members have already rejected/excluded
                    # their whole relation above. Keep blocked ownership once;
                    # never adopt a silently deduplicated area boundary.
                    if ref not in owned_members:
                        db.execute("INSERT INTO owners VALUES(?,?,?)", (ref,entity.id,int(not candidate)))
                        owned_members.add(ref)
                if candidate and kind == "w": db.execute("INSERT OR IGNORE INTO chosen VALUES(?)", (ref,))
        for stage, bits, callback, block in [("index_nodes",osmium.osm.NODE,node,node_block),("index_ways",osmium.osm.WAY,way,way_block),("index_relations",osmium.osm.RELATION,relation,block_start)]:
            _scan(path, stage, event, size, osmium, bits, callback, block_callback=block)
            if stage == "index_nodes":
                locations.seal()
                if locations.ordered and locations.count: shared = SharedRoadNodes(locations, directory)
            if stage == "index_ways":
                decoded_rest()
                flush_ways()
                if shared is not None:
                    db.executemany("INSERT OR IGNORE INTO road_nodes VALUES(?,?)", shared.rows())
                    shared.close()
                    shared = None
            db.commit()
        lazy_header, resolved_blocks = None, 0
        def read_way(identity):
            nonlocal lazy_header, lazy_pool, resolved_blocks
            raw = db.execute("SELECT data FROM ways WHERE id=?", (identity,)).fetchone()[0]
            if not (isinstance(raw,bytes) and raw[:1] == b"L"):
                return _payload(raw)
            if len(raw) != 9: raise ValueError("Invalid indexed PBF block pointer")
            offset = struct.unpack(">Q",raw[1:])[0]
            if not 0 < offset < size: raise ValueError("Invalid indexed PBF block offset")
            if lazy_pool is None: lazy_pool = osmium.io.ThreadPool(1,1)
            with path.open("rb") as handle:
                if lazy_header is None:
                    kind,payload = _read_block(handle)
                    if kind != b"OSMHeader": raise ValueError("Missing captured PBF header")
                    lazy_header = _frame(kind,payload)
                handle.seek(offset)
                kind,payload = _read_block(handle)
                if kind != b"OSMData": raise ValueError("Indexed way is not in a PBF data block")
            processor = osmium.FileProcessor(osmium.io.FileBuffer(lazy_header+_frame(kind,payload),"pbf"), entities=osmium.osm.WAY, thread_pool=lazy_pool)
            processor.with_filter(osmium.filter.IdFilter([identity]))
            iterator, found = iter(processor), None
            try:
                for entity in iterator:
                    if found is not None: raise ValueError("Duplicate indexed way")
                    found = json.dumps([[n.ref for n in entity.nodes],scalar(entity,"ways",counted=False)])
                    payload_size(len(found.encode("utf-8")))
            finally:
                iterator.close()
            if found is None: raise ValueError("Indexed source way is missing")
            db.execute("UPDATE ways SET data=? WHERE id=?",(zlib.compress(found.encode("utf-8"),1),identity))
            resolved_blocks += 1
            return found
        index_bytes = db.execute("PRAGMA page_count").fetchone()[0] * 4096 + locations.written
        if index_bytes > MAX_INDEX:
            soft_limit("stream_index_bytes", index_bytes, MAX_INDEX, "OSM disk index exceeds 2 GiB")
        closure = _structure_closure(db, event, size, read_way, (input_limit, ref_limit, entity_limit, feature_limit))
        event("index_relations", size, size)
        nodes, node_tags, all_ways, ways, relations, blocked = {}, {}, {}, [], [], set()
        counts = dict(nodes=0,ways=0,relations=0,ignored_ways=0,ignored_relations=0,tagged_nodes=0,assembled_relations=0,outer_rings=0,inner_rings=0,member_ways=0)
        selection_bytes, selected_refs = 0, 0
        total = db.execute("SELECT count(*) FROM chosen").fetchone()[0] + db.execute("SELECT count(*) FROM relations WHERE candidate=1").fetchone()[0]
        if total > entity_limit: soft_limit("stream_selected_entities", total, entity_limit, "OSM selected entity budget exceeded")
        event("select", 0, total, "entities")
        def admit(raw, refs=0):
            nonlocal selection_bytes, selected_refs
            selection_bytes += len(raw.encode("utf-8"))
            selected_refs += refs
            if selection_bytes > input_limit:
                soft_limit("stream_selected_bytes", selection_bytes, input_limit, "OSM selected payload budget exceeded")
            if selected_refs > ref_limit:
                soft_limit("stream_selected_references", selected_refs, ref_limit, "OSM selected reference budget exceeded")
            if len(nodes)+len(all_ways)+len(relations) > entity_limit:
                soft_limit("stream_selected_entities", len(nodes)+len(all_ways)+len(relations), entity_limit, "OSM selected entity budget exceeded")
        completed = 0
        # Iterate the integer primary key, then lookup one payload. Avoid a SQL
        # join/sorter that could materialize all payloads before byte admission.
        for (identity,) in db.execute("SELECT id FROM chosen ORDER BY id"):
            raw = read_way(identity)
            admit(raw)
            refs,tags = json.loads(raw)
            admit("",len(refs))
            all_ways[identity] = (refs,tags)
            try:
                kind = category(tags, city)
            except ValueError as exc:
                review.reject("way/" + str(identity), exc)
                kind = None
            if kind: ways.append((identity,kind,refs,tags))
            else: counts["ignored_ways"] += 1
            if len(ways) > feature_limit: soft_limit("osm_features", len(ways), feature_limit, "OSM selected feature budget exceeded")
            for ref in refs:
                if ref in nodes: continue
                if len(nodes) >= point_limit: soft_limit("osm_nodes", len(nodes) + 1, point_limit, "OSM selected node budget exceeded")
                x,y = locations.point(ref)
                tagged = db.execute("SELECT tags FROM node_tags WHERE id=?", (ref,)).fetchone()
                tags_at_node = json.loads(tagged[0]) if tagged else {}
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
            relations.append((identity,category(tags, city),members,tags))
            if len(ways)+len(relations) > feature_limit: soft_limit("osm_features", len(ways)+len(relations), feature_limit, "OSM selected feature budget exceeded")
            completed += 1
            if completed % 100 == 0: event("select",completed,total,"entities")
        event("select",completed,total,"entities")
        # Count the completed selection too (the last insertion follows admit()).
        admit("")
        counts.update(nodes=len(nodes),ways=len(all_ways),relations=len(relations),tagged_nodes=len(node_tags))
        event("parse",0,selection_bytes)
        sites = {}
        if city:
            selected_relations = {identity for identity, *_ in relations}
            for identity, raw in db.execute("SELECT id,members FROM sites ORDER BY id"):
                for kind, ref in json.loads(raw):
                    if (kind == "w" and ref in all_ways or kind == "r" and ref in selected_relations) and (kind, ref) not in sites:
                        sites[(kind, ref)] = "relation/" + str(identity)
        value, counts = build_features(nodes,node_tags,ways,all_ways,relations,blocked,counts,supplement,digest,review,feature_limit=feature_limit,city=city,sites=sites)
        meta = dict(profile=PROFILE,passes=3,source_bytes=size,source_sha256=digest,
                    scan=totals,structure_closure=closure,selected=dict(nodes=len(nodes),ways=len(all_ways),relations=len(relations),references=selected_refs,bytes=selection_bytes))
        if city: meta.update(index_policy="source-block-pointers-v1", resolved_way_blocks=resolved_blocks)
        if region is not None: meta.update(areas=area_meta, _region=region)
        return value, counts, meta
    except (sqlite3.Error, RuntimeError, zlib.error) as exc:
        raise ValueError("invalid/budget-exceeding PBF stream: " + str(exc)[:300]) from exc
    finally:
        if lazy_pool is not None: del lazy_pool
        if shared is not None: shared.close()
        if locations is not None: locations.close()
        if db is not None: db.close()
        for name in OWNED_FILES:
            (directory / name).unlink(missing_ok=True)
