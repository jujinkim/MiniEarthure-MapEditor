# Track piece workspace

This document covers the Editor UI and workflow. Piece geometry, the catalogue,
ports, pipe/ring dimensions and compiler rules belong to MapKit's
[track authoring contract](https://github.com/jujinkim/MiniEarthure-MapKit/blob/main/docs/TRACK_AUTHORING.md).
Icons, palettes and shortcuts are in [WORKBENCH](WORKBENCH.md); drafts and latency
in [TRACK_EDIT_PERFORMANCE](TRACK_EDIT_PERFORMANCE.md).

## Workspace

New Map defaults to a track draft; selecting free roam keeps the ordinary map tools.
Track mode opens a primary 3D workspace with an auxiliary plan, driving/gimmick/action
palettes on the left, source properties on the right and connection/course issues
below. View changes and `free_roam` edits preserve geometry.

Select a piece in the list or by 3D click. Left drag moves it on the selected
elevation plane; numeric X/Y/Z and Euler fields allow any placement. With snap
enabled a nearby entry snaps to another exit. Add, duplicate, delete, port snap,
Bézier connection, control points and entry/exit widths are source edits; MapKit
rebuilds and tessellates all geometry.

The Driving palette includes five extra-wide presets with a fixed 12 m body
(`straight_extra_wide`, `gentle90_extra_wide[_left]`, `right90_extra_wide[_left]`)
and five ultra-wide 18 m presets (`straight_ultra_wide`,
`gentle90_ultra_wide[_left]`, `right90_ultra_wide[_left]`). Entry/exit controls
read the catalogue limits and allow 4–18 m on ordinary roads and transitions. English,
Korean and Japanese names and the stable IDs are searchable; their SVGs carry a
vector-stroked "12" or "18" badge. Newly compiled vertical loops are 10.5 m high
with a 5.25 m radius; their ribbon and the spiral-turn dimensions are unchanged.

Choose a base/alternative route, append/remove roads or reorder them, and pick
samples for start, finish and intermediate checkpoints. Add jump/acceleration/
booster/ring actions with an optional landing road; obstacles attach at a station.
Compiler issues explain disconnected ports, branch-only checkpoints, clearance,
landing or budget failures. Execution export requires a valid graph; manual courses
also require player completion.

Whole-document commands keep source, compiled output, course bindings and provenance
together through Undo/Redo. Disconnected drafts save, reopen and recover, but export
is rejected. A track edit never erases existing geographic geometry; use New Map for
a separate track.

## Seed generation

Seed Track creates a new unsaved document through MapKit's cancellable worker.
Save/discard/Cancel protects the previous document; document and request epochs
reject obsolete results. The dialog offers driving/gimmick/action toggles (all on by
default; all off disables Generate), seed, circuit/sprint, easy/normal/hard,
time of day and a 60/90/120-second target. No category guarantees any member. The
base route must meet MapKit's ±10% reference-time bound at 900 cm/s; actual time
depends on vehicle and input. New panels pick a random seed; reopening restores the
saved settings, source, placements and fingerprints.

Progress shows a translated stage and the shared circular percentage; search and
preparation stay indeterminate. Generate is disabled while busy. Cancel, dialog
close, document change or a newer request discard late results and keep the last
valid document. The ring honours reduced motion.

The first geometry edit converts the seeded result to authoring source and keeps its
seed settings and MapKit's
[`grounded_supports` policy](https://github.com/jujinkim/MiniEarthure-MapKit/blob/main/docs/ASSEMBLED_TRACKS.md#grounded-supports);
the draft preview shows the same floor and support columns as execution. New manual
and imported maps do not enable that policy.

## Grind lines

`Grind Line` edits straight/cubic control points in centimetres, up frame, capture
width and named start/end connections. **Add air line** needs no collider; **Add on
selected fence** fits the selected road's upper side. Rail placement requests an
initial line from MapKit; line and rail are then independent. Deleting a line
removes incoming links and keeps the collider. IDs can be renamed with link updates.

## Attachments and partial-width actions

Attachment picking intersects the actual preview road triangles, including draft
transforms. Panel ghosts use the same MapKit fitting path as the committed
attachment; unsupported geometry is an explicit error. New speed/jump/chain actions
default to 50% of the width inside the 25 cm side margins, centred; placement and
existing actions offer 25/50/75/100% and Left/Center/Right
(`panel_width_percent`, `panel_alignment`).

## Pipes and rings

MapKit supplies width/port limits and defaults: roads use 4/6/8/12 m and dedicated
18 m presets,
manual placement defaults to 4 m, and ports and loop ribbons start at 4 m.
Manual and generated pipes use 4/6 m bores; standalone cylinders default to a
4 m bore and 16 m length. Geometry edits use the same shared validation. New rings use a 3 m opening and 100% strength. Explicit stored sizes,
colours and ring values remain authoritative. Opening a saved narrow v1 map keeps
its exact geometry and control values. Recompilation reports the offending instance
and fields until the user repairs them. Undo restores saved geometry within the
existing history budget; it does not recompile a narrow original.

## Validation

`track_workbench_validator`, `assembled_track_validator`,
`extra_wide_track_validator`, `grind_line_validator` and `pipe_edit_validator`
cover placement, snapping, generation settings, cancellation and stale results,
Undo/Redo and save/reopen. Detailed pointer editing, long sessions, driving and
devices are user checks.

## Reproducible practice course

`scripts/practice_track.py` generates the ten-course manual source and package at
[examples/practice-large-rc](../examples/practice-large-rc/README.md).
Courses 2/3 are mirrored 90° turns with 6 m radius and 8 m width; courses 4/5 are
sharper mirrored 90° bends with 4 m radius and 6 m width, narrowing from 8 m and
widening back to 8 m with exact port widths. The remaining courses keep the jump,
glide, raised grind beam, air turn and 3.6 m climb.

Cubic joins keep exact 3 m gate aprons and 4 m pre-flight markers through MapKit's
curve sampling; the generator resolves checkpoint/action indices from compiler
samples. `--resource-path` binds the consumer entry to the package path. Existing
output directories are rejected. Validate with `tests/test_practice_track.py`, CLI
`verify-track` and `practice_source_validator`; `human_completion` stays
`unverified` until a user completes it.
