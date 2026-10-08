# Seven authored arcade worlds

## Environment authoring replacement

The approved expanded-world path keeps these seven themes, at least five times
each previous horizontal dimension. Editor owns the shared new-region / empty-area
layout engine; MapKit continues to own package validation, cell geometry and common
rendering. Source units remain actual metres, with the existing 1:8 OSM conversion
applied exactly once to imported geometry and inferred scenery. Own formats stay v1.

`scripts/asset_derivatives.py` creates immutable 128/256/512px derivatives (default
256), including embedded GLB images. It rebuilds buffers, shares identical encoded
payloads and reports encoded size and decoded texture memory. Geometry/material UV
atlases and originals survive. Authoring's Assets panel uses the selected Python
environment and texture profile; its existing owned worker, stale-result checks
and 16 MiB Undo budget apply to the derivative. A source may be up to 64 MiB.
New asset paths use their content hash. No source is overwritten or upsampled.

General placement supports additive `yaw_offset_mdeg`; the inspector and placement
settings expose it. MapKit applies it to visuals, light positions, collision and
occupancy. Python derivative tests (embedded resize/dedup/source preservation and
profile bounds) and the 168-assertion asset-worker regression pass on macOS arm64.
Detailed art quality and editing interaction remain user verification.

`examples/arcade-world` contains original MIT sources, `region.json` route plans,
deterministic terrain/assets and current v1 `.memap` exports. Existing examples and
completion evidence are preserved. `scripts/arcade_world.py` authors each road
network independently, then places scenery around its sightlines, branches,
landing areas and water exits. It shares construction helpers, not old layouts.

| ID | Map | Metres | Recommended route lengths (m) |
| --- | --- | --- | --- |
| village | 마을 드라이빙 파크 | 224×192 | 223.84 / 548.49 / 396.42 |
| neon-harbor | 네온 항만 | 384×256 | 238.62 / 497.64 / 599.92 |
| deep-forest | 깊은 숲 | 352×352 | 237.09 / 649.49 / 649.49 |
| red-canyon | 붉은 협곡 | 480×240 | 254.01 / 816.24 / 839.94 |
| snow-mountain | 설산 | 320×416 | 256.15 / 385.66 / 815.78 |
| machine-factory | 기계 공장 | 288×288 | 258.14 / 530.85 / 530.85 |
| sky-park | 공중 놀이공원 | 384×320 | 258.10 / 777.62 / 549.98 |

Intro routes require ordinary driving. Other routes add explicit required gimmick
gates; equal-length recommendations can share roads with different required gates
or branch choices. Harbor and forest offer land/water alternatives with common
before/after checkpoints and wide, gentle dry exits. All 21 recommendations are
`unverified` until a person completes them. They are sprint courses; free driving
remains available. Road grade crossings preserve distinct elevations.

The workbench's **Water** polygon and **Island** tools use the same edit/history
pipeline as other shapes. Authoring settings expose surface/bottom heights and
flow, selected-record edits, starting time and terrain color. Water participates
in selection, move/duplicate, Undo/Redo, save/reopen, affected-cell preview and
native export. The shared preview renders a surface without adding collision.

## Reproduce without replacing originals

From the superproject with its approved `.venv`:

```sh
rtk proxy .venv/bin/python map-editor/scripts/arcade_world.py /tmp/new-arcade-world --kit map-kit
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-arcade-world/village /tmp/new-arcade-world/village.memap
rtk proxy map-kit/target/debug/mapkit validate-cells /tmp/new-arcade-world/village.memap
rtk proxy .venv/bin/python -m unittest discover -s map-editor/tests -p test_arcade_world.py
```

Pack each of the seven IDs in `arcade-world.json` to a new file. The generator
refuses existing destinations. It requires Pillow from root requirements and the
public MapKit asset libraries. Public Editor use needs no private game repository.
For actual shared-renderer images, `tests/render_regional_maps.gd` reads absolute
`REGIONAL_SOURCE` and `REGIONAL_DESTINATION`, producing overview, ground and each
map's `signature` view. Do not share an active Godot import cache across addon
layouts. Runtime course sealing and Client catalog distribution belong to Client.

373 generated source files and all seven repacked packages reproduced byte-for-byte.
All cells passed native validation. Three independent Python checks cover graph
connectivity, route continuity/length, eight-slot start room, explicit gimmick and
branch gates, dry water exits and grade crossings (5–16.52 m separation). The
water-authoring validator passed draw/island/Undo/Redo/edit/save/reopen/native export
and shared preview. Existing authoring regression passed 98 assertions after
correcting stale tab-count and embedded-panel pointer coordinates in the fixture.
Seven overview and fourteen ground/signature renders were inspected. Detailed
editor interaction, driving enjoyment/completion and platform acceptance remain
user verification.

## Display library refresh — 2026-10-02, root §44.262

Current editable examples are in `map-editor/examples/display-world`; current
Client bundled catalog/packages are in `client/maps/display-world`. The previous
`race-flow` and earlier sources/packages remain intact. MapEditor
`scripts/refresh_display_examples.py` copies into a new destination and binds
current MIT library bytes/proxies by content hash. Seven lamp/container bindings
changed, while other authored geometry and user data are preserved. Updated
documents increment their revision; all formats remain v1.

Client's offline `prepare_race_flow_maps` supports explicit source catalog and
resource-root inputs, refuses an existing output directory, exports/opens all
seven maps and the physics fixture, and rebinds course world hashes. The default
`bundled_maps.gd` now selects the new catalog. Common material/quality/50cm wall
changes reach the Editor preview through its MapKit pin; no private renderer or
physics copy is added. Export/load validation passed; course driving and Editor
interaction remain user checks.

## Free Roam classification — 2026-10-02 replacement

Current eight editable sources are in `examples/free-roam-world`: the seven
default worlds and physics-test. Their `free_roam` is true; no embedded race
course existed, so classifying them as races incorrectly rejected startup.
`arcade_world.py` and `physics_test_map.py` now set the classification explicitly.
`refresh_free_roam_examples.py` republishes only the eight known Free Roam maps
to a new directory, rejects actual race sources and existing destinations, and
leaves display-world/user originals intact. The source-preservation unit passes.
Client's new catalog, previews and recommended courses bind freshly exported
packages; all eight actual loaders reach prepared readiness. Race start policy
remains strict. Detailed play acceptance stays with the user.
