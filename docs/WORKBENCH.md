# Editing workbench

E01, 2026-09-09. The central 2D map, object/layer tree, property inspector and
shared MapKit cell preview use the same validated DocumentStore as E02.
See [DOCUMENTS.md](DOCUMENTS.md) for atomic commands, history and recovery.

## Selecting and editing

- Click selects the topmost editable vector object. Shift-click toggles it;
  clicking an already selected object preserves the group for dragging.
  Drag empty space to select fully enclosed objects; Shift adds to the group.
- Roads, graph nodes, buildings, zones, placements and repetition paths have
  typed selection keys. Yellow outlines/vertex handles identify selection;
  translucent fills leave overlapping context visible. Ring outlines show
  building entrances and zone exclusions. Assets and raster heightmaps are not
  independent movable vector objects; their authoring uses the separate [E03 tools](AUTHORING.md).
- Drag changes only the temporary view. Release submits one validated command.
  Escape, focus/tool/document replacement, layer changes and history actions
  cancel pending gestures. Undo/Redo are still bounded by E02's shared limits.
- Grid snapping is configurable from 0.01 to 100 metres. Turning it off still
  writes integer centimetres. Shape drawing also snaps to nearby visible,
  editable vertices; wheel zoom is anchored at the pointer. Middle drag pans;
  **Fit map** resets the view.
- Duplicate retains all source attributes, translates entrances/exclusions,
  generates fresh bounded IDs and selects the copies. It tries at most four
  positions beside the selection's extent (including road widths and rings),
  above/right/below/left. Each candidate passes native validation before it can
  change history. If none fits, the original selection/document is preserved;
  select a smaller group or make space first. This is not an automatic packer.
- Delete removes the selected records in one command. It does not delete source
  asset files, project folders, attribution records or any user dataset.

Road movement preserves explicit graph topology: a selected road translates its
points and both endpoint nodes. Every incident unselected road updates only the
moved endpoint. A node shared by several selected roads moves once. A node can
also move on its own; its incident ends follow. A hidden/locked affected record
rejects the whole command. Native geometry/road rules can reject a deformation;
no endpoints are silently detached or snapped to another graph.

Duplicated roads share fresh copies of their common endpoints and never attach to
the original graph. Deleting roads prunes only their now-unreferenced endpoint
nodes. Deleting a selected node that still has an unselected road is rejected.
Unrelated orphan nodes and all original files remain untouched.

## Layers, properties and panels

The tree groups vector objects by document type. Additional import rows use the
existing GeoJSON adapter's `import-<layer_id>-...` identity prefix and control the
whole imported group across types. Show/Lock and opacity apply cumulatively to
type and import groups. Selecting a layer selects its editable objects; the
filter finds object IDs. Hidden/locked objects cannot be selected, transformed,
deleted or drawn into through that layer. A locked incident road also blocks
indirect graph changes. Unlock/show explicitly before editing it.

These are **2D workbench view layers**: visibility never removes content from
preview, packages or physics. The preview caption makes this distinction visible.
MapDocument has no arbitrary layer metadata. Reimport/adoption and source-layer
authoring remain the separate import work, with no package schema change here.

The inspector provides group translation and changed-field-only batch properties.
Buildings expose height/base; roads explicitly apply widths/surfaces to **all
segments**; zones expose spacing/density/kind; placements expose quarter-turn
rotation; repetitions expose spacing. Mixed-type groups expose translation only.
Unchanged values retain each record's original value, even when the first selected
record has a different one. One Apply is one command, including graph dependencies.
Stale/invalid changes preserve document/history and report the native failure.
Structural road, terrain and asset/proxy authoring use [AUTHORING.md](AUTHORING.md).

Drag the two horizontal splitters or the properties/preview vertical splitter.
The bottom controls toggle either dock and restore panel defaults. Properties
scroll independently; the object tree scrolls and can collapse categories.
Validation/preview state has its own label, separate from pointer coordinates.
Affected-cell preview and frame-budgeted attachment use the same MapKit worker
and renderer; see [PREVIEW_EXPORT.md](PREVIEW_EXPORT.md).

Panel widths/visibility, grid settings and per-map layer view settings live in
`user://workbench.cfg`, separate from map content, provenance and Undo history.
View changes do not dirty the document or alter exported bytes. Layer settings
save when changed; panel/grid settings also save on editor exit. Reset panels
restores visible docks and the default splitter positions.

## Shortcuts

| Input | Action |
| --- | --- |
| V / R / B / G / O | Select / Road / Building / Forest / Orchard |
| Ctrl or Cmd + A / D | Select all editable objects / duplicate |
| Delete or Backspace | Delete selection |
| Ctrl or Cmd + Z / Shift+Z / Y | Undo / redo / redo |
| Ctrl or Cmd + S | Save |
| Escape | Cancel drag, box selection or drawing draft |
| F | Fit map |

Text fields retain their own shortcuts; typing a letter, selecting/deleting text
or undoing text must not alter map objects. Existing file dialogs and Test Drive
keep their own flow. No private game installation is needed for this workbench.

## Verification and handoff

Run the public standalone checks after building the native binding:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --full --log-dir /new/path/checks
python3 scripts/check_documents.py --godot /path/to/godot --script workbench_validator --rendered --log-dir /new/path/rendered
```

`workbench_validator.gd` routes pointer/key events through the real viewport,
exercises graph dependencies, native rejection and view isolation, then saves,
recovers and generates a preview. Set `MAPEDITOR_CAPTURE_PATH` to an absolute PNG
destination to retain its rendered result. The runner copies public sources and
the existing binding into a disposable project and verifies isolated `user://`.
Mac checks are scoped evidence, not Windows/Linux distribution acceptance.

Native Windows/Linux exports and interaction still need their 4.7.2 templates,
matching target-native binding and actual OS runners. Run the same checks, export
with the shipped presets, then verify selection, text input, resize, save/restart,
layers, undo/recovery and preview on each native platform. Require no clipped
controls, unintended edits, stale attachment or lost original data. Large-map
selection/redraw/property costs remain a representative-map performance gate;
the current vector queries scan document objects and are not a spatial index.

E03 authoring is now implemented; see [AUTHORING.md](AUTHORING.md). E04 preview/export and file-copy Save As are implemented in
[PREVIEW_EXPORT.md](PREVIEW_EXPORT.md). The vector planner and atomic record/payload
boundaries are preserved. Complete platform/performance/installed-Client acceptance
remains separate work.
