# Document, history and recovery contract

Current contract: `document_store.gd` separates the latest accepted
authoring draft from the last MapKit-validated MapDocument. `track_source()` returns
the draft. `draft_changed`, `validated_changed` and `file_operation_finished` have
separate consumers; worker completion never resets the next gesture or inspector
input. MapKit owns schema, native paths, normalization and derived geometry. Views
are never serialized. The record-edit contract below still applies to free-roam
commands; interactive track commands use the source transactions described next.

## Continuous track editing and explicit locks

Release immediately accepts an immutable before/after source memento and updates
the draft display. One drag is one command; the common **200 commands / 16 MiB**
retention budget covers both stacks. No-op commands preserve redo. Undo/Redo move
the source immediately, independently of computation. Compilation failure retains
the submitted draft, its history and the last valid document, with a revision/target
error; a later edit clears that error. Calculation cancellation retains the draft.
Editing, Undo/Redo, Save or Validate resumes unconfirmed work.

One running worker and one latest pending snapshot bound calculation demand.
New edits do not cancel the running calculation. Results must match store/session,
request ID, command epoch and draft revision and be unconsumed before adoption.
Old-session and superseded results cannot update document, history or savepoint.
MapKit `track_instance` supplies current cached paths for selection, snapping,
attachments, curves, framing and the navigation plan. Shared draft display reuses
rigidly moved meshes, draws changed paths and attachment/grind guides, and hides
obsolete heavy geometry. Final preview adoption waits for the current drag or
text input to finish; completed calculations never rebuild the active inspector.

Automatic track validation has no dim or edit lock. An unconfirmed calculation
lasting 500 ms shows a small indeterminate “Applying changes” indicator; successive
edits do not reset its timer. The existing reduced-motion preference and English,
Korean and Japanese catalogs apply.

Save, Save As and execution export finish the current terrain stroke in memory,
cancel other unsubmitted gestures, and lock edits while keeping the UI and camera
responsive. One file request freezes the last submitted revision,
waits for its validation, and performs file work on an owned worker. Only actual
successful publication advances the savepoint. Normal project Save accepts valid
structural drafts with course issues; execution export additionally checks that
snapshot's connections/courses. Failure/cancellation retains draft/history and
unlocks only after owned work ends. A rename that already succeeded is reported
as a completed Save even if a cancellation arrived afterward. Synchronous store
helpers remain for detached workers, imports and fixtures; they honor the same
explicit lock and cannot save unconfirmed content.

## Commands and gestures

For record commands, `document_store.gd` applies a batch to a detached candidate, validates it through
MapKit, then publishes it once. Failed commands, undo or redo leave the document,
history, dirty state and savepoint unchanged. Callers must handle the returned
error string. No-op batches preserve redo and do not change edit timestamps.

Record patches contain `field`, `id`, `before` and `after` (null means absent).
Supported collections are nodes, roads, buildings, zones, assets, placements,
repetitions, heightmaps and attributions. Use `record_id(field, record)` to obtain
the key: ordinary object ID, canonical cell JSON for heightmaps, or the canonical
`[source, license, notice]` tuple for attribution records. Changing a composite
key uses remove+insert in one batch. An ambiguous identical duplicate fails
without choosing or rewriting a user record. Scalar patches for bounds, cell
size, seed, explicit recipe, theme and terrain base omit `id`; identity and
producer provenance are not freely editable map values.

Each retained record Command/Memento contains only the touched records' first-before
and final-after values, captured after native normalization. Unchanged objects,
whole documents and rendered meshes are not history entries. E03 file commands
add only their affected immutable binary payloads to the same retention budget.
Undo and redo share **200 commands / 16 MiB of UTF-8 patches and sparse binary height deltas**. Moving
between stacks retains the charge; a new branch releases redo, then evicts oldest
undo entries as needed. One oversized command is rejected before publication.
This is a serialized retention budget, not a claim about allocator overhead/RSS.
Candidate validation and JSON encoding still require transient document copies.

`begin_gesture(label)` → `stage_patches(batch)` → `commit_gesture()` coalesces
repeated edits to a record into one command. Each staged sample's `before` must
match the previous staged `after`. Staging never changes the committed document;
an invalid batch preserves the prior staged batch. Pending mementos have their
own 16 MiB cap while the retained history remains intact. The commit validates
the whole result. Cancel discards pending work; saving or history travel requires
finishing/cancelling the gesture. No timer or document transition writes recovery.

The existing polygon drag uses this boundary. Motion affects only its preview;
release commits once. Escape, tool/focus change and document replacement discard
the gesture. Old mouse releases cannot modify a replacement document. New/Open/
Recover reset history; returning by Undo to saved content clears dirty (edit time
alone does not make content dirty). Scene and worker generation invalidation
continues through the document's `changed` signal.

Terrain uses sparse before/after height samples plus water patches in one command;
see [AUTHORING.md](AUTHORING.md). File-command raw before/after bytes count toward
the shared 16 MiB budget. History detects changed payloads before travel. Cell
identities use canonical integer coordinates across JSON number/key normalization.
Incremental preview is defined in [PREVIEW_EXPORT.md](PREVIEW_EXPORT.md).

## Save and recovery

`document_files.gd` writes a flushed, closed unique `.pending-<id>` file, retains
the current primary as `.previous`, then replaces the primary with one rename.
It never moves the current primary away first. Failure leaves the old primary
and interrupted candidates available. Expected SHA-256 checks detect sequential
external changes before and during saving. Existing unrelated project files are
not silently overwritten by Save As. These checks are not collaborative locking;
simultaneous writers at the final rename boundary are outside this single-user
contract. Filesystem/power-loss durability beyond Godot flush/rename is not proven.

Only **Save**, **Ctrl+S**, or **Cmd+S** publishes the project. A new map can be
sculpted and filled before selecting a directory. Dirty content highlights Save;
Undo/Redo reaching the saved content clears it. Sparse modified sample sets and a
saved baseline determine terrain dirtiness; there is no per-frame full-document
serialization/hash. Save preserves both history stacks. Repeated Save of an
unchanged existing project performs no writes. Failure or cancellation keeps edits
and the previous baseline.

Terrain arrays and detached resource providers feed queries, road fitting, previews,
validation and explicit outputs. Brush `finish` records memory history; it never
encodes PNG. The Save worker freezes the revision, waits for current water/track
validation, encodes only changed PNG16 tiles, installs immutable payloads and
publishes the document last. Source checksums and destination conflicts remain
checked. A successful publication alone updates the baseline.
The working document keeps command source identities separate from published PNG
descriptors. Save therefore preserves earlier import → sculpt → Undo/Redo chains;
Save As includes the original referenced bytes needed by those commands.

New/Open/Recover and Close offer **Save and continue**, **Continue without saving**,
or **Cancel**. Cancelling the first-save picker cancels the transition. Discarding
writes no recovery copy. Existing recovery files are preserved. The old 15-second
timer and transition/exit recovery writes are removed. Tests create explicit v1
recovery fixtures to verify the retained reader; production does not create them.

Use **Recover** to select an existing recovery snapshot, `.previous`, or a complete `.pending-*`
document. Opening a corrupt project suggests this path. Selection is explicit;
no recovery file is automatically adopted, repaired or deleted. A valid snapshot
restores content with fresh history and dirty state. Truncation, bad checksum,
unsupported version, invalid schema or relative origin rejects the candidate
without replacing the current document/native session.

A retained recovery snapshot retains its original disk base: if someone saved a newer project,
Save reports a conflict. Reopen that project or use **Save As** to a new directory.
An explicitly selected raw previous/pending document binds the current primary
digest and can restore it with Save; later external changes still conflict.
Incomplete or corrupt envelopes are rejected. No historical envelope loader or
automatic converter is provided; original recovery files are preserved.

Recovery contains document records and file references, not copies of imported
PNGs/GLBs or other source files. Keep original referenced files available; preview
and packaging validate them. Save As copies current and Undo/Redo-only asset/heightmap files into a new directory,
validates the candidate and publishes its document last; see
[PREVIEW_EXPORT.md](PREVIEW_EXPORT.md). Original files are retained. Recovery history is separate from
map contents. Old session snapshots and interrupted candidates are retained for
the user; automatic disk cleanup is not implemented.

## Standalone checks

After building the public MapKit binding, run without any private game checkout:

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --script document_history_validator --script document_recovery_validator --script terrain_native_validator --log-dir /new/path/editor-document-checks
```

The Python stdlib runner copies only Editor scripts/scenes, the public renderer
and the current native library into a disposable project. It verifies a temporary
platform-specific `user://` directory before executing tests, retains logs/source
hashes, fails engine diagnostics even at exit 0, and removes its own temporary
project/data. It never tests against the Editor's normal user directory.

Continuous editing evidence adds
held-worker/clock, lock, publication-race and draft recovery checks.

`document_history_validator.gd` covers grouped edits, exact save/reopen, no-ops,
stale/partial failure, metadata identity, both budget caps and canvas cancellation.
`document_recovery_validator.gd` covers write/backup/publish failures, origin/hash/
size validation, conflicts and the three-way unsaved guard. It starts disposable Godot
children that kill **themselves** before backup, before primary replacement and
after replacement, then verifies primary/previous/pending recovery. Kill messages
from these fixtures are expected; script/engine failures are not.

Mac arm64 scoped checks and compiled resource-pack execution pass. Native Windows/
Linux exports and UI/filesystem acceptance remain open: install matching Godot
4.7.2 templates and target-native MapKit builds, run the command above, export the
documented preset and exercise edit → drag/cancel → Undo/Redo → Save → restart →
Recover → Save → re-open with synthetic files. Require no partial document/history
mutation or silent conflict overwrite. Actual terrain tools/full map authoring
and installed Client driving remain E01/E03/E04/E05 acceptance.
