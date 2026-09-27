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
