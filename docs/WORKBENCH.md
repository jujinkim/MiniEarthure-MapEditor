# Editing workbench

The workspace edits one DocumentStore through the **Roads & Tracks** and
**Terrain & Landscape** tools. These are editing views of the same document;
`free_roam` is a separate game policy. [World authoring](ARCADE_WORLD.md),
[track authoring](TRACK_AUTHORING.md) and [documents](DOCUMENTS.md) own geometry,
commands, history and explicit saving.

## Layout and appearance

The shared Luna-inspired theme uses ivory `#ECE9D8` panels, white inputs, blue
`#245EDB` accents, shallow bevels and `#B8C2CF` section borders. Text is 14px,
actions at least 40px and palette tiles 52px. The menu is 28px high with a 4px
upper margin. Menus, fields and confirmation actions retain text; icon actions
have accessible names and tooltips. Application text follows
[localization](LOCALIZATION.md); user names and external diagnostics are preserved.

File, Edit, Create and Inspect groups share commands with toolbars, search and
shortcuts. Palettes have search, alphabetical sorting, favorites and object lists.
Track groups separate road pieces, gimmicks and actions. Inspector groups cover
Transform, Connections, Routes & Checkpoints and Actions. Route order has
append/remove/up/down controls. Activity and Problems use the bottom panel.

The center supports 2D, 3D and split views. Right drag orbits, middle drag pans,
and wheel zooms. Frame selection uses the current selection. The track auxiliary
plan cannot edit derived roads. Preview ownership, camera-centred cell updates
and limits are in [preview/export](PREVIEW_EXPORT.md) and
[editing performance](TRACK_EDIT_PERFORMANCE.md); general 3D gizmos remain outside
the implemented scope.

Splitters, dock visibility, grid settings and per-map view layers persist in
`user://workbench.cfg`, separate from map bytes and Undo. Preferences do not dirty
a document. Shortcut/favorite writers reload the file before updating their own
section. Reset panels restores the default visible docks and splitters.

## Commands and placement

`workspace_commands.gd` owns stable IDs, descriptions, icons, contexts, default
keys and availability. Commands explain disabled states; Duplicate/Delete target
the active selection. Ctrl/Cmd+P opens command search. Edit → Shortcuts supports
search, physical-key capture, clear, conflicts, Save and defaults. Overlapping
bindings cannot save, while separate tool contexts may share a key.

| Input | Action |
| --- | --- |
| Ctrl/Cmd+A, D | Select editable objects, duplicate |
| Delete/Backspace | Delete selection |
| Ctrl/Cmd+Z, Shift+Z or Y | Undo, redo |
| Ctrl/Cmd+S | Explicit project save |
| V, Escape | Select, cancel gesture/draft |
| S | Toggle active snap |
| F | Frame track selection or fit the terrain map |
| Q/E | Rotate road placement preview by 15° |
| 1–9 | Assigned palette slots |

Right-click tiles/favorites to assign persistent slot IDs. Search/sort never
renumbers them; every item is separately bindable. Terrain V/R/B/G/O shortcuts
remain available. Text/number focus, supported IME composition, open popups and
key capture block editor shortcuts. Echoed keys never execute commands.

A tile, slot or search result activates a preview without changing the document.
A hidden 3D view opens split mode. Preview height starts at selection height or
0m, width prefers 4m where supported, and numeric rotation accepts any angle.
Port search keeps its 3m radius and uses MapKit snapping. Pointer placement
commits once; Escape, mode/document changes and loss of gesture ownership cancel.
Current road/terrain placement and shared attachments follow [authoring](AUTHORING.md).

## Selection, layers and history

Click selects the topmost editable vector object; Shift toggles/adds. Dragging an
already selected object preserves its group; empty-space dragging encloses a
selection. Roads, nodes, buildings, zones, placements and repetition paths use
typed IDs. Raster/asset editing uses its own authoring tools.

Grid spacing is 0.01–100m; disabling snap still stores integer centimetres.
Drawing also snaps to nearby editable vertices. Duplicate preserves source
attributes, generates new bounded IDs and tries at most four positions around
the selection. Native rejection preserves the original; this is not a packer.
Delete removes records in one command, never source files or attribution.

Road movement preserves graph nodes and updates incident endpoints. A shared node
moves once. Hidden/locked affected records reject the whole command. Duplicate
creates separate endpoint nodes; deleting a road prunes only newly unused nodes.
Deleting a node still used by an unselected road is rejected.

View layers group object types and imported groups, with cumulative visibility,
lock and opacity. Hidden/locked objects cannot be selected or changed indirectly.
These are view settings: hiding a layer does not remove preview/export/physics
content. The inspector applies only changed fields; mixed groups allow translation.
Road width/surface changes apply to all selected road segments. One Apply is one
validated command including dependencies; stale controls preserve current history.

Continuous draft coalescing, drag cancellation, bounded history and the current
49-piece latency issue belong to [editing performance](TRACK_EDIT_PERFORMANCE.md).
Saving, unsaved transitions, recovery and memory-only export follow
[documents](DOCUMENTS.md), not an implicit save on each gesture.

## Files, icons and startup

File → Restore package validates `.memap`/`.mkregions` into a new adjacent
`<package>.source` directory. It cannot replace an existing project. Late/cancelled
results cannot replace the active document. Import review/retry preserves settings;
adoption is one Undo command. Errors retain operation context and the current draft.

The 48 action icons and 70 static road diagrams are Editor-owned MIT artwork.
Road diagrams derive from public MapKit frames. The loader uses valid imported
textures, rasterizes raw SVG when the cache is absent, and supports PCK remapping.
A stable catalogue preserves icon IDs. Missing/empty artwork keeps its text and
reports an error without caching a false success. Popup frames provide a 32px
title bar and inset 24px close control; hover text retains dark `#1F2B3D` ink.

`editor_entry.gd` initializes `mapkit_startup.gd` before loading the workbench or
worker. It reuses or explicitly loads the installed extension and checks native
classes, track methods and catalogue shape. A missing binding shows copyable
project/engine/reason diagnostics before document initialization. Private workers
exit nonzero without UI. It does not rewrite import caches or supply a fallback
implementation.

Regenerate artwork using `tests/palette_icon_source.gd` with
`MAPEDITOR_ICON_SOURCE=/absolute/frames.json`, then
`python scripts/build_palette_icons.py /absolute/frames.json`.

## Essential validation and limits

Scoped Godot 4.7.2/macOS checks passed command/context parity, selection/graph
safety, placement/cancellation, preference conflict protection, document/history,
import ownership and layout at 1024×720, 1440×900 and 1920×1080. All 118 icons
were checked with absent/stale/valid imports and PCK-only resources; six button
states retained visible artwork. Cold source startup, missing-library failure,
worker startup and the independent initial screen were checked separately.

Use the public `scripts/check_documents.py --script workbench_validator` or
`--script icon_workbench_validator` for affected behavior. Source startup and icon
resolution have `tests/test_source_startup.py` and `tests/test_workbench_icons.py`.
Use isolated user state, especially when fixtures persist view preferences.
Detailed editing, Windows source-launch behavior, IME/OS focus, DPI, devices and
native distributions remain user verification. Historical execution logs are not
required inputs or current platform acceptance.
