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

Copernicus mosaics admit at most256 cells of any rectangular aspect ratio while
retaining the combined64MiB source limit, four source tiles,1025² total samples,
513 samples per cell side,64MiB output payload and120-second native deadline.
**Use imported OSM coordinates and full map extent** copies the active imported
frame, selects all cells and uses4m map spacing when the grid permits it. The
source lookup and relative heights retain the linked1:8 denominator.

**Place zero-base OSM buildings on this DSM (estimated)** is an explicit option.
Only active imported OSM buildings whose absolute base is still zero and whose
complete footprint is covered by this mosaic qualify. MapKit samples the raw DEM
at footprint/courtyard vertices and edge midpoints; the lowest sample sets the
base. This is a disclosed DSM estimate, including possible roof/tree bias, not a
surveyed ground elevation. Shapes and building heights stay unchanged, as do
nonzero or non-OSM bases and every bridge/tunnel height. The receipt lists every
old/new base and uncovered building count. Full candidate geometry validation,
source rechecks, revision guards and one atomic terrain/building Undo still apply.

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
On macOS, project/vector/PBF source selection uses the in-app file chooser:
the system Open panel can leave confirmation disabled for a selected source.

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

## Automatic city optimization

PBF streaming enables **Automatic city optimization (1:8)** by default; turn it
off for the exact bounded profile. This is an Editor-owned derived approximation,
with no city-specific coordinates and no change to the original PBF. A 1:8 length
scale alone does not reduce source objects or vertices. The city profile separates
larger bounded source work from the smaller output accepted by MapKit.

Compatible ordinary ground chains join at source degree-two nodes. Simplification
preserves source junction positions, semantic boundaries and existing crossings;
coincident independent source IDs are not welded. Closed ground-loop pieces can
join across nonjunction source vertices. Degree-two ground bends may simplify
within the same disclosed tolerance, with ordered original source positions and
complete traversal ranges retained. Junctions cannot be hidden by that mapping.
Structures and explicit heights keep their existing rules.
Exactly equal adjacent centimetre vertices are removed after the single 1:8
quantization; nonempty holes are never discarded by that cleanup.

Compatible ordinary buildings are grouped within 256 m source tiles, at most 128
sources per group. Deterministic candidates fill gaps from 0 to 64 source metres,
simplify lines by at most 4 m and polygons by at most 8 m, then snap to a 0.08 m source
grid (one map centimetre). Named/public/landmark and tall buildings remain protected
from ordinary aggregation. Road corridors, protected land areas and courtyards
block added filler. Compatible vegetation polygons are unioned as well.
Forest/orchard geometry retains its areas and exclusions; illustrative trees use
a disclosed32 m source lattice (4 m on the1:8 map) at750 per mille density. These
are procedural estimates, not measured individual trees. The exact profile keeps
its previous8 m source lattice.

Road widths without source values use disclosed highway-class estimates, at least
1.6 source metres (20 map centimetres), and source surfaces map to game materials.
Buildings are cut around road space with a 0.8 m source clearance. Overlapping
building volumes are partitioned with a 0.16 m clearance, prioritizing taller/named
geometry. An enclosed source retains all original IDs/names in its containing
volume and records its height as estimated. Complex polygons are split into
bounded native pieces with a 0.32 m source separation; this is also an approximation,
not a survey boundary. Numeric failures keep the original group for validation.

Review reports before/after objects and positions, selected gap/tolerances, width
and material estimates, road cuts and overlap changes. A compact source table maps
every supported source to contiguous output records; validation rejects missing,
duplicate or excluded source claims. No supported source object is silently dropped
to meet a limit. If a building lies entirely inside derived road space, the
default mode fails with its source ID. Explicit exclusion review may instead
exclude that whole source, including all multipart pieces, with a warning that
road widths may be estimates. Adoption requires the same inspected-exclusions
checkbox; the building is never silently moved into a nearby block.

City candidates generate every map cell sequentially before review and adoption,
up to256 cells, with the existing120-second child timeout and native cell budgets.
Batches of16 reuse immutable native preparation and discard generated chunks
without building unused presentation buffers; every cell still generates.
The Map authoring page exposes cell size in metres: smaller cells reduce local
generation work without changing map extent or1:8 scale. Terrain tiles and
assembled tracks prevent resizing because their grid references must not be
reinterpreted. Changing cell size is one Undo command. The exact import profile
keeps its16-cell structural check.
If protected geometry or output/native budgets still do not fit,
the entire candidate fails. This is not unlimited or proven coverage of every city.

## Facilities

Select **Facility CSV**, set its license and source reference, choose the file's
encoding, and map the exact name/latitude/longitude headers in **Facility CSV
columns**. Supply the category explicitly. **Use imported OSM coordinates** fills
the existing source origin without retyping coordinates; conflicting imported
frames require an explicit choice instead. The scrollable mapping dialog keeps
its confirmation button on screen. Coordinates share the declared import
origin and the adopted map's1:1 or1:8 scale. The selected OSM crop can filter the
rows in addition to map bounds. Review includes every invalid line/name/reason
and every outside line; invalid rows require explicit exclusion before adoption.
Files stay unchanged. Up to20,000 rows and 32 MiB source bytes are accepted.

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
reject; city approximation never supplies missing structural heights or repairs
invalid original topology.

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

Exact snapshot input≤32MiB, result≤12MiB,20,000 features,200,000 positions and60,000
records remain admission bounds. City source work permits 250,000 features,
2 million positions/selected entities,4 million references and 256 MiB selected JSON;
derived city output is bounded to 100,000 features,800,000 positions,180,000 records
and 32 MiB in both wire and Editor JSON representations. Both retain 50 warning
samples, whole-candidate native validation and shared 16 MiB retained Undo. City
output is still subject to MapKit's 32 MiB document,200,000 objects and 1 million
vertices; any smaller package, local geometry or projection bound remains active.
Compressed history and native transfer are described in [DOCUMENTS](DOCUMENTS.md).
Selected
large-PBF scanning has a combined2GiB disk allowance for coordinate files and
SQLite metadata; this does not relax selected
payload, native geometry or history limits. Logical reservations are not RSS limits.
The national-source scan permits100million raw entities and80million references,
bounded independently by2GiB source/index and the15-minute deadline. This replaces
the20million raw-entity scan cap that rejected the Korean source before spatial
selection. Name
lookup filters boundary member IDs in libosmium before materialising Python objects.
Sorted node IDs use disposable read-only file arrays of exact1e-7-degree integer
coordinates. Up to20,000 references are looked up together, preserving enclosing
polygons and crossing ways even when no source vertex is inside the crop.
Way lookups and SQLite writes are grouped across at most 128 ways,20,000 total
references and4MiB serialized payload. Each way retains its own envelope; empty
ways, missing nodes and duplicate IDs cannot be merged away by batching. Metadata
and incidence stay in SQLite; its page limit reserves the coordinate-file bytes
before each64KiB append. Unsorted inputs use bounded-block SQLite indexing under
the same combined disk allowance, with duplicate/missing-ID checks on both paths.
Unselected ways retain compact immutable PBF block locations rather than expanded
tags/vertices in SQLite. Selected relation members are resolved from captured
blocks on demand with duplicate/missing-node and source-hash checks. The file
mappings share that2GiB reservation; it is not a fixed resident-RAM claim.
Exact mode performs no geometric generalization. NumPy2.5.3 is an explicit importer dependency;
install `requirements-import.txt` in Python3.12 or newer.
Full failure text is available in **Activity → Operation details…**.
The PBF picker uses the single `*.pbf` extension filter, which also accepts
`.osm.pbf`. The in-app macOS chooser is used because the system Open panel can
still keep confirmation disabled for a selected source.

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

City tests cover synthetic cities in different hemispheres,20,100 source buildings,
road/park/courtyard/name protection, merged loops, topology, source coverage,
determinism, width/material estimates, overlap partition and unchanged originals.
The native synthetic city flow covers review, forged metadata, complete adoption,
atomic Undo/Redo, project/package reopen, generated geometry and cancellation.
Compressed-history and batch tests additionally cover 6,000 mixed records and
corrupt/oversized/stale command failures. Read-only real-data diagnostics are kept
separate from maps actually authored through the UI.
The bounded DEM extension passes10 Python cases plus the compiled96-cell city
and native DEM validators. These include explicit building estimates, unchanged
authored heights, projection mismatch/uncovered footprint rejection, cancellation,
same-size source mutations, last-cell corruption, atomic Undo/Redo and reopen.

The scoped macOS real-data workflow verified browser acquisition, Korean Suwon and
Yeongtong name/boundary selection, click/drag coordinates, wide button labels,
source preservation and reopening the saved project. The in-app macOS source
chooser opens the original regional PBF; the system chooser remains unreliable.
Projection CLI numbers preserve full precision and origin checks compare the same
JSON-decoded representation as the helper response, avoiding SpinBox binary
rounding mismatches while still rejecting changed coordinates.

The actual UI-authored full Yeongtong rectangle
`[127.032369,37.231186,127.089872,37.320589]` reduces21,828 features/156,136 positions
to14,148/108,678 (7,659 roads,5,409 buildings,1,080 areas; gap32 source metres).
All96 native128m cells pass before atomic UI adoption. The saved1024×1536m map
uses WGS84 origin127.061119/37.275887, source-local4096/6144m and1:8 scale.
The rectangle also includes parts of neighboring Suwon districts, Yongin and
Hwaseong; it is not the administrative polygon itself.

The UI imported the E127 GLO-30 tile at4m map spacing into96 terrain cells and
explicitly grounded5,409 zero-base OSM buildings using123,578 DSM samples.
CP949 library CSV mapping adopted42 of135 rows (93 outside, no invalid rows),
using the imported OSM frame and category `작은도서관`. All42 projected positions
match the original CSV to the authored centimetre. Source file hashes are unchanged.
Project save/reopen, three representative3D cells(3/2,2/4,3/7), whole-map2D facility
pins/Korean labels, UI export and UI package restore pass. Restored document,
all96 terrain payloads and facility/source receipts match the saved project exactly.
The `.memap` is1,881,000 bytes; saved document9,163,635 bytes. Nullable sidewalks,
preview-vs-export indexing and conservative preview/receipt costs were corrected
without raising preview or package-restore allowances. Actual Client loading is
recorded separately in the [Client import guide](../../client/docs/PACKAGE_FILE_IMPORT.md).
These local user artifacts are not public fixtures or committed datasets.

The full Suwon candidate still exceeds the32MiB output allowance at33,822,459 bytes;
its two DEM tiles total79,266,369 bytes, above the64MiB source allowance. Full
Yeongtong is the authorized fallback, not a claim of full Suwon or every-city
success. National extraction fits the unchanged2GiB index allowance; the former
20,000 selected-source ceiling belongs to exact mode, not automatic city mode.
Ground roads follow terrain; explicit DSM building bases remain surface estimates
with possible roof/tree bias. OSM omissions and unsupported source exclusions
remain recorded, without invented bridge/tunnel heights. Overture/GIS building
completeness comparisons and detailed driving were not performed.

For a change, choose its `tests/test_osm*.py`, `test_collections.py` or other adapter
unit and the relevant Godot validator via the root isolated checker. Do not repeat
all historical suites for documentation/pins. Installed OS file dialogs/permissions,
real-region accuracy, large-area performance and detailed Client driving remain user
verification. General POI/structural GeoJSON, broader OSM/Overture semantics and
raster/geoid preparation are feature work, not unperformed acceptance tests.
