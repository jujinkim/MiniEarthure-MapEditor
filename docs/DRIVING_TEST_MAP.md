# Offline driving map

`g01-driving-v1`, revision 1, is an original MIT four-cell 1,024 m square
project. It uses the current v1 source contract and contains no downloaded input. This is
small reproducible gameplay geometry, not a representative performance workload.
The reference profile remains independently frozen. Fixture map IDs and dimensions
are data, not format versions or the current default-world cell size.

The ready-to-open source is `examples/driving/`; the verified ready-to-use package
is `examples/driving.memap`. Copy the source to a new directory before editing
if you want to retain the baseline. To regenerate from the public Editor repository:

```sh
rtk proxy python3 scripts/driving_test_map.py /new/g01
```

Open `/new/g01` in MapEditor, Save (or Save As to a new directory), close and reopen,
then Export to a new `/new/g01.memap`. Existing destinations are preserved by the
creator and Editor export workflow. `document.json` is the editable source;
`driving.json` fixes the starting point, segment purposes and a simple sprint.
`tests/driving_map.lock.json` freezes the original source, package/world and all
four generated cell hashes. Save As may change Editor provenance; compare the
original fixture identity when testing deterministic regeneration.

| Segment | Exact map coordinates in cm | Purpose |
| --- | --- | --- |
| east-corner | default start (94000,30000), surface `east-corner` | Default vehicle heading follows increasing map Y; long straight, corners, building occlusion and Y=51200 seam |
| straight | (14000,16000) → (88000,16000) | Acceleration/braking and X=51200 seam; steer east/west before testing |
| tunnel | (88000,78000) → (10000,78000) | Ground approaches, descent to −600 cm, ceiling/walls and exit |
| west-bridge | (10000,78000) → (10000,16000), via X=4000 | Ground approaches, +600 cm deck and both grades |
| surface-lane | (22000,36000) → (80000,36000) | Asphalt → gravel at X=42000 → dirt at X=62000 |
| bumps | (22000,52000) → (40000,52000) | 100 cm deck, two 40 cm crests at X=30000/34000, with 20 m ramps |

The first four roads share exact graph endpoints as a closed circuit. Inner lanes
are independent test pads; choose their explicit surface spawn for comparison.
The bumps use authored elevated road geometry on a 100 cm deck so explicit
surface spawn is separated from the underlying terrain. They are not a raster
height accuracy claim.
MapKit's existing world scale applies; the coordinates above are source centimetres.

For gameplay, use a compatible application that accepts `.memap`, choose the fixed
start from `driving.json`, and retain the same vehicle/input configuration between
comparisons. Game-specific commands and controls belong to that application's
private documentation; this public repository has no game dependency.

Public native/compiler verification (new paths each time):

```sh
rtk proxy python3 -B -m unittest discover -s tests -p test_driving_test_map.py -v
rtk proxy env MAPEDITOR_DRIVING_ROOT=/new/g01 MAPEDITOR_DRIVING_REPORT=/new/result.json python3.12 scripts/check_documents.py --godot /path/to/godot --script driving_map_validator --script test_drive_validator --resource-pack --log-dir /new/logs
```

Build the matching public MapKit binding first. The validator opens/saves/reopens
through Editor, exports a new package, generates every cell, checks exact surface
heights and frozen hashes, and preserves the original source. `--resource-pack`
checks compiled host resources; it is not a native Windows/Linux distribution.
Human driving feel, complete circuit driving, target platforms and final gameplay
acceptance remain separate from these deterministic checks.

## Flat and hill physics fixture

[physics-test.memap](../examples/physics-test.memap) is a synthetic MIT test map:
one actual **128 × 128 m** cell, 33×33 PNG16 height samples, 4 m spacing and 2,048
terrain triangles. Hills reach 2 m and 1 m. Custom authoring metres are game metres;
there is no display multiplier. No objects or visual detail were removed.

Start at X=64 m, Y=32 m, surface `terrain`; the hill approach is X=88 m, Y=64 m.
The surface is grass. Vehicle forces and driving acceptance belong to the consumer.

```sh
rtk proxy python3 scripts/physics_test_map.py /new/physics-test
rtk proxy /path/to/mapkit pack /new/physics-test /new/physics-test.memap
rtk proxy python3 scripts/check_driving_school.py --mapkit /path/to/mapkit --project /new/physics-test --output /new/physics-check
```

The package is 1,519 bytes. `tests/physics_test.lock.json` locks its source and cell.
[Old source](../examples/physics-test-v1/) and [package](../examples/physics-test-v1.memap)
remain intact as reference artifacts. Their old scale measurements are not current
application acceptance; all own format versions remain v1.
