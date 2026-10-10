# MiniEarthure MapEditor

[Documentation index](docs/README.md) · [Current v1 contracts](docs/CURRENT_V1.md)

Independent Godot 4.7.2 map editor, licensed MIT. Requires
only this repository and its public MapKit submodule; no game installation or
private repository is needed to build or edit.

English, Korean and Japanese UI are bundled. Choose **View → Language** and
restart to apply; preferences are independent of the game Client. See
[localization, fonts and validation](docs/LOCALIZATION.md).

## Build and run

```sh
git submodule update --init --recursive
cargo build --locked --manifest-path addons/mapkit/Cargo.toml -p mapkit-godot
godot --headless --import --frame-delay 1000 --path .
godot --path .
```

Direct source launch (including the Client's **Map editor** button) also works
before the first import: the entry scene loads the installed MapKit extension
before constructing a document. A missing or incompatible binding shows a startup
error with copyable diagnostics. This still requires a current native build;
see [source-startup evidence](docs/WORKBENCH.md).

Use Godot **4.7.2**. Run the editor validator with:

```sh
godot --headless --path . --script res://tests/editor_validator.gd
godot --headless --path . --script res://tests/test_drive_validator.gd
```

For workbench/document/history/recovery checks with isolated user data and no private game
dependencies, use `python3 scripts/check_documents.py --godot /path/to/godot --full
--log-dir /new/path/checks` (geographic/OSM validators need `--import-python` with
`requirements-import.txt` installed). See [document and recovery contracts](docs/DOCUMENTS.md).

New creates a 1024x1024 metre map. Click road/polygon vertices and right-click to
finish. The 2D workbench supports object/box/multiple selection, configurable grid
and vertex snapping, graph-aware movement, duplication and deletion. Type/import
layers have Show/Lock/opacity controls and an object filter. The property inspector
applies changed fields to a whole selection. Resize or hide the docks; view
preferences stay separate from map content. See [workbench controls and contracts](docs/WORKBENCH.md).

Ctrl/Cmd+Z and Ctrl/Cmd+Y undo/redo; Ctrl/Cmd+S saves. Commands group a complete
polygon, road, property apply or drag. Save chooses a project directory. Export
writes a new `.memap`; existing outputs are preserved. Export and test drive use current memory edits without saving the project. Tool-specific instructions stay
under the map; failed imports expose Retry import with retained settings. Packages can be unpacked
with the public MapKit CLI.

Terrain and water remain in memory through editing, Undo/Redo, previews and
validation. Save (Ctrl+S/Cmd+S) is explicit and highlights unsaved changes. A new
map needs no directory until its first Save. The timed 2D/3D brush defaults to
16 m radius, 2 m/s and 50% steepness; Water fills connected low ground from a slope.
Raise terrain for islands or use Remove water for the connected surface.

There is no timer, transition or exit autosave. New/Open/Recover/Close offers Save,
Continue without saving, or Cancel. Recover still reads existing recovery,
`.previous` and complete `.pending-*` files without deleting them. Save detects
external conflicts and preserves 200 commands / 16 MiB of Undo/Redo. Save As
copies current/history assets into a new directory, preserving originals.
Memory preview reuses unchanged cells with a 3 ms installation budget; compressed
capacity reports belong to explicit package export.
See [preview, Save As and export contracts](docs/PREVIEW_EXPORT.md).

## Test drive in installed Client

For a ready-made large map, open [Driving School Town](docs/history/REFERENCE_WORLDS.md):
a 6.144km square connected school, city, village, 2km straight, S curves,
six hairpins and two kart courses studying Village Freeway and The Glove, with
round collision walls and a Cylinder wall authoring tool. Both an editable project
and a ready-to-drive `.memap` are included.

Choose **Test Drive**, select an installed MiniEarthure Client executable, local
x/y in metres and a terrain/road surface, then **Save, Package and Launch**.
An unsaved map first asks for its project directory. The action saves the current
document, exports a unique `.memap` under the editor user-data `test-drives`
directory and validates that exact document and spawn before launching Client.
Selected roads prefill their first segment midpoint and explicit surface ID.

A missing executable, invalid surface/position or packaging failure reports an
error. Editing or replacing the document during packaging prevents a stale
launch. Client receives an argument vector, so spaces in paths stay literal.
Tool path settings live in `editor_tools.cfg`, separate from map data and history.
Snapshots are retained for inspection; close Client to end a drive. The launch
status confirms process creation only; Client reports its own loading/readiness.
This feature requires a Client supporting `--test-drive --map-file` and local
`--spawn-x`, `--spawn-y`, `--surface-id`. Building/editing/packaging remain usable
without Client. Supported static assets use the shared MapKit renderer.

The standalone validator uses a recording process adapter and needs no game.
Optionally set `MINIEARTHURE_TEST_CLIENT` to an installed Linux executable to run
an additional headless, bounded native launch. It does not require private source.

## Features and boundaries

| Need | Current implementation |
| --- | --- |
| Roads, terrain, tracks and assets | [Authoring](docs/AUTHORING.md), [track workspace](docs/TRACK_AUTHORING.md), [workbench](docs/WORKBENCH.md) |
| Save, Undo/Redo and recovery | [Document ownership](docs/DOCUMENTS.md), [memory preview and explicit output](docs/PREVIEW_EXPORT.md) |
| Local GeoJSON, OSM PBF/XML, Overture and DEM input | [Supported profiles, height references and limits](docs/IMPORTS.md) |
| `.memap` and `.mkregions` export/reopen | [Current v1](docs/CURRENT_V1.md), [regional packages](docs/REGIONAL_SOURCE.md) |
| Language-neutral world assets and map-owned signs | [World authoring](docs/WORLD_THEME_AUTHORING.md) |
| Seven authored default worlds | [Sources, recipes and scoped review](docs/ARCADE_WORLD.md) |
| Reproducible synthetic diagnostics | [Reference fixtures](docs/REFERENCE_MAPS.md), [scale fixtures](docs/SCALE_MAPS.md), [driving fixtures](docs/DRIVING_TEST_MAP.md) |
| Editing latency | [Known 49-piece commit latency limit](docs/TRACK_EDIT_PERFORMANCE.md) |

Default sources are `examples/default-worlds`. All seven themes are implemented;
Village's first art direction is user-approved. Detailed driving, remaining art
and device acceptance are separate user checks. Public sources and MapKit assets
contain no private game dependency. Earlier town fixtures are described only in
[reference-world history](docs/history/REFERENCE_WORLDS.md).

Run affected feature/unit checks and necessary build/load checks. In the
superproject use its root `.venv` and development workflow. Detailed interaction,
installed-Client test driving, OS/device and export acceptance belong to the user;
full check/clean-clone/long performance runs require an explicit request.
No CI/CD is included. Source/native startup errors and the cold-import workaround
are described in [workbench validation](docs/WORKBENCH.md#essential-validation-and-limits).
