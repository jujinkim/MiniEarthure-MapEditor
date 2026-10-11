# Synthetic reference and scale fixtures

These are original MIT, offline, reproducible authoring workloads. They are not
surveyed regions, calibrated city densities or performance acceptance. Every tool
writes only to a new destination and refuses existing paths; generated projects and
packages are not committed. Cell size is a per-document value: these fixtures keep
their own sizes (512 m reference, 16 m scale), unlike the 32 m default worlds.

## Reference projects (`p01-synthetic-v1`)

`tests/reference_maps.lock.json` records source SHA-256, counts, centreline length,
bounds, provenance, routes, package/world hashes and size accounting. Change the
profile ID when changing the workload; never recalibrate it to pass a later gate.

- **baseline:** 10,000 × 10,000 m source (1,250 m at 1:8), 400 cells of 512 m
  including partial outer cells; four 5 × 5 km quadrants (urban/residential/rural/
  forest); 441 nodes, 840 connected road segments, 700 buildings, 200 vegetation
  rules, 400 terrain descriptors. All cells use 257 × 257 PNG16 grids at 2 m with
  zero edges; 64 forest cells share a 12.8 m tent/plateau payload. Sidewalks are
  deliberately zero-width.
- **baseline-user:** baseline plus one custom PNG and one box-proxy placement for
  custom-payload accounting.
- **structures:** 1,024 m square, four cells: ground junction, bridge/elevated
  crossings, underpass and tunnel with grades, a seam-crossing gable building,
  orchard, fence and streetlight. Bridge ends need explicit surface spawns.

A 2,100-building candidate exceeded existing placement work limits and was not
frozen; no generator limit was raised.

```sh
rtk proxy python3 scripts/reference_maps.py /new/reference-v1
rtk cargo build --manifest-path addons/mapkit/Cargo.toml -p mapkit-cli
rtk proxy addons/mapkit/target/debug/mapkit pack /new/reference-v1/baseline /new/reference-v1/baseline.memap
rtk proxy python3 -B -m unittest discover -s tests -p test_reference_maps.py -v
rtk proxy env MAPEDITOR_REFERENCE_ROOT=/new/reference-v1 MAPEDITOR_REFERENCE_REPORT=/new/native-results.json python3 scripts/check_documents.py --godot /path/to/godot --script reference_maps_validator --log-dir /new/checks
```

Pack `baseline-user` and `structures` the same way. The validator opens the Editor
store, exports/reopens, compares hashes and generates sample baseline cells, the
custom cell and every structure cell. Add `--resource-pack` to test compiled
resources. All 400 cells, OS parity, driving and real-region density are not covered.

## Scale fixtures

`scripts/scale_maps.py` builds a new source from this repository's driving-school
assets using only the Python standard library.

- 2,000 m square with 16 m execution cells and 64 m lots. **mixed** has equal
  urban/residential/rural/forest lots; **dense** repeats the urban lot (the six Hanbit
  shops, 25 placements and seven local roads) everywhere. At 2 km: mixed 2,475
  buildings / 7,200 placements, dense 5,400 / 22,500.
- Terrain uses 4 m samples, 1 cm quantization, zero seams and a 2 m central hill. A
  separate bridge route in the margin has 3 m elevation, ramps and its own spawn;
  test both the dense streets and the bridge.
- `scale.json` records hashes, quality signature, asset counts, bytes, road length,
  density, terrain, routes and limits. Every used asset is in the map; there is no
  shared-pack credit.

```sh
rtk proxy python3 scripts/scale_maps.py /new/l02-mixed --profile mixed
rtk proxy python3 scripts/measure_scale_maps.py /new/l02-mixed /new/l02-mixed-results --mapkit addons/mapkit/target/release/mapkit --side-cells 8 16
rtk proxy python3 -B -m unittest discover -s tests -p test_scale_maps.py -v
rtk proxy env MAPEDITOR_SCALE_CASES=/new/cases.json MAPEDITOR_SCALE_REPORT=/new/native.json python3 scripts/check_documents.py --godot /path/to/Godot --script scale_maps_validator --resource-pack --log-dir /new/native-build
```

`--size-m 288|1056` gives smaller controls; `--side-cells` compares regional storage
sizes without changing execution cells. The measurement tool writes a fresh package
per candidate and records commands, exits and sizes; a nonzero child result is a
failed stage. `MAPEDITOR_SCALE_CASES` is a JSON array of
`{"source","path","export","cells":[[x,y],...]}`; the validator performs native
audit admission, optional export parity and the listed cells. A refusal is kept as an
unsupported case. Larger 5–10 km areas need a separate decision.

## Route sidecars

`scripts/scale_routes.py` reads fixed source/package bytes and native-restored source
and writes a new `l02-road-routes-v1` sidecar; hashes, index digest and restored
records must agree.

| Profile | Coverage |
| --- | --- |
| `full` | Residential/rural/forest and transition corridors plus bridge grades; roads ≥4 m with a 2 m clear corridor |
| `shuttle-240` | Four connected 64 m lots: 240 m flat routes with 4 m stopping room |
| `turns` | Forward outbound/return routes through shared nodes; flat asphalt ≥4 m wide |
| `forest-hill` | Derivative adds a 4 m road through one retained 2 m hill (`scripts/scale_hill_maps.py`) |
| `bridge-shuttle` | 256 m full or 160 m east-ramp routes over a 6 m bridge with 32 m ramps |

```sh
rtk proxy /path/to/mapkit unpack-regions /existing/map.mkregions /new/restored 1073741824
rtk proxy python3 scripts/scale_routes.py /existing/source /existing/map.mkregions /new/routes.json --restored /new/restored --profile turns
```

Hill/bridge profiles also take `--mapkit` and `--native-output`. Sidecars are fixture
diagnostics, not pathfinding or driving proof. Unit tests: `test_scale_*.py`.
