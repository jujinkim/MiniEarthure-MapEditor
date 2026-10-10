# Supported local imports and atomic adoption

Editor owns MIT adapters and document adoption; public MapKit owns native geometry
validation. No private game dependency or provider download path is used. Obtain
files separately and explicitly choose the source format. Source files, PBF/DEM,
receipts, projects and packages are never overwritten by importing.

## Current contract and units

[CURRENT_V1](CURRENT_V1.md) defines one current shape per adapter. There is no
recipe selector, feature promotion, old reader or automatic converter. ImportLayer
contains additive nodes, roads, buildings, zones and facility POIs with source provenance. A new
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
| Facility CSV `facility-csv-v1` | Explicit UTF-8/CP949/EUC-KR, header mapping, WGS84 names/positions/category/source; geographic and map-bounds filtering | Missing/invalid coordinates are review rows, never guessed or geocoded; malformed headers/encoding fail the import |

Every whole candidate is validated before adoption. Repeated/invalid JSON keys,
missing coordinates, zero/invalid rings, conflicting identities and unsupported
members reject rather than silently flattening or partially importing. Source SHA,
bytes, license, accuracy, extent, feature/point counts, estimates and bounded warning
samples are retained. Precision is not treated as source accuracy.

## Choosing a geographic area

Open **Import vector source → OSM crop**. Choose the downloaded PBF, enter an
administrative area name (local name or an alias recorded in the source), and press
**Find area by name**. If English search has no match, try the area's local name;
the lookup does not invent translations absent from the PBF.
The local lookup reads administrative relations and their complete direct outer
ways/nodes. It shows matching names, relation IDs, exact boundary extents and
simplified outlines with OpenStreetMap attribution. Missing/nested outer geometry
has an explicit unavailable reason; no guessed extent is returned. Search is
bounded to32 matches,200,000 references and20,000 display points, with the same
exclusive capture, source hash, cancellation and15-minute worker lifetime.

Selecting a result fills outward-rounded west/south/east/north fields and centres
the WGS84 origin. Click the boundary diagram to move that origin, or drag to set
a rectangular crop and its centre. The origin maps to the current map centre
after1:8 adoption. Approximate scaled dimensions help compare against map bounds;
the actual import still uses the exact UTM conversion and20km corner radius.
The rectangle includes surrounding territory outside the named boundary. This is
an offline boundary diagram, not street imagery or cadastral coverage. Manual
coordinates remain available for unnamed areas. No city coordinates are embedded
in the adapter. Wide action buttons display both their icon and action text.

The former0.02-degree OSM side limit is replaced by the existing projection,
selected-object, position, result, native and Undo budgets. Overture's separate
selection limits remain unchanged. National PBF metadata is validated when a
selected object uses it; unrelated multilingual country/place tags do not consume
the selected-object tag allowance. Scan/index/reference quotas still apply.

**Review and exclude unsupported source objects** is an explicit PBF streaming
option. Default imports still reject unsupported selected objects. With review
enabled, exact source IDs and reasons are retained and the adoption checkbox must
be checked after inspection. Rejected area members cannot reappear as flattened
standalone polygons. Aggregate budgets and whole-candidate native validation stay
mandatory; no bridge/tunnel height is invented from `layer` or DSM values.

## Facilities

Select **Facility CSV**, set its license and source reference, choose the file's
encoding, and map the exact name/latitude/longitude headers in **Facility CSV
columns**. Supply the category explicitly. Coordinates share the declared import
origin and the adopted map's1:1 or1:8 scale. The selected OSM crop can filter the
rows in addition to map bounds. Review includes every invalid line/name/reason
and every outside line; invalid rows require explicit exclusion before adoption.
Files stay unchanged. Up to20,000 rows and32MiB source bytes are accepted.

Facilities appear in the Editor's Facilities list and the shared map pin/label
renderer. Current-v1 `pois` preserves names, classifications, local coordinates
and source/license/row provenance through one-command Undo/Redo, project save,
package export and reopen. Pins have no height or collision semantics. Geographic
source values and the input hash remain in each facility's source notice.

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
large-PBF scanning has a combined2GiB disk allowance for coordinate files and
SQLite metadata; this does not relax selected
payload, native geometry or history limits. Logical reservations are not RSS limits.
The national-source scan permits100million raw entities and80million references,
bounded independently by2GiB source/index and the15-minute deadline. This replaces
the20million raw-entity scan cap that rejected the Korean source before spatial
selection; the250,000 selected-entity and20,000 feature caps are unchanged. Name
lookup filters boundary member IDs in libosmium before materialising Python objects.
Sorted node IDs use disposable read-only file arrays of exact1e-7-degree integer
coordinates. Up to20,000 references are looked up together, preserving enclosing
polygons and crossing ways even when no source vertex is inside the crop.
Way lookups and SQLite writes are grouped across at most128 ways,20,000 total
references and4MiB serialized payload. Each way retains its own envelope; empty
ways, missing nodes and duplicate IDs cannot be merged away by batching. Metadata
and incidence stay in SQLite; its page limit reserves the coordinate-file bytes
before each64KiB append. Unsorted inputs use bounded-block SQLite indexing under
the same combined disk allowance, with duplicate/missing-ID checks on both paths.
The file mappings share that2GiB reservation; it is not a fixed resident-RAM claim.
No geometry is simplified. NumPy2.5.3 is an explicit importer dependency;
install `requirements-import.txt` in Python3.12 or newer.
Full failure text is available in **Activity → Operation details…**.
The native PBF picker uses the single `*.pbf` extension filter, which also accepts
`.osm.pbf`. On macOS, the former redundant multipart extension filter could list
a PBF while keeping Open disabled. The same downloaded file opens with the corrected
filter; standalone startup and this native file-selection path were verified.

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
Focused place/CSV tests cover Korean encodings and names, English aliases,
incomplete boundaries, geographic filtering, invalid coordinates, exact receipt
and review accounting, worker cancellation, source preservation, map-centre1:8
placement, atomic facility Undo/Redo and project/package reopening. Boundary
selection and name-search Godot validators pass. OSM extraction/structure/loop
regressions retain exact multipolygon membership counts after exclusion review.
Focused stream/import/place Python checks include exact seven-decimal source
positions in both hemispheres, sorted/unsorted parity, combined disk limits,
exclusive workspace ownership, source preservation and cleanup after cancellation.
The bulk-coordinate index passes15 Python stream cases and compiled Godot stream
(45 checks), exclusion review, name lookup and import-job validators. The stream
fixture generates its actual occupied1:8 cell; native vegetation visits only the
cell/zone envelope while retaining its global lattice and existing work limits.
Undo/Redo compares authored content independently of the intentional edit timestamp.
The Editor UX validator passes 61 assertions, including complete timeout text,
read-only details and minimum-window layout; name lookup also passes independently.

The scoped macOS real-data workflow verified browser acquisition, Korean Suwon and
Yeongtong name/boundary selection, click/drag coordinates, wide button labels,
native PBF selection, source preservation and reopening the saved empty project.
It did not produce a completed regional map: the 2026-10-09 Korean national PBF
exhausts the combined2GiB index allowance, and a separately downloaded2,434,654-byte
BBBike regional PBF still exceeds20,000 selected source features for the full
Yeongtong rectangle `[127.032369,37.231186,127.089872,37.320589]`. Both reject before
candidate adoption. DEM/facility adoption, real-map export/reopen and Client loading
of that map remain unperformed. A small diagnostic area is not whole-region success.
Supporting that region under the same budgets needs bounded partitioning with
source topology, duplicate control, whole-candidate validation and atomic history;
merely enlarging limits was not used. Ground roads follow terrain, but building
`base_cm` is absolute: applying DEM does not automatically align estimated building
bases, and the combined real-data height check remains outstanding.

For a change, choose its `tests/test_osm*.py`, `test_collections.py` or other adapter
unit and the relevant Godot validator via the root isolated checker. Do not repeat
all historical suites for documentation/pins. Installed OS file dialogs/permissions,
real-region accuracy, large-area performance and detailed Client driving remain user
verification. General POI/structural GeoJSON, broader OSM/Overture semantics and
raster/geoid preparation are feature work, not unperformed acceptance tests.
