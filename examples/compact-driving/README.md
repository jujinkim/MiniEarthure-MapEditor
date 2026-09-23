# Compact driving districts

Seven original MIT maps retain the previous regional identity at half the width
and depth. Original `regional-districts` and `regional-miniatures` sources and
packages remain unchanged. This directory owns all new placements, terrain,
road widths, start grading, challenges and three route records per map. MapKit
owns the reusable geometry and declarative motion contract. Embedded font notices
remain in the source assets and packages.

Run from the superproject with its Python environment (Pillow is required):

```sh
rtk proxy .venv/bin/python map-editor/scripts/compact_maps.py /tmp/new-compact-driving --kit map-kit
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-compact-driving/haeon /tmp/new-compact-driving/haeon.memap
rtk proxy env MAPKIT_ROOT="$PWD/map-kit" .venv/bin/python -m unittest discover -s map-editor/tests -p test_compact_maps.py
```

Always generate into a new directory. `region.json` contains metre dimensions,
districts, challenges with bypass widths, explicit acceleration sections, start
grading and ordered route points. Challenge spacing is normally 35 m. A protected
Kanupi technical-start approach intentionally has an 81.41 m acceleration interval.
Intro routes use a safe lane; technical routes use the district loop; sprints use
longer/elevated connections. Route bounds are 350–600 / 500–900 / 600–1000 m;
the previous unconditional 900 m minimum is no longer the current rule.

`tests/test_compact_maps.py` checks deterministic source/package bytes, source
hashes, height seams, connected roads, four-district challenge coverage, kinds,
active sites, bypass widths, spacing and route lengths. Consumer-specific vehicle
and course proof validation is not part of this public project. Detailed driving,
artistic quality and editing UX require user review.
