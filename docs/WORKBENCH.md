# Editing workbench

The workspace edits one DocumentStore through the **Roads & Tracks** and
**Terrain & Landscape** tools; `free_roam` is a separate game policy.
[World authoring](ARCADE_WORLD.md), [track authoring](TRACK_AUTHORING.md) and
[documents](DOCUMENTS.md) own geometry, commands, history and saving.

## Layout and appearance

The Luna-inspired theme uses ivory `#ECE9D8` panels, white inputs, blue `#245EDB`
accents and `#B8C2CF` borders; text is 14 px, actions ≥40 px, palette tiles 52 px,
the menu 28 px. Icon actions have accessible names and tooltips; buttons ≥160 px
wide show their label beside the icon and clip with an ellipsis. Popups have a 32 px
title bar and an inset 24 px close control. Text follows
[localization](LOCALIZATION.md).

File, Edit, Create and Inspect share commands with toolbars, search and shortcuts.
Palettes have search, sorting, favourites and object lists; track groups separate
pieces, gimmicks and actions. Inspector groups cover Transform, Connections, Routes
& Checkpoints and Actions. Activity and Problems use the bottom panel; **Activity →
Operation details…** shows the full latest message read-only.

The centre offers 2D, 3D and split views: right drag orbits, middle drag pans, wheel
zooms, and Frame uses the selection. The track plan cannot edit derived roads.
Below four screen pixels per metre the 2D overview batches unselected roads and
outlines by colour; this changes display only, not picking or data.

Splitters, docks, grid settings and per-map view layers persist in
`user://workbench.cfg`, separate from map bytes and Undo; they never dirty a
document. Reset panels restores the defaults.

## Commands and placement

`workspace_commands.gd` owns stable IDs, descriptions, icons, contexts, default keys
and availability; disabled commands explain why. Ctrl/Cmd+P opens command search.
Edit → Shortcuts supports search, key capture, clear, conflicts and defaults;
overlapping bindings cannot save, while separate tool contexts may share a key.

| Input | Action |
| --- | --- |
| Ctrl/Cmd+A, D | Select editable objects, duplicate |
| Delete/Backspace | Delete selection |
| Ctrl/Cmd+Z, Shift+Z or Y | Undo, redo |
| Ctrl/Cmd+S | Save |
| V, Escape | Select, cancel gesture/draft |
| S | Toggle snap |
| F | Frame track selection or fit the terrain map |
| Q/E | Rotate road placement preview by 15° |
| 1–9 | Assigned palette slots |

Right-click tiles/favourites to assign slots; search/sort never renumbers them.
Terrain V/R/B/G/O shortcuts remain. Text focus, IME composition, popups and key
capture block editor shortcuts; echoed keys never execute.

A tile, slot or search result starts a placement preview without changing the
document; a hidden 3D view opens split mode. Preview height starts at the selection
or 0 m, width prefers 4 m, rotation accepts any angle and port search uses a 3 m
radius with MapKit snapping. Placement commits once; Escape or a mode/document change
cancels.

## Selection, layers and history

Click selects the topmost editable vector object; Shift toggles. Dragging a selected
object moves its group; dragging empty space box-selects. Grid spacing is
0.01–100 m and coordinates are always integer centimetres; drawing also snaps to
nearby vertices. Duplicate keeps attributes, creates new IDs and tries up to four
offsets. Delete removes records in one command, never source files or attribution.

Road movement preserves graph nodes: a shared node moves once and incident endpoints
follow. Hidden/locked affected records reject the command. Deleting a node used by
an unselected road is rejected.

View layers group object types and imports with visibility, lock and opacity; hidden
or locked objects cannot be changed indirectly, but still export. The inspector
applies only changed fields, and one Apply is one validated command.

## Files, icons and startup

File → Restore package validates `.memap`/`.mkregions` into a new adjacent
`<package>.source` directory; it never replaces a project. Import review/retry keeps
settings and adoption is one Undo command.

The 48 action icons and 70 road diagrams are Editor-owned MIT artwork derived from
MapKit frames. The loader uses imported textures, rasterizes raw SVG without a cache
and supports PCK remapping; missing artwork keeps its text and reports an error.
Regenerate with `tests/palette_icon_source.gd` and
`MAPEDITOR_ICON_SOURCE=/absolute/frames.json`, then
`python scripts/build_palette_icons.py /absolute/frames.json`.

`editor_entry.gd` initializes `mapkit_startup.gd` before the workbench or workers.
It loads the installed extension and checks native classes, track methods and the
catalogue. A missing binding shows copyable diagnostics; workers exit nonzero. No
fallback implementation is supplied.

## Essential validation and limits

Use `scripts/check_documents.py --script workbench_validator` or
`--script icon_workbench_validator`; source startup and icons have
`tests/test_source_startup.py` and `tests/test_workbench_icons.py`. Use isolated user
state because fixtures persist view preferences. Layout is checked at 1024×720,
1440×900 and 1920×1080.

Cold headless import needs `--frame-delay 1000` to avoid a GDExtension documentation
shutdown race (SIGABRT on Linux without it). This is a workaround, not an engine
fix; keep fresh failure diagnostics. Detailed editing, Windows source launch, IME/OS
focus, DPI, devices and native distributions are user checks.
