# Track piece workspace

The 2026-09-30 [icon workbench replacement](WORKBENCH.md) supersedes immediate
palette placement, fixed shortcut UI and the previous visual presentation below.


New Map defaults to a track draft. Selecting free roam retains the existing map
editing tools. Track mode opens a primary 3D workspace and auxiliary plan, three
category palettes on the left, source properties on the right and connection /
course issues below. View changes and `free_roam` edits preserve geometry.

The generation dialog has only driving/gimmick/action category toggles, enabled
by default, plus seed, circuit/sprint, difficulty, time of day and target duration.
No category promises all its members. All-off disables Generate. Failure, cancel
or a stale completion keeps the current document. The estimate uses MapKit's
900cm/s reference speed and ±10% base-route contract.

The manual palette exposes all public supported pieces and widths. Select by list
or 3D click. Left drag moves on the selected elevation plane; numeric X/Y/Z and
Euler controls give unrestricted placement. Snap can be disabled; enabled dragging
snaps a nearby entry to another exit. Add, duplicate, delete, explicit port snap,
Bézier connection, control-point positions and entry/exit widths are source edits.
All geometry is rebuilt by MapKit and rendered by its production tessellator.

Choose a base/alternative route, append/remove selected roads or edit their order.
Choose a sample for the start, finish or intermediate common checkpoint. Add
independent jump/acceleration/booster/ring actions with optional landing road and
sample. Obstacles attach at a selected station. The composition button provides
a wide zigzag / upper jump shortcut example. Compiler issues explain disconnected
ports, branch-only checkpoints, clearance, landing or budget failures. Execution
export requires a valid graph; manual courses also require player completion.

The first geometry edit converts a seeded result to authoring source and retains
its original seed settings. Whole-document commands keep source, compiled output,
course bindings and provenance together through Undo/Redo. Disconnected drafts
save, reopen and recover through the ordinary project and explicit recovery-reader flow; export is
rejected. Existing non-track geographic geometry is preserved rather than erased
by an attempted track edit; create a New Map to start a separate track.

Focused `track_workbench_validator` covers draft save/reopen/recovery, export
rejection, Undo/Redo, stale edit/generation, failed generation retention, policy
preservation and initial layout. `assembled_track_validator` covers three-category
settings, seed-to-manual provenance and Undo/Redo. Detailed mouse editing, long
sessions, player test driving, OS/device and platform acceptance are user checks.

Automated delivery: both focused validators passed with strict behavioral diagnostics.
The basic standalone initial screen also passed on macOS arm64 / Godot 4.7.2.
The command fixture exercises palette placement, numeric movement, duplicate/delete,
free connection replacement, continuous-road action placement and Undo without
claiming detailed interactive acceptance.


Grounded seed policy (2026-09-30): first manual conversion keeps MapKit's
`grounded_supports` policy with the original seed settings. Source edits rebuild
the grounded floor and per-piece collision columns. The shared draft preview now
shows this floor and the same columns as execution. Independent new manual maps
and imported maps do not enable the policy. The focused assembly validator passed
policy preservation, Undo/Redo, project save/reopen with exact floor/support
records, and shared preview identities. Placement/generation failure still keeps
the existing document; detailed interactive editing remains user verification.


The 2026-10-01 [responsive editing implementation](TRACK_EDIT_PERFORMANCE.md) replaces
synchronous interactive track commits and whole-preview selection refreshes. It
documents live move ghosts, sequential cancellable worker edits, exact scoped
measurements (including the 49-piece seed latency miss) and user verification.


## Grind Line palette

`Grind Line` opens independent line authoring: straight/cubic control points in
centimetres, up frame, capture width and named start/end connections. `Add air
line` needs no supporting collider; `Add on selected fence` fits the selected
ordinary road's upper side, including curves. The public MapKit cap geometry is
used in the preview. Rail placement asks MapKit for an explicit initial line;
the line and rail remain independent after placement. Deleting a line removes
its incoming links and leaves the supporting collider.

Line edits use the existing cancellable source worker and history. IDs can be
renamed with link updates. Invalid edits retain the current document. Focused
`grind_line_validator` and existing `track_workbench_validator` cover editing,
connections, deletion, undo, save/reopen and cancellation. Detailed editor
interaction and game driving remain user verification.

Reproducible manual-flight/static-structure example: [Practice track](../examples/practice-tight-corners/README.md).

## Generation readiness progress

The generator displays a translated stage and shared circular percentage; unknown
search/preparation stages stay indeterminate. The button is disabled while busy.
Work continues through worker-prepared preview meshes before adopting the result.
Cancel, dialog close, changed document epoch and replaced request reject late
progress/completion and preserve the previous document. The common ring supports
reduced motion. English, Korean and Japanese stage labels are included.

The generation worker/preview adoption unit and shared progress validator pass,
including unknown search, measured stages, matching requests and prepared preview.
Detailed dialog interaction is user verification; no video was recorded.

## Panel surface placement

Attachment picking now intersects the actual shared preview road triangles,
including quantized transverse strips and current draft transforms. Panel ghosts
include their connected road support and use the same MapKit fitting path as the
committed attachment. Unsupported geometry remains an explicit placement error.
Native/load and focused UI-state verification are grouped with the partial-width
panel delivery. Detailed pointer interaction and device acceptance remain user
verification.

## Partial-width action editing

New attached speed/jump/chain tools default to50% of the road width after the
25cm side margins, centered. Placement controls offer25/50/75/100% and
Left/Center/Right; existing attached actions expose the same controls. Each edit
uses the ordinary source history and asynchronous compiler/preview path.
Preview cancellation does not alter the document. Undo/Redo and save/reopen keep
the explicit `panel_width_percent` / `panel_alignment` fields. Air-ring UI is
unchanged; all own formats remain v1 without old-source conversion.

Scoped validation passes; detailed pointer
editing and device readability remain user verification.

## Pipe material and dimensions

MapKit `cb37b0d7e20874957b437358fdc5dcbac148451f` supplies the shared matte
metal material and current pipe catalogue. New general pipes select the catalogue
2m default (explicit wide presets remain 4m); manual bores offer 1/2/3/4/6m. Pipe
and ramp port SpinBoxes use the catalogue 1m minimum. Ordinary road defaults and
2m minimum ports are unchanged. Existing stored 4/6m sizes remain editable.

Standalone cylinder radius controls allow 0.50–6m with centimetre precision,
so the new 1.25m radius is not rounded to a 0.1m input step. The template remains
16m long. Loop and halfpipe radius minima are unchanged. Stored colours are
preserved; preview uses the same MapKit material and geometry as display.

Strict Godot4.7.2/macOS arm64 checks pass: `pipe_edit_validator`, shared
`pipe_material_validator`, existing `track_workbench_validator`, and the refreshed
package's `practice_source_validator`. They cover new placement, all size choices,
compiled radius, cancellation/stale preview rejection, exact Undo/Redo, 4/6m
source save/reopen, standalone minimum/default input and ordinary-road defaults.
Initial test-fixture issues (localized labels instead of IDs, absent optional
gimmicks after Undo) were corrected; no product failure was hidden.

Previous practice packages remain preserved. Current output and reproduction
are described below. All own formats remain v1; detailed editing, material
preference and game driving remain user verification.

## Air ring defaults 09

Consumes MapKit 6c5e3a0. New automatic/manual rings and standalone preview now
use a3m opening and100% strength. Existing explicit ring parts/radius/strength
remain authoritative; no source migration is performed.
Scoped checks pass new defaults, full Euler
preview, explicit6m/37% preservation, Undo/Redo/save/reopen and practice source
unpack/recompile/reopen. The existing authoring validator was corrected to select
options by metadata and initialize an ordinary document; its earlier translated
label/assembled-document assumptions failed and timed out. Product editor code
needed no change. Detailed interactive authoring is user verification.

## Pipe minimum

MapKit now owns a 1m minimum radius/2m minimum bore. Editor reads the native
catalogue for standalone radius and assembled ports; manual choices are 2/3/4/6m.
The standalone 2.5m bore and 16m length remain. Existing source is not converted.
The scoped `pipe_edit_validator` passes minimum/default values, all editable
sizes, cancelled previews, Undo/Redo and save/reopen. A no-op 2m edit was corrected
in the test to edit 3m before undoing; no product history behavior was changed.

## Reproducible practice course

`scripts/practice_track.py` generates the ten-course manual source and package at
[examples/practice-tight-corners](../examples/practice-tight-corners/README.md).
Courses 2/3 are ordinary mirrored 90-degree turns with the former drift geometry:
6m radius and 8m width. Courses 4/5 are sharper mirrored 90-degree bends with 3m
radius and 4m width. Their approach narrows from 8m to 4m and runout widens back
to 8m; all neighbouring endpoints and port widths connect exactly. The remaining
jump, glide, raised grind beam, air turn and 3.6m climb dimensions are retained.
No drift-specific completion field or new format is introduced.

Collinear cubic joins retain exact 3m gate aprons and 4m pre-flight markers through
MapKit's ordinary curve sampling. The generator resolves checkpoint/action indices
from the current compiler's samples rather than duplicating tessellation constants.
The optional `--resource-path` binds the consumer entry to its new package path.
Existing output directories are rejected without overwriting them. All earlier
sources and generated packages remain preserved.

Current package SHA256:
`641ff8132f2fd7884e718a840bf177193b90db8477dcc2117de866d609694753`.
Python `test_practice_track.py` (4 tests), repeated generation/byte identity,
source recompile, CLI `verify-track`, mirrored geometry/continuous widths, exact
checkpoint/action stations and headless `practice_source_validator` open/edit/
save/reopen pass with the pinned MapKit on macOS arm64/Godot 4.7.2. Course metadata
retains `human_completion: unverified`; actual driving and detailed editor/device
acceptance remain user verification.
