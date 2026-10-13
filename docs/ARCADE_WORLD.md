# Authored default worlds

[`examples/default-worlds`](../examples/default-worlds/) holds the seven current
sources, v1 packages and three road-route plans each. IDs are
`default-<theme>-authored-20261009`. Each world is an explicitly authored recipe
(`default_worlds.py` plus `default_village.py`, `default_harbor.py`,
`default_forest.py`, `default_canyon.py`, `default_snow.py`, `default_factory.py`,
`default_park.py`); general **New region** does not reproduce them. The general
generator, infill and asset derivatives are in [ENVIRONMENT](ENVIRONMENT.md).
MapKit owns validation, cell geometry, packages and rendering; Client/Host receive
finished packages only.

| Theme | Metres | 32 m cells |
| --- | --- | --- |
| Village Driving Park | 1120 × 960 | 1050 |
| Neon Harbor | 1920 × 1280 | 2400 |
| Deep Forest | 1760 × 1760 | 3025 |
| Red Canyon | 2400 × 1200 | 2850 |
| Snow Mountain | 1600 × 2080 | 3250 |
| Machine Factory | 1440 × 1440 | 2025 |
| Sky Amusement Park | 1920 × 1600 | 3000 |

Village lays out Market Street and its clock hall, orchard cottages, ridge gardens,
two farms with crops and irrigation, a river meadow, two supported bridges and a
wooded ridge. Neon Harbor leads commercial streets, courtyards and service alleys
through warehouses to two cargo quays and a channel bridge; neon bindings keep sign
colour at night and disable emission by day. Terrain shares 2 m integer samples at
every 32 m cell edge; vegetation and props fill declared habitats only. All primary
and distant models are original MapKit assets. Theme boundaries use shared solid
wall, fence and railing modules, keep road clearance and provide open entrances.
Village has garden/farm boundaries; Harbor has warehouse/cargo partitions; Forest
has camp palisades and trail markers; Canyon has overlook/quarry walls; Snow has
lodge fences and snow breaks; Factory has safety partitions; Park has plaza rails.

Village river terrain and water share one sampled centreline: the 2.2 m bed rises
to the 3.8 m water edge and then the banks. The river-walk road uses a narrow
shoulder so native road fitting preserves the adjacent bank. Actual generated
terrain, including cell seams and bridge crossings, is checked against that edge.

## Editing roads, tracks and landscape

The **Roads & tracks** and **Terrain & scenery** tabs are tools on one document;
they do not change `free_roam` or load another map. Open a default-world source,
select a road, choose an anchor/handle and edit X/height/Z, width, shoulder and
terrain policy. Moving a shared node updates connected roads; paired handles keep
a continuous tangent.

The full track palette works on this terrain. A new piece's entry uses the pointed
terrain height unless a nearby road/track port gives height and direction; disable
`Use pointed terrain height` to type a height. Roads and track surfaces share
attached action/obstacle/rail placement.

Ordinary roads default to derived cut/fill and shoulder fitting; original PNGs are
unchanged and moving/deleting a road restores the prior fit. Preserve/elevated
policies keep the landscape; special pieces use terrain-based supports. Unsafe
terrain, occupied driving space or support interference blocks export and shows
the location; the editor never deletes or moves those objects. A road with its
terrain fit, connected pieces and attachments is one Undo command. Preview and
latency ownership are in [TRACK_EDIT_PERFORMANCE](TRACK_EDIT_PERFORMANCE.md).

Free-roam maps may run unconnected pieces; a published race route also needs
connection, start and checkpoint validation. Driving-content changes invalidate
old course hashes and proofs.

## Generate a world

Generate one theme into a new location and validate every cell:

```sh
rtk proxy .venv/bin/python map-editor/scripts/default_worlds.py /absolute/new-worlds --theme village --kit map-kit --cli map-kit/target/debug/mapkit
```

Themes: `village`, `neon-harbor`, `deep-forest`, `red-canyon`, `snow-mountain`,
`machine-factory`, `sky-park`. Existing theme destinations are rejected. Recipes,
geometry helpers and model code form the authoring fingerprint; package hashes
change with content. The seven-map distribution budget is 256 MiB with textures
≤512 px. Client tooling seals routes and eight-car grids with Runtime and publishes
completed candidates under `client/maps/default-worlds`.

## Render capture

```sh
run_godot_checks.py --project editor --script render_default_world --rendered
```

Set `DEFAULT_WORLD_SOURCE` and a new `DEFAULT_WORLD_OUTPUT`; optional
`DEFAULT_WORLD_THEME` and `DEFAULT_WORLD_VIEWS` pick one theme/view. `DEFAULT_WORLD_QUALITY=0|1|2` overrides the preset;
`DEFAULT_WORLD_REVISIT=1` repeats selected views with their shared asset cache.
Reports include preparation stages, cell/frame percentiles, draws, triangles and
memory, plus actual renderer/driver, VSync, viewport/internal sizes, quality and
sample count. Rows are labelled `editor_preview`: this project's default OpenGL
Compatibility timings do not establish Client performance. Use Client's
`scripts/debug/render_default_world.gd` for its execution settings. Views use the
common near/distant renderers, quality 2 and a 384 m limit; road eyes are 1.7 m
above the surface and the overview is orthographic. Village views: main street,
farm road, nature road, river distance, overview. Harbor adds day/night high
street, cargo road, promenade, channel bridge and city overview. Images go to each
theme's `review/`; `<theme>-render-report.json` binds them to the package SHA-256.
`DEFAULT_WORLD_WIDTH/HEIGHT`, `DEFAULT_WORLD_WARMUP/FRAMES/REPEATS` and
`DEFAULT_WORLD_OCCLUSION=0|1` support matched diagnostic comparisons;
`DEFAULT_WORLD_CAPTURE=0` skips images. Defaults retain the preview dimensions,
warmup, sample count and one repetition. `DEFAULT_WORLD_TIMEOUT_MS` bounds scene
preparation. Fixed FPS/movie timing is rejected and captures run after timing.
The superproject runner forwards `--rendering-method`, `--rendering-driver`,
`--disable-vsync` and `--max-fps`; omitted options retain project/engine defaults.
`--engine-profiler` enables per-frame CPU work timing. Zero GPU timings are
unavailable, not GPU headroom. Each row separates frame-target verdicts from
successful tool completion; driving remains unmeasured. Timer definitions and
failure/release checks: [MapKit diagnostics](../addons/mapkit/docs/RENDER_DIAGNOSTICS.md).

## Validation and acceptance

`test_default_worlds.py` checks authored road clearance, solid boundary geometry
and entrances. `default_river_bank_validator` samples final native terrain at the
water edge and bridge crossings.

`mapkit audit-roads` checks collision triangles every 0.5 m across five width
lines and junctions with 1 cm tolerance and a 12% maximum designed grade; all
seven worlds pass. Editor `composite_road_validator`, `track_workbench_validator`
and `document_history_validator` cover road editing, attachments, derived-terrain
restoration, Undo/Redo, save/reopen and stale-document protection.

The enriched seven-theme art requires user review. Detailed editing feel, driving,
course completion and device performance are user checks.
General asset gizmos and a reusable scenery palette are separate work.
