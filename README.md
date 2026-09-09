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
writes a new `.memap`; existing outputs are preserved. First export guides the
project save and then package filename selection. Tool-specific instructions stay
under the map; failed imports expose Retry import with retained settings. Packages can be unpacked
with the public MapKit CLI.

Recovery snapshots live in Godot's user-data `recovery` directory, separate from
map content. Autosave runs every 15 seconds and before New/Open/Recover/Close;
failed retention keeps the current document open. Unsaved New/Open/Recover/Close
asks whether to save, retain recovery and continue, or keep editing. Recover selects an autosave,
`.previous` or complete `.pending-*` document. Save retains `.previous` and checks
for external changes. Recovery validates the document and checksum with fresh undo
history. Undo/Redo share 200 commands / 16 MiB of serialized mementos. Escape or
focus/tool changes cancel a drag. Save As to a new directory resolves document
conflicts and copies current/history-referenced assets and heightmaps while preserving
originals. 3D Preview refreshes affected selected cells on a worker, reuses unchanged
cached cells and attaches candidates across frames. Validate/Export show file/index/
overview and compressed/expanded capacity reports; full 3D checks are optional.
See [preview, Save As and export contracts](docs/PREVIEW_EXPORT.md).

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

The implementation includes terrain brush/PNG16, bridge/tunnel editing, asset/proxy
authoring, affected-cell preview, bounded attachment and file-copy/export tools.
E01's 2D type/import view layers never remove source records from preview or export.
Full platform, representative-map performance and installed-Client authoring acceptance
remain open; this is not the completed transition plan.

**Import vector** selects GeoJSON or bounded local OSM PBF/XML snapshots, with
source accuracy and license (fixed ODbL/contributor notice for OSM), then prepares
a typed local-metre or WGS84 layer in a Python 3 child process. WGS84 uses an explicit geographic/local
origin and optional pyproj 3.7.2 from `requirements-import.txt`. Review extent, provenance and estimated values
before **Adopt new layer**. Discard changes nothing; reimport creates a fresh layer
and adoption is one Undo command. See [import contracts](docs/IMPORTS.md).
The wizard supports Python executable selection, actual per-stage progress, Cancel
and Retry last source. Child exit/output/identity budgets protect publication;
owner shutdown and a parent-EOF watchdog stop helpers. OSM needs optional osmium
4.3.1 and imports supported simple ways; incomplete/structural/area-relation
geometry rejects rather than flattening. Terrain authoring also supports staged
PNG16 review and explicit active-tile adoption. OSM downloads, general OSM
geometry remains outside that profile. Overture building-area snapshots and Copernicus
2021 DEM (one source tile/one local cell, explicit EGM2008 zero and bilinear
sampling) are available through the import dialog; see the scoped contracts and
remaining multi-theme/multi-cell limits in [IMPORTS](docs/IMPORTS.md).

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
[AUTHORING.md](docs/AUTHORING.md). Incremental preview/file-copy Save As/export:
[PREVIEW_EXPORT.md](docs/PREVIEW_EXPORT.md). Final native-platform/performance and E05
installed-Client authoring acceptance remain open.


Reproducible offline synthetic reference projects, frozen source/generated hashes,
capacity accounting and scoped validation: [REFERENCE_MAPS.md](docs/REFERENCE_MAPS.md).
These development fixtures do not establish representative-map performance acceptance.
