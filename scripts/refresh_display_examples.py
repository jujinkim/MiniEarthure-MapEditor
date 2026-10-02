#!/usr/bin/env python3
"""Copy authored examples and bind current MIT library assets, preserving inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def refresh(source: Path, destination: Path, library: Path):
    if destination.exists():
        raise ValueError(f"Refusing existing destination: {destination}")
    catalogue = json.loads((library / "library.json").read_text())
    replacements = {entry["id"]: entry for entry in catalogue["assets"]}
    shutil.copytree(source, destination)
    updated = 0
    for path in sorted(destination.glob("*/document.json")):
        document = json.loads(path.read_text())
        changed = False
        for asset in document["assets"]:
            replacement = replacements.get(asset["id"])
            if replacement is None:
                continue
            content = (library / replacement["path"]).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            target = "assets/" + digest + ".glb"
            if (path.parent / asset["path"]).read_bytes() == content:
                continue
            asset.update({key: value for key, value in replacement.items() if key != "path"})
            asset["path"] = target
            (path.parent / target).write_bytes(content)
            changed = True
            updated += 1
        if changed:
            document["revision"] += 1
            document["provenance"].update(build_id="display-library-v1", last_edited="2026-10-02T00:00:00Z")
            path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"Refreshed {updated} library bindings in {destination}; inputs preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    refresh(args.source, args.destination, args.library)
