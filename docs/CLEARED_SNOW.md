# Cleared Snow Mountain — 2026-09-27

The new source is `examples/cleared-snow/snow-mountain`; its v1 package is beside
it. `scripts/cleared_snow.py` copies the preserved arcade source into a new
nonexistent destination, increments the source revision and sets ordinary roads
to asphalt, 15% snow retention, dark base color, yellow center and white edges.
Natural snow terrain, scenery, geometry, placements, gimmicks and route layout
remain unchanged. Prior sources, packages and completion evidence are preserved.

Selected road properties expose **Snow retention (%)** (0–100, default 100).
The edit shares the existing atomic graph command, validation, undo and export
path. MapKit owns schema, hashes and presentation. The native authoring validator
passed 99 assertions including the new property. A separate fresh-directory
reproduction matched every source and package byte; unpack succeeded.

```sh
rtk proxy .venv/bin/python map-editor/scripts/cleared_snow.py map-editor/examples/arcade-world /tmp/new-cleared-snow
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-cleared-snow/snow-mountain /tmp/new-cleared-snow/snow-mountain.memap
```

Actual overview, ground and signature captures use the source's initial wet/snow
stages. Shared material captures passed snow stages 0/1/2 contrast and markings.
Detailed editor interactions, driving and device acceptance remain user tests.
The package SHA-256 is `db1256b54c4f218a730521703c67bab1533214b9df532861af2f84314683ff67`.
