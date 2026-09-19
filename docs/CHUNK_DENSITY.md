# Chunk density diagnostics

The Editor reuses MapKit generation estimates and the existing256MiB preview work
calculation. At192MiB it warns; above256MiB it distinguishes an exceeded allowance.
An object count alone never decides density. The list includes triangle, prism,
convex and presentation costs; selecting a row centers the2D map on that cell.

After350ms without a document change, an immutable snapshot is analyzed on a
worker. Existing preview signatures reuse unchanged estimates. Document changes,
Undo/Redo and cancellation clear displayed rows immediately. Results are accepted
only for the current generation. Package preview/export waits asynchronously for
a cancelled analysis worker to retire before allocating another package snapshot.

Validate and Export include per-cell estimates. Density warnings do not block
Save/Export; existing native validation and preview limits still apply. Preview
generation taking more than5s is recorded separately as measured elapsed time,
with its source signature. Stale measurements are not carried across edits.

Automated density and preview/export checks pass on Windows Godot4.7.2. Final UI
acceptance and root integration remain pending; no release completion is implied.
