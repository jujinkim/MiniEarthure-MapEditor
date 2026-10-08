# Authored default worlds and general environment tools

Editor owns `environment_generation.py`, the layout/composition/metrics modules,
`environment_profiles.py` and the metre-scale modules in `environment_assets.py`.
MapKit owns current v1 validation, cell geometry,
package I/O and common rendering. Client/Host receive finished packages and assets;
they do not receive this layout engine. Default worlds now use separate, explicitly
authored recipes in `default_worlds.py` / `default_village.py`; generic generation
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
lights, collision and occupancy. Every own format remains v1. Water/Island tools
and ordinary authoring/history remain available. No pedestrian/traffic simulation
or whole-building interiors are generated.

## Authored default-world workflow

[`examples/default-worlds`](../examples/default-worlds/) contains the current
Village source, v1 package, three road-route plans and five actual review images.
Its ID is `default-village-authored-20261009`. The user approved the five actual
Village renders on 2026-10-09; the other six themes now proceed in the agreed order.
A partial catalog is an authoring checkpoint, not a seven-map release.

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

The CLI rejects existing theme destinations; the remaining recipes are still to
be implemented. Source recipes, geometry helpers and model
code determine the recorded authoring fingerprint. Package/world hashes change
with content. Own formats stay v1. The final seven-map distribution budget is
256 MiB with textures at most 512 px; runtime budgets remain unchanged.

Capture through `run_godot_checks.py --project editor --script render_default_world
--rendered`, with `DEFAULT_WORLD_SOURCE` and a fresh `DEFAULT_WORLD_OUTPUT`.
Optional `DEFAULT_WORLD_THEME` and `DEFAULT_WORLD_VIEWS` select one theme/view.
The five Village views are main street, farm road, nature road, river distance
and overview. All use common near/distant renderers, quality 2 and a 384 m view
limit. Road eyes are 1.7 m above the surface; the overview is orthographic.
Images live in `village/review/`; the report binds them to the package hash.
Client tooling seals routes and eight-car grids using Runtime, then publishes
only this completed local candidate under `client/maps/default-worlds`.

Default-only historical source/distribution families, previews, course catalogs
and batch improvers were removed. Git retains history. Shared sign/climate
examples, practice, physics tests, ordinary generation and common asset libraries
remain. `driving_features.py` isolates common feature placement and the independent
five-feature demo from the retired default-map batch script.

## Focused validation

On macOS ARM64 / Godot 4.7.2, five authored-world Python tests pass: exact
reproduction, 1,050 terrain-cell seams, road/water separation, bridge support,
three distinct routes and paired assets. Native validation generates all 1,050
cells. Maximum road grade is 11.165%. Package size is 1,271,545 bytes; native
validation peak allowance is 698,787,330 bytes, within the existing source budget.
This is an admission estimate, not measured whole-map residency.

Three asset-derivative tests and Editor paired-file save/Undo/Save As/hash/cancel/
release checks pass, including small-prop quality changes. Package restoration
and common display-quality validators pass. General environment generation's
four regressions and the extracted five-feature demo regression pass after
removing the default-specific scripts. The owned-worker validator also passes
29 checks for preview, cancellation, stale result, one Undo/Redo, recovery,
atomic publication and reopening. Full Editor interaction was not rerun.

All five actual Village captures pass strict diagnostics on the Compatibility
renderer. The near/far terrain comparison has a maximum RGB difference of 1/255.
A bounded dense-street comparison renders the same 174 cells normally and with
forced authored-far geometry: draw calls 1,563→432, shared-cache allowance
92,779,776→63,963,136 bytes. Visible primitives increase 145,593→187,650 because
batching/occlusion differs; this is not an FPS or device-performance pass. Largest
far-cell retained/display charge is 2,270,208 bytes. Far resource owners retire
after capture cancellation. No execution/admission cap was raised.

Visual review removed terrain tint seams, a deep road cut and canal/road overlap;
farms, foreground crop rows, river vegetation and shop frontages were adjusted.
**The user approved Village's art direction on 2026-10-09**. Detailed driving/course completion, editing
interaction and device performance are user checks; object counts and automated
success do not establish visual acceptance.

The current default recipe is a scripted authoring workflow. Its editable source
can be opened and modified in Editor, but the general New region command does not
reproduce this authored result. A reusable asset/assembly palette and general 3D
object gizmos/surface snapping remain separate, incomplete usability work; the
Track Mode tools do not establish those capabilities for arbitrary assets.
