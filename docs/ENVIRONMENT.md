# Environment design and generation

Editor owns `environment_generation.py`, the layout/composition/metrics modules,
`environment_profiles.py` and `environment_assets.py`. MapKit owns v1 validation,
cell geometry, packages and rendering. The authored default worlds are in
[ARCADE_WORLD](ARCADE_WORLD.md).

## Environment profile

Open **Authoring settings → Environment**. Choose a map concept, independent
architecture/climate/settlement dimensions, latitude/longitude, time zone and
sunrise/sunset defaults. Apply is one Undo command (including removing an optional
profile). Regional overrides are ordered centimetre polygons; the first match wins.
Light bindings use asset IDs and GLB material indices with explicit bulb positions,
ranges and colours; empty bindings add nothing. Invalid metadata never mutates the
document.

The 3D preview uses the same MapKit materials and sky; preview hour/weather does not
change source data. Environment start and preview share six localized
time presets (09:00/12:00/17:00/18:00/21:00/06:00). Existing non-preset times stay
exact until a new selection; opening a picker never rounds them. Session weather is
not written into packages. `examples/driving-school-atmosphere` and
`examples/world-themes-atmosphere/<concept>` are atmosphere examples with their own
`.memap` and package lock.

## General generation

Configure the root `.venv` Python in Import settings. **Create → New region** and
**Create → Complete selected area** share one engine: choose theme, seed, density,
texture size and bounds, review composition and diagnostics, then apply. Bounds
start around the selection, or the document bounds. New regions publish to a new
absolute directory by sibling rename. Infill needs a saved free-roam project and is
one Undo command; a result over the 16 MiB history limit is applied without Undo
and releases earlier history with a warning. More than 18,000 generated objects
warns and nothing is dropped; more than 200,000 warns that the game refuses the
map. There is no time limit: after 600 s a running-time warning appears and Cancel
remains. Payload hashes are rechecked on apply; preview, cancel,
failure and stale documents publish nothing.

`ThemeProfile` declares facility groups, functional hubs, district density ranges,
hierarchy/loop roads, natural-space floors and asset assemblies.
`GenerationContext` holds terrain, source geometry, semantic regions, protection and
scale; `GenerationRequest` picks mode/theme/seed/bounds; `GenerationResult` holds
candidate patches, immutable assets, ownership hashes and diagnostics.

Stages: terrain/water, landscape-aware hubs, road hierarchy, road-facing
assemblies, working access, landscape bands and vegetation, then measurement and
bounded alternative sites. Rules:

- Urban concentration is 20–35% of land; tensor directions apply only inside
  districts. Remote themes use one terrain-cost loop with three accesses; their
  nature floor is 85%, village green space ≥65%.
- Road widths: 10–12/6–8/4–6 m urban arterial/connector/service, 6/4 m remote
  main/access. Each world reserves a grounded 200 m straight. Grades stay below 12%.
- Lot occupancy targets 30–55% residential/commercial and 25–45% production at
  density 1.0. Required failures block Apply; dense-cell checks include GLB
  triangles, collision proxies and every touched 32 m cell.
- Terrain shares global samples across 32 m cell edges; polygon holes survive
  triangulation; residual slivers are rejected. Infill never alters existing
  roads or terrain.

The preview shows district use/density, road hierarchy, parcels/entrances,
protected polygons and diagnostic locations; hovering an issue names its district
and reason. The tensor layout is an independent implementation informed by
[ProbableTrain's overview](https://github.com/ProbableTrain/MapGenerator/blob/master/docs/algorithmoverview.md)
and [Chen et al., 2008](https://web.engr.oregonstate.edu/~zhange/images/street_sig08.pdf);
no code from those projects is included. Seed streams use region/parcel/tile
identities so changes elsewhere do not shift another region's sequence.

## Infill ownership

OSM imports keep original way/relation IDs, land-use polygons, inner rings and
protected regions in Editor provenance. Source polygons stay unscaled; an
`authored_regions` copy and infill assets receive the single 1:8 conversion.
Unknown land use gets low-intensity ground cover, never guessed buildings. Generated
scenery is labelled as an estimated game environment. Original roads, buildings,
manual objects, water, entrances, protected areas and forest/orchard sources are
fixed.

Ownership hashes travel with save, recovery and Undo/Redo. Only unchanged owned
objects inside the selection regenerate; a 64 source-metre boundary band stays
fixed. Facility assemblies regenerate atomically: crossing the boundary or editing
or deleting one member keeps the whole assembly. Deletion tombstones persist.
Rerunning infill does not duplicate objects. Terrain, road topology and supports
stay fixed.

## Asset derivatives

`asset_derivatives.py` makes immutable 128/256/512 px derivatives (default 256),
including embedded GLB images. `asset_bundle` derives the primary and optional
`distant_path` with identical scaling and independent hashes; save, snapshots and
Undo keep both. Originals are never upscaled or overwritten; identical contents
share content-addressed paths and material atlases/UVs survive. Standalone asset
import accepts sources up to 1 GiB (warning above 64 MiB) and textures up to 128
megapixels (warning above 16); a change over the 16 MiB Undo budget is applied
without Undo.
Placement adds `yaw_offset_mdeg` to the quarter-turn orientation, applied by MapKit
to visuals, lights, collision and occupancy. No pedestrian/traffic simulation or
building interiors are generated.

## Validation

`tests/environment_validator.gd` covers adoption, Undo/Redo and invalid edits;
`tests/test_atmosphere_assets.py` checks atmosphere-example geometry and payload
preservation. Detailed editor interaction and devices are user checks.
