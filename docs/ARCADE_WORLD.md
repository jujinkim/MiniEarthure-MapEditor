# Authored default worlds and general environment tools

Editor owns `environment_generation.py`, the layout/composition/metrics modules,
`environment_profiles.py` and the metre-scale modules in `environment_assets.py`.
MapKit owns current v1 validation, cell geometry,
package I/O and common rendering. Client/Host receive finished packages and assets;
they do not receive this layout engine. Default worlds now use separate, explicitly
authored recipes in `default_worlds.py`, `default_village.py`, `default_harbor.py`,
`default_forest.py`, `default_canyon.py`, `default_snow.py`, `default_factory.py`
and `default_park.py`; generic generation
and semantic infill remain available. The seven themes retain these dimensions:

| Theme | Metres | 32 m cells |
| --- | --- | --- |
| Village Driving Park | 1120 × 960 | 1050 |
| Neon Harbor | 1920 × 1280 | 2400 |
| Deep Forest | 1760 × 1760 | 3025 |
| Red Canyon | 2400 × 1200 | 2850 |
| Snow Mountain | 1600 × 2080 | 3250 |
| Machine Factory | 1440 × 1440 | 2025 |
| Sky Amusement Park | 1920 × 1600 | 3000 |

## Roads, tracks and landscape in one document

The `Roads & tracks` and `Terrain & scenery` tabs select tools on the same map.
They do not change `free_roam`, load another map or replace the document. Open
any current default-world source to edit its ordinary roads: select a road in
the viewport/list, choose an anchor/handle, edit X/height/Z, width, shoulder and
terrain policy, then apply the alignment. Moving a shared node updates connected
roads; anchors carry their handles and paired handles retain a continuous tangent.

The complete existing track palette works on that terrain. A new piece's entry
uses the pointed terrain height; a nearby road/track port takes precedence for
height and direction. Disable `Use pointed terrain height` to enter a height.
Selected pieces can snap to a road port or create a connecting curve from it.
Ordinary roads and track surfaces share attached action/obstacle/rail placement.

Ordinary roads default to derived cut/fill and shoulder fitting. Original PNGs
are unchanged, and moving/deleting a road restores its previous fitted area.
Preserve/elevated policies retain the source landscape; special pieces keep
their authored shape with terrain-based supports. Existing buildings, water,
assets and independent gimmicks stay in the document. Unsafe terrain, occupied
driving space or support interference blocks execution export and displays the
reported location; the editor never deletes or relocates those objects.

A road, its terrain fit, connected pieces and attached tools form one Undo
command. History records changed fields/IDs within its existing byte budget.
Terrain/scenery previews use cancellable native workers and disposable 32 m
cells, with bounded asset/picking/render work and reuse of unchanged meshes.
Late responses cannot update a replaced document. See
[editing ownership](TRACK_EDIT_PERFORMANCE.md).

Free-roam maps can run unconnected pieces without a race course. Unsafe geometry
still blocks export. Publishing a race route additionally requires its connection,
start and checkpoint validation. Driving-content changes invalidate old course
hashes/proofs. User projects are saved only after explicit edits/save; no automatic
conversion or overwrite occurs. All own formats remain v1.

## Authoring

Configure the root `.venv` Python in Import settings. **Create → New region** and
**Create → Complete selected area** share the same engine. Select theme, seed,
density, texture size and bounds; review the composition and diagnostics, then
apply. Selection bounds begin around selected geometry, or the document bounds
when nothing is selected. New projects require a new absolute directory and publish
by a sibling-directory rename. Infill requires a saved free-roam project and creates
one Undo command. A result over the existing 16 MiB history limit is rejected with
an area-reduction diagnostic. Preview, cancellation, failure and stale documents do
not publish editing changes. Project payload hashes are checked again on apply.

`ThemeProfile` declares required facility groups, functional hubs, district density
ranges, hierarchy/loop roads, natural-space floors and shared asset assemblies.
Entrance orientation, access, adjacency and exclusions remain explicit. `GenerationContext` holds
terrain, source geometry, semantic regions, protection and source scale;
`GenerationRequest` selects mode/theme/seed/bounds; `GenerationResult` contains the
candidate patches, immutable assets, ownership hashes and diagnostics.

The stages are terrain/water, landscape-aware functional hubs, road hierarchy,
road-facing assemblies, working access, landscape bands and vegetation, then
geometry measurements and bounded alternative sites. `environment_layout.py`
keeps urban concentration at 20–35% of land; its tensor directions apply only
inside districts. Village has a civic centre and two housing clusters, harbor a
large working port and smaller town blocks, factory a production core and gate,
and amusement park a fairground and open entrance/plaza. Remote themes use one
nonrectangular terrain-cost loop and three accesses, independent of density.
Their nature floor is 85%; village fields/green space retain at least 65%.

Road widths are 10–12/6–8/4–6 m for urban arterial/connector/service, and 6/4 m
for remote main/access roads. Each world reserves a grounded 200 m straight.
Road profiles stay below 12% grade; new terrain follows their cut/fill and facility
foundations. Infill never alters existing roads or terrain. Terrain uses shared
global samples across 32 m cell edges. Polygon holes survive constrained
triangulation and centimetre rounding; residual ground slivers are rejected.
Facility extents derive from their complete asset footprints. Container rows have
truck aisles, warehouses have docks/canopies, production has connected pipe runs,
and attractions have clear access and associated queue/plaza space.

`environment_metrics.py` measures occupancy from emitted footprints, access to
every facility member, real graph cycles/junctions, grades, natural area, habitat
transitions and repeated frontage silhouettes. Residential/commercial lots target
30–55%; production/warehouse lots 25–45% at density 1.0. Plazas, parks and loading
aisles are separate uses. Required failures block Apply. Dense-cell candidates
include GLB triangle counts, collision proxies and every touched 32 m cell, rather
than just placement counts. Native validation retains the existing budgets.
Ground/deck junctions share level approach aprons. Frontage paths reach building
footprints, crop modules fill productive field interiors, and fence runs leave
access openings. Retained metre-scale source modules include rounded broadleaf
crowns, layered rock outcrops and a continuous supported observation wheel, with
solid box/convex collision declarations. No original library files are replaced.
Homes, shops, lodges, production halls and asymmetric boulders each provide three
silhouettes. Forest clusters mix mature oak/birch/pine, saplings, undergrowth and
fallen logs; overlapping soft crowns preserve solid trunk clearance. Snow terrain
changes from valley grass/trees to alpine rock and snow. The fairground has four
attraction/queue clusters, while its entrance plaza stays open. Density changes
optional frontage and vegetation fill without changing these required clusters.

The preview can show district use/density, road hierarchy, parcels/entrances,
protected polygons and diagnostic locations. Hovering an issue identifies its
district and reason. Geometry or required-facility failures disable Apply.

The tensor implementation is independent, informed by
[ProbableTrain's overview](https://github.com/ProbableTrain/MapGenerator/blob/master/docs/algorithmoverview.md)
and [Chen et al., 2008](https://web.engr.oregonstate.edu/~zhange/images/street_sig08.pdf).
No implementation code from those projects is included. Algorithm source and Shapely
version form the fingerprint. Seed streams use region/parcel/tile identities so a
change elsewhere does not consume another region's random sequence.

## Infill ownership and source preservation

OSM imports retain original way/relation IDs, semantic land-use polygons, inner
rings and protected regions in existing Editor provenance metadata. Source polygons
stay unscaled there; an `authored_regions` copy receives the existing 1:8 conversion
once. Infill dimensions and asset proxies receive the same single 1:8 scale.
[OSM land-use meanings](https://wiki.openstreetmap.org/wiki/Key:landuse) provide
context; generated scenery is explicitly labeled an estimated game environment.
Unknown land use receives low-intensity ground cover, never guessed buildings.
Original roads/buildings, manual objects, water, entrances and protected areas are
fixed. Forest/orchard source objects remain intact.

Ownership hashes for generated placements and ground surfaces travel with normal
save/reopen, recovery and Undo/Redo. Only unchanged owned objects inside the selected
area are regenerated; a conservative 64 source-metre boundary band stays fixed.
Facility boundaries and member hashes make regeneration atomic: crossing a
selection boundary, editing one member or deleting one member retains the whole
assembly. Deletion tombstones persist across repeated runs. Manual edits and deletions are protected. Terrain, road topology and structural
supports remain fixed during infill. Rerunning current infill does not duplicate
objects. User source files and their packages remain preserved. Retired default-only
examples and batch improvers were removed under the approved rebuild decision.

## Asset and format contracts

`asset_derivatives.py` makes immutable 128/256/512px derivatives, default 256,
including embedded GLB images. `asset_bundle` derives primary and optional
`distant_path` together with identical local scaling and independent content hashes.
Save, snapshots, Undo payloads and preview invalidation retain both paths. It never
upscales or overwrites originals. Rebuilt
buffers remove old embedded image bytes; identical contents share buffer ranges
and content-addressed paths. Original material atlases/UVs survive. Procedural
modules batch faces by shared material without per-instance texture copies.
Diagnostics report compressed payload sizes and decoded texture memory separately.
Standalone asset import accepts sources up to 64 MiB, while the derived Undo command
still has the 16 MiB limit. High-quality library originals and procedural source
geometry remain available for another export profile.

General placement adds `yaw_offset_mdeg` to quarter-turn orientation. Inspector and
placement controls expose it; MapKit uses the same transform for visual geometry,
lights, collision and occupancy. Every own format remains v1. Slope-based Water and connected-surface removal are available; islands are made
by raising terrain. Ordinary authoring/history remain available. No pedestrian/traffic simulation
or whole-building interiors are generated.

## Authored default-world workflow

[`examples/default-worlds`](../examples/default-worlds/) contains the current
Village, Neon Harbor, Deep Forest, Red Canyon, Snow Mountain, Machine Factory and
Sky Park sources, v1 packages and three road-route plans each.
Their IDs are `default-<theme>-authored-20261009`. The user approved the five actual
Village renders on 2026-10-09. All seven themes are implemented; detailed driving,
device performance and the remaining themes' human art acceptance are separate.

The Village recipe explicitly lays out Market Street and its clock hall,
orchard cottages, ridge gardens, two working farms, crops and irrigation, river
meadow, two supported bridges and a wooded ridge. Terrain shares 2 m integer
samples at every 32 m cell edge. Roads shape their cut/fill; building pads connect
to yards and paths. Vegetation and small props fill declared habitats only.
All primary and distant models are newly authored MapKit assets. General Editor
creation, imports, semantic infill and manual editing remain independent.

Generate one theme into a fresh location, then validate every cell:

```sh
rtk proxy .venv/bin/python map-editor/scripts/default_worlds.py /absolute/new-worlds --theme village --kit map-kit --cli map-kit/target/debug/mapkit
```

The CLI accepts `village`, `neon-harbor`, `deep-forest`, `red-canyon`, `snow-mountain`,
`machine-factory` or `sky-park` and rejects existing theme destinations.
Source recipes, geometry helpers and model
code determine the recorded authoring fingerprint. Package/world hashes change
with content. Own formats stay v1. The final seven-map distribution budget is
256 MiB with textures at most 512 px; runtime budgets remain unchanged.

Capture through `run_godot_checks.py --project editor --script render_default_world
--rendered`, with `DEFAULT_WORLD_SOURCE` and a fresh `DEFAULT_WORLD_OUTPUT`.
Optional `DEFAULT_WORLD_THEME` and `DEFAULT_WORLD_VIEWS` select one theme/view.
The five Village views are main street, farm road, nature road, river distance
and overview. All use common near/distant renderers, quality 2 and a 384 m view
limit. Road eyes are 1.7 m above the surface; the overview is orthographic.
Images live in each theme’s `review/`; the report binds them to the package hash.
Harbor adds paired daytime/nighttime high-street views, cargo road, coastal
promenade, channel-bridge distance and a city overview. Each view records its
authoritative time; the common bounded streetlight pool is included.
Client tooling seals routes and eight-car grids using Runtime, then publishes
only completed local candidates under `client/maps/default-worlds`.

Neon Harbor is an explicitly designed 1920 × 1280 m coast. Its commercial streets,
residential courtyards and service alleys lead through warehouses to two cargo
quays and a supported channel bridge. Original MapKit shop/apartment variants have
storefronts, entrances, balconies, rear stairs and rooftop equipment. Container
stacks, open gantry cranes, loading docks, parked trucks, pipe runs, quay walls and
moorings define working spaces. Coastal woodland frames the northern hills;
vegetation fills only those declared habitats. Paired neon bindings preserve sign
colour at night and disable emission during daylight. Far mesh GLTF colours use
the same colour space as the primary importer on both common render backends.

Default-only historical source/distribution families, previews, course catalogs
and batch improvers were removed. Git retains history. Shared sign/climate
examples, practice, physics tests, ordinary generation and common asset libraries
remain. `driving_features.py` isolates common feature placement and the independent
five-feature demo from the retired default-map batch script.

## Focused validation

Current independent roads are compiled from editable cubic controls, with analytic
lateral frames and continuous shared junction boundaries. Default profiles retain
broad hills and valleys. Red Canyon's close wash branch was rerouted, bridge
clearance was opened in Canyon/Forest and Snow's three climbs were lengthened.
The seven IDs, bounds and principal landmarks are unchanged. Original height PNGs
contain the landscape and explicit foundation pads; road cut/fill is derived at
runtime and restores when a road moves or is removed.

On macOS ARM64 / Godot 4.7.2, native generation passes every execution cell and
`mapkit audit-roads` checks actual collision triangles every 0.5 m along five width
lines, junctions and the road-paint display budget. The tolerance is 1 cm and the
maximum designed grade is 12%:

| Theme | Generated cells | Collision samples | Max error (cm) | Max designed grade |
| --- | ---: | ---: | ---: | ---: |
| Village Driving Park | 1,050 | 43,053 | 0.489 | 11.856% |
| Neon Harbor | 2,400 | 70,745 | 0.500 | 8.871% |
| Deep Forest | 3,025 | 52,862 | 0.494 | 11.294% |
| Red Canyon | 2,850 | 62,773 | 0.489 | 8.450% |
| Snow Mountain | 3,250 | 58,854 | 0.486 | 10.582% |
| Machine Factory | 2,025 | 50,994 | 0.000 | 0.000% |
| Sky Amusement Park | 3,000 | 41,210 | 0.477 | 10.641% |

All 17,600 cells and 380,491 collision samples pass. The MapKit feature suites
also cover curves, grade transitions, explicit junctions, overpasses, cell seams,
the complete palette over terrain, occupied supports, source preservation, shared
attachments, race binding and free-roam export. Recipe tests cover deterministic
reconstruction, terrain seams, connected routes, bridge clearance and supports.

The strict Editor `composite_road_validator`, `track_workbench_validator` and
`document_history_validator` pass road controls/width/policy, road-to-track
connections, attachments, derived-terrain restoration, bounded Undo/Redo,
save/reopen, original preservation on failure, cancellation, stale document
protection and preview mesh reuse. Locale key parity passes in English, Korean
and Japanese. Road previews prepare a bounded 3 × 3-cell window asynchronously;
owner/resource budgets are unchanged.

All 38 actual common-renderer views pass strict diagnostics and owner release,
including a fixed-camera Red Canyon junction comparison against its original
package. The old large junction step is absent in the new capture. Peak shared
cache charge is 133,667,072 bytes, below 128 MiB; the largest far-cell charge is
4,948,800 bytes. This is a bounded display/admission result, not an FPS benchmark.
Each `review/<theme>-render-report.json` binds images to the final package SHA-256.
Runtime seals all 21 recommended courses and validates eight maximum-vehicle/
glider start footprints per course. Human completion remains unverified.

Earlier paired-asset, source/cancel/release, near/far terrain and water-color
regressions remain recorded in their owning contracts. No automatic full suite,
export matrix or prolonged performance run was added. The existing 49-piece
track-edit completion target remains unmet; see [editing performance](TRACK_EDIT_PERFORMANCE.md).

Detailed editing feel, driving, course completion, other themes' art and device
performance are user checks. The first Village art direction was approved before
this road revision; that is not acceptance of the new road rendering. Client
verification stops at standalone startup and the initial menu.

The recipes are a scripted authoring workflow. Their editable sources open in
Editor, but general New region does not reproduce these authored worlds. General
asset gizmos and a reusable scenery assembly palette remain separate usability
work; the road/track tools do not implement arbitrary asset editing.
