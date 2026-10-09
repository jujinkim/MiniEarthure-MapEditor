# Authored default worlds and general environment tools

Editor owns `environment_generation.py`, the layout/composition/metrics modules,
`environment_profiles.py` and the metre-scale modules in `environment_assets.py`.
MapKit owns current v1 validation, cell geometry,
package I/O and common rendering. Client/Host receive finished packages and assets;
they do not receive this layout engine. Default worlds now use separate, explicitly
authored recipes in `default_worlds.py`, `default_village.py`, `default_harbor.py`, `default_forest.py`, `default_canyon.py`, `default_snow.py` and `default_factory.py`; generic generation
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
Village, Neon Harbor, Deep Forest, Red Canyon, Snow Mountain and Machine Factory sources, v1 packages and three road-route plans each.
Their IDs are `default-<theme>-authored-20261009`. The user approved the five actual
Village renders on 2026-10-09; Sky Park remains after Machine Factory.
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

The CLI accepts `village`, `neon-harbor`, `deep-forest`, `red-canyon`, `snow-mountain` or `machine-factory` and rejects existing theme destinations;
the remaining recipes are still to be implemented. Source recipes, geometry helpers and model
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

On macOS ARM64 / Godot 4.7.2, the five Village authored-world Python tests pass: exact
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

Harbor's four additional recipe tests pass reproducibility, all 2,400 terrain-cell
seams, centimetre-valid nonoverlapping ground paint, water/road separation, flat
bridge approaches, pier/container support and paired neon bindings. Native
validation generates every cell, with a 5.782% maximum road grade. The package is
1,597,761 bytes; its validation peak allowance is 853,060,542 bytes. Native course
preparation seals all three routes and checks each of eight maximum-vehicle grid
footprints. Six actual views pass strict diagnostics and release far owners.
Model review removed aliasing from fine container rib geometry, fixed approach
junctions and kept crane/bridge openings in the authored far mesh.

The bounded Harbor day-street comparison uses the same 175 cells: draw calls
1,184→616, primitives 147,000→275,122, shared-cache allowance
83,064,832→63,963,136 bytes. Its largest far-cell charge is 3,719,936 bytes. The
six normal captures peak at 126,376,960 shared-cache bytes, below the existing
128 MiB preview limit. This is a display-work comparison, not an FPS benchmark.
Harbor art, full course driving and device performance remain user checks.

Deep Forest keeps its 1760 × 1760 m bounds and explicitly connects a ranger
station, old-growth crest, fern hollow, cedar valley and lake camp through two
supported gorge crossings. Cedar, beech and sapling crowns have different growth
forms; shrubs, spatial fern patches, fallen timber, riparian reeds and rock groups
continue below the canopy. Only declared habitat fill uses deterministic jitter.
The first forest camera is sampled on the actual road centreline; the lake and
camp overview stays within the existing view distance. Review removed submerged
riverbank plants from the lake interior and corrected the common near/far water
material discontinuity, without changing physical water or admission caps.

Four forest recipe tests cover exact reconstruction, 3,025 shared terrain seams,
connected/distinct courses, road-water separation, flat bridge aprons, eight pier
supports and dry tree/shrub roots. Native all-cell validation passes with a
maximum road grade of 11.862%, 22,093 placements and a 2,399,979-byte package.
Its validation peak allowance is 939,973,474 bytes. Forest's five fixed views
show the hollow road, ranger station, camp, lake/river distance and an overview.
The common water pixel test passes low/high quality on Compatibility and Forward
Mobile on the same M1; mean near/far RGB delta stays below 1/255, terrain colour
remains matched and far water resources retire. These automated counts and colour
checks do not constitute human art/driving/device acceptance.

Forest's native preparation seals all three courses and eight-car footprints. The
five final captures pass strict diagnostics and resource release, with a maximum
127,009,472-byte shared-cache allowance and 2,372,352-byte far-cell charge. On the
same 172-cell forest-road view, normal→authored-far draws are 2,107→677, primitives
391,947→301,114 and cache 106,520,576→63,963,136 bytes. This bounded comparison
does not measure frame rate or device performance.

Red Canyon's 2400 × 1200 m source connects two gorge bridges, layered cliff
roads, a dry wash descent/switchback, mesa overlooks and a quarry with crushers,
conveyors, static loaders, stockpiles and an office. Continuous sculpted terrain
backs four eroded sandstone silhouettes; talus and sparse cactus/scrub fill the
landscape. Visual review widened excessive road cuts and removed terrain from
under the bridge decks. The source paint helper clips at world bounds.

Four canyon tests pass exact reconstruction, all 2,850 cell seams, connected
courses, 6.709% maximum grade, flat aprons, eight grounded piers and bridge/terrain
clearance. Two model tests retain far silhouettes and open crusher/bridge bays.
Native validation generates every cell, with 4,926 placements and a 1,784,540-byte
package; its validation peak allowance is 478,718,812 bytes. Human art, course
driving and device acceptance remain separate user checks.

Five final canyon captures pass strict diagnostics and release checks. The same
174-cell cliff-road comparison uses normal→authored-far draws
689→225, primitives 96,914→91,710
and shared cache 72,317,696→63,963,136 bytes. Normal views peak at
77,969,408 cache bytes; the largest far cell is
693,248 bytes. These stay within existing caps, not an FPS acceptance.
The common sky's dark lower-horizon step was removed; day/night pixel deltas
stay below .024 in Compatibility and .012 in Forward Mobile.

Snow Mountain's 1600 × 2080 m recipe follows a broad alpine valley from six
timber lodges through fir woods to a treeless ridge, rock cirque and sheltered
lookout. Snow-covered tree ages, granite outcrops, a solid frozen tarn, roadside
drifts and 138 grounded guardrail sections mark altitude and exposure. Road
heights follow the terrain profile before detailed cut/fill; the maximum grade
is 10.389%. The lookout remains beside the road, retaining the native conservative
placement/road-clearance contract.

Four snow recipe tests pass exact reproduction, all 3,250 terrain seams, distinct
connected routes, altitude-dependent woodland, the frozen surface and grounded
shelter. Native validation generates every cell: 4,777 placements, a 2,003,102-byte
package and a 525,841,638-byte validation peak allowance. Human art, detailed
course driving and device performance remain separate user checks.

The frozen shore is an open rocky clearing. Its solid surface sits above the
terrain basin, avoiding coplanar flicker; the representative eye follows the
actual ridge ground height.

Five actual snow captures, all three native courses and eight-car start footprints
pass. On the same 165-cell valley view, normal→authored-far draws are
1,115→254, primitives 130,601→106,782
and cache 75,973,376→63,963,136 bytes. Normal captures peak at
93,686,528 cache bytes and 601,856 per far cell.
Far leases retire; no cap changed. This is a bounded render comparison, not FPS.

Machine Factory keeps 1440 × 1440 m bounds. Its level industrial grid connects
production, process tanks, boiler courts, electrical equipment, maintenance,
administration and a crane/warehouse yard. Continuous supported racks and feed
branches link tanks; elevated busbars connect transformers. Concrete gate access
links each work yard to the road. A stormwater channel and wooded perimeter frame
the site. Review bounds include the actual highest placed model, preserving tall
stacks and later landmark silhouettes without increasing render distance.

Four factory tests pass exact reconstruction, 2,025 terrain seams, road/water
separation, connected/distinct routes, pipe spans, gate access and tall-model
review bounds. Native all-cell validation passes: 3,044 placements, zero road
grade, a 1,358,915-byte package and 624,130,158-byte validation peak allowance.
Human art, detailed driving and device performance remain separate user checks.

Five actual factory views, all three sealed courses and their eight-car start
footprints pass. The bounded 171-cell production view changes normal→authored-far
draws 589→261, primitives 111,240→110,546
and cache 90,481,408→63,963,136 bytes. Normal views peak at
97,811,456 cache bytes and 1,142,144 per far cell.
Far leases retire; this is a render-work comparison, not FPS acceptance.
