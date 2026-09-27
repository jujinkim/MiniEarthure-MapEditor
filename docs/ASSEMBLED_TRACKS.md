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
