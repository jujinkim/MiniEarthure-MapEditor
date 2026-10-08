# Environment worlds and semantic infill

Editor owns `environment_generation.py`, `environment_profiles.py` and the metre-scale
modules in `environment_assets.py`. MapKit owns current v1 validation, cell geometry,
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

`ThemeProfile` declares required facility groups, area/dimension/density ranges,
entrance orientation, access, adjacency and exclusions. `GenerationContext` holds
terrain, source geometry, semantic regions, protection and source scale;
`GenerationRequest` selects mode/theme/seed/bounds; `GenerationResult` contains the
candidate patches, immutable assets, ownership hashes and diagnostics.

The stages are terrain/water, functional districts, mixed tensor-field roads,
noded graph/block extraction, road-facing parcels, frontage/service yards,
clustered vegetation/details, then quality checks and bounded alternative sites.
Terrain uses shared global samples across 32 m cell edges. Forest/mountain fields
weight contours; urban fields mix grid, radial and shoreline directions. Dead ends,
cut edges and invalid rings are diagnosed. Open parks, fields and courtyards remain
intentional surfaces. Polygon holes are preserved with constrained triangulation;
small invalid rounded slivers are rejected. Facility sizes come from actual model
footprints; their slope-limited foundations flatten only newly generated terrain.
All required groups and required object lists are checked; unresolved failures block
Apply. Native preview checks representative dense cells within unchanged budgets.

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
Manual edits and deletions are protected. Terrain, road topology and structural
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

## Focused validation

Current checks cover deterministic regeneration, required facilities, terrain seams,
regional boundaries, manual edits/deletions, no duplicate reruns, semantic holes and
protection, exact 1:8 scale, unknown-space restraint and rotated footprints. The four environment Python tests and 86 OSM feature tests pass, including
XML/PBF region identity, crop/streaming, holes and protected boundaries. The
29-check owned-worker validator checks preview, cancel, stale result, one Undo/Redo, recovery,
new-directory publication and reopening. The OSM authoring validator passes 45 checks and shared document history passes
571 assertions. Stale fixtures were updated for the initial track document and
the existing rejection of overlapping independent imports.
Seven full-size packages pass native save/load validation; two dense cells per theme
were generated within existing limits. Their validation peaks are below 640 MiB.
Asset derivative/source-preservation tests and the asset worker regression pass.

Detailed editing interaction, driving/course completion, device acceptance and final
art quality remain user checks. A package or screenshot check does not complete them.
