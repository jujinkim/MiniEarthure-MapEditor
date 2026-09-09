# Map authoring tools

E03, 2026-09-09. Public MIT Editor tools use the existing MapKit recipes and
DocumentStore. No native ABI, package schema, generator or game dependency changed.
[DOCUMENTS.md](DOCUMENTS.md) defines atomic commands and recovery;
[WORKBENCH.md](WORKBENCH.md) defines selection, layers and shortcuts.

## Start and draw

Save a project directory before file-backed edits. Open **Authoring settings…**.
The Map tab explicitly chooses recipe 1–4 and default/urban/rural theme as one
command. Typed map bounds and implicit terrain base have their own atomic Apply;
existing payload dimensions/seams and road junctions are revalidated. Reads and
saves never upgrade a recipe. Use recipe 2 for current terrain
roads/structures, 3 for entrances/repetitions/building rules, and 4 for convex
proxies/material overrides. Unsupported input is rejected by MapKit.

The Drawing tab sets the next shape's parameters. Close the dialog, choose the
canvas tool and click vertices; right-click finishes. Place uses a single click.
Backspace/Delete removes the last draft vertex; Escape discards the draft. A
rejected shape keeps its vertices for correction. Tool/focus/document/history
changes cancel pending input. Every successful shape is one Undo operation.
The tool list scrolls at small window sizes; Authoring, Duplicate/Delete and Snap
remain outside that scroll area. The workbench still supports 1024×720.

- Road: ground/elevated/bridge/underpass/tunnel, width, surface, start/end height
  and graph levels, clearance and sidewalks. Heights interpolate by polyline
  distance. Matching exact XYZ and level reuse an explicit endpoint node; a 2D
  crossing does not connect roads. Start a branch at an existing endpoint using
  its exact height/level. New endpoints respect the Nodes layer lock.
- Select one road, then Authoring → Selected to edit each point's X/height/Y,
  each segment's width/surface, kind, clearance, sidewalks and endpoint levels.
  Shared endpoint positions and every incident road end change once, together.
  Hidden/locked dependencies, stale inputs or invalid junctions reject everything.
- Building: drawn footprint, base/wall height, use, concrete/brick/wood and flat/
  gable roof. Gables require axis-aligned rectangles. The ordinary property dock
  also edits material/use/roof. Select a building and draw Entrance polygons for
  access corridors. Native bounds, topology and overlap rules apply.
- Forest/Orchard: polygon, spacing and density; select a zone and draw Exclusion
  polygons. Place supports builtin tree/fence/streetlight and custom assets with
  absolute base and quarter turns. Repeat supports builtin fence/streetlight
  paths, authored heights and spacing; fence segments must be cardinal.
- Selected exposes exact record editing for non-road footprint/path/ring and
  other detailed geometry. The stable ID must be retained. JSON form input is limited to 1 MiB and malformed
text is reported without engine parse diagnostics. This is an explicit
  JSON geometry editor alongside graphical creation and vector transforms;
  arbitrary-angle props, curved fences and free-form roof generators are outside
  the existing MapKit profile.

Road creation/structural editing checks generated junction cells through MapKit
before publication (closed seams, at most 16 cells per operation). Terrain edits
with roads also generate affected cells, so changing terrain cannot silently break
a ground/structure portal. Generation failures appear in persistent validation
status. This is bounded correctness preflight, not incremental preview scheduling.

## Terrain and heightmaps

Terrain has its own 2D Show/Lock/opacity row. Hidden/locked terrain cannot be
painted or imported. Layer changes cancel a stroke; visibility affects neither
export nor physics. A cursor circle and continuous stroke samples show the draft.
Committed tiles have bounded 33×33 height-tint thumbnails (at most 16 visible
tiles) and coordinate/offset labels. Thumbnails are presentation, never height data.

The Terrain tab provides raise, lower, flatten and smooth, brush radius, per-stroke
amount, flatten target and grid spacing. Left-drag followed by release is one
operation. The whole polyline determines linear radial falloff, so event frequency
does not repeatedly raise the same point or leave gaps between pointer samples.
Every touched cell evaluates the same world samples; shared edges/corners agree.
Smooth reads the original four neighboring samples rather than in-place updates.
If needed nonflat neighboring context is outside the bounded tile set, it rejects
with guidance to include that tile rather than assuming flat terrain.

The lossless authoring adapter reads unsigned grayscale16, non-interlaced PNG,
including all five PNG row filters and CRC checks. Dimensions must be exactly
`cell_size / spacing + 1` square, including partial map-edge padding. Spacing must
be at least 200 cm, divide cell size and match existing raster spacing for brushes.
Existing sources retain their accuracy metadata; imported accuracy is a separate
field, not inferred from resolution. Import also requires source/license/notice.
Native MapKit validates restored heights, all adjacent grids and implicit-flat
edges before adoption. Invalid seams fail without rewriting or flattening sources.

Brush output uses exact 1 cm samples with an explicit offset. A range wider than
65535 cm, invalid offsets or native-invalid heights rejects the operation; it does
not quantize away source accuracy. One stroke is bounded to 2048 points, 16 tiles,
one million samples and eight million point-distance evaluations. Radius is one
sample through two cells. The adapter caps PNG input at 4 MiB and side at 513;
these are Editor operation limits, not a replacement MapKit file format.

## Assets and proxies

Assets tab imports static GLB/PNG/WebP into the saved project with source, license
and notice. Its library selector reopens existing records. Box dimension controls
create an exact box proxy; the tetrahedron preset creates an outward-oriented
convex proxy. Multi-box centers/sizes and convex vertices/faces remain explicitly
editable arrays. There is no inferred visual-mesh collider. MapKit rejects open,
nonconvex, malformed, out-of-bounds or excessive proxy geometry.

Recipe-4 material controls provide albedo RGBA, metallic/roughness per mille,
double-sided and optional declared texture asset ID. Existing placements use the
updated asset after validation. File decoder, bounds/clearance, texture references
and provenance validation run before publication. A failed import/proxy/material
edit preserves both document and history. Select the new asset in Drawing before
using Place; close/reopen settings to refresh a library after adding records.

## Atomic payloads, history and limits

Original PNG/GLB/WebP files are never overwritten. Editor writes content-addressed
`editor/<sha256>.<ext>` payloads in the saved project, checks an existing file's
bytes before reuse, and validates a detached temporary project through the native
reader before publishing a document command. Candidate payload copies are capped
at 64 MiB; only this operation's random scratch directory is removed. Validation
and these bounded tools run synchronously; large-map input latency/RSS calibration
remains a representative-hardware acceptance gate, not a frame-time guarantee.

Binary before/after bytes accompany file-command mementos and count toward the
same shared **200 commands / 16 MiB** Undo+Redo limit as serialized record patches.
An oversized command is rejected before installation/publication. History travel
checks retained bytes against referenced files and validates the candidate payloads;
an externally changed/missing file blocks travel without changing the stacks or
rewriting that file. Heightmap identities canonicalize integer cell coordinates,
including JSON-decoded floats and key ordering.

Installed immutable payloads are retained after Undo, cancellation after install,
or history eviction because saved documents, previous versions and recovery
snapshots can still reference them. Binary files are not embedded in recovery JSON.
Keep the project directory with its snapshots. Automatic on-disk garbage collection is not implemented; no source cleanup is
performed. External-file-copy Save As is defined in [PREVIEW_EXPORT.md](PREVIEW_EXPORT.md).
A failed operation may leave an unreferenced new immutable payload if filesystem
installation succeeded before a later write/commit failure. It never replaces the
original document. Single-user checks do not claim cross-process write locking or
power-loss durability beyond the existing flush/rename contract.

## Verification and next work

After building the unchanged public MapKit native binding:

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --full --log-dir /new/path/editor-checks
rtk proxy env MAPEDITOR_CAPTURE_PATH=/new/path/authoring.png python3 scripts/check_documents.py --godot /path/to/godot --script authoring_validator --rendered --log-dir /new/path/editor-rendered
```

The standalone runner copies only public Editor/MapKit sources and the matching
native library, verifies isolated user data and retains source/native hashes and
strict diagnostics. `authoring_validator` covers actual viewport creation,
brush PNG/native generation, file/history/recovery/export, graph structures,
custom proxies/materials and the shared preview. `authoring_safety_validator`
covers budgets, stale/cancelled operations, immutable-file conflicts, layer locks
and terrain/structure rejection. Existing document/recovery/workbench/launch
adapter regressions remain in `--full`.

Mac evidence is scoped implementation verification. Native Windows/Linux export,
filesystem and input need Godot 4.7.2 templates, matching native bindings and actual
OS runners. Run the same checks and exported Editor with synthetic/licensed maps;
require the complete edit → cancel → Undo/Redo → save/recover → export path,
visible controls, exact seams/graph invariants and no lost source bytes/diagnostics.
Representative-map p95/RSS and E05 installed-Client driving remain separate gates.

**E04 preview/export** is implemented in [PREVIEW_EXPORT.md](PREVIEW_EXPORT.md):
affected-cell invalidation, frame-budgeted preview attachment, file-copy Save As
and capacity/error presentation preserve these command/payload boundaries.
E05 installed-Client authoring and final platform/performance acceptance remain open.
