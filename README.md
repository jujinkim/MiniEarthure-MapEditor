# MiniEarthure MapEditor

[Documentation index](docs/README.md) · [Current v1 contracts](docs/CURRENT_V1.md)

Independent Godot 4.7.2 map editor, licensed MIT. It needs only this repository and
its public MapKit submodule; no game installation or private repository is required.
English, Korean and Japanese UI are bundled (**View → Language**, applied on restart;
see [localization](docs/LOCALIZATION.md)).

## Build and run

```sh
git submodule update --init --recursive
cargo build --locked --manifest-path addons/mapkit/Cargo.toml -p mapkit-godot
godot --headless --import --frame-delay 1000 --path .
godot --path .
```

When embedded in a superproject, its native installer may supply the same pinned
MapKit library; use that build entry point to avoid a second Cargo cache. The
commands above remain sufficient for this independent public checkout.

Direct source launch (including the Client's **Map editor** button) works before the
first import; a missing or incompatible MapKit binding shows copyable startup
diagnostics. See [workbench validation](docs/WORKBENCH.md#essential-validation-and-limits).

## Editing basics

New creates a 1024 × 1024 m map. Click road/polygon vertices and right-click to
finish. The [workbench](docs/WORKBENCH.md) provides selection, snapping, layers and
the property inspector; terrain, water and assets are in
[authoring](docs/AUTHORING.md). Ctrl/Cmd+Z / Ctrl/Cmd+Y undo/redo and Ctrl/Cmd+S
saves; there is no autosave. Save, Save As and recovery are defined in
[documents](docs/DOCUMENTS.md); Export writes a new `.memap` or `.mkregions` from
memory without saving ([preview and export](docs/PREVIEW_EXPORT.md)). The seven
authored default worlds live in `examples/default-worlds` ([ARCADE_WORLD](docs/ARCADE_WORLD.md)).

## Test drive in an installed Client

Choose **Test Drive**, select an installed MiniEarthure Client executable, local
x/y in metres and a terrain/road surface, then **Save, Package and Launch**. The
action saves the document (asking for a directory if new), exports a unique `.memap`
under the editor user-data `test-drives` directory and validates the document and
spawn before launch. A selected road prefills its first segment midpoint and surface.
Editing during packaging prevents a stale launch. Tool paths live in
`editor_tools.cfg`, separate from map data. The Client must support `--test-drive
--map-file`, `--spawn-x`, `--spawn-y` and `--surface-id`; launch status confirms
only process creation.

For a ready-made map, open [Driving School Town](docs/DRIVING_TEST_MAP.md#preserved-fixtures)
(576 × 192 m with practice, city and kart courses) or the small
[offline driving map](docs/DRIVING_TEST_MAP.md).

## Checks

```sh
godot --headless --path . --script res://tests/editor_validator.gd
godot --headless --path . --script res://tests/test_drive_validator.gd
python3 scripts/check_documents.py --godot /path/to/godot --script <validator> --log-dir /new/path/checks
```

`check_documents.py` runs validators with isolated user data; geographic/OSM
validators need `--import-python` with `requirements-import.txt`. Set
`MINIEARTHURE_TEST_CLIENT` to an installed Linux Client for an optional bounded
launch. Run only affected checks; detailed interaction, Client driving, OS/device and
export acceptance belong to the user. No CI/CD is included.
