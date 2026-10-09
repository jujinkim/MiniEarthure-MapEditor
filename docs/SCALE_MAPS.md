# Scale and route fixtures

The scale sources and route sidecars below are preserved synthetic stress fixtures.
Their original 16m cells and recorded runs are not the current default-world 32m
profile or a current size/performance acceptance claim. Use matching current-v1
tooling and fresh outputs; never convert the original artifacts automatically.

`scripts/scale_maps.py` creates a **new**, original synthetic source directory.
It uses only this public repository's versioned driving-school source and MIT
assets. It needs Python's standard library; rebuilding the unrelated town/kart
geometry and installing Shapely are unnecessary. Existing destinations are refused.
The shipped town and previous reference fixtures are never rewritten.

The first stage is 2,000 × 2,000 metres with 16m execution cells. Mixed and dense
conditions use identical 64m lot spacing at every tested size. The mixed map has
equal numbers of urban, residential, rural and forest lots. Dense repeats the
urban lot everywhere. Each urban lot retains the exact six Hanbit shops, all 25
placements, seven local roads, collision declarations and model bytes. Two access
roads join the block to an explicit connected grid. Residential lots have four
houses/two benches, rural lots one house/orchard, and forest lots a vegetation
rule plus one 16m hill tile. Source vegetation rules are not generated tree counts.

At 2km there are 30 × 30 lots. Mixed has 2,475 building instances and 7,200 total
placements; dense has 5,400 buildings and 22,500 placements. Building instances
are custom model placements, **not** the empty procedural `buildings` array.
Occupied lot area is 3,686,400m²; the 313,600m² outer margin is reported separately.
This repetition is controlled stress, not an accepted city composition or a
claim that the entire surface meets a person's art-quality expectations.

Terrain uses 4m samples, 1cm quantization, exact zero seams and a synthetic 2m
central hill, with implicit flat terrain outside declared tiles. Source accuracy
is unknown/not applicable. A separate full-width bridge route in the margin has
explicit 3m elevation, ramps and a surface-specific spawn. It is not silently
connected to the block grid. Both the dense local street and the clear bridge
route must be tested: the bridge alone cannot establish dense-area performance.
The metadata's 8/12m/s targets describe stress scenarios, not a consumer vehicle
speed guarantee. Driving evidence must record the actual selected vehicle's
maximum speed; do not modify physics to manufacture a pass.

`scale.json` records source hashes, exact quality signature, asset hashes/counts,
unique and hypothetical unshared instance bytes, road length, local/global
density, terrain, routes and limits. All declared assets are included in the map;
there is **zero installed-common-pack credit**, no new common download and no
bundled generated accelerator. Repeated file bytes are not repeated downloads,
and shared transfer bytes are not a shared renderer memory claim.

## Reproduction

From this repository, with a built, matching public MapKit CLI/native binding:

```sh
rtk proxy python3 scripts/scale_maps.py /new/l02-mixed --profile mixed
rtk proxy python3 scripts/scale_maps.py /new/l02-dense --profile dense
rtk proxy python3 scripts/measure_scale_maps.py /new/l02-mixed /new/l02-mixed-results --mapkit addons/mapkit/target/release/mapkit --side-cells 8 16
rtk proxy python3 scripts/measure_scale_maps.py /new/l02-dense /new/l02-dense-results --mapkit addons/mapkit/target/release/mapkit --side-cells 8 16
rtk proxy python3 -B -m unittest discover -s tests -p test_scale_maps.py -v
```

`--size-m 288` and `--size-m 1056` provide smaller controls with the same lot
geometry and density. The outer margin and resulting global density remain
explicit. `--side-cells 4 8 16` compares 64/128/256m storage without changing 16m
execution cells. Arbitrary larger area is not accepted just because authoring
succeeds; 5/10km runs require a successful preceding workload decision.

The measurement tool verifies original hashes, invokes the actual CLI, records
each command/exit/timeout, and writes a fresh package for every storage candidate.
It records exact compressed/expanded bytes from the hash-checked front index;
that accounting is **not** a substitute audit. Full CLI audits use the unchanged
512MiB and 1GiB limits. A recorded nonzero child result is a failed stage, even
though the measurement process successfully produced evidence. macOS additionally
records `/usr/bin/time -l` process peak RSS; other platforms leave it unavailable.
Do not run competing workloads for calibrated performance measurements.

Native validation uses a JSON array supplied as `MAPEDITOR_SCALE_CASES`:

```json
[{"source":"/new/l02-mixed","path":"/new/l02-mixed-results/side-8.mkregions",
  "export":false,"cells":[[3,3],[63,3],[3,63],[64,64],[4,0]]}]
```

```sh
rtk proxy env MAPEDITOR_SCALE_CASES=/new/cases.json MAPEDITOR_SCALE_REPORT=/new/native.json python3 scripts/check_documents.py --godot /path/to/Godot --script scale_maps_validator --resource-pack --log-dir /new/native-build
```

This builds and executes the standalone compiled Editor resources, performs
native audit admission/refusal, optionally checks native/CLI export byte parity,
generates specified cells only after full admission, and verifies cancellation
does not invalidate an independently held source. A refusal is preserved as an
unsupported case. The native consumer audit includes metadata/overview allowances
in addition to the CLI audit; report the two separately. Consumer scheduling,
rendering, collision, input, network and lifetime tests belong to each consumer.

## Route sidecars

`scripts/scale_routes.py` reads fixed source/package bytes and native-restored
source, then writes a new `l02-road-routes-v1` test sidecar. Source/payload hashes,
index digest and semantically equal restored records must agree. Collection order
and omitted empty collections may normalize; road points and geometry stay exact.
This is fixture tooling, not pathfinding or a substitute for full native admission.

| Profile | Coverage and required limits |
| --- | --- |
| `full` | Residential/rural/forest and transition corridors, plus separate bridge grades; 8m ground endpoint trims; source roads ≥4m and obstacle-free 2m corridor |
| `shuttle-240` | Four connected 64m lots with 8m trims: 240m complete flat routes and 4m stopping room beyond each end; mixed or dense even grid ≥8 lots |
| `turns` | Separate forward outbound/return routes through shared graph nodes; flat orthogonal asphalt ≥4m wide/16m long; ≤32 edges/128 support roads; 2m-radius targets, 1.10m sweep and 4m stopping room |
| `forest-hill` | A new derivative source adds a 4m road and 6m vegetation exclusion through one retained 2m hill; preserve original terrain/assets and audit generated height/normal references |
| `bridge-shuttle` | Separate 256m full or 160m east-ramp routes; 6m bridge, two 32m ramps with 3m relief, 12m stopping room and 1.10m sweep; native audit ≤64 cells/2,048 faces/4,096 probes |

Flat shuttle stopping support and obstacle envelopes are checked explicitly.
Turns use exact shared-node connectivity and full swept-box road-union coverage,
not coordinate overlap or corner samples. Forest-hill derivatives use
`scripts/scale_hill_maps.py`, retain the original hill PNG and place the centreline
0.40m from its apex. Bridge probes sample at ≤25cm with upward normal >0.9,
height error ≤10cm and relief ≥285cm. These diagnostics do not prove driving.

```sh
rtk proxy /path/to/mapkit unpack-regions /existing/map.mkregions /new/restored 1073741824
rtk proxy python3 scripts/scale_routes.py /existing/source /existing/map.mkregions /new/routes.json --restored /new/restored --profile turns
```

Hill/bridge profiles also take `--mapkit` and `--native-output`; all outputs must
be new. Failed native stages cannot publish an accepted sidecar. Frozen historical
index/size comparisons are available through Git and preserved artifacts, not a
supported old-reader path. The owning unit tests are `test_scale_*.py`; no new
execution is claimed by this documentation cleanup. Consumer traversal, timing,
loading, collision and device acceptance are separate. Broad 5–10km expansion and
source-residency changes remain outside the approved scope.
