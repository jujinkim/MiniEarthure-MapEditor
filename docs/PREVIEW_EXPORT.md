# Incremental preview, Save As and package output

E04 implementation, 2026-09-09. This public Editor unit uses the unchanged MapKit
native generator, queries, estimates, file validator, compressor and shared renderer.
No game installation, new recipe, package schema or native ABI is required.

## Preview

Choose a cell and **3D Preview**. Committed edits refresh the selected cell after
150 ms of inactivity. Source changes during generation cancel the old request;
changing cells, New/Open/Recover and **Cancel operation** cannot attach an old
result to the new selection. Cancel stops automatic pending refresh until another
edit or explicit request. Cancellation is observed between native calls; it does
not preempt one native validation/compression/generation call.

One worker owns a detached canonical document and immutable referenced-file
snapshot. It validates files/seams through MapKit and builds an Editor object/cell
invalidation index with native closed-cell queries. The index is rebuilt from each
snapshot; it is not an incrementally persisted database or a new package index.
Only selected cells whose dependency signature changed are generated/attached.
Unchanged cached cells retain the same scene nodes. Each generated affected cell
still uses the complete MapKit generator; Editor never generates partial physics.

The index deliberately over-invalidates: a one-cell Editor halo plus authored
proxy extents surrounds vector bounds. Local roads, zones and repetitions retain
the global road/node/building/zone/placement/repetition dependency closure because
junctions, sidewalks, tree spacing and ordered suppression can depend on other
objects. Assets/materials and their bytes are shared dependencies; terrain depends
on its cell's exact descriptor/bytes. Global map generation fields invalidate all
cells. Provenance-only and 2D Show/Lock/opacity changes do not change geometry.
This favors correctness over minimal regeneration; representative-map index and
snapshot cost remains a performance gate.

A hidden candidate is attached with the same MapKit renderer in batches. The
previous visible root is retained until successful completion; failure or cancel
releases only the candidate. Batch admission targets **8 ms/frame**, uses observed
batch cost to yield before another batch, and records maximum batch/frame times.
An indivisible mesh/GLB operation may exceed that target; there is no hard engine
preemption or claim that whole-frame p95/RSS has been accepted.

Editor admission limits: 64 MiB unique source payloads, 200,000 object/cell index
references, 4 MiB overview JSON, 256 MiB source-derived preview-work charge and
four cached cells with a combined 256 MiB charge. Cache eviction occurs on candidate
publication; the old cache and one candidate may coexist. Work charge includes
native scratch, conservative per-triangle/ID/object and presentation allowances.
These are admission estimates, not measured allocator/GPU/RSS bounds. Package
validation has its own native peak/retained estimates; the report keeps them
separate. Over-budget work fails visibly without evicting the current preview.

## Save As

Choose a directory without an existing `document.json`. Save As preserves relative
asset/heightmap paths and byte contents and copies **both current and Undo/Redo-only
referenced files**. It validates the current candidate with MapKit, verifies binary
mementos, rejects missing/changed/over-budget sources and conflicting target files,
and refuses symlink destinations for payloads. Existing identical payloads may be
reused. It never relocates or deletes originals, saved versions or recovery files.

Each new payload is flushed to a unique pending file, hash-checked and renamed.
All copied files are checked before `document.json` is published last through the
existing document writer. The live path, savepoint and dirty state change only
on success; history remains usable from the copied directory. Recovery snapshots
written afterward refer to the new directory. Existing snapshots retain their
old origin and original files remain available.

A failed copy publishes no new document. It can leave new immutable payloads or
pending files in the selected directory, retained for inspection/retry; no user
cleanup is performed. Copying/validating Save As is synchronous and bounded by the
64 MiB source limit, not a background or latency guarantee. Single-user conflict
checks do not provide cross-process locks or power-loss durability beyond Godot
flush/rename. See [DOCUMENTS.md](DOCUMENTS.md) and [AUTHORING.md](AUTHORING.md).

## Validate and Export

**Validate** and **Export .memap** run on the same worker with an immutable source
snapshot. Neither implicitly saves edits or changes the document/history/dirty
state. Export's UI requires an existing project directory; the snapshot includes
committed unsaved edits. A selected existing package filename is refused.

The report shows file/seam/schema/inventory validation, native cell count, Editor
index references, a shared MapKit 2D road/building overview, native memory estimates
and elapsed operation time. The overview is read-only and ignores view layers;
it is not a full 3D image or a new package resource.

Capacity distinguishes total compressed ZIP bytes, compressed user-asset payloads,
expanded base data and expanded user assets. The displayed base-package count is
**total ZIP bytes minus compressed user-asset payloads**: ZIP headers, manifest and
all metadata remain charged to the base. It is a conservative accounting partition,
not the size of a hypothetical separately repacked asset-free map. The 50,000,000
byte base goal produces a visible over-goal report, not a new format rejection.

**Full 3D check on Validate / Export** is optional and off by default. It generates
all map cells sequentially through MapKit with the same per-cell work admission,
reports completed-cell progress and discards each result. It checks generation,
not full-map renderer attachment, actual driving or target-device performance.
Default validation still checks all package files and terrain seams.

Export writes only inside its own scratch directory until successful validation
and compression. Main-thread completion checks the document generation and cancel
state, copies to a unique destination-side pending file, verifies its hash and
renames to the absent destination. A cancelled/stale/invalid result never publishes
a package; current preview and existing outputs stay available. The short final
copy/hash/rename step is synchronous. Scratch belonging to completed/cancelled work
is removed; interrupted process scratch and failed destination pending files are
not garbage-collected. Native calls and final publication are single-user operations.

## Checks and remaining acceptance

```sh
python3 scripts/check_documents.py --godot /path/to/godot --full --log-dir /new/path/checks
python3 scripts/check_documents.py --godot /path/to/godot --script preview_export_validator --script workbench_validator --rendered --log-dir /new/path/rendered
MAPEDITOR_CAPTURE_PATH=/new/path/report.png python3 scripts/check_documents.py --godot /path/to/godot --script capture_export_report --rendered --log-dir /new/path/report-check
```

The public runner isolates synthetic sources, process state and `user://`, records
source/native hashes and fails engine diagnostics. E04 checks cover actual Preview
button input, automatic refresh, same-root reuse, remote/local changes, LRU,
selection/revision/cancel races, dense terrain frame yields and mid-attachment
cancellation, source/work budgets, independent copies and history/recovery,
file conflicts/corruption, optional full generation and compressed-byte accounting.
The 1024x720 capture checks report bounds and native rendered overview.

Mac focused native/headless/rendered checks and compiled Editor resource execution
pass. Native Windows/Linux export attempts still fail for missing Godot 4.7.2 mono
export templates; matching target bindings and OS runners are also needed. Run the
same tests and exported Editor on both OSs, including native dialogs, copying,
restart/recovery, cancel/retry and original-data preservation. E05's complete
empty-map authoring → installed Client driving, representative-map p95/RSS/GPU,
public anonymous clone and final integration remain separate acceptance gates.
E04 implementation delivery is not final product/platform acceptance.
