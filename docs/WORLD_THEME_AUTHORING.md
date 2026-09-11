# World themes and map-owned writing — Q03-G

Seven authored representative scenes are implemented in `examples/world-themes/`:
polar, metropolis, countryside, middle-eastern, desert, jungle and southeast-asian.
Each source directory has `document.json`, all required GLBs, and `world.json`
with its axes, fictional reference region, spawn, wall probe, hashes and costs.
The adjacent `.memap` files are ready to open in a consumer's map chooser. Existing
Korean town v3–v6, Hanbit, driving courses, spawns and intentional burial are unchanged.

| Profile | Architecture / climate / settlement | Visible vocabulary |
| --- | --- | --- |
| Polar | Utility / polar / outpost | Raised utility cabins, white pitched roofs, snow banks, ice ridges, shelter |
| Metropolis | Contemporary / temperate / dense | Podium towers, glazing and mullions, paved frontage, sidewalks, lamps |
| Countryside | Farm / temperate / farmstead | Gabled barns, doors and wood trim, crop beds, fences and scattered buildings |
| Middle Eastern | Courtyard / temperate / village | Open U-shaped stone courts, lattice shade, parapets and market shelters |
| Desert | Utility / arid / sparse | Dune ridges, rocks, sparse arid plants, gravel track and service cabin |
| Jungle | Veranda / humid / sparse | Layered canopy, roots, undergrowth, earth beds, clearing and drainage |
| Southeast Asian | Veranda / tropical / village | Deep eaves, raised floors, shutters, palms, drainage and paved shop frontage |

These are miniature fictional samples, not surveyed locations or universal regional
styles. `world.json` records the reference region. They are not final human art
acceptance or broad biome simulation: implicit grass remains between landscaped
plots, no ice/wet-ground traction is added, and distant cells are still streamed.
Shopping/residential/market/office/hotel/plaza in town v6 remain land-use variants.

## Compose independent axes

The public MapKit library owns 31 original MIT, language-neutral assets and their
source generator (`addons/mapkit/scripts/world_assets.py`). MapEditor owns their
placement and profile choices. Common building meshes do not contain shop names;
map signs are separate placements. Library reuse means identical source bytes;
it does not promise GPU instancing or an installed shared-pack download system.
Every package includes all of its used common and map-specific assets.

Generate into a **new** output directory with the standalone editor checkout:

```sh
rtk proxy python3 scripts/world_themes.py /tmp/world-new --signs examples/world-signs
rtk proxy python3 scripts/world_themes.py /tmp/tropical-city-new --signs examples/world-signs --profile southeast-asian --architecture contemporary --settlement dense --sign arabic
rtk proxy python3 scripts/world_themes.py /tmp/courtyard-farm-new --signs examples/world-signs --profile middle-eastern --settlement farmstead --sign thai
```

`--architecture`, `--climate`, `--settlement` and `--sign` are independent choices.
The two combinations above passed native packaging. Other combinations still go
through native bounds/overlap/road admission; composition is not an unconditional
promise that any density/asset layout fits. Runtime generation and packaging
remain MapKit's responsibility. Use `mapkit pack PROJECT NEW.memap`, then
`mapkit validate-cells NEW.memap` after editing.

## Author a sign in the editor

Save a project, open **Map authoring → Signs**, choose an asset ID and enter either:

- A local licensed TTF/OTF, text, font source/license, language, direction,
  alignment, colors and size; press **Create text sign**.
- A prepared PNG with image source/license and language; press **Import prepared
  sign image**. Its existing layout is retained; it is not editable text shaping.

The sign is a separate asset. Select it in Drawing and place it with the desired
height and quarter turn beside a blank board or facade; original buildings stay
unchanged. The local surface faces source -Y; 2 quarter turns face +Y. Default size
is 3 × 1.1 m. The source origin is the bottom center. Its 2 cm collision proxy is
explicit and must not overlap another placement's footprint or a road. The sample
board and sign have separate, non-overlapping footprints. Existing native checks
reject invalid attachment/placement instead of ignoring it.

Text uses Godot TextServer Advanced shaping and a **single explicitly selected
font**, with system fallback disabled. Korean/Latin, combining Latin, Arabic RTL
with marks and Thai were exercised. Other scripts/mixed text work only when the
selected font and shaper support every character; no universal-language claim is
made. Missing codepoints/clusters and text overflow produce diagnostics. This
version supports one line of 1–128 characters, 12–160 px, a 1024×256 raster, and
TTF/OTF inputs up to 32 MiB. It does not silently shrink or clip text. A rendering
display is required for text rasterization; prepared PNG import also works headless.

The MapKit `godot/sign_asset.gd` wrapper gives the sign one normalized UV rectangle
and embeds its PNG in a static GLB. A generic PNG collision-box texture tiles and
is not the sign surface. All resulting GLBs pass the existing native PNG/glTF
validator, decoder limits, 16 MiB binary Undo budget and runtime memory accounting.
Creation uses the existing cancellable detached asset worker for candidate
validation and adoption. Changes/restored controls, closed panels, document
changes and stale workers prevent adoption. Invalid input never substitutes a
blank sign. Temporary content-addressed sign bakes live in `user://sign-bakes/`;
no original input is overwritten. They are not needed by exported maps.

## Save, reopen and share

`attribution.notice` stores a JSON `text-sign-v1` or `image-sign-v1` descriptor:
text when applicable, language, direction/layout, font/image source and license,
font SHA-256, baked image SHA-256, dimensions and shaper identification. Local font
paths are not exported. Select the existing sign asset and reopen Signs to restore
its text/provenance and physical dimensions. Reselect a licensed font to regenerate
text; the authoring font itself is not a package dependency or bundled font editor.

Save As copies the GLB and binary Undo/Redo dependencies. Reopening and export
preserve exact package bytes for all seven samples. A missing sign file blocks
export. Consumers need neither fonts nor a network connection. MapKit includes
asset hashes and license notices in package identity/inventory. Changing the
application's UI language changes neither the map's text pixels nor its hashes.

`examples/world-signs/` contains the four baked PNG/GLB examples, editable metadata,
font source URLs/SHA-256 and OFL notices. The original fonts are not redistributed.
To reproduce text, supply matching fonts in `WORLD_SIGN_FONTS` and run
`tests/sign_bake_validator.gd` in a rendered Godot project with a new
`WORLD_SIGN_OUTPUT` directory. API references: [TextLine](https://docs.godotengine.org/en/stable/classes/class_textline.html),
[TextServer glyph flags](https://docs.godotengine.org/en/stable/classes/class_textserver.html#enum-textserver-graphemeflag).

## Verification and remaining acceptance

`tests/test_world_themes.py` checks independent axes, clear routes, language-only
variants, normalized UV/embedded image contracts, missing/hash-invalid dependencies
and deterministic non-overwriting authoring. `tests/world_theme_validator.gd`
checks seven Save As/reopen/export paths, missing files, the real Signs UI,
text creation, prepared Arabic import, binary Undo/Redo and stale controls.
The existing `asset_native_validator.gd` fault/cancel/late-response suite passed.

macOS arm64/Godot 4.7.2 consumer evidence confirms all seven scenes rendered and
moved 20.84–21.63 m with real vehicle input, new committed cells, four-wheel support,
wall contact and exact retirement under 512 MiB. The baked image pixel hashes were
matched to actual GLB materials and preserved across English/Korean/Japanese UI.
These small 96×64 m fixtures have 24 cells each. They do not resolve the separate
known dense Korean town v6 512 MiB transition refusal. Human art/direct driving,
other target devices, sustained performance and final release acceptance remain.
