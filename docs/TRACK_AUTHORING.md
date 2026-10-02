# Track piece workspace — 2026-09-30

The 2026-09-30 [icon workbench replacement](ICON_WORKBENCH.md) supersedes immediate
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
save, reopen and recover through the ordinary project/autosave flow; export is
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


## Grind Line palette — 2026-10-01

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

Reproducible manual-flight/static-structure example: [Practice track](../examples/practice-track/README.md).

## Generation readiness progress — 2026-10-02

The generator displays a translated stage and shared circular percentage; unknown
search/preparation stages stay indeterminate. The button is disabled while busy.
Work continues through worker-prepared preview meshes before adopting the result.
Cancel, dialog close, changed document epoch and replaced request reject late
progress/completion and preserve the previous document. The common ring supports
reduced motion. English, Korean and Japanese stage labels are included.

The generation worker/preview adoption unit and shared progress validator pass,
including unknown search, measured stages, matching requests and prepared preview.
Detailed dialog interaction is user verification; no video was recorded.
