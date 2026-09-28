# Seed Track

Use **Seed Track** to choose seed, circuit/sprint, approximate duration,
difficulty, candidate special pieces and time of day. Basic geometry varies
automatically; four identical pieces is the maximum consecutive run. Dimensions,
catalogue, generation and package verification are owned by MapKit.

Generation and initial package save run through MapKit's cancellable worker.
The result opens as a new unsaved document; the original project remains on disk
and dirty source is autosaved to recovery first. A changed document epoch or
cancelled/replaced request prevents a late result from replacing the current
document. Existing Save/Export and 2D/3D preview work with the generated document.
Reopening retains seed, settings, resolved placements and generator fingerprints,
and reopening Seed Track restores those settings. No piece authoring or manual
piece-layout tool is introduced.

`tests/assembled_track_validator.gd` covers original/recovery preservation,
new-document semantics, save/reopen and settings restoration. Detailed editor
interaction and driving acceptance are user verification.

The 2026-09-28 catalogue adds left curves to the always-available basic shapes;
neither curve direction is shown as an optional gimmick. The existing generated
document/save/reopen/settings test passes against the new seeded circuit layout.

2026-09-28 short-track follow-up: time choices come directly from MapKit's
catalogue. Circuit offers 30 seconds/1 minute/2 minutes **per lap**, with maximum
3/3/2 laps; sprint offers 1/2/3 minutes. The default is a one-minute circuit.
Settings store `duration_seconds`; basic sharp corners and hairpins are automatic
geometry. The current catalogue requires regenerated packages; existing files
are preserved without automatic conversion.

2026-09-28 vehicle-scale follow-up: the existing **Cylinder** checkbox represents
MapKit's `selection_groups.cylinder` family. Variant names do not create extra
controls. The generated shape, source frames and bounds remain MapKit-owned;
the driving-structure panel asks the native `special_track_bounds` API for
bounds instead of copying shape constants, and preserves the 1 m swept bore
radius when loading it. Generation/save/reopen/settings and native swept bounds
are checked with synthetic documents. Detailed editing/preview acceptance is a
user check.

2026-09-28 catalogue-load fix: the panel checks the required `selection_groups`
dictionary before creating controls. A stale loaded native module now produces
restart guidance with generation disabled, not a Dictionary access error or an
old-catalogue fallback. Settings restore is a no-op in that state. The focused
validator covers missing groups and the current single cylinder-family control.


2026-09-28 RC venue replacement: the shared catalogue now mixes 2m/4m roads and
2m/4m curved tubes, retains one Cylinder checkbox, and exposes eight additional
choices: banked U chicane, jump hurdle, ramp/overpass shortcut, roller hills,
offset landing, slalom walls, rotating sweepers and lifting gates. Seed selects
indoor carpet, outdoor circuit or toy plastic. Shared MapKit rendering supplies
the stage and track materials; generated packages must be regenerated for the
current catalogue fingerprint. Original files are preserved. Detailed driving,
whole races, multiplayer and manual application acceptance remain user checks.

## Mandatory variety settings — 2026-09-28

The current catalogue adds the plain 32m sprint lane. Every checked family is
required, so the estimate may exceed the requested time. Descriptions explain
6/4/2m widths, seeded straight/corner balance and consecutive special sections.
Generation reports actual estimated seconds and the ordinary-road straight share.
The new document/recovery/epoch and cancellation behavior is unchanged. Focused
`assembled_track_validator` covers checkbox/result display and source preservation;
detailed authoring and driving remain user tests. See root `docs/SEED_TRACK_VARIETY.md`.
