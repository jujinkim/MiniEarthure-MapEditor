# Supported local imports and atomic adoption

**Import OSM / PBF** guides PBF selection → area selection → review → Apply using
the existing 1:8 city profile, budgets and explicit exclusions. An empty track
project proposes fitted bounds; populated maps retain their extent. Bounds,
composition and layer adoption share one Undo; cancel/failure preserves the map.
Ordinary vehicle roads split where they share original OSM nodes with other vehicle
roads before optimization; paths, footways, cycleways and pedestrian streets keep
independent ends (`osm_pedestrian_roads`). Surviving source endpoints retain identity
through crop/quantization; new cuts remain independent. Adoption asks MapKit for
ordinary source junctions it cannot build (for example a way doubling back) and turns
only those into separate road ends at the same position (`separated_junctions` in the
attribution); explicit structural junctions still fail review. Selection never rewrites geometry or infers height. See
[3D road editing](WORKBENCH.md).

Editor owns the MIT import adapters and document adoption; public MapKit owns native
geometry validation. Obtain source files separately and choose the source format
explicitly. Importing never overwrites source files, PBF/DEM, receipts, projects or
packages. The automatic OSM city profile is described in [IMPORT_CITY](IMPORT_CITY.md).

## Contract and units

[CURRENT_V1](CURRENT_V1.md) defines one shape per adapter; there is no recipe
selector or automatic converter. An ImportLayer adds nodes, roads, buildings, zones
and facility POIs with source provenance under a new 128-bit namespace, even when
the same bytes are reimported. References to existing objects, arbitrary map-value
mutation and deletions are rejected.

Custom maps use real metres. OSM adoption divides coordinates, widths, heights,
clearances and vegetation spacing by 8 once (`osm-import-1to8-v1`); staged input
keeps source units. Adopted vehicle road segments narrower than 150 cm (`road_width_floor_cm`,
about 2.5 widths of the 61 cm car) widen to it; pedestrian roads keep their estimate, each side stopping 20 cm (plus
sidewalk) before the nearest new or existing building edge; wider segments never change. Linked DEM uses the same factor (map position × 8 for lookup,
relative elevation ÷ 8). Standalone DEM, GeoJSON and Overture use their declared
units. Undo/Redo/save operate on adopted coordinates and never reapply the factor.

## Supported profiles

| Input | Supported | Refused or unresolved |
| --- | --- | --- |
| GeoJSON `geojson-v1` | Local metres or WGS84; LineString/MultiLineString ground roads; Polygon/MultiPolygon buildings or forest/orchard with holes; bounded nested GeometryCollection | Point semantics, legacy CRS, Z, structural heights/graph IDs, empty/unsupported leaves |
| OSM XML/PBF `osm-extract-v1` | Bounded snapshot or selected-area streaming; supported highways/buildings/vegetation; source-node loops; explicit bridge/tunnel heights with ground anchors | Unsupported tags, missing metric heights without a supplement, heights inferred from `layer`, invalid original topology |
| Local Overture | Building parts/courtyards, ground transportation with exact spans/connectors, forest land cover | Structural transportation without metric height/datum/clearance, unbounded selections |
| PNG heightmap | 16-bit full-cell PNG with explicit extent, offset/step and shared-edge validation | Undeclared units, bad cell edges, arbitrary CRS/resampling |
| Copernicus COG `copernicus-dem-v1` | One bounded array of local COGs (single file or atomic mosaic) | Remote acquisition, arbitrary raster/nodata/warp profiles |
| Facility CSV `facility-csv-v1` | UTF-8/CP949/EUC-KR, header mapping, WGS84 name/position/category/source | Invalid coordinates become review rows; nothing is geocoded or guessed |

Every whole candidate is validated before adoption. Repeated keys, missing
coordinates, invalid rings, conflicting identities and unsupported members reject
the candidate instead of flattening it. Source SHA, bytes, license, accuracy,
extent, counts, estimates and bounded warning samples are retained.

## DEM mosaics and building bases

Copernicus mosaics allow up to 256 cells of any aspect ratio, four source tiles,
64 MiB combined source, 1025² total samples, 513 samples per cell side, 64 MiB
output and a 120-second native deadline. DEM is optional: a multi-district region
beyond these limits is refused with that explanation and keeps its flat terrain. **Use imported OSM coordinates and full
map extent** copies the imported frame, selects all cells and uses 4 m map spacing
when the grid allows.

**Place zero-base OSM buildings on this DSM (estimated)** is optional. It changes
only imported OSM buildings whose base is still zero and whose footprint the mosaic
covers fully; the lowest DSM sample at vertices and edge midpoints sets the base.
This is a disclosed surface estimate (roof/tree bias possible), not surveyed ground.
Shapes, heights, other bases and bridge/tunnel heights are unchanged. The receipt
lists every changed base and uncovered count; terrain and buildings adopt as one Undo.

## Choosing a geographic area

Open **Import vector source → OSM crop**, choose the PBF (the picker's `*.pbf`
filter also accepts `.osm.pbf`), enter an administrative name or recorded alias and
press **Find area by name**. If an English search fails, try the local name; no
translation is invented. Results show relation IDs, exact extents and simplified
outlines (≤32 matches, 200,000 references, 20,000 display points); missing outer
geometry is reported, never guessed.

Selecting a result fills outward-rounded W/S/E/N fields and centres the WGS84
origin. **Add selected area** combines up to eight results (for example neighbouring
districts): the fields become their combined extent and the PBF streaming import
clips to the exact union of their boundaries, read from the same captured PBF
(`--osm-areas`, crop `region` `administrative-union-v1` with the area IDs and names in
the receipt). Missing or open boundaries, or areas outside the rectangle, reject the
import. Click the diagram to move the origin or drag a rectangle; dragging returns
to a plain rectangle crop, which includes territory outside the named boundary. The
origin maps to the map centre after 1:8 adoption. Manual coordinates remain available. On macOS the in-app file
chooser is used because the system Open panel can leave confirmation disabled.

**Review and exclude unsupported source objects** is an explicit PBF option.
By default unsupported selected objects reject the import. With review enabled,
exact source IDs and reasons are retained and the adoption checkbox must be
checked. Excluded area members never reappear as standalone polygons.

## Facilities

Choose **Facility CSV**, set license, source reference and encoding, map the
name/latitude/longitude headers and supply the category. **Use imported OSM
coordinates** reuses the existing origin. Rows share the import origin and the
map's 1:1 or 1:8 scale; the OSM crop can filter rows besides map bounds. Invalid
rows must be explicitly excluded. Limits: 20,000 rows, 32 MiB.

Facilities appear in the Facilities list and the shared pin/label renderer.
Current-v1 `pois` keep names, classes, local coordinates and source/row
provenance through Undo/Redo, save, export and reopen. Pins have no height or
collision.

## Topology, structures and heights

GeoJSON multipart lines keep independent endpoints and are never welded by
position. Collections preserve order and inherited properties (16 levels, 40,000
nodes, 20,000 leaves). OSM connections use original node identity; crop cuts get
local IDs and cannot connect by position. Original topology and heights are
validated before cropping, including incident ways outside the area.

Structures need explicit source heights, vertical datum, clearance and two ground
anchors per connected component. Snapshot-bound local height supplements may fill
missing values but never override source heights. Native generation checks every
affected corridor (≤16 cells) at review and adoption. WGS84 height conversion
needs explicit reference metadata; a bounded EGM96→EGM2008 delta grid must cover
every vertex. Preparing grids from arbitrary geoid formats is unsupported.

## Worker, review and limits

One ImportJob owns one helper, request ID and scratch directory. Progress uses real
stage/count events; IPC is bounded (events ≤4 KiB, total ≤1 MiB, stderr ≤4 KiB).
Cancellation terminates the child and removes only its scratch. Full failure text
is in **Activity → Operation details…**.

| Bound | Exact profile |
| --- | --- |
| Snapshot input | 32 MiB |
| Result | 12 MiB, 20,000 features, 200,000 positions, 60,000 records |
| Native check | 16 cells |
| PBF scan | 100 million entities, 80 million references, 2 GiB disk index, 15 minutes |

Exact mode performs no generalization. Disk index bytes are logical reservations,
not RSS limits. The review candidate is immutable; source recheck and command
preparation run in owned workers, and late or stale results are rejected. Adopt
adds the whole layer in one Undo command; Discard releases the candidate. Layer
visibility/lock are view state. Saving stays explicit. Compressed history and
native transfer limits are in [DOCUMENTS](DOCUMENTS.md); PNG/asset adoption
follows [AUTHORING](AUTHORING.md).

The importer needs Python 3.12+ with `requirements-import.txt` (NumPy 2.5.3).

## Known limits

- Full Suwon output is 33.8 MB, above the 32 MiB output allowance; Yeongtong is
  the verified fallback, not a claim for every city.
- Two Suwon DEM tiles total 79 MB, above the 64 MiB source allowance.
- Overture/GIS completeness, broader OSM/Overture semantics, general POI/structural
  GeoJSON and geoid preparation are feature work.

For a change, run the affected `tests/test_osm*.py`, `test_collections.py` or
adapter test and the related Godot validator through the isolated checker. OS file
dialogs, real-region accuracy, large-area performance and Client driving are user
checks.
