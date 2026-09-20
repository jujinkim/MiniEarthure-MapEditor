# Authored regional districts

Seven independent current-v1 maps. The 2026-09-21 redesign prioritizes visible
urban density and distinct land use over the former 110,000 m² size limit.
Haeon's business avenues, irregular market blocks, contour housing streets and
quays are authored separately. The other maps have their own road networks,
terrain functions, settlement patterns and three recommended routes.

The original `regional-miniatures` sources/packages are preserved. Reusable
models belong to MapKit `examples/district-library`; this directory owns all
placements, roads, terrain, signage, district boundaries, landmarks and routes.
No game course codec is included in the public editor.

From the superproject with Python 3.12:

```sh
rtk proxy .venv/bin/python map-editor/scripts/district_maps.py /tmp/new-regional-districts --library map-kit/examples/district-library
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-regional-districts/haeon /tmp/new-regional-districts/haeon.memap
rtk proxy env MAPKIT_ROOT="$PWD/map-kit" .venv/bin/python -m unittest discover -s map-editor/tests -p test_district_maps.py
```

`region.json` contains source hashes, metre dimensions, district/landmark
records, road paths, starting locations and ground-level review cameras. The
shared offline renderer `tests/render_regional_maps.gd` accepts REGIONAL_SOURCE,
REGIONAL_DESTINATION and optional comma-separated REGIONAL_IDS. Its whole-map
capture coalesces visible surfaces and uses an offline-only template cache;
consumer streaming policies and memory caps are unchanged.

Generated sources are original MIT geometry and layouts. Embedded sign assets
retain their upstream OFL font notices. Each source/package is self-contained.
Detailed driving and artistic acceptance remain user checks.
