# World themes and map-owned writing

`examples/world-themes/` contains seven miniature fictional scenes with
`document.json`, required GLBs, `world.json` (axes, reference region, spawn, wall
probe, hashes, costs) and an adjacent `.memap`:

| Profile | Architecture / climate / settlement | Visible vocabulary |
| --- | --- | --- |
| Polar | Utility / polar / outpost | Raised cabins, white pitched roofs, snow banks, ice ridges |
| Metropolis | Contemporary / temperate / dense | Podium towers, glazing, paved frontage, lamps |
| Countryside | Farm / temperate / farmstead | Gabled barns, crop beds, fences |
| Middle Eastern | Courtyard / temperate / village | Stone courts, lattice shade, market shelters |
| Desert | Utility / arid / sparse | Dunes, rocks, sparse plants, gravel track |
| Jungle | Veranda / humid / sparse | Layered canopy, roots, undergrowth, clearing |
| Southeast Asian | Veranda / tropical / village | Deep eaves, raised floors, palms, shop frontage |

They are not surveyed locations, universal regional styles or biome simulation:
grass remains between plots and no ice/wet traction is added.

## Compose independent axes

MapKit owns 31 original language-neutral assets and their generator
(`addons/mapkit/scripts/world_assets.py`); MapEditor owns placement and profiles.
Building meshes contain no shop names; signs are separate placements. Every package
includes all assets it uses.

```sh
rtk proxy python3 scripts/world_themes.py /tmp/world-new --signs examples/world-signs
rtk proxy python3 scripts/world_themes.py /tmp/tropical-city-new --signs examples/world-signs --profile southeast-asian --architecture contemporary --settlement dense --sign arabic
```

`--profile`, `--architecture`, `--climate`, `--settlement` and `--sign` are
independent. Every combination still passes native bounds/overlap/road admission;
not every layout fits. After editing run `mapkit pack PROJECT NEW.memap` and
`mapkit validate-cells NEW.memap`.

## Author a sign

Save the project, open **Map authoring → Signs**, choose an asset ID and either:

- choose a local licensed TTF/OTF, text, font source/license, language, direction,
  alignment, colours and size, then **Create text sign**; or
- choose a prepared PNG with source/license and language, then **Import prepared sign
  image** (layout kept as-is).

The sign is a separate asset; place it with height and quarter turn beside a board
or facade. Its surface faces source −Y, default size is 3 × 1.1 m with a
bottom-centre origin and a 2 cm collision proxy that must not overlap other
footprints or roads.

Text uses Godot TextServer Advanced shaping with **one selected font** and no system
fallback. Missing glyphs and overflow are diagnostics, never shrink or clip. Limits:
one line of 1–128 characters, 12–160 px, 1024×256 raster, fonts ≤32 MiB. Text
rasterization needs a rendering display; PNG import also works headless.

MapKit `godot/sign_asset.gd` embeds the PNG in a static GLB with one normalized UV
rectangle; the result passes the native PNG/glTF validator and the 16 MiB binary Undo
budget. Creation uses the cancellable asset worker; changed controls, closed panels
or document changes prevent adoption. Temporary bakes live in `user://sign-bakes/`.

## Save, reopen and share

`attribution.notice` stores a `text-sign-v1` or `image-sign-v1` descriptor (text,
language, layout, font/image source and license, font and image SHA-256, dimensions,
shaper). Local font paths are not exported; reselect a licensed font to regenerate
text. Save As copies the GLB and Undo-only dependencies; a missing sign file blocks
export. Consumers need no fonts or network, and the UI language never changes map
pixels or hashes.

`examples/world-signs/` holds four baked examples, editable metadata and font source
URLs/SHA-256 with OFL notices (fonts not redistributed). To reproduce, supply fonts
in `WORLD_SIGN_FONTS` and run `tests/sign_bake_validator.gd` in a rendered project
with a new `WORLD_SIGN_OUTPUT`. References:
[TextLine](https://docs.godotengine.org/en/stable/classes/class_textline.html),
[TextServer glyph flags](https://docs.godotengine.org/en/stable/classes/class_textserver.html#enum-textserver-graphemeflag).

## Validation

`tests/test_world_themes.py` checks axes, routes, language variants, UV/embedded image
contracts, dependencies and non-overwriting output. `tests/world_theme_validator.gd`
checks Save As/reopen/export, the Signs UI, text creation, prepared Arabic import,
binary Undo/Redo and stale controls. Human art review, driving and devices are user
checks.
