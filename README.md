# MiniEarthure MapEditor

Independent Godot 4.7.2 Windows/Linux editor foundation, licensed MIT. Requires
only this repository and its public MapKit submodule; no game installation or
private repository is needed to build or edit.

## Build and run

```sh
git submodule update --init --recursive
cargo build --locked --manifest-path addons/mapkit/Cargo.toml -p mapkit-godot
godot --headless --import --frame-delay 1000 --path .
godot --path .
```

Use Godot **4.7.2**. Run the editor validator with:

```sh
godot --headless --path . --script res://tests/editor_validator.gd
godot --headless --path . --script res://tests/test_drive_validator.gd
```

For workbench/document/history/recovery checks with isolated user data and no private game
dependencies, use `python3 scripts/check_documents.py --godot /path/to/godot --full
--log-dir /new/path/checks`. See [document and recovery contracts](docs/DOCUMENTS.md).

New creates a 1024x1024 metre map. Click road/polygon vertices and right-click to
finish. The 2D workbench supports object/box/multiple selection, configurable grid
and vertex snapping, graph-aware movement, duplication and deletion. Type/import
layers have Show/Lock/opacity controls and an object filter. The property inspector
applies changed fields to a whole selection. Resize or hide the docks; view
preferences stay separate from map content. See [workbench controls and contracts](docs/WORKBENCH.md).

Ctrl/Cmd+Z and Ctrl/Cmd+Y undo/redo; Ctrl/Cmd+S saves. Commands group a complete
polygon, road, property apply or drag. Save chooses a project directory. Export
writes a new `.memap`; existing outputs are preserved. Packages can be unpacked
with the public MapKit CLI.

Recovery snapshots live in Godot's user-data `recovery` directory, separate from
map content. Autosave runs every 15 seconds and before New/Open/Recover/Close;
failed retention keeps the current document open. Recover selects an autosave,
`.previous` or complete `.pending-*` document. Save retains `.previous` and checks
for external changes. Recovery validates the document and checksum with fresh undo
history. Undo/Redo share 200 commands / 16 MiB of serialized mementos. Escape or
focus/tool changes cancel a drag. Save As to a new directory resolves document
conflicts; copying referenced assets/heightmaps to a new project remains pending.
3D Preview generates the chosen cell
on a worker; stale preview results never attach after document edits.

## Test drive in installed Client

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

## Current boundaries

This is an early editor, not the completed transition plan. Terrain brush/import
UI, bridge/tunnel editing, asset library/authoring UI and incremental multi-cell
preview remain outstanding. E01 provides 2D type/import view layers; hiding a
layer never removes its source records from preview or export. Preview attachment is not yet frame-budgeted.

Import GeoJSON asks for an explicit license and local-metre coordinates, then runs
the isolated Python 3 adapter in a child process. It emits a new layer and warnings,
never modifies the source and never guesses geographic projection. Import cancellation
and progress IPC remain outstanding. WGS84,
OSM/PBF/downloads, Overture and Copernicus import adapters are not implemented.

Linux native build, command/save/recovery/export and rendered preview are tested.
E01 Mac pointer/key, layer/property/panel and graph-safety checks are scoped
workbench evidence. Native Windows/Linux final export/interaction and full authoring/game
driving acceptance remain unverified.
No CI/CD or private game assets are included.

Cold headless import uses `--frame-delay 1000` to avoid the observed Godot
GDExtension documentation shutdown race. Without it, a fresh import exited with
SIGABRT although later runs succeeded; do not ignore that failure. The upstream
[Godot issue 111048](https://github.com/godotengine/godot/issues/111048) describes a
similar timing-sensitive failure and this workaround. Fresh import plus the
editor validator passed with the documented command on Linux.


K07 asset previews now use the same MapKit packed renderer as game consumers.
Saved projects with static GLB/PNG/WebP and declarative materials load validated
in-memory resources; empty-file document previews use the same style decoration.
A failed replacement leaves the previous preview visible. Asset/proxy editing
widgets are implemented in the [E03 authoring tools](docs/AUTHORING.md). `tests/asset_preview_validator.gd` verifies a
synthetic project through open, preview, save/export, failed replacement and
resource cleanup without installing the private game.

Authoring tools (terrain strokes/PNG16, structural roads, buildings/zones, assets/proxies):
[AUTHORING.md](docs/AUTHORING.md). E04 incremental preview/file-copy Save As and final
native-platform/performance acceptance remain open.
