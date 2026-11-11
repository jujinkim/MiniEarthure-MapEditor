# Regional source composition

Real-city recipe v1 accepts optional `regional` inputs. Omission preserves the
existing city import rules. MapKit owns the shared
[appearance catalogue](../addons/mapkit/spec/APPEARANCE.md); Editor owns acquisition,
classification, source fusion and author selection. No consumer contacts an external
service during play.

## Local sources and acquisition

Use the root `.venv` and pinned `requirements-import.txt`. Explicit authoring
acquisition uses DuckDB's installed `httpfs` and `spatial` extensions and rasterio:

```sh
python scripts/acquire_regional_sources.py --bbox WEST SOUTH EAST NORTH \
  --destination /absolute/new/snapshot --catalog-cache /absolute/catalog-cache
```

The command requests only intersecting Parquet row groups from a fixed Overture
release and native-grid windows from ESA WorldCover 2021 v200 COGs. STAC metadata
is cached with its URLs and hashes. `acquisition.json` records source tiles, ETags,
windows and selected Parquet metadata. `sources.json` supplies the two recipe
source descriptors. An existing destination is refused; a failed acquisition
publishes no snapshot and retains user sources. Only its own temporary files are
retired. Required DuckDB extensions are installed explicitly during tool setup.

Each descriptor has exactly `path`, `sha256`, `release`, `bbox`, `source_url` and
`license`. Paths resolve relative to the recipe. `worldcover.release` is
`2021-v200`; `buildings.release` is an immutable date/revision. Snapshots must cover
the requested OSM extent. Missing files, hash changes, invalid coverage, unsupported
raster classes, invalid footprints and missing requested building parts fail the
whole candidate. Offline generation never substitutes a different release.

WorldCover is a single-band WGS84 native 10 m grid, with the eleven published
classes. It supplies broad cover, including built-up, rock/bare ground, vegetation,
crops, wetland and snow. It supplies no individual sidewalk or flowerbed evidence.
OSM areas, detailed roads, buildings, water and vegetation take precedence. Water
pixels are not converted to traversable ground. Classification and geometry are
clipped to the saved playable boundary on the shared map-centimetre lattice.

Overture snapshots are bounded GeoJSON FeatureCollections with fixed `release`,
`bbox`, GERS IDs, source references and available height/use/facade/roof information.
Building parts retain parent IDs and their metric heights. Taller visible parts
precede lower ones and the parent remainder; their shared interior seams use the
native two-map-centimetre clearance. Point-touching components of one source
part share a native building owner, retaining every outline and height. Courtyards
that meet another ring at a lattice vertex use constrained triangle parts under
that owner, preserving the exact outer boundary and empty courtyard. Distinct
part styles remain separate. The parent outer boundary remains the source
outline up to the integer lattice. Source OSM IDs (including
compact versioned `w…@…` and `r…@…` references) and footprint intersection-over-union
of at least one half identify duplicates. OSM geometry wins. Other overlap conflicts
and underground objects are reported by source ID; they never silently replace an
OSM footprint. Supplemental footprints that conflict with retained OSM road
space, including rounded junctions and bridge edge collision, are excluded with
both identities in the report. The remaining buildings are classified and added with independent
identities. All horizontal and vertical source metres receive the same 1:D scale.

## Recipe and precedence

```json
{
  "version": 1,
  "profile": {
    "architecture": "nordic_timber",
    "climate": "cold",
    "settlement": "village",
    "terrain": "mountain"
  },
  "regions": [],
  "worldcover": {
    "path": "auxiliary/worldcover-2021-v200.tif",
    "sha256": "<exact file SHA-256>",
    "release": "2021-v200",
    "bbox": [8.0, 60.0, 8.1, 60.1],
    "source_url": "<fixed source URL>",
    "license": "<source attribution>"
  }
}
```

Put this object under the real-city recipe's `regional` key; the source example
needs the actual acquisition descriptor. Both sources are optional, but a requested
source must succeed. Profiles use independent catalogue axes. Up to 64 ordered
regions each contain `id`, a WGS84 longitude/latitude `polygon` and a partial
`profile`. The first matching polygon wins; its provided axes override the base
profile. Native saved regions contain the resulting axes in map centimetres.

Optional `overrides` contains `osm_sha256` and `objects`. Each object names one
selected `source_id` and any of `architecture`, `building_type`, `material`,
`ground`, `height_m`, `roof_shape`, `roof_material`. Targets must exist in that exact PBF snapshot; all are checked
before mutation. Precedence is author correction → specific source information →
auxiliary information → local context. Countries do not force one building style.

OSM building use, material, roof and surface tags are retained before optimization.
School, university, hospital, civic, religious, station, commercial, residential,
industrial and agricultural types keep distinct style IDs. Record grouping keeps
type, style, region and evidence boundaries. Original heights beat incompatible
floor counts. Missing heights use source floors, matched auxiliary data, a same-use
neighbour median, then a conservative type/profile estimate. Randomness chooses
neither building type nor storey count. Regional footprints retain their source outline by default. Explicit
`road_conflicts: "trim_buildings"` permits only partial carriageway-conflict cuts,
with a four-map-centimetre rounding margin for native mouth, offset, intersection, curve and building
quantization; sidewalks do not enlarge the cut. Bridge collision edges include the
shared 20-map-centimetre rail outset. A building with the required 50-map-centimetre
roof clearance below a deck retains its footprint. Height inference precedes this check. Buildings above tunnels retain their
footprint only when native validation confirms 50 map centimetres between every
overlapping ceiling face and the building base.
Shallow tunnel portals use the same authorized partial-conflict cut and report.
The production report records source building/road IDs, original/removed/remaining
source areas and the removed WGS84 geometry. A completely covered building fails
instead of disappearing. The policy enters the input fingerprint. Footprints are
not simplified to fit a density target. Road bends remain
unsimplified when their full paved corridor would newly invade a retained source
footprint; this applies to ordinary chains and closed-road pieces. Local roads
without source widths or lane counts use retained OSM building clearance to
reduce the class lane estimate, with 3.25m lanes and a disclosed context receipt.
Source dimensions and author corrections retain priority. Supplemental footprints
also reserve space before procedural street furniture is placed. Shared lattice,
courtyard, overlap and native validity rules still apply.

Ground appearances remain separate from physical `Surface`. Explicit paving and
natural ground keep different appearance IDs even when they share physics. A
sidewalk connection candidate requires road proximity within ten source metres,
a nearby retained building or barrier, built-up context and clear space outside
buildings, water and natural ground. Its qualified area is disclosed in the report.

## Editor, publication and reports

The recipe classifies before OSM grouping, imports optional facility CSV, prepares
regional composition in an owned worker, then applies DEM and exports. Auxiliary
building parts retain source-relative bases in their receipt and join the same
perimeter-grounding step as OSM buildings. Authored bases remain authoritative.
The worker
uses the existing token, command epoch, document signature and prepared-command
transfer. Cancel, owner closure, stale completion and failure retain the prior
accepted document. Apply is one validated command with normal Undo limits. Source
paths are excluded from the input fingerprint; releases, hashes, coverage,
attribution, profiles and corrections are included. Source names and full license
credits also occupy the package attribution fields displayed by the Client;
structured provenance stays in the accompanying notice. Editor code identity includes
root Python modules as well as GDScript and importer Python modules.

Large `groups` and `objects` evidence arrays may use an optional `<key>_blob`
inside the v1 notice: `codec: gzip-base64`, exact expanded `bytes`, `sha256` and
base64 `data`. The JSON array is retained losslessly; source hashes, coordinate
frames and license credits remain plain. Decoders bound expansion to 32 MiB and
verify length, hash and JSON before using evidence. Ambiguous or damaged records
refuse composition/profile changes. Recipe reports retain expanded OSM and
auxiliary classifications. This keeps detailed provenance within the existing
package manifest allowance without discarding source identities or corrections.

The import review's exact details contain `regional` facts and per-group evidence.
The production report includes type/style distributions, source/auxiliary/context
counts, duplicate/conflict reasons and source IDs. The Environment panel changes
classified architecture by map/region: groups crossing a new profile boundary
split into independent records while retaining every solid's footprint and height.
Source/author wall materials and explicit object architecture remain authoritative.
Profile and style changes share one Undo command. To change source data or
classification rules, generate a new project/package from the pinned recipe.

## Verification

Synthetic tests cover detailed classes, author/source/auxiliary priority, original
height, deterministic regions, source-ID/spatial deduplication, natural holes,
road/water/building protection and acquisition failure preservation. Editor checks
exercise the real recipe worker through export, cancellation, stale results,
profile-driven group splitting and Undo. Detailed user driving and device checks
remain user acceptance.

For bounded real-data render inspection, run `tests/capture_regional_map.gd`
through the isolated Godot runner with `MAPEDITOR_REGION_CAPTURE_PLAN` pointing
to a local JSON plan. It names `source` (project or package), a fresh `output`
directory and `views`: each view has `name`, explicit `target_cm`, `offset_m`,
`size_m`, `cell_radius` (0–7) and `near_radius` (−1 for all distant, or 0–2).
Only those cells are loaded; fixed lighting and orthographic views make terrain,
cell joins and near/distant appearance comparable. Source files are read-only.

Sources: [ESA WorldCover data and attribution](https://esa-worldcover.org/en/data-access),
[Overture buildings](https://docs.overturemaps.org/guides/buildings/),
[Overture bounded DuckDB queries](https://docs.overturemaps.org/getting-data/duckdb/).

Source roof shape/material selections use the optional building style components
in [MapKit appearance](../addons/mapkit/spec/APPEARANCE.md). Explicit facts outrank
profile defaults; a blue Cycladic dome additionally requires a religious building
and matching dome information. Regional profile edits retain explicit roof facts.

Recipe builds derive source-object namespaces from input hashes and semantic settings,
independent of output paths. Fresh worker nonces still bind progress, cancellation and
late-response checks. Geometry, classifications and appearance seeds are reproducible;
Editor creation/edit timestamps remain authoring audit metadata.
