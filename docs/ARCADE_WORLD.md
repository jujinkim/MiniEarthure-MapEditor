# Seven authored arcade worlds

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
