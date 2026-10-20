"""Explicit review of unsupported source objects. The review list warns above
its former size; only its raised memory ceiling (and budget failures) stay fatal."""
import json
from import_layer import BudgetExceeded, soft_limit

MAX_EXCLUDED = 20000  # Warn above.
MAX_BYTES = 4 * 1024**2  # Warn above.
CEILING_EXCLUDED = 1_000_000  # Memory guard.
CEILING_BYTES = 64 * 1024**2  # Memory guard.


class Review:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.excluded = {}
        self.bytes = 0

    def reject(self, identity, reason):
        message = str(reason)
        if isinstance(reason, BudgetExceeded):
            raise BudgetExceeded(f"OSM {identity}: {message}")
        if not self.enabled:
            raise ValueError(f"OSM {identity}: {message}")
        if identity in self.excluded:
            return
        record = dict(source_id=identity, reason=message[:512])
        size = len(json.dumps(record).encode())
        if len(self.excluded) >= CEILING_EXCLUDED or self.bytes + size > CEILING_BYTES:
            raise BudgetExceeded("OSM exclusion review exceeds 1,000,000 objects or 64 MiB; use a smaller area")
        self.bytes += size
        self.excluded[identity] = record
        if len(self.excluded) > MAX_EXCLUDED:
            soft_limit("review_objects", len(self.excluded), MAX_EXCLUDED, "OSM exclusion review lists many objects")
        if self.bytes > MAX_BYTES:
            soft_limit("review_bytes", self.bytes, MAX_BYTES, "OSM exclusion review exceeds 4 MiB")

    def restore(self, count):
        """Drop the records after the first `count`, the review as it stood then."""
        for identity in list(self.excluded)[count:]:
            self.bytes -= len(json.dumps(self.excluded.pop(identity)).encode())

    def metadata(self):
        return dict(profile="explicit-source-exclusions-v1", excluded=list(self.excluded.values()))


def source_error(tags):
    if tags.get("_source_error"):
        raise ValueError(tags["_source_error"])
