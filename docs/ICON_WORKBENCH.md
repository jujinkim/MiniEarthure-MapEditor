# Icon workbench — Luna appearance updated 2026-10-01

This replaces the immediate-add palette and fixed shortcut UI described in
[Track authoring](TRACK_AUTHORING.md) and [Workbench](WORKBENCH.md). Product changes
are owned by MapEditor. The public MapKit API, package definitions and own format /
protocol versions remain v1. No user map, source dataset or generated package is
rewritten by preferences, tool selection or preview.

## Implemented behavior

The shared Luna-inspired theme uses ivory `#ECE9D8` panels, white inputs, blue
`#245EDB` accents, 1px borders and shallow bevels. Warm hover, pale blue selection,
explicit focus and muted disabled controls replace the original cream/ink theme
and offset shadows. Action buttons use owned MIT color SVG icons, accessible names
and descriptive tooltips. Menus,
property/input labels and confirmation actions retain text. Application-authored
text is English; user names, source IDs and external diagnostics are not translated.
70 road tile diagrams are generated from public MapKit sample frames, with a coral
entry point and a direction arrow. They are checked-in SVG resources, not another
runtime geometry implementation. General actions are at least 40px; tiles 52px.

The menu row is 28px high with a 4px top margin; Import work sits with the Inspect
toolbar actions. The top bar groups File, Edit, Create and Inspect actions. Both left palettes have
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

### Original 2026-09-30 delivery evidence

Machine-readable results and source hashes
and the standalone initial screen
record macOS arm64 / Godot 4.7.2.stable, using the unchanged MapKit pin
`ccead3e31ec469f5fde93103b369d7a2a8f29c8e` and existing native binding.

| Automated check | Result |
| --- | --- |
| Palette entry validator | All 70 presets, action/obstacle previews, surface picking, pointer commit/replay passed |
| Icon workbench validator | 147 checks passed: registry parity, mode ownership, input guards, settings/conflicts, favorites, placement/cancellation/failure, route order and layouts |
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

## Luna appearance and missing icons — 2026-10-01

The user's review replaces the original neobrutalist appearance with a Luna-inspired
desktop editor. The functional icon/shortcut/placement decisions above remain.
All changes belong to MapEditor; MapKit APIs and all own v1 formats remain unchanged.

### Implementation

- Panels, menus, tabs, inputs, checkboxes, scrollbars, dialogs, tooltips and the
  auxiliary plan share the new palette. Button bevels are small in-memory textures,
  with no dependency on imported theme artwork. Text remains 14px, action targets
  40px, palette tiles 52px; the standard left palette retains four columns.
- All 48 action icons now use original color artwork, while 70 road diagrams keep
  their native-frame geometry, entry marks and direction arrows with revised colors.
- The local source checkout contained all SVGs and import descriptors but none of
  their 118 compiled texture targets. A minimal test reproduced `load()` returning
  null without the cache and succeeding with it. The preceding isolated screenshot
  had a populated cache, so that evidence did not cover the user's failure mode.
- The common loader reads valid imported textures, rasterizes raw SVGs when their
  cache is absent, and accepts remapped PCK resources without requiring raw SVGs.
  A stable icon-name catalogue prevents source-file checks from changing IDs in a
  package. Successful textures are cached; missing or invisible artwork is diagnosed,
  leaves the action name visible and is not cached as a successful result. Route
  reorder buttons use the same common decoration and failure behavior.

### Automated results

Results, timings and source hashes,
cold-cache initial screen
and six rendered button states
record macOS arm64 / Godot 4.7.2. The unchanged MapKit native build was reused.

| Check | Result |
| --- | --- |
| SVG/import/resource-pack fixture | All 118 icons passed with no cache, stale descriptors, valid imports and PCK-only resources; missing, empty raw and empty imported artwork showed text and recovered |
| Control rendering | Normal, hover, pressed, selected, disabled and keyboard focus each rendered measurable icon pixels, compared with the same button without its icon |
| Icon workbench | 297 checks passed, including commands, preference/input protection, placement safety, routes, compact menu and tile/badge bounds |
| Workspace commands | 32 checks passed |
| Free-roam workbench | 66 assertions passed with independent test/user state |
| Layout | Both modes fit 1024×720, 1440×900 and 1920×1080; menu top/height are 4/28px |
| Standalone initial screen | Actual entry scene rendered at 1280×800 after deleting all icon cache artifacts in an isolated copy; visible icon actions contain nonempty artwork; no blocking load errors or unexpected diagnostics |

The resource-only PCK is an asset-resolution fixture, not a native distribution or
platform export matrix. Missing/empty-artwork fixtures intentionally assert their
diagnostic warning; normal execution has no unexpected diagnostics.

Local reproduction commands, from the superproject with its existing native build:

```sh
rtk proxy .venv/bin/python map-editor/tests/test_workbench_icons.py --godot /path/to/godot --log-dir /new/path/icon-checks
rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --godot /path/to/godot --script icon_workbench_validator --import-cache /isolated/cache --log-dir /new/path/layout-checks --strict-diagnostics
rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --godot /path/to/godot --script workbench_appearance_validator --rendered --import-cache /isolated/cache --reuse-import --log-dir /new/path/control-checks --strict-diagnostics
```

Reuse an import cache only when its resource/native inputs are unchanged. Use a
fresh runner invocation for workbench fixtures that persist view preferences: the
root runner shares user state between scripts in one invocation. One initial
free-roam failure came from a preceding fixture's saved 3D-only view; a separate
isolated run passed. The new startup assertion also needed a typed string message
and exclusion of intentionally textual section headers. These test failures were
corrected or isolated; no executed failure remains unresolved.

### User verification and delivery boundary

Godot Editor reload/session behavior, detailed editing comfort, continuous placement,
OS/IME/DPI/device acceptance and packaged platform distributions remain user checks.
No full bootstrap, recursive clean clone, export matrix or prolonged test was run.
This is an implementation delivery, not product-wide release acceptance.

Changes are delivered on `main`, MapEditor first and root gitlink/compatibility pin
last. The root's §44.234 explicitly replaces §44.233's appearance requirement.


## Section boundaries — 2026-10-01

Following user review, the Luna appearance now adds a consistent 1px light blue-grey
`#B8C2CF` boundary to the menu, toolbar groups, project strip, palettes/favorites,
object-layer controls, central workspace and views, properties/expanded sections,
snap controls and output controls. Existing panel backgrounds share the lighter
border. Frames are drawn in existing container gaps, retaining the menu dimensions,
52px four-column palette, split handles, focus and pointer routing. No document,
command, icon-loading or MapKit contract changed.

Initial screen and
scoped results record the change.
The existing icon workbench validator passed 297 assertions, including both modes
at 1024×720, 1440×900 and 1920×1080. The standalone initial screen rendered with
visible icons and no blocking load errors or unexpected diagnostics. Valid native
and import artifacts were reused. There are no known failures in this scope;
detailed editing, Godot Editor/OS/DPI/device acceptance remain user verification.
The confirmed visual refinement is recorded in root architecture §44.235 and is
delivered on main, child first, then the root gitlink and compatibility pin.

## Source launch without import metadata — 2026-10-01

### Reproduction and implementation

The user reported **Drawing tools / 2D MAP**, only Select enabled, and unavailable
Seed Track generation after a successful Windows native build, opening MapEditor
from Godot → Client → Map editor. The current Client correctly launches the sibling
source project with `--path`; the build helper includes its debug MapKit DLL and
checks copied hashes. Neither path performs a Godot import scan.

A disposable project with the current native library but no `.godot` directory
reproduced the symptoms: `MapKitBridge` was not registered, `track_catalogue()`
failed during workbench construction, and the base free-roam screen remained while
the document/commands selected track mode. Earlier “cold” icon checks removed
compiled textures but retained `extension_list.cfg`, so they did not cover this
startup condition. The Windows user's actual log was not available; this is a
matching local reproduction, not a claimed test on that PC.

`editor_entry.gd` now calls `mapkit_startup.gd` before dynamically loading the
editor or private worker scene. It explicitly loads the installed extension when
needed, reuses an already registered one, and checks the required native classes,
track methods and catalogue shape. It uses Godot's
[GDExtensionManager](https://docs.godotengine.org/en/stable/classes/class_gdextensionmanager.html).
There is no alternate native implementation, format conversion or import-cache
rewrite. Client, the build helper, MapKit and all v1 contracts remain unchanged.

Failure opens a startup error with copyable reason/project/engine diagnostics,
without constructing a document store or editable workbench. A private worker
reports the failure and exits nonzero without opening UI. The successful source
launch requires no new native build when the existing binding is current.

### Scoped automated results

Results and retained logs and
the initial screen use
Godot 4.7.2 on macOS arm64, synthetic fixtures and isolated user data. The installed
MapKit pin `ccead3e31ec469f5fde93103b369d7a2a8f29c8e` and native binary were reused.

- No import metadata: actual entry, track palette/title, Seed Track controls,
  asynchronous Seed 42 generation and adoption passed (10 assertions).
- Existing extension registration: normal entry and repeated initialization reuse
  passed (6 assertions).
- Missing native library: a single error screen, actionable diagnostics and no
  document/recovery/preferences initialization passed (5 assertions). Expected
  engine library-load diagnostics were retained; no cascading script errors.
- Private worker: cold startup reaches argument validation (exit 2); missing
  native binding exits at bootstrap (exit 1), with no editor session.
- Independent initial-screen render with no extension list or texture cache passed.
- Existing native-import review/adoption/cancel/deadline and ownership regression:
  117 checks passed, without unexpected diagnostics (8.447 s).
- Build-helper audit: current preflight includes the Editor DLL destination;
  17 unit tests passed and the Windows-only file-lock test was skipped on macOS.

Reproduction commands:

```sh
python tests/test_source_startup.py --godot /path/to/godot --log-dir /new/path/startup --rendered
```

The native-import check used the root isolated runner, the existing import cache,
and `MAPEDITOR_TEST_IMPORT_PYTHON` pointing at the root `.venv` interpreter.
Its fixture now explicitly creates a free-roam document: the default assembled
track rejects its unrelated seed/terrain edits. The first diagnostic run lacked
that fixture initialization and Python environment and stopped before a native
job; it was interrupted, corrected and rerun. The missing-library harness also
initially rejected the expected macOS loader error spelling; the assertion was
corrected and only the failing cases rerun. These are corrected test failures,
not unresolved product failures. Passed startup/render checks were not repeated
for documentation or pin changes.

### Delivery and user verification

Baseline MapEditor `d2892f86ae3d65492934f6b30c846656448c4050`, root
`d89db9b1122dc983a4351a1abddfdf428a157ad1`; delivery is on main, owning child first,
then root gitlink/compatibility pin. There are no known failures in the scoped
checks. Actual Windows Godot → Client → Editor launch, detailed editing, OS/device
and exported-application acceptance remain user verification. No full bootstrap,
export matrix, recursive clone or detailed interactive acceptance was performed.

## Popup frames and readable hover text — 2026-10-01

User review confirmed the source-startup correction, then reported floating popup
close buttons and near-white hover text on light backgrounds. The common theme
painted `Window.embedded_border` only over the content rectangle; Godot draws the
title and close icon above it. Tabs, trees and item lists also use
`font_hovered_color` / `font_hovered_selected_color`, which the earlier
`font_hover_color` override did not cover.

The shared theme now paints a 32px title bar in both focused and unfocused frames.
A 24px close control sits within it with 4px insets, a light button face and a dark
X in normal and pressed states. Tab/tree/list hover and selected-hover labels keep
the ink color; tree column headers, menu separator/shortcut text and read-only
inputs also have explicit light-theme colors. Tree/list hover backgrounds remain
light. Main-menu spacing, editor commands, popup lifecycle and native APIs do not
change. All product changes are in `workbench_style.gd`.

Before/after evidence includes
popup title bars, generated
with synthetic controls and isolated user data on macOS / Godot 4.7.2. For Window,
AcceptDialog, ConfirmationDialog and FileDialog, the prior frame excluded the X
and had no painted title background; after the fix both containment and sampled
title pixels passed. Live control theme lookups for the six affected hover colors
changed from `#F2F2F2` / white to `#1F2B3D`.

The existing six-state icon-rendering regression and standalone initial-screen
check passed without unexpected diagnostics. Native/import results were reused;
no full suite or export matrix ran. The disposable rendering probe initially
used an unavailable geometry/hover getter and was corrected; its offscreen tab
mouse injection did not activate tab hover, so the hover evidence is explicitly
resolved control theme values, not an OS pointer acceptance result. Detailed
Windows pointer hover, popup dragging and DPI behavior remain user verification.
There are no known product failures in the scoped checks. Baseline MapEditor is
`6dac9404936d5829c16eb0519830b5918eb26df7`; deliver on main, child first and root pin
last. Root architecture §44.237 records this presentation correction.
