"""Explicit review of unsupported source objects; aggregate quotas stay fatal."""
import json


class Review:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.excluded = {}
        self.bytes = 0

    def reject(self, identity, reason):
        message = str(reason)
        if not self.enabled or "budget" in message.lower():
            raise ValueError(f"OSM {identity}: {message}")
        if identity in self.excluded:
            return
        record = dict(source_id=identity, reason=message[:512])
        self.bytes += len(json.dumps(record).encode())
        if len(self.excluded) >= 20000 or self.bytes > 4 * 1024**2:
            raise ValueError("OSM exclusion review budget exceeded; use a smaller area")
        self.excluded[identity] = record

    def metadata(self):
        return dict(profile="explicit-source-exclusions-v1", excluded=list(self.excluded.values()))


def source_error(tags):
    if tags.get("_source_error"):
        raise ValueError(tags["_source_error"])
