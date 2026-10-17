# Document, history and recovery contract

`document_store.gd` separates the latest accepted authoring draft from the last
MapKit-validated MapDocument. `track_source()` returns the draft. `draft_changed`,
`validated_changed` and `file_operation_finished` have separate consumers; worker
completion never resets the next gesture or inspector input. MapKit owns schema,
native paths, normalization and derived geometry. Views are never serialized.
Free-roam record edits use the command contract below; interactive track edits use
source transactions.

## Continuous track editing and explicit locks

Release accepts an immutable before/after source memento and updates the draft
display. One drag is one command. No-op commands preserve redo. Undo/Redo move the
source immediately, independently of computation. A compile failure keeps the draft,
its history and the last valid document with a revision/target error; the next edit
clears it. Editing, Undo/Redo, Save or Validate resumes unconfirmed work.

One running worker and one latest pending snapshot bound calculation; new edits do
not cancel the running one. Results must match store/session, request ID, command
epoch and draft revision before adoption. MapKit `track_instance` supplies cached
paths for selection, snapping, attachments, curves, framing and the plan. Preview
adoption waits for the current drag or text input to finish. An unconfirmed
calculation lasting 500 ms shows a small "Applying changes" indicator; there is no
dim or edit lock.

Save, Save As and execution export cancel unsubmitted gestures and lock edits
while the UI and camera stay responsive. One file request freezes the last submitted revision, waits for its
validation and works on an owned worker. Only successful publication advances the
savepoint. Project Save accepts valid drafts with course issues; execution export
also checks connections/courses. Failure or cancellation keeps the draft/history and
unlocks after owned work ends; a rename that already succeeded is reported as saved.

## Commands and gestures

Record commands apply a batch to a detached candidate, validate it through MapKit,
then publish once. Failed commands, Undo or Redo leave document, history, dirty
state and savepoint unchanged; callers handle the returned error string. No-op
batches preserve redo and do not change edit timestamps.

Record patches contain `field`, `id`, `before` and `after` (null means absent) for
nodes, roads, buildings, zones, assets, placements, repetitions, heightmaps and
attributions. `record_id(field, record)` returns the key: object ID, canonical cell
JSON for heightmaps, or `[source, license, notice]` for attributions. Changing a
composite key uses remove+insert in one batch; an ambiguous duplicate fails. Scalar
patches for bounds, cell size, seed, recipe, theme and terrain base omit `id`;
identity and producer provenance are not editable values.

Each retained command stores only touched records' first-before and final-after
values after native normalization, plus affected immutable binary payloads. Undo and
Redo share **200 commands / 16 MiB** of patches and sparse height deltas. A new
branch releases redo, then evicts the oldest undo entries; one oversized command is
rejected before publication. This is a serialized budget, not an RSS claim.

Commands with at least 1 MiB of text use a private lossless Zstandard envelope when
smaller (expanded ≤48 MiB; length, SHA-256 and shape checked). Detached import
transfer is limited to 24 MiB compressed / 96 MiB expanded; the native document
stays at 32 MiB. Large city imports remain one atomic command.

`begin_gesture(label)` → `stage_patches(batch)` → `commit_gesture()` coalesces
repeated edits into one command. Each staged `before` must match the previous staged
`after`; staging never changes the committed document and pending mementos have
their own 16 MiB cap. Cancel discards pending work; Save and history travel require
finishing or cancelling the gesture. Escape, tool/focus change and document
replacement discard a gesture; old mouse releases cannot modify a new document.
New/Open/Recover reset history; returning by Undo to saved content clears dirty.

Heightmap and asset imports keep binary payload mementos; see
[AUTHORING](AUTHORING.md). History detects changed payloads before travel. Cell
identities use canonical integer coordinates.

## Save and recovery

Only **Save**, **Ctrl+S** or **Cmd+S** publishes the project; there is no timer,
transition or exit autosave. Dirty content highlights Save. Save keeps both history
stacks; an unchanged repeat Save writes nothing.

The Save worker freezes the revision, waits for track validation, reuses unchanged
payloads, installs immutable payloads and publishes `document.json` last. `document_files.gd` writes a
flushed `.pending-<id>` file, keeps the current primary as `.previous`, then replaces
the primary with one rename. Expected SHA-256 checks detect external changes before
and during saving. Failure keeps the dirty state, old primary and interrupted
candidates. Command source identities stay separate from published PNG descriptors,
so import → Undo/Redo chains survive Save.

**Save As** requires a directory without a document and copies current plus
Undo/Redo-only asset and heightmap payloads, validates the candidate and publishes
the document last. Original files and recovery snapshots are preserved.

New/Open/Recover/Close offer **Save and continue**, **Continue without saving** or
**Cancel**; cancelling the first-save picker cancels the transition. **Recover**
selects an existing recovery snapshot, `.previous` or complete `.pending-*` document;
nothing is adopted, repaired or deleted automatically. A valid snapshot restores
content with fresh history. Truncation, bad checksum, unsupported version, invalid
schema or relative origin rejects it. A recovered snapshot keeps its original disk
base, so Save reports a conflict with a newer project; use Save As instead.

Recovery holds records and file references, not copies of PNG/GLB sources; keep
referenced files available. Old snapshots, interrupted candidates and unreferenced
immutable payloads are kept; there is no automatic disk cleanup. Conflict checks are
single-user, not locking; durability beyond Godot flush/rename is not proven.

## Standalone checks

After building the public MapKit binding:

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --script document_history_validator --script document_recovery_validator --script terrain_native_validator --log-dir /new/path/editor-document-checks
```

The runner copies Editor scripts, the renderer and the native library into a
disposable project with an isolated `user://`, fails on engine diagnostics even at
exit 0 and removes its temporary data. `document_history_validator`,
`city_history_validator` and `document_recovery_validator` cover grouped edits,
budgets, compressed history, conflicts and crash recovery; recovery fixtures kill
their own child processes, so those kill messages are expected. Native Windows/Linux
exports, filesystem behavior and full authoring sessions are user checks.
