"""Copy the authored snow world to a new directory and clear its ordinary roads."""
from pathlib import Path
import argparse
import json
import shutil


def create(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("Choose a new directory; existing sources/packages are preserved")
    destination.mkdir(parents=True)
    shutil.copytree(source / "snow-mountain", destination / "snow-mountain")
    path = destination / "snow-mountain/document.json"
    document = json.loads(path.read_text())
    document["revision"] += 1
    for road in document["roads"]:
        road["snow_retention_percent"] = 15
        road["surfaces"] = ["asphalt"] * len(road["surfaces"])
        road["markings"] = dict(road.get("markings", {}), color=[39, 43, 49], lanes=2,
                                center_line=True, edge_lines=True,
                                crosswalk_start=False, crosswalk_end=False)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    (destination / "arcade-world.json").write_text(json.dumps({"maps": ["snow-mountain"]}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    create(args.source, args.destination)
