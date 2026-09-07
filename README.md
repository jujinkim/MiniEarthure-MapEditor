# MiniEarthure MapEditor

Independent Godot 4.7.1 Windows/Linux editor foundation, licensed MIT. Requires
only this repository and its public MapKit submodule; no game installation or
private repository is needed to build or edit.

## Build and run

```sh
git submodule update --init --recursive
cargo build --locked --manifest-path addons/mapkit/Cargo.toml -p mapkit-godot
godot --headless --import --frame-delay 1000 --path .
godot --path .
```

Use Godot **4.7.1**. Run the editor validator with:

```sh
godot --headless --path . --script res://tests/editor_validator.gd
```

New creates a 1024x1024 metre map. Click road/polygon vertices, then right-click to
finish. Roads reuse snapped existing endpoints. Shift-select polygons, drag to
move, duplicate with Ctrl+D. Wheel zooms; middle-drag pans. Property controls
change width/surface, building height/base elevation, or planting spacing/density.
Ctrl+Z/Ctrl+Y undo/redo; Ctrl+S saves. Commands group a complete polygon, road or
drag. Save chooses a project directory. Export writes a new `.memap`; existing
outputs are preserved. Package files can be unpacked with the public MapKit CLI.

Recovery snapshots live in Godot's user-data `recovery` directory, separate from
map content. Autosave runs every 15 seconds and before New/Open; Recover selects
a snapshot. Existing project save retains `.previous`. Recovery restores a
validated document with fresh undo history. 3D Preview generates the chosen cell
on a worker; stale preview results never attach after document edits.

## Current boundaries

This is an early editor, not the completed transition plan. Terrain brush/import
UI, bridge/tunnel editing, asset library/rendering, deletion/road movement,
full layer management, incremental multi-cell preview and client test-drive
launch remain outstanding. Preview attachment is not yet frame-budgeted.

Import GeoJSON asks for an explicit license and local-metre coordinates, then runs
the isolated Python 3 adapter in a child process. It emits a new layer and warnings,
never modifies the source and never guesses geographic projection. Import cancellation
and progress IPC remain outstanding. WGS84,
OSM/PBF/downloads, Overture and Copernicus import adapters are not implemented.

Linux native build, command/save/recovery/export and rendered preview are tested.
Native Windows export/interaction and game driving acceptance remain unverified.
No CI/CD or private game assets are included.

Cold headless import uses `--frame-delay 1000` to avoid the observed Godot
GDExtension documentation shutdown race. Without it, a fresh import exited with
SIGABRT although later runs succeeded; do not ignore that failure. The upstream
[Godot issue 111048](https://github.com/godotengine/godot/issues/111048) describes a
similar timing-sensitive failure and this workaround. Fresh import plus the
editor validator passed with the documented command on Linux.
