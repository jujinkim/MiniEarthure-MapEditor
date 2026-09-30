# Icon workbench — 2026-09-30

This replaces the immediate-add palette and fixed shortcut UI described in
[Track authoring](TRACK_AUTHORING.md) and [Workbench](WORKBENCH.md). Product changes
are owned by MapEditor. The public MapKit API, package definitions and own format /
protocol versions remain v1. No user map, source dataset or generated package is
rewritten by preferences, tool selection or preview.

## Implemented behavior

The shared cream `#FFF7E6` / ink `#202020` theme uses 2px borders, offset shadows,
yellow hover, blue selection, explicit focus and muted disabled controls. Action
buttons use owned MIT SVG icons, accessible names and descriptive tooltips. Menus,
property/input labels and confirmation actions retain text. Application-authored
text is English; user names, source IDs and external diagnostics are not translated.
70 road tile diagrams are generated from public MapKit sample frames, with a coral
entry point and a direction arrow. They are checked-in SVG resources, not another
runtime geometry implementation. General actions are at least 40px; tiles 52px.

The top bar groups File, Edit, Create and Inspect actions. Both left palettes have
search, optional alphabetical sorting, a horizontally scrollable favorite strip
and an object list. Track retains Driving / Gimmick / Action tabs, with road pieces
separate from attached obstacles/actions. The center retains 3D and a navigation
plan; the right inspector collapses Transform, Connections, Routes & Checkpoints,
and Actions. Route order is an item list with append/remove/up/down actions.
Activity and Problems remain below the workspace.

`workspace_commands.gd` resolves stable IDs, labels, descriptions, icons, contexts,
default keys and availability. Toolbar, palette, inspector track commands, menus,
command search and keyboard execution use that registry. Selection-dependent
commands explain their disabled state. Duplicate/Delete target only the active
mode's selection. Track's auxiliary plan cannot edit derived roads. Free roam
retains polygon completion, draft-point removal and terrain brush behavior.

| Slot | Track | Free roam |
| --- | --- | --- |
| 1 | Straight | Select |
| 2 | Gentle 90° | Road |
| 3 | Hairpin | Building |
| 4 | Slope Up | Terrain |
| 5 | Free Curve | Water |
| 6 | Cylinder | Forest |
| 7 | Loop | Place |
| 8 | Jump | Repeat |
| 9 | Attached Jump Panel | Surface Area |

Right-click a palette tile or favorite to assign a slot. IDs persist per mode;
search/sort cannot renumber them. Every palette item is searchable and separately
bindable. Edit → Shortcuts supports search, physical-key capture, clear, conflict
feedback, Save and restore defaults. Overlapping global/mode bindings cannot save;
track and free-roam bindings may reuse a key. Cmd is the primary modifier on macOS,
Ctrl on Windows/Linux. Existing Save, Undo/Redo, search and free-roam V/R/B/G/O/F
bindings remain. V selects, Escape cancels, S toggles the active mode's snap and
track F frames selection. Q/E rotate a road preview by 15°. Numeric input allows
any angle. Text/number focus, IME composition where supported, open popups and key
capture block editor shortcuts; echoed keys never execute a command.

Bindings and favorites share `user://workbench.cfg` with panel preferences. Both
writers reload the file before saving so one section cannot erase another. They
are excluded from document changes, history and exported content.

## Placement and safety

Choosing a tile, slot or search result activates the same preview tool; hidden 3D
opens split view. It does not modify the document. Height starts at the selected
instance's height, or 0m, and width prefers 4m where supported. Preview controls
set height, rotation and width before placement. Port search keeps the existing
3m radius and delegates snapping to MapKit. Guides show entry/exit directions and
the snap target. Attached actions/obstacles require a pointed road surface.

`track_placement.gd` caches up to 24 isolated native preview shapes. Pointer motion
uses their shared meshes and native frames without compiling the full document.
Flight Curve has no physical road mesh, so its shared samples supply a visible
trajectory guide. Attached preview geometry is compiled from one isolated target,
not the entire edited map.

A successful left press makes one native-validated document command and one Undo
step, then keeps the tool for the next candidate. Release, double-click replay,
key repeat and consumed/stale candidate tokens cannot duplicate that edit.
Candidate serial, document identity and command epoch must still match. Tool/view/
document changes, Undo/Redo, Escape, V, focus loss and popup opening cancel pending
placement. Failed native validation preserves document, selection and Undo state.

Disconnected drafts remain saveable. Connection/course issues separately explain
why execution export is unavailable; manual courses still need player completion.
Seed-to-manual provenance, grounded policy, save confirmation and recovery remain
under their existing document command boundaries. A recovery envelope missing
its v1 version is now rejected normally instead of raising a script error; no
historical loader or conversion was added.

## Validation and user verification

Automated results and the exact final source evidence are recorded in the delivery
record below. Checks use synthetic maps and isolated user directories. The public
`check_documents.py` runner now copies/fingerprints `ui/` alongside scripts/tests,
so icon imports are exercised in isolation.

Detailed editing, continuous mouse workflow comfort, IME/OS focus integration,
Windows/Linux/device acceptance and driving remain user verification. No full
bootstrap, recursive clean clone, export matrix or prolonged performance run was
performed. These are not claimed as passed or as a release/cutover.

To regenerate the static piece artwork, run `tests/palette_icon_source.gd` in an
isolated Godot project with `MAPEDITOR_ICON_SOURCE=/absolute/path/frames.json`, then
`python scripts/build_palette_icons.py /absolute/path/frames.json`. This reads only
MapKit's public catalogue/frames and writes Editor-owned SVG artwork.

### Delivery evidence

[Machine-readable results and source hashes](validation/icon-workbench-2026-09-30/results.json)
and the [standalone initial screen](validation/icon-workbench-2026-09-30/initial-screen.png)
record macOS arm64 / Godot 4.7.2.stable, using the unchanged MapKit pin
`ccead3e31ec469f5fde93103b369d7a2a8f29c8e` and existing native binding.

| Automated check | Result |
| --- | --- |
| Palette entry validator | All 70 presets, action/obstacle previews, surface picking, pointer commit/replay passed |
| Icon workbench validator | 146 checks passed: registry parity, mode ownership, input guards, settings/conflicts, favorites, placement/cancellation/failure, route order and layouts |
| Track workbench validator | Draft save/reopen/recovery, execution-export rejection, edits/Undo and late-generation protection passed |
| Workspace commands / workbench | 32 / 66 checks passed |
| Authoring safety / editor UX | 25 / 53 checks passed |
| Document history / recovery | 571 / 60 checks passed |
| Assembled track validator | Seed-to-manual provenance, grounding, Undo/Redo, project round trip and English generation controls passed |
| Standalone initial screen | Actual editor entry scene rendered; no blocking load errors or engine diagnostics |

Both modes fit 1024×720, 1440×900 and 1920×1080. The public isolated runner imported
the new SVG resources. Prior valid native build results were reused; native source
and formats did not change. Layout-only and final preference refinements were
checked with their affected validators, without repeating unrelated passed suites.

Initial failures were corrected: headless IME feature probing, explicit free-roam
fixtures after the new track default, empty search handling, minimum-height dock
overflow, missing v1 recovery fields, translated assertion text, Flight Curve's
non-solid guide, exact shared surface seams, and integer/JSON-number comparison
for the 4m default. No executed failure remains unresolved in the recorded scope.
Raw local diagnostic paths are in the results file; they are not required inputs
for later sessions. Detailed user verification above remains unperformed.
