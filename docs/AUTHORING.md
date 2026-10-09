# Map authoring tools

Current authoring uses [CURRENT_V1](CURRENT_V1.md). All current features use v1
without a recipe selector.
[DOCUMENTS.md](DOCUMENTS.md) defines atomic commands and recovery;
[WORKBENCH.md](WORKBENCH.md) defines selection, layers and shortcuts.

Selected roads expose **Snow retention (%)** (0–100, default 100). The property
uses the normal atomic graph edit, validation, Undo and export path. MapKit owns
its rendering and hashes; it does not alter terrain traction. Authoring-property
checks cover the edit, and shared material checks cover snow-stage contrast and
markings. The retired snow-only default-map improver is no longer required.

## Start and draw

Terrain and water can be edited before the first Save. Asset imports require a project directory. Open **Authoring settings…**.
The Map tab chooses the theme with **Apply theme**. Typed map bounds and implicit
terrain base have their own atomic Apply; payload seams and road junctions are
revalidated. Roads, buildings, entrances, repetitions, convex proxies, courtyards,
vegetation and environment all use the current v1 rules. Unsupported input is
rejected by MapKit; there is no recipe selection or automatic upgrade.

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

The same circular brush works in 2D and 3D. Hold to raise/lower over time and drag
to interpolate a continuous ridge or valley. Defaults are **16 m radius, 2 m/s,
50% steepness**. Radius ranges from the existing grid spacing to twice the storage
cell size; new terrain uses **2 m** samples. Flatten keeps the first click's height
as its fixed target, or accepts an explicit numeric height. Flatten/smooth strength
(default **50%**) controls approach speed. Shared cell edges change together.
Hidden/locked terrain cannot be painted. Escape, focus/tool/layer changes cancel
an unfinished stroke without publication.

Working height tiles stay as arrays. `begin / step / preview / finish / cancel`
manages each stroke; `finish` records one sparse Undo command, including shoreline
changes. Input time and path are retained while display requests coalesce. Only
changed 32 m display cells and necessary neighbors rebuild; other meshes, common
materials and assets are reused. The 2D tint cache invalidates touched storage
tiles. There is no 16-tile or 2048-point brush cap: a stroke permits **one million
changed samples**, with **16 MiB / 200 commands** shared Undo/Redo and **64 MiB**
working height-array/resource admission. Nothing spills to disk.

**Water** clicks a slope and fills connected lower terrain at that height. Flat
terrain is unchanged. Search reaches the map boundary without draining an open
edge. Raising terrain makes islands and splits lakes; lowering it joins connected
same-level water. A horizontally overlapping higher surface removes the entire
lower connected lake. **Remove water** deletes the clicked connected surface.
Direct water/island polygon drawing is removed. New water has zero flow; there is
no fluid/drainage simulation. MapKit uses the common fitted terrain surface.

Water searches run on cancellable workers. Session, command revision and request
ID must still match before applying a result. A terrain stroke and its completed
shore update share one Undo. Large shorelines use valid v1 `water_bodies` fragments;
connected equal-level fragments behave as one lake. Search and polygon budgets
fail with a visible error and restore the previous command rather than writing
intermediate files.

Save runs PNG16 encoding in its worker, using exact 1 cm samples and an offset.
A range wider than 65535 cm cannot be losslessly encoded: Save fails and leaves
the edit dirty. Existing unmodified PNGs are reused. PNG import still accepts
unsigned grayscale16, exact full-cell dimensions, CRC/filter checks, explicit
spacing/accuracy and attribution; original files are preserved. Preview, query,
road fitting, validation and explicit export use the same unsaved arrays.

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

Apply now prepares the asset in an owned Godot child with progress and Cancel in
the authoring dialog. This includes original/project-file hashes, static asset
decoding, detached native validation, complete attribution and binary Undo command
preparation. Changing/restoring controls, switching the selected asset, closing
authoring, changing the document or starting another gesture invalidates the
result. An unchanged source is required through preparation; no file is installed
until the successful result passes the current document/selection guard.
Metadata/proxy edits without a new source use the same path and retain the old
file. Synchronous `AuthoringTools.asset()` remains available to script callers.
See [asset execution and checks](ASSET_ASYNC_VALIDATION.md).

## Environment composition

**Create → New region / Complete selected area** opens the shared theme/seed/bounds
preview. Use the configured Import Python and review diagnostics before Apply. New
worlds publish to a new directory; infill is one Undo and protects source/manual
objects. See [environment contracts and checks](ARCADE_WORLD.md). Assets offers
128/256/512px immutable derivatives (default 256); placement/Inspector yaw adds
`yaw_offset_mdeg` to the quarter-turn orientation.

## Atomic payloads, history and limits

Original PNG/GLB/WebP files are never overwritten. Editor writes content-addressed
`editor/<sha256>.<ext>` payloads in the saved project, checks an existing file's
bytes before reuse. Candidate validation uses an in-memory MapKit resource provider
and a 64 MiB payload allowance. Standalone PNG review/adoption and asset/proxy
authoring retain their cancellable owned workers. Terrain strokes write no payloads. Synchronous script APIs remain
available.
Request/selection signatures, transfer decoding and final file/history installation
remain synchronous. Large-map latency/RSS calibration is a separate acceptance gate.

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

Affected native and isolated Godot validators cover timed brushes, interpolation,
shared seams, saved baselines, no implicit writes, save failure/cancel/conflicts,
water topology (including partial map edges), memory preview/export/reopen and
retained recovery reading. Cancel before adoption rolls back height and shore
together; late request/session/revision results cannot publish.
`terrain_frame_validator` measures a short synthetic input-to-installed-mesh loop
with a 3 ms scene installation budget. Detailed editor feel, long sessions,
Windows/Linux/device behavior and Client driving remain user verification.

On macOS arm64 / Godot 4.7.2, the 9 native working-snapshot tests and isolated
memory/save (163), document history (571), retained recovery (63), preview/export
(82), continuous track editing (271) and minimum-window UI (57) checks passed.
Water authoring, PNG/asset import, portal safety and test-drive snapshot checks
also passed. The Client standalone initial screen loaded without blocking errors;
this does not claim detailed driving or platform acceptance.
The matching Runtime native dependency rebuilt and its isolated water-cell
registration/disposal check passed.

Run focused checks after building the matching public MapKit binding:

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --script terrain_native_validator --script terrain_frame_validator --script water_authoring_validator --script authoring_validator --log-dir /new/path/checks
```

The runner uses isolated synthetic data and rejects engine/script diagnostics.
[Preview and explicit output](PREVIEW_EXPORT.md) defines cache and publication
budgets; [document lifecycle](DOCUMENTS.md) defines Save and the unsaved prompt.

The PNG UI uses staged asynchronous review/adoption, with progress and Cancel in
the Authoring window. The original PNG must remain unchanged until adoption;
changed options/layers discard review. The old direct import button is removed.
See [IMPORTS.md](IMPORTS.md) for source,
active-cell replacement, source notices and review cancellation semantics.

The offline [G01 driving test map](DRIVING_TEST_MAP.md) provides a fixed small
project with connected grades, structures, surface transitions and bumps.


## Cylinder walls

Choose **Cylinder wall** and click its centre. **Authoring settings → Drawing**
sets the radius (0.25–500 m), wall height, base and material. The cursor previews
its footprint. Select a wall and use **Selected → Apply cylinder wall** to change
its centre, radius, base or height. Move, rotate, mirror, duplicate, undo/redo,
save/reopen and package export use the ordinary document operations.

This authoring shape emits a 48-sided solid, flat-roof MapKit building prism
(current v1). The integer polygon is authoritative for both rendering and solid
collision; no custom assets or new package/runtime version are needed. An edited
irregular polygon remains editable as ordinary geometry instead of being silently
rounded. Locked layers, invalid bounds and road/obstacle overlaps reject atomically.
See [Driving School Town](DRIVING_SCHOOL.md) for two ready-to-drive kart courses
using these round inside-corner walls.

## World themes and map writing

The Signs tab creates text with an explicit licensed font or imports a prepared PNG,
then adopts a separate UV-mapped GLB through native asset validation. See
[world profiles, language separation and limits](WORLD_THEME_AUTHORING.md).

Planting: choose a GLB under **Planting tree**, set canopy half-width and obstacle clearance, then draw Forest/Orchard. The model's declared collision must fit within that footprint (up to the existing 2m tree radius). Polygons, exclusions, spacing, density and seed drive MapKit generation; there is no fixed count or relocation. Density zero or an occupied zone may produce no trees.
