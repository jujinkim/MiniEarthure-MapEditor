# Map authoring tools

Authoring follows [CURRENT_V1](CURRENT_V1.md). [DOCUMENTS](DOCUMENTS.md) defines
atomic commands, Save and recovery; [WORKBENCH](WORKBENCH.md) defines selection,
layers and shortcuts.

## Start and draw

**Scenery** offers direct 3D tree/fence/building/GLB placement, movement, rotation
and delete; shared work height and detailed controls are in [WORKBENCH](WORKBENCH.md).
Advanced drawing/assets/environment panels build on first opening. Imported-road selection is read-only; explicit curve/height/width edits
use MapKit and atomically move shared nodes and attachments, rejecting locked
or hidden dependencies. Scenery promotes a standalone track through the existing
composition path in the same Undo; subsequent track edits retain it.

Asset and heightmap imports need a project directory. In **Authoring settings…**
the Map tab applies the theme, typed map bounds and terrain base, each as one atomic
Apply with seams and junctions revalidated. Unsupported input is rejected by MapKit.

The Drawing tab sets the next shape's parameters. Choose the canvas tool and click
vertices; right-click finishes, Place uses one click. Backspace/Delete removes the
last vertex; Escape discards the draft. A rejected shape keeps its vertices.
Tool/focus/document/history changes cancel pending input. Each shape is one Undo.

- **Road:** ground/elevated/bridge/underpass/tunnel, width, surface, start/end height
  and levels, clearance and sidewalks. Heights interpolate by distance. Matching XYZ
  and level reuse an endpoint node; a 2D crossing does not connect roads. Selected
  roads also expose **Snow retention (%)** (0–100, default 100), a rendering property
  that does not change traction.
- **Selected road:** Authoring → Selected edits each point's X/height/Y, each
  segment's width/surface, kind, clearance, sidewalks and endpoint levels. Shared
  endpoints and incident road ends move together; hidden/locked dependencies or
  invalid junctions reject the whole edit.
- **Building:** footprint, base/wall height, use, concrete/brick/wood and flat/gable
  roof (gables need axis-aligned rectangles). Draw Entrance polygons on a selected
  building for access corridors.
- **Forest/Orchard:** polygon, spacing and density; draw Exclusion polygons on a
  selected zone. Choose a GLB under **Planting tree** and set canopy half-width and
  obstacle clearance; the model's collision must fit that footprint (≤2 m tree
  radius). MapKit generates trees from polygons, exclusions, spacing, density and
  seed; zero density or an occupied zone can produce none.
- **Place/Repeat:** builtin tree/fence/streetlight and custom assets with absolute
  base and quarter turns; Repeat follows paths with spacing (fence segments must be
  cardinal).
- **Selected (other records):** exact JSON geometry editing for footprints, paths and
  rings (≤1 MiB, stable ID retained).

Road creation and structural edits generate affected junction cells through MapKit
before publication (≤16 cells). Heightmap imports with roads also regenerate affected
cells, so terrain cannot silently break a portal. Failures appear in validation status.

## Terrain and water

Terrain comes from imported heightmaps and linked DEM; see [IMPORTS](IMPORTS.md).
The Terrain tab stages an unsigned grayscale16 PNG with exact full-cell dimensions,
explicit spacing/accuracy and attribution, using asynchronous review/adoption with
progress and Cancel. Adoption is one Undo command; original files are never
rewritten. Existing water bodies keep their surface, bottom and flow editable in
**Selected**.

## Assets and proxies

The Assets tab imports static GLB/PNG/WebP into the saved project with source,
license and notice; its library selector reopens existing records. Box controls
create an exact box proxy; the tetrahedron preset creates a convex proxy; multi-box
and convex arrays stay editable. There is no inferred visual-mesh collider. Material
controls set albedo RGBA, metallic/roughness ‰, double-sided and an optional texture
asset ID. Select the new asset in Drawing before using Place.

Apply runs one owned Godot child with progress and Cancel. It hashes the original
and project files, decodes the asset, validates the detached document with MapKit,
prepares attribution and the binary Undo command, and rechecks all inputs.
Metadata-only edits reuse existing bytes. The parent binds the result to the store,
command epoch, document, project and selection; changing a field, the selection,
layers, closing authoring, a new gesture, save or document replacement invalidates
it. The supervisor enforces a 120-second deadline, EOF termination, strict IPC and
child reaping. Only then is the immutable file installed and one command published.

Limits: one asset ID and at most one new GLB/PNG/WebP payload per job; 16 MiB shared
history; 64 MiB candidate payloads; 24 MiB transfer. Output paths are registered in
a request-owned marker before writing; cleanup removes only known paths after
confirmed exit. `AuthoringTools.asset()` stays synchronous for scripts.

## Payloads and history

Original PNG/GLB/WebP files are never overwritten. Editor writes content-addressed
`editor/<sha256>.<ext>` payloads and checks existing bytes before reuse. Binary
before/after bytes count toward the shared 16 MiB Undo budget. History travel checks
retained bytes against referenced files; a changed or missing file blocks travel
without changing the stacks. Installed payloads are kept after Undo, cancellation or
eviction because saved documents and recovery snapshots may reference them; there
is no automatic garbage collection.

## Cylinder walls

Choose **Cylinder wall** and click its centre. **Authoring settings → Drawing** sets
radius (0.25–500 m), wall height, base and material; select a wall and use **Selected
→ Apply cylinder wall** to change it. It is a 48-sided flat-roof MapKit building
prism whose polygon drives both rendering and collision. An edited irregular polygon
stays ordinary geometry. The [Driving School Town](DRIVING_TEST_MAP.md#preserved-fixtures)
kart courses use these round walls.

## Related tools

- Environment and generation: [ENVIRONMENT](ENVIRONMENT.md).
- Signs and world themes: [WORLD_THEME_AUTHORING](WORLD_THEME_AUTHORING.md).
- Preview and output budgets: [PREVIEW_EXPORT](PREVIEW_EXPORT.md).
- Small fixed driving project: [DRIVING_TEST_MAP](DRIVING_TEST_MAP.md).

## Validation and open work

```sh
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --script terrain_native_validator --script authoring_validator --log-dir /new/path/checks
```

Add `asset_native_validator` for asset changes. The runner uses isolated synthetic
data and rejects engine diagnostics. General 3D gizmos outside Track Mode, broad
collision editing and camera-neighbourhood streaming remain open; the 49-piece commit
latency issue is in [TRACK_EDIT_PERFORMANCE](TRACK_EDIT_PERFORMANCE.md). Editor feel,
devices and Client driving are user checks.
