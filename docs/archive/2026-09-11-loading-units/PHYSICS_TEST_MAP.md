# Physics test map

`examples/physics-test.memap` is an original MIT, terrain-only vehicle tuning map.
It has one 1024 × 1024 authored-metre cell (128 × 128 m at the game's 1:8 scale),
a 33 × 33 PNG16 heightfield and 2,048 terrain triangles. No roads, buildings,
vegetation, placements, assets or external textures are authored. Most ground is
flat; two smooth compact hills reach 16 m and 8 m in authoring coordinates
(2 m and 1 m in the game). Terrain uses the existing terrain material and grip.

The flat starting point is X=512 m, Y=256 m, surface `terrain`, heading 0°.
The hill approach is X=704 m, Y=512 m on the same surface and faces uphill.
The current game sedan can stall on this slope; this is a useful tuning repro,
not evidence that the heightfield failed to load. No vehicle constants changed.
The finite outer boundary retains the consuming runtime's existing recovery.

Recreate in a **new** directory using the deterministic authoring script, then
pack using the public MapKit CLI (existing destinations must not be overwritten):

```sh
rtk proxy python -B scripts/physics_test_map.py /new/physics-test
rtk proxy /path/to/mapkit pack /new/physics-test /new/physics-test.memap
```

`tests/physics_test.lock.json` records native package validation, exact source
repacking and all-cell generated hashes. The existing generic native fixture
checker can verify this single-cell project despite its historical school name:

```sh
rtk proxy python -B scripts/check_driving_school.py --mapkit /path/to/mapkit --project examples/physics-test --output /new/physics-evidence
```

2026-09-11 Windows native validation: package 1,541 bytes, 1 cell, 0 user asset
bytes; source repack and generation passed in 0.109 seconds. Source SHA-256
`fef187fb54a05a417f2257cac4f92092ada71f37937324075302769fb23114ec`, package SHA-256
`3b2e750d7f03217ab7e4bb797da8e07a87bd986854d9a7c7749a1186881773e7`.
Original and regenerated source document/heightfield are unchanged by the final
starting-point metadata adjustment. No schema, recipe implementation or native
dependency changes are required. Client owns its bundled copy and selection UI.
