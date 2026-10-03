# Fixed practice track (v1)

This MIT example is an authored source, an editable project and its compiled
`.memap`. Edit `scripts/practice_track.py` and regenerate into a **new** directory;
never patch generated collision or rendering geometry. The compiler is the pinned
MapKit CLI. No external data, private dependency or human completion evidence is
included. `courses.json` explicitly records human completion as unverified.

```sh
python3 scripts/practice_track.py /absolute/new-output --mapkit /absolute/mapkit
```

`source.json` contains 31 connected pieces and 11 ordered checkpoints. Open
`project/` with the project store, or unpack the package's authoring source. The
first ten checkpoints name each stopped-start apron; the eleventh is completion.
`entry.json` includes the package SHA-256 and the first entry point. A downstream
application may use it separately from its ordinary map catalogue.

| Course | Fixed geometry |
| --- | --- |
| 1 | 8 m wide straight, 20 m approach / 16 m runout, drive/brake/reverse |
| 2–3 | 8 m wide, 32 m radius right/left turns |
| 4–5 | 8 m wide, 6 m radius right/left turns |
| 6 | 0.36 m high, 0.24 m deep low barrier |
| 7 | 12 m unsupported glide gap, 20 m landing |
| 8 | 18 m gap, solid 0.20 × 0.20 m beam top and independent line 0.45 m above road |
| 9 | 4 m wide right-angle air route; departure 2 m earlier, unchanged landing |
| 10 | 10 m gap, 3.60 m wall and raised 20 m landing |

The supported road ends at each flight gap: no ground supports or invisible road
bridge are generated. Manual-flight actions reference a supported takeoff and
landing. They create neither jump nor boost panels. The five static structures
are the low barrier, beam, high wall and 1m-high start/end lane barriers; all go through shared source compilation.
The fixed environment is noon, with no per-entry random generation.

## Current tutorial geometry — 2026-10-03

Raised beam/line and earlier air departure are generated from the authoring script.
Package SHA256: `2eb57e620efb1dd41c3c29b99e0c506e35a72982913a37c5bd73a6b36cb417c8`.
[Reproducibility and source reopen evidence](../../docs/validation/tutorial-air-grind-2026-10-03/README.md).

## Earlier continuous-clearance fingerprint refresh — 2026-10-03

Recompiled the preserved, byte-identical `source.json` into a new directory with
MapKit `47a07f13d7e05ede6fe8d6376b0665df12f4db2f`. Only seven generator/derived
identity fields changed; all geometry, samples, courses and dimensions are equal.
Package/entry SHA256:
`36c07f812f9436d53798e1e542f9edf2d8e6e39f4a962b7390b5148784cc652b`.
CLI validation and native Editor source/save/reopen pass. Original packages and
sources remain preserved; human completion remains unverified.
[Scoped evidence](../../docs/validation/straight-clearance-2026-10-03/README.md).

## Earlier wall-preparation fingerprint refresh — 2026-10-03

Recompiled from the preserved, byte-identical `source.json` with MapKit
`425d67b02675e191f4e786ed14cf1a5d791e7d1b` after piece-local wall preparation.
Only generator/derived identity fields changed; geometry, samples, courses and
approved dimensions match the previous package. Package/entry SHA256 is
`8de012b0c189449c14f8f6826c178904497f480ae2f8c87a8985407e0d039727`.
CLI validation and native Editor source/save/reopen pass. The old package remains
preserved; human completion is still unverified.
[Current implementation and scoped results](../../docs/TRACK_EDIT_PERFORMANCE.md#fixed-input-latency-improvement--2026-10-03).

## Earlier geometry refresh — 2026-10-03

**Regenerated and verified with MapKit `e563b8d1`.** The separate invalid-action
and corner-clearance failures were reproduced and their original files/logs
preserved. Finite straight-road clearance is corrected in MapKit; this example
retains its approved 8 m width / 6 m radius and all authored geometry/order.
Sample references come from current compiler path distances. Two fresh output
directories match byte-for-byte, stored source recompiles to the same package,
and Editor source extraction/open/edit/save/reopen preserves exact identity.
Package/entry SHA256:
`4745728b36f1573c7f989732a6fe1c1b635779e40e41d52b34ed2a8727e5eebc`.
[Current evidence and retained failures](../../docs/validation/practice-refresh-2026-10-03/README.md).
`human_completion` remains `unverified`; detailed driving is a user check.

## Verification (2026-10-01)

`tests/test_practice_track.py` passed both source/geometry checks and two byte-equal
fresh exports, `verify-track`, source identity, eleven checkpoints and absence of
completion proof. `tests/practice_source_validator.gd` passed package source unpack,
project open, edit/save and reopen with strict diagnostics. See
[the retained result](../../docs/validation/practice-2026-10-01/editor-practice_source_validator.log).
The isolated placement preview omits whole-track static structures when showing
one piece; full compilation retains them. Editor interaction and human driving
acceptance are separate, unperformed user checks.

## Playtest dimensions — 2026-10-02 / T10

The first three approach straights shrink from30m to20m and runouts from20m to16m.
Checkpoint gates are located near3m into each supported start; manual flight
references near4m before departure. A temporary MapKit compilation resolves
indices from real distances, so this script copies no tessellation constants.
The final original records those indices and reproduces byte-identical exports.
[2026-10-02 focused results](../../docs/validation/playtest-2026-10-02/README.md).
