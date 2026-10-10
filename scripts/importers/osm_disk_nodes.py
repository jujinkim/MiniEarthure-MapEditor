"""Quota-limited exact node coordinates for a private PBF import worker.

Sorted source IDs use two read-only file arrays and bounded vector lookups.
Unsorted snapshots retain the same semantics through the SQLite index. Neither
path retains a Python/libosmium dictionary containing the country's locations.
"""
from array import array

FILES = ("node-ids.i64", "node-xy.i32")
BATCH = 4096
MAX_LOOKUP = 20000
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
        self.paths = [directory / name for name in FILES]
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

    def _flush(self):
        if not self.keys: return
        amount = len(self.keys) * 16
        pages = (self.quota - self.written - amount) // 4096
        if pages < self.db.execute("PRAGMA page_count").fetchone()[0]:
            raise ValueError("OSM combined node/SQLite index budget exceeded")
        # Reserve the binary bytes before writing them. SQLite cannot grow into
        # their reservation during later way/relation indexing.
        self.db.execute(f"PRAGMA max_page_count={pages}")
        self.keys.tofile(self.ids_file)
        self.positions.tofile(self.xy_file)
        self.written += amount
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

    def _points(self, refs):
        if not self.ready: raise ValueError("PBF node index is not sealed")
        if not 0 < len(refs) <= MAX_LOOKUP: raise ValueError("OSM node lookup reference budget exceeded")
        if not self.ordered:
            rows = [self.db.execute("SELECT x,y FROM nodes WHERE id=?", (ref,)).fetchone() for ref in refs]
            if any(row is None for row in rows): self._missing()
            return self.np.asarray(rows, dtype=self.np.int32)
        if self.count == 0: self._missing()
        wanted = self.np.asarray(refs, dtype=self.np.int64)
        indices = self.ids.searchsorted(wanted)
        if self.np.any(indices >= self.count) or self.np.any(self.ids[indices] != wanted): self._missing()
        return self.xy[indices]  # Bounded copy, never an escaping mmap view.

    @staticmethod
    def _missing():
        raise MissingNode("OSM way missing referenced node; use a complete snapshot")

    def bounds(self, refs):
        if not refs: return None
        points = self._points(refs)
        low, high = points.min(axis=0), points.max(axis=0)
        return [int(low[0])/PRECISION,int(low[1])/PRECISION,int(high[0])/PRECISION,int(high[1])/PRECISION]

    def bounds_many(self, groups):
        """One bounded search for several ways, without mixing their envelopes."""
        if len(groups) > 256: raise ValueError("OSM node lookup group budget exceeded")
        refs, starts, owners = [], [], []
        result = [None] * len(groups)
        for owner, group in enumerate(groups):
            if not group: continue
            if len(refs) + len(group) > MAX_LOOKUP:
                raise ValueError("OSM node lookup reference budget exceeded")
            starts.append(len(refs)); owners.append(owner); refs.extend(group)
        if not refs: return result
        points = self._points(refs)
        lows = self.np.minimum.reduceat(points, starts, axis=0)
        highs = self.np.maximum.reduceat(points, starts, axis=0)
        for owner, low, high in zip(owners, lows, highs):
            result[owner] = [int(low[0])/PRECISION,int(low[1])/PRECISION,
                             int(high[0])/PRECISION,int(high[1])/PRECISION]
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
