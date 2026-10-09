# Memory preview and explicit output

Terrain, water, records and referenced resources form one detached MapKit working
snapshot. Height queries, road cut/fill, display, validation and export read that
snapshot, including unsaved height arrays. Editor owns commands and saved baselines;
MapKit owns generation, polygon operations, PNG16 and the public v1 contracts.

## Preview and validation

Terrain input immediately updates arrays and requests affected **32 m display
cells** plus needed neighbors. One running worker and latest pending cells bound
demand while preserving all brush input time/path. Nearby display is a 3×3 cell
window. Unchanged nodes and common mesh/material/asset caches are retained.
Request epoch/session checks prevent old documents from receiving results.

Explicit **3D Preview** generates a chosen storage cell from memory. Committed
record edits refresh it after 150 ms of inactivity. Generated content signatures
retain unchanged cached roots, including a remote-object-only change. A hidden
candidate replaces the old root only after successful frame-budgeted installation.
The scene installation admission budget is **3 ms/frame**; one indivisible engine
operation may exceed it. This is not an engine preemption or GPU/RSS guarantee.

Preview and **Validate** never stage projects, encode terrain PNGs or write recovery
files. Validation checks document/resources/seams using arrays. Optional full 3D
validation generates cells in memory. A memory validation report gives cell/cost
information; compressed package sizes are available only after explicit export.

Limits remain 64 MiB unique source resources, 256 MiB preview work and four cached
storage cells / 256 MiB. Native scratch, triangle/ID/object and decoded presentation
costs are charged. Nearby display also caps resource and picking geometry demand.
These are admission bounds, not measured process/GPU memory. Over-budget work
retains the prior preview and reports a recoverable error.

## Save and Save As

Save finishes current terrain input in memory and waits for necessary water/track
validation. The revision remains frozen while a worker encodes **only modified
height tiles** as lossless PNG16. Original unchanged payloads are reused. The same
source hash and external document conflict checks apply. Save As selects a directory
without an existing document and carries current plus Undo/Redo-only referenced
payloads. Existing original files and recovery snapshots are preserved.

Payloads are flushed, checked and atomically installed before publishing
`document.json` last through the existing pending/previous writer. A successful
publication alone updates the path and saved baseline. History survives Save.
Failure/cancellation retains the dirty memory state; unchanged repeat Save skips
writes. The UI/camera remain responsive while editing is locked. See
[DOCUMENTS.md](DOCUMENTS.md) for shortcuts and unsaved document transitions.

## Export and test drive

Export and test drive accept a **new unsaved map**. They create explicit independent
outputs from the current working snapshot without saving the project or clearing
dirty. Existing package filenames are refused. Test drive uses the installed
Client through its existing argument-vector adapter.

Only explicit output preparation encodes changed PNGs and uses disposable staging
for package validation/compression. Cancellation and request/session/revision checks
prevent stale publication/launch. Completed/cancelled operation scratch is removed;
original projects, packages and recovery files are not garbage-collected. Final
package publication checks destination hashes and renames an owned pending file.

The export report separates compressed ZIP/base/asset bytes, expanded resources,
native memory estimates and optional full-generation results. Existing package,
regional, course and format-v1 limits remain. Single-user conflict detection is not
a filesystem lock or a power-loss guarantee beyond flush/rename.

## Verification

Affected isolated validators cover memory preview/export/reopen, cache reuse,
resource budgets, file conflicts, cancellation, saved baselines and test-drive
snapshot ownership. The short synthetic terrain benchmark on macOS arm64 / Godot
4.7.2 measured **35.9 updates/s**, input-to-installed-mesh **p95 28.5 ms**, with a
**3 ms** installation budget. Detailed input feel, long sessions, platform/device
performance and Client driving remain user verification.
