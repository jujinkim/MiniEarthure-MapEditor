# Document, history and recovery contract

E02 implementation, 2026-09-09. The Editor's validated MapDocument dictionary is
the source of truth. MapKit owns its typed schema, normalization and invariants.
JSON is storage; canvas selection, drag offsets, drafts, panels and generated
preview nodes are presentation state. No Scene tree is serialized into a project.

## Commands and gestures

`document_store.gd` applies a batch to a detached candidate, validates it through
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
Undo and redo share **200 commands / 16 MiB of serialized UTF-8 mementos**. Moving
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
finishing/cancelling the gesture. Autosave captures only committed content.

The existing polygon drag uses this boundary. Motion affects only its preview;
release commits once. Escape, tool/focus change and document replacement discard
the gesture. Old mouse releases cannot modify a replacement document. New/Open/
Recover reset history; returning by Undo to saved content clears dirty (edit time
alone does not make content dirty). Scene and worker generation invalidation
continues through the document's `changed` signal.

E03 now uses this boundary for raster brushes and immutable binary tile mementos;
see [AUTHORING.md](AUTHORING.md). File-command raw before/after bytes count toward
the shared 16 MiB budget. History detects changed payloads before travel. Cell
identities use canonical integer coordinates across JSON number/key normalization.
Incremental preview remains E04 work.

## Save and recovery

`document_files.gd` writes a flushed, closed unique `.pending-<id>` file, retains
the current primary as `.previous`, then replaces the primary with one rename.
It never moves the current primary away first. Failure leaves the old primary
and interrupted candidates available. Expected SHA-256 checks detect sequential
external changes before and during saving. Existing unrelated project files are
not silently overwritten by Save As. These checks are not collaborative locking;
simultaneous writers at the final rename boundary are outside this single-user
contract. Filesystem/power-loss durability beyond Godot flush/rename is not proven.

Autosave runs every 15 seconds while dirty and before replacing or closing a dirty
document. New/Open/Recover and window Close stop if retention fails; the status
shows the error. Each document session gets a separate recovery path, so another
session cannot overwrite it. Unchanged snapshots do not rotate. Snapshot version
1 carries the validated document checksum, original project directory and disk
base checksum. Snapshots and input JSON are bounded to 64 MiB before reading or
writing; MapKit's smaller package document limits still apply at packaging.

Use **Recover** to select an autosave, `.previous`, or a complete `.pending-*`
document. Opening a corrupt project suggests this path. Selection is explicit;
no recovery file is automatically adopted, repaired or deleted. A valid snapshot
restores content with fresh history and dirty state. Truncation, bad checksum,
unsupported version, invalid schema or relative origin rejects the candidate
without replacing the current document/native session.

An autosave retains its original disk base: if someone saved a newer project,
Save reports a conflict. Reopen that project or use **Save As** to a new directory.
An explicitly selected raw previous/pending document binds the current primary
digest and can restore it with Save; later external changes still conflict.
Legacy envelopes without a checksum can be read after native validation, but
cannot silently replace an existing primary without a known base.

Recovery contains document records and file references, not copies of imported
PNGs/GLBs or other source files. Keep original referenced files available; preview
and packaging validate them. Save As for documents with external assets/heightmaps
is blocked rather than writing a project with missing files; copying those files
belongs to the remaining file/export tools. Recovery history is separate from
map contents. Old session snapshots and interrupted candidates are retained for
the user; automatic disk cleanup is not implemented.

## Standalone checks

After building the public MapKit binding, run without any private game checkout:

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --full --log-dir /new/path/editor-document-checks
```

The Python stdlib runner copies only Editor scripts/scenes, the public renderer
and the current native library into a disposable project. It verifies a temporary
platform-specific `user://` directory before executing tests, retains logs/source
hashes, fails engine diagnostics even at exit 0, and removes its own temporary
project/data. It never tests against the Editor's normal user directory.

`document_history_validator.gd` covers grouped edits, exact save/reopen, no-ops,
stale/partial failure, metadata identity, both budget caps and canvas cancellation.
`document_recovery_validator.gd` covers write/backup/publish failures, origin/hash/
size validation, conflicts and UI retention failures. It starts disposable Godot
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
