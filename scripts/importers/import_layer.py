"""Editor-owned typed import boundary. No game or MapServer dependency."""
from dataclasses import asdict, dataclass, field, fields
import json
import math
import re
import time

# Budgets on the user's own data are soft: exceeding one records a limit
# warning (see soft_limit) and the import continues. Memory guards were raised
# and warn above their former value. Only the CEILING constants still refuse.
MAX_INPUT = 32 * 1024 * 1024  # Warn above; non-streamed input is read whole.
INPUT_CEILING = 256 * 1024 * 1024  # Memory guard: non-streamed input.
MAX_OUTPUT = 12 * 1024 * 1024
MAX_RECORDS = 60_000
MAX_POINTS = 200_000
CITY_OUTPUT = 32 * 1024 * 1024
CITY_RECORDS = 180_000  # Leave room below current-v1's 200,000 document objects.
CITY_POINTS = 800_000  # Leave room below current-v1's 1,000,000 vertices.
CITY_FEATURES = 100_000
DOCUMENT_OBJECTS = 200_000  # current-v1 document maxima; the game refuses more.
DOCUMENT_VERTICES = 1_000_000
FIELDS = ("nodes", "roads", "buildings", "zones", "surface_areas", "pois", "barriers", "water_bodies", "placements")
LIMIT_PREFIX = "Limit warning: "
MAX_WARNINGS = 50


class BudgetExceeded(ValueError):
    """A hard ceiling (memory/parser guard) or a typed budget failure. Control
    flow distinguishes it by type, never by matching message text."""


# One process runs one import; every soft limit it meets is listed once per code.
_LIMITS = {}


def soft_limit(code, actual, limit, message, runtime_rejects=False):
    """Record that a budget was exceeded and continue. One entry per code keeps
    the number of occurrences and the largest actual value."""
    entry = _LIMITS.get(code)
    if entry is None:
        _LIMITS[code] = dict(code=code, actual=actual, limit=limit, message=message, runtime_rejects=bool(runtime_rejects), count=1)
    else:
        entry["count"] += 1
        if actual > entry["actual"]:
            entry["actual"] = actual
        entry["runtime_rejects"] = entry["runtime_rejects"] or bool(runtime_rejects)


def limit_entries():
    return [dict(entry) for entry in _LIMITS.values()]


def limit_snapshot():
    return {code: dict(entry) for code, entry in _LIMITS.items()}


def limit_restore(snapshot):
    _LIMITS.clear()
    _LIMITS.update({code: dict(entry) for code, entry in snapshot.items()})


def reset_limits():
    _LIMITS.clear()


def limit_delta(snapshot, exclude=()):
    """Entries hit since `snapshot` (new codes or a higher count), so a cached
    computation can replay the limits it met. `exclude` skips codes that the
    replay records by itself."""
    return [dict(entry) for code, entry in _LIMITS.items()
            if code not in exclude and (code not in snapshot or entry["count"] > snapshot[code]["count"])]


def limit_replay(entries):
    for entry in entries:
        soft_limit(entry["code"], entry["actual"], entry["limit"], entry["message"], entry["runtime_rejects"])


def limit_text(entry):
    suffix = "; the game refuses maps beyond this" if entry["runtime_rejects"] else ""
    tail = f" ({entry['actual']} > {entry['limit']}){suffix}"
    # The Editor accepts warnings of at most 512 characters.
    return LIMIT_PREFIX + entry["message"][:512 - len(LIMIT_PREFIX) - len(tail)] + tail


PROGRESS_INTERVAL = 0.1  # Seconds between progress events of one stage.


class Progress:
    """JSON-lines progress with a contiguous seq. Soft limits let counts grow far
    beyond their former budgets, so events of one stage are throttled to one per
    PROGRESS_INTERVAL; the Editor bounds the whole pipe. The first and last event
    of every stage, events with extra fields and `complete` are always emitted."""

    def __init__(self, request, clock=time.monotonic, write=None):
        self.request, self.clock = request, clock
        self.write = write if write is not None else (lambda line: print(line, flush=True))
        self.sequence, self.stage, self.last, self.pending = 0, None, 0.0, None

    def __call__(self, stage, completed, total, unit="bytes", **extra):
        now = self.clock()
        if stage == self.stage:
            if not extra and stage != "complete" and now - self.last < PROGRESS_INTERVAL:
                self.pending = (stage, completed, total, unit, extra)
                return
            self.pending = None  # Superseded: counters only grow within a stage.
        elif self.pending is not None:
            self._emit(*self.pending)
        self._emit(stage, completed, total, unit, extra)
        self.stage, self.last, self.pending = stage, now, None

    def _emit(self, stage, completed, total, unit, extra):
        self.sequence += 1
        self.write(json.dumps(dict(request=self.request, seq=self.sequence, stage=stage, completed=completed, total=total, unit=unit, **extra)))


def number(value, name, minimum=-100_000, maximum=100_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name}: expected finite number in [{minimum}, {maximum}]")
    return value


def text(value, name, maximum=512):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name}: expected nonempty bounded text")
    return value.strip()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite JSON value: {value}")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


@dataclass(frozen=True)
class Source:
    name: str
    sha256: str
    bytes: int
    license: str
    accuracy: str


@dataclass
class ImportLayer:
    layer_id: str
    source: Source
    coordinates: dict
    import_version: int = 1
    adapter: str = "geojson-v1"
    patches: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    estimates: dict = field(default_factory=dict)
    extent_cm: list = field(default_factory=list)
    feature_count: int = 0
    point_count: int = 0
    warning_count: int = 0

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{32}", self.layer_id):
            raise ValueError("layer ID must be a fresh 128-bit lowercase hex token")
        text(self.source.name, "source name")
        text(self.source.license, "license")
        text(self.source.accuracy, "accuracy")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source.sha256):
            raise ValueError("invalid source hash")

    def city(self):
        return bool(self.coordinates.get("city_source_ids") or self.coordinates.get("osm_city"))

    def add(self, field_name, record):
        if field_name not in FIELDS:
            raise ValueError("unsupported record")
        limit = CITY_RECORDS if self.city() else MAX_RECORDS
        if len(self.patches) >= limit:
            soft_limit("import_records", len(self.patches) + 1, limit, "Import record budget exceeded")
        if len(self.patches) >= DOCUMENT_OBJECTS:
            soft_limit("document_objects", len(self.patches) + 1, DOCUMENT_OBJECTS, "Import records exceed the current-v1 document object limit", True)
        self.patches.append({"field": field_name, "id": record["id"], "before": None, "after": record})

    def warning(self, message):
        self.warning_count += 1
        if len(self.warnings) < 50:
            self.warnings.append(message)

    def estimate(self, field_name):
        self.estimates[field_name] = self.estimates.get(field_name, 0) + 1

    def point(self, x, y):
        self.point_count += 1
        limit = CITY_POINTS if self.city() else MAX_POINTS
        if self.point_count > limit:
            soft_limit("import_coordinates", self.point_count, limit, "Import coordinate budget exceeded")
        if self.point_count > DOCUMENT_VERTICES:
            soft_limit("document_vertices", self.point_count, DOCUMENT_VERTICES, "Import coordinates exceed the current-v1 document vertex limit", True)
        if not self.extent_cm:
            self.extent_cm = [x, y, x, y]
        else:
            self.extent_cm = [min(x, self.extent_cm[0]), min(y, self.extent_cm[1]), max(x, self.extent_cm[2]), max(y, self.extent_cm[3])]

    def data(self):
        """JSON-ready fields. Only the source is a nested dataclass; a deep
        asdict copy of every patch would serialize identically, only slower."""
        return {f.name: asdict(self.source) if f.name == "source" else getattr(self, f.name) for f in fields(self)}

    def merge_limit_warnings(self):
        """Put one text per recorded limit into `warnings`. Limit warnings
        always keep a slot; ordinary warnings are dropped first. Idempotent."""
        ordinary = [w for w in self.warnings if not (isinstance(w, str) and w.startswith(LIMIT_PREFIX))]
        limits = [limit_text(entry) for entry in _LIMITS.values()][:MAX_WARNINGS]
        # Each limit code counts once toward warning_count, however often merged.
        counted = self.__dict__.setdefault("_counted_limits", set())
        added = [code for code in _LIMITS if code not in counted]
        counted.update(added)
        self.warnings = ordinary[:MAX_WARNINGS - len(limits)] + limits
        self.warning_count = max(self.warning_count + len(added), len(self.warnings))

    def encode(self):
        self.merge_limit_warnings()
        data = json.dumps(self.data(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        maximum = CITY_OUTPUT if self.city() else MAX_OUTPUT
        if len(data) > maximum:
            before = list(self.warnings)
            soft_limit("import_output", len(data), maximum, "ImportLayer exceeds the 32 MiB city output budget" if self.city() else "ImportLayer exceeds the 12 MiB output budget")
            self.merge_limit_warnings()
            if self.warnings != before:
                data = json.dumps(self.data(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return data
