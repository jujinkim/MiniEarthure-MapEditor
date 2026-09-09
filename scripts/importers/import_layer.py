"""Editor-owned typed import boundary. No game or MapServer dependency."""
from dataclasses import asdict, dataclass, field
import json
import math
import re

MAX_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 12 * 1024 * 1024
MAX_RECORDS = 60_000
MAX_POINTS = 200_000
FIELDS = ("nodes", "roads", "buildings", "zones")


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
    adapter: str = "geojson-local-v1"
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

    def add(self, field_name, record):
        if field_name not in FIELDS or len(self.patches) >= MAX_RECORDS:
            raise ValueError("unsupported record or import record budget exceeded")
        self.patches.append({"field": field_name, "id": record["id"], "before": None, "after": record})

    def warning(self, message):
        self.warning_count += 1
        if len(self.warnings) < 50:
            self.warnings.append(message)

    def estimate(self, field_name):
        self.estimates[field_name] = self.estimates.get(field_name, 0) + 1

    def point(self, x, y):
        self.point_count += 1
        if self.point_count > MAX_POINTS:
            raise ValueError("coordinate budget exceeded")
        if not self.extent_cm:
            self.extent_cm = [x, y, x, y]
        else:
            self.extent_cm = [min(x, self.extent_cm[0]), min(y, self.extent_cm[1]), max(x, self.extent_cm[2]), max(y, self.extent_cm[3])]

    def encode(self):
        data = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(data) > MAX_OUTPUT:
            raise ValueError("ImportLayer exceeds 12 MiB; use a smaller source area")
        return data
