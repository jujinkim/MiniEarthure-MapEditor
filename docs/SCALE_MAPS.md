# L02 area and density experiments

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

## Initial measured boundary (macOS arm64, 2026-09-11)

| 2km condition | Storage side | Complete file B | Expanded records B | Native audit |
| --- | ---: | ---: | ---: | --- |
| Mixed | 128m | 29,066,928 | 379,277,989 | 512MiB refuses; 1GiB passes, 873,501,200B peak |
| Mixed | 256m | 7,536,599 | 97,779,668 | 512MiB refuses; 1GiB passes, 874,568,272B peak |
| Dense | 128m | 58,769,616 | 895,448,743 | 512MiB and 1GiB refuse; also exceeds 50,000,000B |
| Dense | 256m | 15,257,626 | 231,146,207 | 512MiB and 1GiB refuse |

The main size amplification is regional source duplication, including global
roads/rules, not the unique models (675,064B mixed; 511,620B dense). Larger storage
reduces transfer duplication while retaining a large source validation workspace.
It does not solve dense 2km admission. No limit, quality model, proxy or source
validation was relaxed. The 288m controls pass native audit at both budgets for
all three storage candidates, and five sampled generated hashes agree across
storage sizes. These are scoped observations, not whole-map or platform support.

A 1,056m dense control (16 × 16 lots, 1,536 buildings) produces 5,950,536B at
128m storage and 2,021,115B at 256m. Both refuse 512MiB audit and pass 1GiB native
audit, requiring 707,927,022B and 710,724,654B respectively. This narrows the
admission boundary without changing lot quality; it is not a maximum-size claim.

The frozen `tests/scale_maps.lock.json` owns authored identity/counts. External
integration reports own consumer runs, actual frame/CPU/RSS/GPU and deferred
device/human acceptance. Source sharding/global dependency and audit-cost work
is a separate implementation decision; this experiment does not change MapKit's
format, transport, validation limits or generation contracts.

## L01-C same-source storage comparison (2026-09-12)

The existing sources, lock, lot density, terrain and all asset hashes are unchanged.
With MapKit index v2, mixed 2km packages are 1,481,432/781,915B at 128/256m storage;
dense 2km packages are 2,293,070/1,375,142B. Expanded records are respectively
13,025,027/8,022,910B and 23,790,760/16,775,740B, including all original payloads.
Complete native audit passes 512MiB for mixed and 1GiB for dense. Dense still
refuses 512MiB. The 288m controls and 1,056m dense control pass native 512MiB.
Native admission does not include the game screen's existing memory reservations.

The compiled Editor runs 387 scale checks plus export/reopen and preview/export
regressions using the matching v2 native build. Across all 12 old/new artifact
pairs, 126 sampled cells preserve generated geometry and occupied solids. The
old v1 artifacts and original failures remain comparison evidence. This storage
improvement does not authorize 5/10km expansion or complete L02 performance/device
acceptance; use the same reproduction commands with fresh output directories.
