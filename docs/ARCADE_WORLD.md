# Environment worlds and semantic infill

Editor owns `environment_generation.py`, the layout/composition/metrics modules,
`environment_profiles.py` and the metre-scale modules in `environment_assets.py`.
MapKit owns current v1 validation, cell geometry,
package I/O and common rendering. Client/Host receive finished packages and assets;
they do not receive this layout engine. The seven default themes use these dimensions:

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
objects. Existing source files and earlier example/package directories are preserved.

## Asset and format contracts

`asset_derivatives.py` makes immutable 128/256/512px derivatives, default 256,
including embedded GLB images. It never upscales or overwrites originals. Rebuilt
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

## Current editable catalog

[`examples/environment-world-varied`](../examples/environment-world-varied/) contains the seven
editable projects, validated `.memap` files and three connected road-route plans
per theme. Seed 9026 and the algorithm fingerprint are recorded in each project.
Earlier example directories remain intact. To reproduce into a new directory from
the superproject, using the already built public MapKit CLI:

```sh
rtk proxy .venv/bin/python map-editor/scripts/environment_catalog.py /absolute/new-worlds --kit map-kit --cli map-kit/target/debug/mapkit
```

The optional `--prepared` path reuses a current-fingerprint candidate after checking
every payload hash. It never overwrites a prior output. Shared-render captures use
`tests/render_environment_maps.gd` with `REGIONAL_SOURCE` and a new
`REGIONAL_DESTINATION`; bounded cell groups cover core, transition and outer areas.
Each theme has five review views. Overview, signature and a road-level 1.7 m eye
view form the 21 distribution previews; transition and outer views support review.
The offline overhead view draws all prepared props; gameplay distance culling
would otherwise omit small objects without the runtime distant renderer.
Use `run_godot_checks.py --rendered` for capture and display-quality/material
validators: headless dummy rendering does not retain their GPU instance data or
shader defaults. The current rendered validators pass.
Runtime/Client offline tooling seals course hashes and validates the eight-car
start grid separately. Client receives these finished files and 256px distribution
assets, without the Editor Python engine. Exporting another texture profile requires
new packages, world identities, courses and preview hashes.

## Focused validation

On macOS ARM64 / Godot 4.7.2, the four generation and five composition Python
regressions pass. These cover 7 themes × seeds 9026/17/410, actual geometry metrics,
determinism, terrain seams, rotated clearances, density-independent remote topology,
manual edits/deletions, atomic boundary preservation across three reruns, semantic
holes/protection, exact 1:8 scale and unknown-space restraint. Run with the root
`.venv/bin/python -m unittest discover -s map-editor/tests -p 'test_environment_*.py'`.
The three catalog regressions additionally verify dimensions, package/source bytes
and distinct reproducible hub routes. Spatial seed tests skip terrain PNG baking;
all seven distribution worlds receive full terrain and native validation.

The owned-worker validator passes 29 checks for preview, cancel, stale result,
one Undo/Redo, recovery, new-directory publication and reopening. The preview
validator exercises all five overlay layers, diagnostic district/location and
blocking Apply. These run through `run_godot_checks.py --project editor --script
environment_native_validator --script environment_preview_validator` with isolated
user data. Existing native builds and valid imports are reused.

Seed 9026 / density 1.0 packages pass native save/load validation and six cells per
theme ranked by geometry/collision cost (42 total). Urban core land is 26.1–26.5%;
remote nature is 98.8–99.0%, with one graph cycle and three accesses. Measured
residential/commercial parcel occupancy is 33.5–48.3% and production/warehouse
occupancy is 40.0%. Maximum road grade is 10.10%; every map has a 200 m launch
straight. No triple frontage repetition or unresolved required diagnostics remain.
Native validation peaks range from 326,090,814 to 1,194,603,562 bytes, below the
existing 1536 MiB Android source budget. These are admission estimates, not measured
whole-map runtime residency. No required facility or collision was removed to fit.

Shared-render checks compare core, transition, outer and road-eye views; the 21
selected overview/ground/signature images belong to the Client distribution.
Native recommendation preparation validates all 21 courses, their world/surface
bindings and all eight start-grid footprints. These are offline authoring checks.

Detailed editing interaction, driving/course completion, device acceptance and final
art quality remain user checks. A package or screenshot check does not complete them.
