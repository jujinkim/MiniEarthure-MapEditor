# Fixed practice track (v1)

This is a preserved fixture. For the active authoring workflow, see
[track authoring](../../docs/TRACK_AUTHORING.md#reproducible-practice-course).
[Revision history](../../docs/history/REFERENCE_WORLDS.md#practice-package-revisions)
is optional; `entry.json` identifies this exact package.

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

## Validation scope

The recorded source/geometry, byte-equal export, source reopen/edit/save and
package verification checks passed for this fixture. The isolated piece preview
omits whole-track static structures; full compilation retains them. Detailed
Editor interaction and human driving remain unperformed user checks.
