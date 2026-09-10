"""Explicit local EGM96 supplements for missing original structural OSM nodes.

The exact source snapshot is bound by SHA-256. No source tag is overwritten and
no height, datum or connectivity is inferred. Public MIT; offline only.
"""
import hashlib
import re
from import_layer import number, text, strict_json
from vertical import CRS

MAX_BYTES = 256 * 1024
MAX_NODES = 4096
ORDER = "fill missing original nodes before graph normalization, datum conversion and crop"


def read_source(path):
    if not path.is_file(): raise ValueError("height supplement must be a local file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not 0 < len(raw) <= MAX_BYTES: raise ValueError("height supplement requires 1..256 KiB")
    return raw.decode("utf-8")


class Supplement:
    def __init__(self, raw):
        if not isinstance(raw, str) or not 0 < len(raw.encode("utf-8")) <= MAX_BYTES:
            raise ValueError("height supplement requires UTF-8 JSON of at most 256 KiB")
        value = strict_json(raw)
        keys = {"format", "osm_sha256", "source", "license", "accuracy", "vertical_crs", "nodes"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("invalid height supplement fields")
        if value["format"] != "miniearthure-osm-node-heights-v1" or value["vertical_crs"] != CRS["EGM96"]:
            raise ValueError("height supplement requires absolute EGM96 metres, before target conversion")
        if not isinstance(value["osm_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["osm_sha256"]):
            raise ValueError("height supplement requires the exact OSM snapshot SHA-256")
        for key in ("source", "license", "accuracy"): text(value[key], "height supplement " + key)
        entries = value["nodes"]
        if not isinstance(entries, list) or not 0 < len(entries) <= MAX_NODES:
            raise ValueError("height supplement requires 1..4096 nodes")
        self.heights = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"node_id", "height_m"}:
                raise ValueError("height supplement node requires node_id and height_m")
            identity = entry["node_id"]
            if not isinstance(identity, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", identity) or int(identity) > 2**63-1:
                raise ValueError("height supplement node ID must be a canonical positive int64 string")
            if int(identity) in self.heights: raise ValueError("duplicate height supplement node ID")
            self.heights[int(identity)] = number(entry["height_m"], "supplement elevation", -10000, 10000)
        self.osm_sha256 = value["osm_sha256"]
        self.metadata = dict(profile="osm-node-heights-v1", order=ORDER, applied_nodes=len(entries),
            source=dict(json=raw, bytes=len(raw.encode("utf-8")), sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest()))

    def apply(self, nodes, node_tags, ways, source_sha256):
        if source_sha256 != self.osm_sha256:
            raise ValueError("height supplement OSM snapshot SHA-256 mismatch; prepare for this exact file")
        structures = {ref for _, kind, refs, tags in ways if kind == "road" and
                      (tags.get("bridge", "no") != "no" or tags.get("tunnel", "no") != "no") for ref in refs}
        eligible = {ref for _, kind, refs, _ in ways if kind == "road" and
                    any(n in structures for n in refs) for ref in refs}
        # At most the already-admitted 200000 source refs; supplementary IDs do
        # not fetch nodes, enlarge closure or introduce nonstructural roads.
        result = dict(node_tags)
        for identity, height in self.heights.items():
            if identity not in nodes or identity not in eligible:
                raise ValueError(f"height supplement node {identity} is unreferenced by selected structures/approaches")
            tags = node_tags.get(identity, {})
            if "ele" in tags:
                raise ValueError(f"height supplement node {identity} already has OSM ele; conflicts/redundant overrides are forbidden")
            # Copy only changed dictionaries: the captured source is immutable.
            result[identity] = dict(tags, ele=format(float(height), ".17f").rstrip("0").rstrip("."))
        return result
