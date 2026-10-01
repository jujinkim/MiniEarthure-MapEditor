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
| 8 | 18 m gap, one solid 0.20 × 0.20 m beam and one independent grind line |
| 9 | 4 m right-angle route with the corner missing |
| 10 | 10 m gap, 3.60 m wall and raised 20 m landing |

The supported road ends at each flight gap: no ground supports or invisible road
bridge are generated. Manual-flight actions reference a supported takeoff and
landing. They create neither jump nor boost panels. The five static structures
are the low barrier, beam, high wall and 1m-high start/end lane barriers; all go through shared source compilation.
The fixed environment is noon, with no per-entry random generation.

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
[Current focused results](../../docs/validation/playtest-2026-10-02/README.md).
