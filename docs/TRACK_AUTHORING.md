# Track piece workspace — 2026-09-30

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
