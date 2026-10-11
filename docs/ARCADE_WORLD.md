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
and distant models are original MapKit assets.

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
`DEFAULT_WORLD_THEME` and `DEFAULT_WORLD_VIEWS` pick one theme/view. Views use the
common near/distant renderers, quality 2 and a 384 m limit; road eyes are 1.7 m
above the surface and the overview is orthographic. Village views: main street,
farm road, nature road, river distance, overview. Harbor adds day/night high
street, cargo road, promenade, channel bridge and city overview. Images go to each
theme's `review/`; `<theme>-render-report.json` binds them to the package SHA-256.

## Validation and acceptance

`mapkit audit-roads` checks collision triangles every 0.5 m across five width
lines and junctions with 1 cm tolerance and a 12% maximum designed grade; all
seven worlds pass. Editor `composite_road_validator`, `track_workbench_validator`
and `document_history_validator` cover road editing, attachments, derived-terrain
restoration, Undo/Redo, save/reopen and stale-document protection.

Village's first art direction is user-approved. Detailed editing feel, driving,
course completion, other themes' art and device performance are user checks.
General asset gizmos and a reusable scenery palette are separate work.
