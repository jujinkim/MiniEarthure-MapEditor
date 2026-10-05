# Supported local imports and atomic adoption

Editor owns MIT adapters and document adoption; public MapKit owns native geometry
validation. No private game dependency or provider download path is used. Obtain
files separately and explicitly choose the source format. Source files, PBF/DEM,
receipts, projects and packages are never overwritten by importing.

## Current contract and units

[CURRENT_V1](CURRENT_V1.md) defines one current shape per adapter. There is no
recipe selector, feature promotion, old reader or automatic converter. ImportLayer
contains additive nodes, roads, buildings and zones with source provenance. A new
128-bit layer namespace is allocated even when reimporting the same source bytes.
Existing object references, arbitrary map-value mutation and deletions are rejected.

Custom maps use actual metres. OSM adoption divides source coordinates, widths,
heights, clearances and vegetation spacing by8 once; raw staged input remains in
source units. `osm-import-1to8-v1` records the denominator. Linked DEM uses the same
factor (map positions×8 for source lookup; relative elevations÷8). Standalone DEM,
GeoJSON and Overture use their declared units. Undo/Redo/save operate on adopted
coordinates and never apply the factor again.

## Supported profiles

| Input | Supported interpretation | Refused or unresolved |
| --- | --- | --- |
| GeoJSON `geojson-v1` | Explicit local metres or WGS84; LineString/MultiLineString ground roads; Polygon/MultiPolygon buildings or forest/orchard with holes; bounded nested GeometryCollection | Point/MultiPoint semantics, legacy CRS, Z, structural heights/graph IDs, empty/unsupported leaves |
| OSM XML/PBF `osm-extract-v1` | Bounded snapshot or explicit selected-area streaming; supported highways/buildings/vegetation; source-node ground/structural loops; explicit bridge/tunnel heights and ground anchors | Unsupported tags/classes, missing metric height without approved supplement, geometry inferred from layer number, invalid original topology |
| Local Overture | Building multipart/courtyard/vertical parts, ground transportation with exact physical spans/connector positions, land-cover forests | Structural transportation lacking metric height/datum/clearance, unsupported flags/classes, larger unbounded selections |
| Local PNG heightmap | Staged16-bit full-cell PNG with explicit extent, offset/step and shared-edge validation | Undeclared units, partial/bad cell edges, arbitrary CRS/resampling |
| Copernicus COG `copernicus-dem-v1` | One bounded array of local COGs, including single file and atomic mosaic | Remote acquisition, arbitrary raster/nodata/warp profiles, unbounded partitioning |

Every whole candidate is validated before adoption. Repeated/invalid JSON keys,
missing coordinates, zero/invalid rings, conflicting identities and unsupported
members reject rather than silently flattening or partially importing. Source SHA,
bytes, license, accuracy, extent, feature/point counts, estimates and bounded warning
samples are retained. Precision is not treated as source accuracy.

## Topology and source mapping

GeoJSON multipart lines keep independent endpoints and source/part mapping; they
are never welded by coincident positions. Collections preserve feature/child/leaf
order and inherited feature properties, with16 levels,40,000 visited geometry nodes
and20,000 leaves maximum. Exact source trees map to ordered output IDs/point counts.
The Editor independently checks completeness, order, uniqueness and types.

OSM connections use original node identity, including every source vertex on a
simple loop and all incident approaches. Crop walks source order; interpolated
cuts have feature/segment-local IDs and cannot create a connection by position.
Complete original topology/height validation precedes crop, including incident
ways outside the selected area. PBF closure is bounded; open ordinary approaches
do not recursively pull the entire road network. Source hashes/byte counts and
retained intervals survive save/recovery/export in attribution metadata.

Structures require explicit complete source heights, vertical zero/datum, clearance
and at least two distinct ground anchors per connected structural component.
Snapshot-bound local height supplements can fill supported missing values; they
cannot silently override source heights. Ground connections, junction arms,
continuations and partial bridge/tunnel crop use one current v1 provenance shape.
Native generation verifies every affected corridor, at most16 cells, both at review
and adoption. Tight/overlapping mouths, unsafe grades and conflicting clearances
reject; no automatic simplification or geometry repair hides them.

WGS84 projection and height conversion require explicit source/reference metadata.
The bounded EGM96→EGM2008 delta-grid input must cover every original vertex.
Preparing such a grid from arbitrary official geoid formats remains unsupported.
Source heights are validated/converted before crop. Estimated ground heights do
not invent a vertical datum; generated ground follows terrain.

## Worker, review and document lifetime

One ImportJob owns one helper, request ID and exclusive scratch directory. Progress
uses real stage/count/unit events with sequence/deadline/EOF checks. Stdout/stderr
are drained in bounded slices (16KiB each/frame); events≤4KiB, total IPC≤1MiB,
retained stderr≤4KiB. Cancellation invalidates generation, terminates/reaps the owned
child and removes only its scratch. Interrupted owned work is discovered without
touching source files or another request's directory.

Snapshot input≤32MiB, result≤12MiB,20,000 features,200,000 positions,60,000 records,
50 warning samples and shared16MiB Undo budget remain admission bounds. Selected
large-PBF scanning has its own bounded2GiB disk index; this does not relax selected
payload, native geometry or history limits. Logical reservations are not RSS limits.

The immutable review candidate exposes summary and exact provenance details.
Native validation, source recheck and final command preparation use owned workers;
cancel/document revision changes reject late results. Adopt adds the entire layer
and metadata in one Undo command. Existing layers remain unchanged on failure.
Discard only releases the candidate. Save/recovery/package preserve provenance;
visibility/lock are Editor view state, not package execution layers. Saving is an
explicit action. Terrain/PNG and asset/proxy authoring use the same revision,
exclusive-payload and atomic command ownership in [AUTHORING](AUTHORING.md).

## Verification and current limits

Scoped synthetic Python/import and compiled Godot tests cover original source
preservation, outside-incidence rejection, crop/stream equivalence, exact provenance,
height supplements, native floors/ceilings, cancellation/deadline, forged metadata,
atomic adoption/Undo/save/recovery/package. The last broad importer consolidation
passed165 Python tests and focused OSM loops251/structures196/continuations85/
junctions242/supplements68/native117/collections104 checks. Current v1 source and
adoption regressions also passed at the v1 transition; no old-shape support remains.

For a change, choose its `tests/test_osm*.py`, `test_collections.py` or other adapter
unit and the relevant Godot validator via the root isolated checker. Do not repeat
all historical suites for documentation/pins. Installed OS file dialogs/permissions,
real-region accuracy, large-area performance and detailed Client driving remain user
verification. General POI/structural GeoJSON, broader OSM/Overture semantics and
raster/geoid preparation are feature work, not unperformed acceptance tests.
