"""Quota-limited exact node coordinates for a private PBF import worker.

Sorted source IDs use two read-only file arrays and bounded vector lookups.
Unsorted snapshots retain the same semantics through the SQLite index. Neither
path retains a Python/libosmium dictionary containing the country's locations.
"""
from array import array

from import_layer import BudgetExceeded

FILES = ("node-ids.i64", "node-xy.i32", "road-incidence.u8", "road-pairs.bin")
BATCH = 4096
MAX_LOOKUP = 20000  # One vector lookup; longer requests are chunked.
PRECISION = 10000000.0


class MissingNode(ValueError):
    pass


class DiskNodes:
    def __init__(self, directory, db, quota):
        try:
            import numpy as np
        except ImportError as exc:
            raise ValueError("PBF streaming needs NumPy; install requirements-import.txt") from exc
        self.np, self.db, self.quota = np, db, quota
        self.paths = [directory / name for name in FILES[:2]]
        self.ids_file = self.xy_file = None
        self.ids = self.xy = None
        self.count, self.written, self.last = 0, 0, 0
        self.ordered, self.ready = True, False
        self.keys, self.positions = array("q"), array("i")
        if self.keys.itemsize != 8 or self.positions.itemsize != 4:
            raise ValueError("PBF coordinate index requires 64/32-bit integer arrays")
        self.ids_file = self.paths[0].open("xb")
        try:
            self.xy_file = self.paths[1].open("xb")
        except BaseException:
            self.ids_file.close()
            raise

    def add(self, identity, x, y):
        if self.ready: raise ValueError("PBF node index is already sealed")
        if identity <= self.last: self.ordered = False
        if identity == self.last: raise ValueError("OSM duplicate node ID")
        self.last = identity
        self.keys.append(identity)
        self.positions.append(x)
        self.positions.append(y)
        self.count += 1
        if len(self.keys) == BATCH: self._flush()

    def add_many(self, ids, xy):
        """Same order, duplicate and flush semantics as add() for decoded int64 IDs/int32 pairs."""
        if self.ready: raise ValueError("PBF node index is already sealed")
        np = self.np
        if not len(ids): return
        previous = np.empty_like(ids)
        previous[0] = self.last
        previous[1:] = ids[:-1]
        if np.any(ids == previous): raise ValueError("OSM duplicate node ID")
        if np.any(ids < previous): self.ordered = False
        self.last = int(ids[-1])
        start = 0
        while start < len(ids):
            take = min(BATCH - len(self.keys), len(ids) - start)
            self.keys.frombytes(ids[start:start+take].astype(np.int64).tobytes())
            self.positions.frombytes(xy[start:start+take].astype(np.int32).tobytes())
            self.count += take
            start += take
            if len(self.keys) == BATCH: self._flush()

    def reserve(self, amount):
        pages = (self.quota - self.written - amount) // 4096
        if pages < self.db.execute("PRAGMA page_count").fetchone()[0]:
            raise BudgetExceeded("OSM combined node/SQLite index exceeds its disk quota (3x source, within free disk)")
        # Reserve the binary bytes before writing them. SQLite cannot grow into
        # their reservation during later way/relation indexing.
        self.db.execute(f"PRAGMA max_page_count={pages}")
        self.written += amount

    def release(self, amount):
        self.written -= amount
        self.db.execute(f"PRAGMA max_page_count={(self.quota - self.written) // 4096}")

    def _flush(self):
        if not self.keys: return
        amount = len(self.keys) * 16
        self.reserve(amount)
        self.keys.tofile(self.ids_file)
        self.positions.tofile(self.xy_file)
        self.keys = array("q")
        self.positions = array("i")

    def seal(self):
        self._flush()
        self.ids_file.close()
        self.xy_file.close()
        self.ids_file = self.xy_file = None
        if not self.ordered:
            # Bounded blocks, no country-sized argsort allocation. This path
            # also catches duplicate IDs that were not adjacent in the source.
            with self.paths[0].open("rb") as ids, self.paths[1].open("rb") as xy:
                remaining = self.count
                while remaining:
                    count = min(BATCH, remaining)
                    keys, positions = array("q"), array("i")
                    keys.fromfile(ids, count)
                    positions.fromfile(xy, count * 2)
                    self.db.executemany("INSERT INTO nodes VALUES(?,?,?)",
                        ((key, positions[i*2], positions[i*2+1]) for i,key in enumerate(keys)))
                    remaining -= count
            for path in self.paths: path.unlink()
            self.written = 0
            self.db.execute(f"PRAGMA max_page_count={self.quota//4096}")
        elif self.count:
            self.ids = self.np.memmap(self.paths[0], dtype=self.np.int64, mode="r", shape=(self.count,))
            self.xy = self.np.memmap(self.paths[1], dtype=self.np.int32, mode="r", shape=(self.count, 2))
        self.ready = True

    def indices(self, refs):
        """Positions in the sorted file arrays (ordered snapshots only)."""
        if not self.ready or not self.ordered: raise ValueError("PBF node index is not sealed/ordered")
        if not len(refs): raise ValueError("OSM node lookup requires references")
        if len(refs) > MAX_LOOKUP:
            return self.np.concatenate([self.indices(refs[i:i+MAX_LOOKUP]) for i in range(0, len(refs), MAX_LOOKUP)])
        if self.count == 0: self._missing()
        wanted = self.np.asarray(refs, dtype=self.np.int64)
        indices = self.ids.searchsorted(wanted)
        if self.np.any(indices >= self.count) or self.np.any(self.ids[indices] != wanted): self._missing()
        return indices

    def _points(self, refs):
        if not self.ready: raise ValueError("PBF node index is not sealed")
        if not len(refs): raise ValueError("OSM node lookup requires references")
        if len(refs) > MAX_LOOKUP:
            return self.np.concatenate([self._points(refs[i:i+MAX_LOOKUP]) for i in range(0, len(refs), MAX_LOOKUP)])
        if not self.ordered:
            rows = [self.db.execute("SELECT x,y FROM nodes WHERE id=?", (ref,)).fetchone() for ref in refs]
            if any(row is None for row in rows): self._missing()
            return self.np.asarray(rows, dtype=self.np.int32)
        return self.xy[self.indices(refs)]  # Bounded copy, never an escaping mmap view.

    @staticmethod
    def _missing():
        raise MissingNode("OSM way missing referenced node; use a complete snapshot")

    def bounds(self, refs):
        if not refs: return None
        points = self._points(refs)
        low, high = points.min(axis=0), points.max(axis=0)
        return [int(low[0])/PRECISION,int(low[1])/PRECISION,int(high[0])/PRECISION,int(high[1])/PRECISION]

    def bounds_many(self, groups):
        """One chunked search for several ways, without mixing their envelopes."""
        refs, starts, owners = [], [], []
        result = [None] * len(groups)
        for owner, group in enumerate(groups):
            if not group: continue
            starts.append(len(refs)); owners.append(owner); refs.extend(group)
        if not refs: return result
        points = self._points(refs)
        lows = self.np.minimum.reduceat(points, starts, axis=0)
        highs = self.np.maximum.reduceat(points, starts, axis=0)
        # float64 division of the exact integers, as int(x)/PRECISION would give.
        boxes = (self.np.concatenate((lows, highs), axis=1).astype(self.np.float64) / PRECISION).tolist()
        for owner, box in zip(owners, boxes): result[owner] = box
        return result

    def point(self, ref):
        point = self._points([ref])[0]
        return [int(point[0])/PRECISION,int(point[1])/PRECISION]

    def close(self):
        for file in (self.ids_file, self.xy_file):
            if file is not None: file.close()
        for mapped in (self.ids, self.xy):
            if mapped is not None: mapped._mmap.close()
        self.ids_file = self.xy_file = self.ids = self.xy = None


class SharedRoadNodes:
    """Highway (node, way) incidences, kept only where two or more ways share a node.

    Needs an ordered DiskNodes index. A per-node saturating counter and the raw pairs
    are disk files inside the same quota; rows() yields the shared pairs once the
    ways are complete, and close() releases both reservations.
    """
    def __init__(self, nodes, directory):
        self.nodes, self.np = nodes, nodes.np
        self.paths = [directory / name for name in FILES[2:]]
        self.counter = self.pairs = None
        self.reserved = 0
        # 12-byte pairs: a uint32 position in the node arrays and the int64 way ID.
        self.dtype = self.np.dtype([("node", "<u4"), ("way", "<i8")])
        if nodes.count >= 2**32: raise ValueError("OSM node index budget exceeded")
        nodes.reserve(nodes.count)
        self.reserved = nodes.count
        self.counter = self.np.memmap(self.paths[0], dtype=self.np.uint8, mode="w+", shape=(max(nodes.count, 1),))
        self.pairs = self.paths[1].open("xb")
        self.written = 0

    def add(self, ways):
        """`ways`: (way ID, refs) of one batch; lookups are chunked."""
        np = self.np
        ways = [(identity, refs) for identity, refs in ways if refs]
        if not ways: return
        positions = self.nodes.indices([ref for _, refs in ways for ref in refs])
        owners = np.repeat(np.asarray([identity for identity, _ in ways], dtype=np.int64), [len(refs) for _, refs in ways])
        order = np.lexsort((owners, positions))
        positions, owners = positions[order], owners[order]
        unique = np.ones(len(positions), dtype=bool)
        unique[1:] = (positions[1:] != positions[:-1]) | (owners[1:] != owners[:-1])
        positions, owners = positions[unique], owners[unique]
        # Saturate at 2 ways per node; increments are clipped first, so no batch size wraps uint8.
        nodes, ways = np.unique(positions, return_counts=True)
        self.counter[nodes] = np.minimum(self.counter[nodes].astype(np.int64)+ways, 2)
        pairs = np.empty(len(positions), dtype=self.dtype)
        pairs["node"], pairs["way"] = positions, owners
        self.nodes.reserve(pairs.nbytes)
        self.reserved += pairs.nbytes
        pairs.tofile(self.pairs)
        self.written += len(pairs)

    def rows(self):
        np = self.np
        self.pairs.close()
        self.pairs = None
        with self.paths[1].open("rb") as source:
            remaining = self.written
            while remaining:
                count = min(MAX_LOOKUP, remaining)
                pairs = np.fromfile(source, dtype=self.dtype, count=count)
                if len(pairs) != count: raise ValueError("OSM road incidence index is truncated")
                remaining -= count
                pairs = pairs[self.counter[pairs["node"]] >= 2]
                if not len(pairs): continue
                nodes = self.nodes.ids[pairs["node"]]
                order = np.lexsort((pairs["way"], nodes))
                yield from zip(nodes[order].tolist(), pairs["way"][order].tolist())

    def close(self):
        if self.pairs is not None: self.pairs.close()
        if self.counter is not None: self.counter._mmap.close()
        self.pairs = self.counter = None
        for path in self.paths: path.unlink(missing_ok=True)
        if self.reserved: self.nodes.release(self.reserved)
        self.reserved = 0
