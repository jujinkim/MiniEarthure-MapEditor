# Import boundary and adoption

**Local files only (2026-09-10).** Obtain source files separately, then select them
in the Editor. Direct Geofabrik catalog/probe/download, Overture remote readers
and Copernicus availability/download controls and helper entry points are removed.
No map-provider SDK or automatic fetch is needed. Existing sources, receipts,
projects and packages remain untouched; their attribution and license notices stay.


Editor-owned MIT adapters depend only on public tools. No MapServer/game module,
private data or runtime generator is imported. `scripts/importers/import_layer.py`
defines the version-1 typed interchange; `scripts/import_layer.gd` revalidates
untrusted results before native MapKit checks and explicit adoption.

Adapters include `geojson-v2` below and the bounded `osm-extract-v1` snapshot profile
at the end of this document. Select the format explicitly in **Import vector**.
The [PBF streaming extension](#osm-pbf-selected-area-streaming--2026-09-10)
adds an explicit local-source profile beyond 32 MiB; earlier whole-source limits
still apply when streaming is disabled.
`geojson-v2`: explicit local-metre or WGS84 LineString, Polygon and MultiPolygon input.
Forest/orchard polygon holes become existing zone exclusions; recipe-5 building holes
are supported by the courtyard extension below, which supersedes earlier rejection.
The local-metre extension is not RFC 7946 geographic GeoJSON. Legacy `crs`, Z, other
geometry and invalid/duplicate JSON keys are rejected, never silently flattened. Road endpoints remain disconnected; building/vegetation defaults are
reported as estimates. Source accuracy defaults to unknown, not coordinate precision.

Every import gets a fresh 128-bit layer namespace, including the same source bytes.
Source SHA-256/byte count/license/accuracy, coordinate mode, extent, feature/point
counts, estimated-field counts and bounded warning samples accompany typed additive
node/road/building/zone records. No map-value mutation, deletion or existing-node
reference is accepted. Native validation and the existing history budget reject the
entire candidate on invalid topology/geometry, conflicting identities or oversize.

The review dialog shows provenance/extent/estimates and offers Adopt new layer or
Discard. Adoption adds all geometry and a JSON metadata attribution notice in one
Undo command. This uses existing public document attribution fields, not a package
layer schema. Save/recovery/package I/O retain the notice; package world content
hash remains independent of attribution metadata. Layer visibility/lock remains
an Editor view. Document changes/cancel discard stale candidates. Reimport adds a
separate layer; it never replaces old objects or rewrites source/project/package
files. Saving afterward is still an explicit document action.

Limits: input 32 MiB; output 12 MiB; 20,000 features; 200,000 positions; 60,000
records; 50 warning samples plus total count. History retains its shared 16 MiB
budget. These are admission bounds, not whole-process RSS guarantees.

Standalone checks:

```sh
python3 -m unittest discover -s tests -p test_importers.py -v
python3 scripts/check_documents.py --godot /path/to/godot --script import_layer_validator --script editor_validator --script document_history_validator --script document_recovery_validator --log-dir /new/path/import-core
python3 scripts/check_documents.py --godot /path/to/godot --script import_layer_validator --rendered --log-dir /new/path/import-rendered
```

I01/I03 Mac import/native/document, rendered adoption and compiled resource-PCK
checks are scoped evidence. Actual Windows/Linux exported filesystem/UI and
installed Client acceptance remain open. WGS84 projection is implemented below;
The staged local heightmap and local OSM extract profiles are documented below;
The bounded local Overture snapshot and Copernicus COG profiles below are implemented.

## Local process lifecycle (I03)

One `ImportJob` owns one Python helper, fresh request ID and private job directory.
The import wizard accepts a Python executable and preserves it separately from map
data. Retry last source launches a new job; choose a different file through the
normal picker. The form retains license and accuracy. The status reports selected
source bytes before processing; a progress bar and labels report actual per-stage
byte/feature counters, not a fabricated overall percentage.

Nonblocking stdout/stderr are drained at most 16 KiB each per frame. Request ID,
sequence, ordered stage, nondecreasing completed/total and units are checked.
Limits are 4 KiB/event, 1 MiB total IPC and 4 KiB retained stderr. Result bytes have
an announced size/hash and must match after a successful process exit before the
I01 boundary accepts them. Vector and local DEM candidate validation use the
asynchronous native processes described below; final command preparation and
other authoring paths retain synchronous work. Quotas do not establish whole-frame latency or process RSS.

Cancel, changed document and owner close kill the owned child; a 120-second job
deadline bounds stalled work. Terminal PID state is cached because Godot kill
reaps children. Remaining pipe bytes are drained after natural exit. The Python
helper exits on parent-pipe EOF and has its own 120-second watchdog, including
Editor crash. No grandchildren are spawned. Each result is consumed once; cleanup
removes only that request's known scripts/result. If termination fails, original
files remain protected and the failure is reported; retained scratch can be
inspected and is never adopted automatically. No broad directory deletion occurs.

### Live request scratch ownership — 2026-09-10

Vector and local DEM jobs now reserve the request directory with one exclusive
directory creation before claiming ownership or staging helpers. An existing
directory, regular file or symbolic link at that token is rejected without being
remembered as disposable scratch. A linked `import-jobs` root is also refused.
Rejected jobs cannot remove any files through later shutdown/cleanup calls.
Every start attempt consumes its job object, including a rejected request; retry
creates a fresh object/token. A closed or cancelled object cannot launch a child.

Both adapters share process-handle setup. If Python never starts, staged known
files are removed immediately. If a child starts with incomplete pipe handles,
shutdown must confirm its exit before cleanup; closing pipes alone is insufficient.
Cleanup is blocked while an owned child may still be running. After one disposal
attempt the object relinquishes cleanup ownership, so repeating cleanup cannot
touch a later request reusing the same token. Unknown files/subdirectories remain;
there is no recursive deletion. Partial file-write leftovers or failed filesystem
removals can still require manual inspection.

The initial lifetime fix above was in-memory only. The following discovery unit
adds persistent evidence and a read-only report. Earlier job directories are never
automatically resumed, adopted or cleaned on startup.
External replacement of a live directory by another same-user process is not an
adversarial filesystem guarantee. Source/project/package preservation still applies.

`import_scratch_validator` (included in `--full`) covers rejected reservations,
file/link collisions, no-process/partial-handle launch failures, pre-launch
validation, live cleanup refusal, old-owner reuse, unknown/nested preservation and
retry with real child processes. Its symlink fixtures require OS symlink creation
permission. Run alongside the existing lifetime and affected import/native checks:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/local-python --script import_scratch_validator --script import_job_validator --script import_layer_validator --script osm_stream_validator --script dem_validator --script dem_mosaic_validator --script local_only_validator --resource-pack --rendered --log-dir /new/scratch-ownership
```

Additional checks:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --script import_job_validator --script import_layer_validator --log-dir /new/path/lifetimes
python3 scripts/check_documents.py --godot /path/to/godot --script import_layer_validator --resource-pack --log-dir /new/path/resource
```

The resource mode compiles a host PCK then hides loose Editor product scripts/main
scene before executing the validator. It is not a native OS distribution and does
not require repeating known missing-template exports. Supported-platform process,
Python discovery/installation, native file dialogs and exported UI need actual OS
runners. Progress describes only local parsing, copying and sampling.

Sources: [GeoJSON](https://www.rfc-editor.org/rfc/rfc7946),
[Godot OS process API](https://docs.godotengine.org/en/stable/classes/class_os.html).


## WGS84 local projection (I02 local vector unit)

Select WGS84 longitude/latitude explicitly, enter a geographic origin and where
that origin belongs in local map metres. Source order is always `[longitude,
latitude]`; output local x is easting and local y is northing. Height properties
remain local authored metres; Z/vertical-datum conversion is unsupported. The
source is not clipped, resampled or silently repaired.

Optional independent Python setup (no private repository needed):

```sh
python3 -m venv .venv-import
.venv-import/bin/python -m pip install -r requirements-import.txt
```

On Windows use `.venv-import/Scripts/python.exe`. Select that executable in the
import wizard. Local metre imports remain standard-library-only. WGS84 requires
pyproj 3.7.2; missing/mismatched dependencies return an actionable error and leave
the map unchanged. Dependency installation is explicit; the Editor does not run pip.

The offline transformer uses WGS84 EPSG:4326 to the standard six-degree UTM strip
containing the origin (zones 1–60; longitude 180 selects 60), with north/south EPSG
326xx/327xx from origin latitude. Always-xy, no ballpark and best operation are
explicit; PROJ network access is disabled. Origin easting/northing is subtracted,
then the chosen local origin is added and values are rounded once to integer cm.
The review/attribution retain source/target CRS, origins, axis order, radius,
quantization and actual pyproj/PROJ versions. This is a projected grid, not an
assertion of survey/ground-distance accuracy. Source accuracy stays independent.

This initial bounded profile accepts latitude -80..84, one standard strip and
hemisphere, and points no farther than 20 km from the origin. Norway/Svalbard
special-zone selection, cross-zone/equator/antimeridian maps, arbitrary CRS,
general vertical datum conversion and raster reprojection are not claimed. The
explicit OSM height-reference extension below supports a bounded local difference grid. Multipart and
vegetation-hole support follows the bounded extension below.
Out-of-profile data rejects the entire import; choose/split the source area explicitly.
Native MapKit still checks all geometry and map bounds before adoption. Existing
stored documents are never reprojected automatically by a library/tool update.

Geographic checks (install optional requirements first):

```sh
.venv-import/bin/python -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script projection_validator --script import_layer_validator --script import_job_validator --log-dir /new/path/geographic
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script projection_validator --resource-pack --log-dir /new/path/geographic-pack
```

`--full` now includes geographic validation and therefore needs this optional
Python via `--import-python`; local-only checks can select specific scripts.
The tests cover official north/south PROJ reference values, local-cm fixture parity,
axis/radius/zone rejection, metadata/recovery/package/native generation and changed
source → new layer → Undo/Redo without replacing an existing saved package (I04
local vector scope). Existing E03 PNG16 authoring import remains a separate direct
terrain-edit operation; the staged raster ImportLayer/reimport workflow below is a separate action.
Other local source formats remain separate units; direct provider acquisition is outside scope.

Projection references: [PROJ UTM](https://proj.org/en/stable/operations/projections/utm.html),
[pyproj Transformer](https://pyproj4.github.io/pyproj/stable/api/transformer.html).
No third-party implementation is copied; optional packages retain their own licenses.


## Staged local heightmap (I02 raster unit)

Authoring settings → Terrain → **Stage heightmap for review…** uses the same
explicit PNG/cell/spacing/offset/step/accuracy/source/license fields as direct
terrain editing. A saved project and unlocked terrain are required. Review shows
the captured source SHA-256/bytes, fresh layer identity, full-cell sample grid,
restored height range, accuracy, axes and previous active descriptor. **Discard**
leaves document/history/project payloads unchanged. **Adopt and activate tile**
commits the tile and source notice as one binary/text Undo command.

`heightmap_import_layer.gd` is an Editor-local typed raster candidate, separate
from the additive vector interchange. Each import has a fresh namespace and notice;
MapKit still permits only one active heightmap per cell. Explicit adoption selects
the new tile; reimport never automatically replaces it. Previous active references
are included in the notice and actual old/new bytes are retained by the shared
16 MiB Undo/Redo budget. Source notices persist after later replacements. This is
not a persistent pending-layer library: closing/discarding a review releases its
candidate. Inactive file references embedded in notices are provenance; Save As
copies current and history-referenced files under its existing contract, not every
historical notice's files. Original project payloads are never garbage-collected.

PNG columns advance local x and rows local y from the cell's minimum corner;
unsigned samples restore `offset_cm + sample * step_cm`. No flip, clipping,
resampling, geographic/vertical CRS inference or neighbor repair occurs. Existing
4 MiB input/513-side PNG16, 2 m minimum dividing spacing, offset ±1,000,000 cm,
step 1–100 cm and accuracy 0 (unknown)–1,000,000 cm admission limits apply. Source
accuracy is independent of spacing/step. Native MapKit validates exact dimensions,
bounds, neighboring/implicit-flat seams and affected road generation before review
and again at adoption. Candidate payload validation keeps the 64 MiB total limit.

Staging captures bytes without publishing to the project. Later changes to the
selected source do not alter this reviewed snapshot; stage again to read new bytes.
Document change signals (including Undo then Redo), project replacement, changed
referenced project files, locks and active gestures block stale adoption. Known
project payload hashes are rechecked before adoption, including the replaced file.
Consumed candidates cannot be adopted twice. Existing native validation and
immutable file installation preserve original files and saved packages on failure.

This small one-cell profile reuses E03 bounded synchronous PNG/native/file work;
it does not claim cancellable in-stage processing, subprocess progress or RSS/frame
latency acceptance. Cancel applies to the pending review. The Copernicus profile below adds owned-process geographic sampling. Larger multi-cell
DEM mosaics remain unimplemented.
No package schema, MapKit generator or game dependency changes are introduced.

Checks (synthetic sources; isolated public project/user data):

```sh
python3 scripts/check_documents.py --godot /path/to/godot --script heightmap_import_validator --script authoring_safety_validator --script authoring_validator --script import_layer_validator --script document_history_validator --script document_recovery_validator --log-dir /new/path/raster-core
python3 scripts/check_documents.py --godot /path/to/godot --script heightmap_import_validator --rendered --log-dir /new/path/raster-rendered
python3 scripts/check_documents.py --godot /path/to/godot --script heightmap_import_validator --resource-pack --log-dir /new/path/raster-pack
```

Mac tests cover snapshot/discard/reimport/one-shot/stale/lock/file-conflict/seam/
invalid-input safety, metadata save/recovery/package preservation, old/new binary
Undo/Redo, review controls and compiled resource loading. Windows/Linux dialogs,
exported UI and real datasets/performance remain separate acceptance gates.

## Local OSM PBF/XML extracts (I02 snapshot unit)

**Import vector → OSM PBF extract / OSM XML extract** accepts a local current
snapshot (`.osm.pbf`/`.pbf` or UTF-8 `.osm`). Install `requirements-import.txt` in
the selected Python: osmium 4.3.1 is optional for OSM, pyproj 3.7.2 for projection.
The MIT adapter calls public pyosmium; it copies no MapServer implementation and
does not install dependencies, download data or invoke other child programs.
Pyosmium and dependencies retain their own licenses; OSM data is not MIT.

Enter the WGS84 origin and its local map position explicitly. The existing
single-strip/hemisphere/20 km UTM profile applies to every selected coordinate;
native validation rejects geometry outside the authored map. Extent and actual
selected feature/point/record counts appear in review. No bounding-box clipping
is inferred from an extract's header: border-crossing objects can extend beyond
the provider's advertised area. Prepare a small, reference-complete extract.

The profile converts supported open highway ways to independent ground roads,
closed building ways to footprints, and forest/wood/orchard ways to zones. It also
assembles explicit building/forest/wood/orchard `type=multipolygon` relations from
complete way members. Ways are sorted by OSM ID before assigning fresh layer IDs;
relations follow in relation-ID order, with canonical node-ID ring/part order. Shared OSM endpoints are
still disconnected authored endpoints; this is geometry, not a routable graph.
Plain positive decimal metres (optional ` m`) are accepted for width/height.
Defaults and omitted tags are explicitly reviewed: no access/oneway/restriction
semantics, POIs, roof/level-derived heights or survey elevation inference. Tagged
nodes and unrelated ways/relations are counted as omitted. Unknown source accuracy
stays unknown, independent of centimetre quantization. Ground/base elevations,
missing dimensions, vegetation and material/roof values remain estimates.

Missing selected-way nodes, repeated IDs/deletions/history, unsupported highway
classes/area or closed roads, nonclosed polygons, ambiguous categories, unsupported
feature relations and selected ways in unhandled boundary/multipolygon relations
reject the whole import. The explicit-height structural extension below replaces
the former blanket bridge/tunnel rejection; all other unsupported vertical tags
still reject. They are never silently flattened or repaired.

### Multipolygon assembly extension — 2026-09-09

Relation tags define the area. Members must be unique complete ways with explicit
`outer`/`inner` roles; endpoint joins work in either direction and independently of
member/entity order. Multiple disconnected outers become separate authored records
within the same atomic layer. Matching outer feature tags are consumed once;
conflicting tags, independently tagged inner features, role inference, old-style
outer-tag-only relations, nested relations and shared area-member ownership reject.
A missing member/node, branching/dangling join, repeated vertex, self-intersection,
touching/crossing boundaries, outside/nested holes or overlapping filled outers
rejects the entire candidate. No interpolation, clipping or repair is performed.

Forest/orchard inner rings become MapKit zone `exclusions`. An independent outer
island inside a hole is preserved. Buildings with multiple disjoint outers work;
building courtyards remain **unimplemented** because the public footprint contract
has no holes. Building parts/vertical structures and large-area support are also
still unimplemented. Current support is a bounded multipolygon profile, not every
OSM geometry. The next independent contract unit is building courtyard footprints.

Topology is checked on source rings and again after UTM/centimetre conversion so
quantization cannot merge separate boundaries silently. Each pass has a shared
2,000,000-check budget covering edge comparisons, containment and matrix allocation;
exhaustion asks for a smaller extract. Point/record/output/history bounds still
apply to **all** parts and exclusions. GeoJSON Polygon/MultiPolygon uses the same
projected topology checks for multipart/holes, with explicit declared hole ownership.
Simple existing single-ring GeoJSON/way output retains its previous record IDs.

Review records assembled relation/outer/inner/member counts separately from ignored
objects, retains source hash/ODbL and all dimension/material estimates, and adopts
all parts/exclusions as one Undo command. New module `polygon_geometry.py` is copied
into the existing owned local import child and included in compiled resources;
no new dependency, package schema, generator recipe or native ABI is introduced.

Admission includes **all input entities**, even omitted ones: 32 MiB captured
source, 250,000 entities, 200,000 nodes, 200,000 total way/member references,
20,000 selected ways/relations (including tagged members), 128 tags/entity and 512 characters/tag key/value. Existing
200,000 positions/60,000 records/12 MiB result and 16 MiB history bounds still
apply. Sparse IDs use bounded dictionaries rather than an ID-sized location
array; no implicit area/location cache is enabled. These are admission limits,
not an RSS guarantee for native PBF decompression. Select a smaller extract on
budget/deadline errors. XML DTD/entity declarations and non-UTF-8 input reject.

The same owned I03 process reads a captured byte snapshot, parses it, converts
features and publishes a size/hash-checked result. Read/parse show start/end byte
counters; convert reports completed selected features. Parsing does not expose
per-entity progress or a fabricated overall percentage. Cancel, deadline, owner
close, parent EOF, stale request and document-generation checks remain active.
Review/discard does not write the map. Adoption stores additive geometry and
source metadata as one Undo command. A retry/reimport gets a new namespace;
existing source/project/package bytes stay unchanged.

The OSM license field is fixed to **ODbL-1.0; © OpenStreetMap contributors;
https://www.openstreetmap.org/copyright** and rechecked at the ImportLayer boundary.
The source hash/name/bytes, projection, adapter/version, input omission counters
and estimate notices survive save/recovery/package attribution. This retained
notice does not by itself establish compliance for every published derived
database or rendered product; source-specific notices and distribution obligations
must also be evaluated for that delivery. No real dataset is included in tests.

```sh
.venv-import/bin/python -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script osm_import_validator --script osm_multipolygon_validator --script import_layer_validator --script import_job_validator --script projection_validator --log-dir /new/path/osm-core
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script osm_multipolygon_validator --resource-pack --log-dir /new/path/osm-pack
```

Synthetic XML and real PBF serialization exercise parity, bounds, malformed input,
omissions, process/native load, adoption/Undo/Redo, source/package preservation,
recovery, cancellation and stale review. Direct provider downloads are removed.
Larger local areas, target OS dialogs and representative source accuracy/performance
remain separately tracked implementation or verification work.

Official contracts checked 2026-09-09:
[pyosmium inputs](https://docs.osmcode.org/pyosmium/latest/user_manual/07-Input-Formats-And-Other-Sources/),
[FileProcessor](https://docs.osmcode.org/pyosmium/latest/reference/File-Processing/),
[Geofabrik extract boundaries](https://download.geofabrik.de/technical.html),
[OSM copyright/ODbL](https://www.openstreetmap.org/copyright).

## Geofabrik region download wizard (I02 remote acquisition)

**Removed on 2026-09-10.**

The catalog, region/size/version probe, URL form and downloader have been removed.
Select an already obtained local PBF/XML file through **Import vector**. Existing
PBFs and receipts remain on disk. Crop/streaming and OSM source/ODbL notices remain;
[extract boundaries](https://download.geofabrik.de/technical.html) describe source
semantics, not an automatic service call. Historical results remain in repository
history; no live-provider acquisition acceptance is required.


## Overture building area input (I02 scoped provider unit)

Select an existing **Overture building area snapshot** (`.overture.json`) in
**Import vector**, choose explicit WGS84/local origins, import, review and adopt.
The local version-1 snapshot embeds a dated release, west/south/east/north bbox
(at most 0.02 degrees per side), complete feature properties/GERS IDs/source notices,
and its fixed license. Snapshot size remains 32 MiB and building count 20,000.
The optional vertical profile below has stricter bounds. Duplicate IDs, incomplete
families and malformed metadata reject the whole input. No query, SDK, Arrow/WKB
reader, remote snapshot writer or acquisition CLI remains in the Editor.

Previously captured files remain supported with their original SHA-256, bytes,
release/bbox and provenance. The bounded local parser uses the selected Python's
projection/geometry dependencies; `overturemaps` and `pyarrow` are unnecessary.
The existing one-strip/hemisphere/20 km UTM profile and
native map bounds/geometry validation apply to every position. Polygon and bounded
MultiPolygon footprints, including recipe-5 courtyard holes and complete islands,
are accepted (see the extensions below). The default profile rejects vertical
parts; the explicit vertical mode below supports complete above-ground families.
Z/M, underground buildings, invalid heights, missing sources and
out-of-query bbox envelopes reject the whole candidate. Crossing footprints remain
whole; bbox overlap is not an exact polygon clipping operation. Source IDs are
sorted before assigning fresh per-import authored IDs. Native topology checks may
reject otherwise valid provider geometry rather than repair it.

Height is used when supplied; base zero, absent height, unknown use represented
explicitly as residential, and flat
concrete appearance are explicitly estimated. Floors, names, facade and roof
attributes are retained in the source snapshot but not modeled. Review shows
release/bbox, source ID/version/dataset notices, source hash/bytes, coordinate
provenance, extent and estimate/omission warnings. The fixed building-theme ODbL
notice and contributor attribution are rechecked at the typed Editor boundary;
source-specific notices survive attribution/save/recovery/package I/O. Source
licenses remain distinct from MIT code. Retaining metadata does not itself settle
all derived-product distribution obligations.

Document changes, cancellation and owner close reject local adoption while the
original source remains.
Review/discard and one-command atomic new-layer adoption use existing I01 gates;
reimport and changed sources add a new layer, preserve existing geometry/files and
support Undo/Redo. A stale or consumed candidate cannot be adopted again.

Official references checked 2026-09-09:
[Python client](https://docs.overturemaps.org/getting-data/overturemaps-py/),
[public API](https://github.com/OvertureMaps/overturemaps-py/blob/main/overturemaps/core.py),
[building schema](https://docs.overturemaps.org/schema/reference/buildings/building/),
[building attribution](https://docs.overturemaps.org/attribution/#buildings).

```sh
.venv-import/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/.venv-import/bin/python --script overture_validator --script import_job_validator --script local_only_validator --script osm_import_validator --log-dir /new/overture-core
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/.venv-import/bin/python --script overture_validator --rendered --log-dir /new/overture-rendered
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/.venv-import/bin/python --script overture_validator --resource-pack --log-dir /new/overture-pack
```

Mac synthetic provider/Arrow/native/document/rendered/resource-PCK checks are scoped
evidence. Actual provider transfer, representative geometry/accuracy/latency/RSS,
native Windows/Linux exported process/file-dialog/hard-link behavior and installed
Client drive remain acceptance work. Use licensed supported-size data in an isolated
validation project, record release/query/bytes/source hashes and test interrupted
transfer/retry, explicit origin/import/adoption/recovery/export/Client drive. Do
not infer whole-area/general-theme support from the synthetic fixtures.


## Copernicus 2021 DEM (I02 bounded raster source and atomic mosaic)

**Import vector → Import Copernicus DEM…** opens a separate terrain wizard. Save
first; enter WGS84 longitude/latitude and its local x/y, target cell, spacing, and
**EGM2008 height in metres corresponding to local height zero**. This does not
convert orthometric heights to ellipsoidal heights. Local terrain is sampled
EGM2008 height minus the explicit zero, in centimetres. No previous map is
reprojected or vertically shifted by opening this dialog.

Choose an existing local **2021 GLO-30 COG**. Enable **Multi-source / multi-cell
mosaic** for a rectangle starting at Cell x/y, with 1..4 columns and rows; select
a local folder of official GLO-30 tile filenames. Local GLO-90 filenames are not
inferred. The existing sampling helpers can still process previously captured
GLO-90/mixed-resolution files with their unchanged legacy review metadata (old download choices are inert
provenance in pure sampling), but the wizard
accepts local GLO-30 only. There is no remote availability check or fallback option.
Source provenance is user-declared, not authenticated by filename or fingerprint.

**Review area, source size and license / retry** computes all projected cells,
required source filenames, local sizes/SHA-256, DSM notice and vertical reference.
Missing files or interpolation support reject the complete input without fetching,
fallback or fabricated zero terrain. **Copy reviewed local source and sample**
rechecks the plan and copies bytes into an exclusive file in `user://import-sources`.
Known combined size is at most **64 MiB**. Reviews expire after ten minutes;
changed size/hash/options require a fresh review. URI, relative and virtual GDAL
paths are rejected before raster decoding; only existing local GTiff files are read.
A complete COG and adjacent receipt survive later raster/native failures.

Cancellation/owner close/parent EOF and the 120-second watchdog stop only the owned
local helper. Retry starts fresh. Only known partial files in its job directory
are cleaned; existing originals, captures, projects and packages are preserved.
The PNG is published exclusively after complete encoding. Cancellation after
publication may leave a complete source/PNG without selecting or adopting it.

The independent Python requires `rasterio==1.4.4` and existing `pyproj==3.7.2`;
install `requirements-import.txt` explicitly. No installation or private code is
performed by the Editor. Rasterio/GDAL reads only the captured local GTiff, with
sidecar discovery disabled and a 16 MiB GDAL cache setting. The adapter admits a
single-band, unscaled float32 north-up EPSG:4326 raster in the documented AWS
2021 COG tile/sample-centre layout. The COG's removed south/east samples are
accounted for. Bilinear interpolation uses full-resolution samples, never average
overviews. Single-cell legacy mode rejects cross-source support. Mosaic mode
explicitly reviews up to four source tiles, including a conservative support
margin of 1/120 degree east and 1/1200 degree south (the admitted minimum COG
width and GLO-90 row size). This can require an extra source even if the exact
sample window does not use it; the review discloses that cost. Removed east/south
samples come from the reviewed neighbor. At mixed GLO-30/90 or longitudinal-width
boundaries, interpolate on the neighbor's own full-resolution lattice, recursively
across a corner when needed. Missing sources/nodata/non-finite support reject;
no edge padding, zero filling, terrain repair or implicit network raster reads.

All target points use the existing offline single-strip/hemisphere/20 km UTM
contract. A target cell is at most 1024 m, spacing divides the cell and is at least
2 m, and there are at most 513 samples per cell side. Mosaic requests have at
most 16 cells and 1,050,625 target samples including duplicate shared edges.
Single-cell legacy mode must fit one source tile. Source read windows are at
most 1024² samples and storage blocks at
most 2048² samples. Progress reports captured bytes and completed target samples
as separate stages; native read/interpolation currently has start/end sample
counters, not a smooth percentage. These admission/cache settings are not whole
process RSS, frame latency or network speed guarantees. Main-thread final file
hashing/native candidate checks remain bounded synchronous operations.

PNG columns increase local easting and rows local northing. Heights round to
nearest integer centimetres (ties to even), then to the smallest integer PNG step
that fits unsigned 16-bit storage (1..100 cm). A mosaic uses one shared offset and
step over all output cells, ensuring identical quantization at shared edges.
Review retains the explicit step,
error bound, source window/resolution, pyproj/PROJ/rasterio/GDAL versions and the
original COG SHA/size. Source accuracy remains **unknown** for this selected area;
source spacing and output centimetres are not accuracy claims. Copernicus is a
**DSM containing vegetation, buildings and infrastructure**, not bare-earth DTM.
No building removal or terrain smoothing is inferred.

After shared native MapKit validation, a second review offers **Adopt all reviewed
terrain / Discard**. All PNG identities and source captures are checked before a
single native candidate is built. No intermediate one-cell candidate is adopted
or used to reject a seam against an about-to-be-replaced neighbor. The complete
candidate must satisfy native seams, bounds, document and 16 MiB binary/text Undo
budgets. Neighboring cells outside the selected rectangle, including implicit-flat
terrain, must already match: this importer does not repair them.

One command changes all active descriptors plus one fresh provenance notice.
One Undo/Redo restores/reapplies every descriptor and retained binary payload.
Reimport is a fresh notice and preserves previous references, files and packages.
Project dependencies are fingerprinted once for the complete candidate and
rechecked at adoption. Stale document/lock/payload, missing/duplicate cells,
changed source/PNG identity and partial failures cannot partly change the document.
Completed COGs, per-source receipts and any completed PNGs survive later failure.
Discard removes only the pending candidate. Editing options away and back also
invalidates pending selection via a monotonic revision. The JSON contract compares
serialized requested options at the UI boundary so harmless floating-point parse
roundoff cannot reject the displayed request; local edit revisions remain exact.

The public package schema, MapKit native ABI/recipe and game contracts are unchanged.
Larger areas and actual provider/platform/accuracy acceptance remain separate.

Original synthetic COG-shaped fixtures exercise real Rasterio, projection, child
IPC, PNG16/native validation, source identity, reimport/Undo/Redo/recovery/package
preservation, cancellation/deadline/owner close, stale coordinates and review UI.
Offline tests reject retired remote requests and URI/VSI paths before decoding,
exercise local copy cancellation/size/hash guards, and retain existing mixed-resolution
sampling tests. Actual terrain accuracy, large areas, Windows/Linux native exports
and installed Client driving remain separate acceptance. Run with an isolated user directory; never use user datasets
as fixtures or clean up completed COG captures as test scratch.

```sh
.venv-import/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/.venv-import/bin/python --script dem_validator --script heightmap_import_validator --script import_job_validator --script local_only_validator --script overture_validator --log-dir /new/dem-core
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/.venv-import/bin/python --script dem_validator --rendered --log-dir /new/dem-rendered
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/.venv-import/bin/python --script dem_validator --resource-pack --log-dir /new/dem-resource
```

Official source contracts checked 2026-09-09:
[AWS registry / 2021 release](https://registry.opendata.aws/copernicus-dem/),
[COG dimensions, sample centres, naming and license](https://copernicus-dem-30m.s3.amazonaws.com/readme.html),
[DSM, WGS84/EGM2008 and attribution](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM),
[Rasterio window/block reads](https://rasterio.readthedocs.io/en/stable/topics/windowed-rw.html).
Data licenses are separate from this MIT adapter. The source notice is retained
for adapted GLO-30/GLO-90 terrain; publishing derived data still follows the linked
source license. This AWS 2021 path does not assert access to newer CDSE releases.

2026-09-09 scoped Mac validation: 38 Python tests including 9 DEM tests passed;
50 native DEM checks, 52 rendered checks with both 1024×720 dialogs inspected,
and 50 checks against a compiled host resource PCK passed. Existing heightmap,
ImportJob, Geofabrik, Overture and document-history regressions also passed.
The runner uses copied public sources, isolated user data and original synthetic
COGs. Runtime/MapKit generation did not change. Actual provider/OS/driving and
multi-cell implementation limits above remain open; this is not final release
acceptance. Rasterio reads emitted a NumPy 2.5 shape-setting deprecation warning
in Python tests; native runner diagnostics were empty.


## Building courtyard extension — recipe 5, 2026-09-09

This replaces the building-hole rejection in the earlier GeoJSON and OSM
multipolygon profile. GeoJSON Polygon/MultiPolygon and explicit complete OSM
outer/inner relations preserve holes in a single MapKit building record. Multiple
outers/islands retain separate identities. No courtyard is filled or split into
arbitrary buildings. Overture now shares this profile through the bounded extension below.

Choose **Recipe 5** in authoring settings before importing a courtyard. The
review states this requirement and native validation rejects legacy recipes with
an actionable error; import does not silently upgrade an existing document.
Other existing records must also meet recipe-5 (recipe-3 placement) validation.
The public MapKit contract requires a flat roof, at most 16 strictly interior,
disjoint holes and 512 total vertices. Touching/crossing/nested rings and invalid
projected topology reject the whole candidate. Roof/material remain declared
import estimates. Unsupported/missing courtyard usage is explicitly estimated as
`residential` (`courtyard_usage`); recognized residential/commercial/industrial/
public values survive. Source labels/hash, counts, projection, attribution and
original files remain preserved. No vertical OSM structure is newly inferred.

Review/discard/adopt is still one bounded owned child and one additive Undo
command. Existing geometry is never replaced: overlapping reimport is rejected
under recipe-5 clearance rules; remove/relocate old layers explicitly if desired.
Move/duplicate translate outer and inner rings together. Canvas picking excludes
the courtyard void; hole-bearing buildings show outlines without a misleading
filled outer polygon. The shared 3D preview renders exact roof/inner wall prisms;
export overview and Client picker retain inner outlines. Save, recovery and
package export preserve the same holes. Cancellation and stale document/request
checks retain their existing whole-layer publication boundary.

Public regression commands: `cargo test --locked` in the MapKit dependency,
`python -B -m unittest discover -s tests -p 'test_*.py' -v`, and
`python scripts/check_documents.py --godot GODOT --import-python PYTHON
--script courtyard_validator --script import_job_validator --script
workbench_validator --script document_history_validator --script
document_recovery_validator --log-dir NEW_DIRECTORY`. Also run courtyard_validator
with `--resource-pack` and `--rendered` in an isolated Mac environment. Native
Windows/Linux/installed Client/export and representative-map performance remain
separate acceptance gates. Structural OSM, vertical Overture parts and large-area DEM
remain distinct unfinished units.


## Overture multipart/courtyard extension — 2026-09-09

The building snapshot adapter accepts 1..256 complete footprint parts per source
feature. Each polygon has one outer and at most 16 holes; a courtyard has at most
512 non-closing vertices. All closing positions count against the existing 200,000
source-point cap. Existing 32 MiB snapshot, 20,000-feature, 60,000-record, IPC and
native admission caps still apply. A shared two-million-operation topology budget
runs separately on source WGS84 and projected integer coordinates. Empty, open,
self-crossing, touching, overlapping, misassigned or nested-hole geometry rejects
the whole layer; there is no clipping, repair or partial acceptance. Complete
islands inside courtyards and parts outside the selected bbox are retained when
the feature envelope intersects it. Envelope overlap is not exact intersection.

Source feature order is sorted by ID. Provider polygon/ring order is preserved;
a single member retains the historical authored ID, while multipart IDs append
`-part-N`. `feature_sources` retains ID/version/full sources and now explicitly
records `footprint_count` and every `building_ids` entry. The Editor boundary
requires unique exhaustive mapping to building-only patches. Snapshot v1 and
adapter v1 remain; old saved snapshots are reparsed to the current candidate
contract. No persisted project or old attribution is migrated automatically.

Every part remains in one reviewed additive command and source notice. A
courtyard requires explicit recipe 5; the document is never implicitly upgraded.
Unknown use is an exposed residential estimate for all Overture footprints,
including solid islands (recipe 3+ cannot generate unknown use). Provider use,
roof/floor details remain unmodeled, retained in the immutable snapshot. Vertical
`has_parts` and elevated buildings require the explicit vertical profile below.
Underground buildings and other themes still reject or are not queried; horizontal
multipart support does not infer vertical building parts.

Focused reproduction with the optional Python dependencies and matching MapKit
binding built as documented above:

```sh
python -B -m unittest discover -s tests -p test_overture_area.py -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script overture_geometry_validator --script overture_validator --script import_job_validator --script import_layer_validator --log-dir /new/overture-geometry
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script overture_geometry_validator --resource-pack --log-dir /new/overture-geometry-pack
```

Synthetic Arrow/WKB snapshots, source-to-part mapping, courtyard/island native
review/generation, forged/invalid whole-layer rejection, explicit recipe,
Undo/Redo, recovery, preview cancellation and unchanged source/package checks
cover this profile. Actual provider/OS/installed-client and full acceptance remain
separate; no representative-data or performance result is claimed.


## Bounded area-selection wizard — 2026-09-09

The surviving selector is **Import vector → OSM crop: off/on**. Enter W/S/E/N or
drag the offline coordinate diagram in either direction. **Fit coordinates** and
**Area at import origin** preserve explicit numeric selection without changing
geographic/local origins. Latitude increases upward. The diagram is not a basemap,
coverage promise or feature preview. Positive non-crossing boxes remain limited
to 0.02 degrees per side. Changed-then-restored selection increments the revision
and rejects stale local import results. Selection and cancel preserve the document.
The remote Overture area/release/theme wizard has been removed.

Validation: `area_selection_validator`, `osm_area_validator`, `osm_stream_validator`,
`local_only_validator`, `import_job_validator` and the standalone compiled pack.


Mosaic regression entry points: `tests/test_copernicus_dem.py` and
`dem_mosaic_validator` via `scripts/check_documents.py`. Tests generate four
original synthetic COGs and exercise mixed resolution/corner interpolation,
shared edges, aggregate caps, completed-source preservation, complete native
adoption/history, outside-neighbor seam rejection, stale selection and shutdown.


## OSM bbox crop and region selection (I02)

Choose an already obtained local PBF/XML. The former online region catalog and
URL probe/download workflow are removed; source files and existing receipts remain.

**OSM crop: off/on → Crop OSM PBF/XML during import** enables an explicit W/S/E/N
rectangle, at most 0.02 degrees per side. Drag the offline coordinate diagram or
enter precise coordinates; **Area at import origin** seeds a box without changing
origins. **Keep selection** returns to import; import still requires an explicit
source and geographic/local origins, candidate review and atomic adoption. Closing
the crop window retains these form settings; it does not adopt anything. The main
import button reports on/off. Invalid bounds block import. Crop settings only apply
to OSM sources; other formats keep their existing separate selection contracts.
Changing crop settings discards the reviewed candidate and invalidates an in-flight
result even when the values are subsequently restored.

The original PBF/XML is fully parsed under the existing entity/reference/feature
caps before cropping. Unsupported structures, missing references, malformed source
geometry and budgets still reject the complete candidate, including outside the
box. A tiny bbox cannot make an oversized provider region admissible. This is
bounded derived geometry processing, not a remote bbox service or source PBF rewrite.

Optional **shapely==2.1.2** performs double-precision WGS84 planar intersections
before the existing offline UTM/centimetre conversion. Road centerlines split into
separate imported lines; widths may extend outside the bbox. Untagged roads keep
independent endpoints; explicit-height roads follow the ground-crop extension below.
Building/forest/orchard polygons retain holes and split
parts, with shared topology checks before native validation. Artificial walls at
cut building edges are a crop consequence, not surveyed building geometry. Boundary
point/line contacts without the required dimension are omitted and counted; no
repair, padding, flattening or invented structural heights. Polygon/line output
uses the existing 200,000-position, 20,000-feature, 12 MiB result and native/Undo
budgets. Complex GEOS work is cancellable by terminating the owned process; these
caps are not a measured native-memory guarantee or a cross-GEOS byte-hash promise.

Review/provenance retain original source bytes/hash/name/ODbL, selected bbox,
`geometry-intersection-v1` (v2 for explicit-height roads, below), Shapely/GEOS versions and input/outside/changed/output/
boundary-contact counts. The ImportLayer consumer rechecks crop identity/counts
against the request. Reimport creates a new layer. Existing sources, project and
packages are never rewritten by crop; adoption/Undo/Redo retain existing atomic
history and native geometry checks. Building courtyards still require recipe 5.

Verification: `test_osm_area.py`, existing OSM Python tests,
`osm_area_validator`, `local_only_validator`, `osm_import_validator`,
`osm_multipolygon_validator`, `import_job_validator`, `import_layer_validator`,
and standalone resource/rendered checks. Official contracts checked 2026-09-09:
[Geofabrik catalog and buffered complete extracts](https://download.geofabrik.de/technical.html),
[Shapely intersection](https://shapely.readthedocs.io/en/stable/reference/shapely.intersection.html).
Actual regional import/accuracy, Windows/Linux dialogs/distributions and large-area
support remain separate acceptance or implementation work; this does not complete I02.


## Explicit OSM bridges, tunnels and ground connections (I02, 2026-09-10)

The existing OSM PBF/XML import and review/adopt flow now accepts `bridge=yes`
and `tunnel=yes` roads with **`ele` on every referenced node**, and explicit-height
ground approaches. This is a bounded source profile, not general OSM terrain
reconstruction. Node `ele` accepts signed decimal metres, optional ` m`, within
±10,000 m. Heights retain the OSM EGM96 sea-level reference: **map Y=0 means
EGM96 zero** by default. The [height-reference extension](#local-height-reference-and-correction-grids--2026-09-10)
adds an explicit local zero and EGM96 → EGM2008 conversion. Active imported DEM/OSM
datum, zero and projection origins must agree; existing data is never shifted.
Missing elevations are rejected, never interpolated from neighboring node tags.
The generated road linearly grades between fully supplied vertices.

- `bridge=yes` maps to MapKit `bridge`; no invented piers, deck thickness or
  under-bridge clearance. `height`/`min_height` cannot substitute for deck elevation.
- `tunnel=yes` maps to `tunnel` and requires `maxheight:physical` in 2..50 m.
  This becomes a constant clearance above the graded floor. The rectangular
  cross-section is an explicitly reviewed estimate. Legal `maxheight` is never
  used as physical geometry; access/vehicle restrictions are not implemented.
- Each structure endpoint must meet an explicit-height **ground** way or the
  [same-kind continuation contract](#connected-osm-structure-endpoints--2026-09-10).
  Missing approaches and unanchored continuation cycles reject.
  Interior shared source nodes split roads into bounded segments. Only matching
  OSM node IDs join; coincident coordinates and geometric crossings never weld.
  Graph node level stays zero, with elevation carrying the vertical geometry.
- Integer `layer` from -5 to 5 is accepted on structures as source ordering, not
  converted to metres or graph-node levels. Nonzero ground layers reject. Source
  bytes/hash remain authoritative for ignored ordering tags.
- Other bridge/tunnel types, way-level `ele`, `ele:*` alternate datums, `incline`,
  `level`, covered/location structures, vertical building parts and ambiguous or
  partial node profiles reject the whole candidate. Width/surface defaults and
  omissions still appear in review. Tagged-node counts include consumed `ele`.
- The ground-crop extension below replaces the original all-roads-contained rule.
  Complete retained bridge/tunnel ways keep their exact graph/profile; explicit
  ground approaches may be clipped while preserving nonzero required connections.
  Partial bridge/tunnel spans follow the section-crop contract below. Legacy ground/polygon crop is unchanged.

This replaces the earlier independent-endpoint rule only for explicit-height
roads. Untagged ground roads retain the previous estimated elevation and independent
endpoints. Source/record/point/output caps and native geometry/budget validation
still apply after splitting. Import metadata prominently reviews vertical datum,
geometry estimates, structural counts and limitations before one-command additive
adoption; cancel, stale review, Undo/Redo, source and prior-package retention remain.
No MapKit ABI, recipe or generator change is required. Tests use synthetic PBF/XML.

Tag semantics: [OSM ele](https://wiki.openstreetmap.org/wiki/Key:ele),
[physical clearance](https://wiki.openstreetmap.org/wiki/Key:maxheight:physical),
[legal maxheight](https://wiki.openstreetmap.org/wiki/Key:maxheight).
Run `python -B -m unittest discover -s tests -p 'test_osm*.py' -v` with optional
requirements, and `scripts/check_documents.py --script osm_structures_validator
--resource-pack --log-dir /new/structures` with the documented Godot/Python arguments.
The full runner now includes the new validator. Real regional accuracy, datum
accuracy, chained structure approaches, other source
profiles and target-platform acceptance remain separate work.


## Overture vertical building parts — 2026-09-10

Select a local version-1 building snapshot with `include_parts=true`, explicit
`ground_m`, and complete `building` / `building_part` families from one dated
release and bbox. The profile allows 256 total source features and 8192 ring
positions within existing source/IPC/native caps. Partial families reject as a
whole. No remote readers or dual-query publication remain.

Choose recipe 3 or newer explicitly (recipe 5 for courtyards). Every solid needs
numeric `min_height` (including explicit zero) and `height`: base is common ground
plus `min_height`, and height is thickness from lowest to highest point, following
[Overture BuildingPart](https://docs.overturemaps.org/schema/reference/buildings/building_part/).
The common ground plane is user supplied, not sampled terrain or a datum conversion.
Missing heights are not reconstructed from floors/level. Underground and nonzero
z-order inputs reject. Roof shape, material and residential use remain reviewed
estimates; original properties are retained in the source snapshot.

Every part must reference exactly one supplied `has_parts` parent. Parent geometry
must lie strictly inside the query, contain every part, and equal their footprint
union. Missing parents/parts, uncovered remainder, nested parts, duplicate IDs and
out-of-parent geometry reject the entire layer without repair. This conservative
coverage profile does not claim every real-world family can be imported. Parent
geometry remains in the preserved snapshot; parent ID/version/full sources and
sorted part IDs remain in provenance. Only parts create solids, avoiding a second
parent volume. Native projected/quantized occupancy validation rejects overlapping
solid volumes; vertically separated parts retain their gap. Standalone elevated
buildings with explicit dimensions also work in this mode.

Review shows attribution, plane/shape assumptions and the complete candidate.
Adoption is one additive command; discard, Undo/Redo, save/reopen, recovery,
cancellation, stale document/review and retry retain the original source and prior
package. No MapKit ABI/recipe or game dependency changes are needed.

Synthetic checks (optional dependencies installed in the selected Python):

```sh
python -B -m unittest discover -s tests -p 'test_overture*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script overture_vertical_validator --script overture_geometry_validator --script import_job_validator --script import_layer_validator --resource-pack --log-dir /new/overture-vertical
```

Actual local source accuracy, installed target platforms and
performance acceptance remain deferred. Larger areas, incomplete family handling,
underground solids, automatic terrain alignment and other themes are unimplemented.


## Overture transportation ground graph — 2026-09-10

`overture-transportation-v1` is a separate bounded local adapter. Select **Overture
transportation snapshot** (`.overture-roads.json`) in **Import vector**, choose
geographic/local origins, import, review and adopt. The complete version-1 source
embeds one dated release/bbox, explicit road plane, segment/connector records and
source attribution. No SDK readers, source-query form or acquisition CLI remain.

Supported profile:

- Source cap: 32 MiB, 1024 total segment/connector features, 8192 source positions,
  at most 2048 split roads. Existing 12 MiB output/16 MiB history/native admission,
  owned worker deadline/pipe/parent lifetime and exclusive publication remain.
- Every source position must be strictly inside the reviewed bbox. No segment
  clipping or selected-feature dropping. Every endpoint and internal reference
  must resolve under the explicit-position contract below. All connectors must be referenced.
  Missing/duplicate/ambiguous references, incomplete endpoints, out-of-area features,
  loops/self-crossings and centimetre projection collapse reject the whole layer.
- Interior connectors split the polyline at a checked source position. One
  source connector ID maps to one authored node; coincident distinct IDs remain
  distinct and 2D crossings never add graph edges. Reference `at` is checked using
  WGS84 ellipsoid distance (pyproj Geod) with absolute fractional tolerance 1e-7;
  off-vertex positions additionally use the bounded metric check below; no inferred links.
  Source/connector/segment ordering is canonical; fresh layers get fresh namespaces.
- Road classes: motorway, trunk, primary, secondary, tertiary, residential,
  living_street, service and unclassified. Ground level only; absent/zero `level`
  or one whole-segment zero `level_rules` is accepted. `is_link` and link subclass
  are accepted; bridges/tunnels, nonzero z-order and other flags reject. A z-order
  is never converted into metric elevation.
- `width_rules` and `road_surface` support complete, nonoverlapping partitions of
  `[0,1]`, sorted canonically regardless of input order (at most 1024 rules per
  property/segment). Missing/null/empty property estimates 8 m or asphalt; an
  explicit rule needs a value. Absent/null `between` means `[0,1]`. Gaps, overlaps
  (including global plus scoped rules), reversed/empty ranges, unknown/conditional
  fields and unsupported materials reject the whole layer. Width is 0.2–100 m
  to match native admission; gravel/dirt are retained and paved/unknown estimates
  asphalt. No interval priority, taper or missing-subrange estimation is inferred.
- Physical boundaries are interpolated on the WGS84 geodesic within their source
  edge before centimetre projection. Source vertices remain, and only connectors
  create graph nodes/road records; physical edges carry their own width/material.
  Exact coincident boundary fractions reuse a vertex. Distinct fractions that
  collapse after projection reject, including numerically near-vertex boundaries;
  no tolerance-based property snapping erases short intervals. Output admission
  allows at most 16384 points, counting connector nodes and repeated road endpoints.
  Source limits remain 8192 positions, 1024 features, 2048 roads and 32 MiB.
- The chosen Y plane is a reviewed source-reference estimate. Recipe 2+ ground
  geometry follows terrain; it does not create raised decks or flatten terrain.
  Review terrain alignment yourself. The adapter never samples DEM or infers
  metric bridge/tunnel heights. Names/routes/destinations/speed limits stay in the
  source snapshot and are explicitly not game rules. Nonempty access/turn
  restrictions or unknown semantic properties reject instead of being erased.

Source SHA-256, release/bbox/plane, version and all source attribution entries,
connector→node geometry and segment→ordered split-road mappings survive one native
validated additive command, Undo/Redo, save/reopen/recovery and package export.
The GDScript boundary rechecks mapping completeness, physical arrays, plane and
source/output point counts before whole-document native validation. Reimport adds
a new graph; source and previous package bytes remain unchanged. Cancel/deadline/owner
close stop only the owned child; late document/selection results cannot be adopted.

Official contracts consulted 2026-09-10:
[segment/connector identity](https://docs.overturemaps.org/guides/transportation/segments-and-connectors/),
[geodetic linear references](https://docs.overturemaps.org/guides/transportation/linear-referencing/),
[segment schema](https://docs.overturemaps.org/schema/reference/transportation/segment/),
[road surfaces](https://docs.overturemaps.org/schema/reference/transportation/types/segment/road_surface/),
[transportation attribution](https://docs.overturemaps.org/attribution/#transportation).
Theme notice retains ODbL, OpenStreetMap contributors, TomTom and Overture, together
with the original per-feature source notices. Only synthetic fixtures are tested.

Historical Mac verification before remote removal: Python transportation tests (7) plus existing Overture tests
(15); real synthetic Arrow/WKB dual-reader/exclusive capture, whole rejection and
budgets. Godot compiled PCK on a native display: transportation (67 checks), existing
buildings/vertical parts, area selection, import-layer, worker lifetime and history
passed without diagnostics. Includes actual recipe-2 native junction generation,
source roundtrips, recovery, additive reimport, cancellation and stale responses.

```sh
rtk proxy /path/to/import-python -B -m unittest discover -s tests -p 'test_overture*.py' -v
rtk proxy python3.12 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/import-python --script overture_transportation_validator --script overture_validator --script overture_vertical_validator --script area_selection_validator --script import_layer_validator --script import_job_validator --script document_history_validator --resource-pack --rendered --log-dir /new/transportation
```

The initial tests exposed shared synthetic coordinates, source array order, JSON
integral floats and a colliding test package filename. Fixtures now mutate the
intended feature independently/by ID and use an isolated package name; integral
JSON version numbers are accepted while booleans/fractions reject. The expanded
form initially exceeded the minimum window; its scrollable content now passes.
No assertion was relaxed to accept a broken graph or partial source.

Still unimplemented: conditional restrictions/routing, metric structures,
rail/water paths, partial local graphs/larger areas and terrain/datum alignment.
The physical-interval and explicit-position sections below supersede the earlier
vertex/uniform-only limits. This delivery is not whole-I02 or final acceptance.
Representative local source accuracy, installed Windows/Linux and Client driving,
representative performance and full integration remain deferred to their retained
verification phase. A host PCK does not establish native target distribution.

### Overture physical intervals — 2026-09-10

The preceding uniform-only profile is superseded by the bounded interval contract
above. The original immutable snapshot and adapter/profile identity remain usable.
New provenance records canonical physical rules, original vertex fractions and
ordered per-road fractions/projected points/widths/materials. The GDScript boundary
checks coverage, source/connector boundaries, exact mapped arrays and output budgets
before native validation. Previously authored uniform provenance remains accepted.
This uses MapKit's existing per-edge arrays; no native ABI, recipe or dependency
pin changes. Rule endpoints are hard transitions, not linear width interpolation.

[Official rule scoping](https://docs.overturemaps.org/guides/transportation/scoping-and-travel-modes/)
and [width rules](https://docs.overturemaps.org/schema/reference/transportation/types/segment/width_rule/)
were checked 2026-09-10 together with the geodetic reference above. The complete
partition requirement is this adapter's explicit restriction, not a claim that all
provider data has complete coverage. Structures, restrictions,
large/partial graphs and other themes remain unimplemented. Real provider/installed
platform/user-driving/performance acceptance is deferred; synthetic Mac compiled-PCK
verification is not final I02 acceptance.

Scoped verification: 9 transportation Python tests passed, covering independent
width/surface boundaries, WGS84 interpolation, deterministic order, exact vertex
reuse, gaps/overlaps/unknown conditions, centimetre collapse, input/rule/output
budgets and Arrow source preservation. Final Godot 4.7.2 macOS arm64 rendered
compiled-PCK run passed transportation 77 checks plus import-layer, worker lifetime
and document-history regressions with no diagnostics. This includes native recipe-2
junction generation, distinct physical arrays after adoption, forged span rejection,
Undo/Redo, recovery, package I/O, original preservation, cancellation and stale review.
Use the transportation command above with the last three safety validators; the
unchanged native dylib is reused. Other platforms and full acceptance remain open.


### Overture explicit connector positions — 2026-09-10

This replaces the exact-source-vertex-only constraint. The adapter still uses only
explicit shared connector IDs; coincident different IDs and geometric crossings
never create a connection. The immutable source snapshot remains unchanged.

For an off-vertex connector, compute the closest point on every bounded WGS84
geodesic edge (48 golden-section iterations with endpoint comparison). Require
exactly one candidate within **0.001 m**; candidates separated along the segment
by more than 0.000001 m are distinct and ambiguous, so the entire input rejects.
Require source `at` to agree with the closest fraction within 1e-7. The interpolated
`at` position must also be within 0.001 m of the connector. Source vertices use
the existing exact-vertex/fraction path. Closest source endpoints retain their
source index; other positions insert `at`. Every endpoint still needs a connector.

One connector ID uses its original coordinate for every road endpoint and authored
node, avoiding independent per-road quantization gaps. This permits at most 1 mm
of explicit geometric correction before centimetre projection; the threshold is
an adapter restriction, **not an Overture accuracy guarantee**. Source shape and
physical fractions are preserved; identical fractions reuse one point, while
nearby distinct fractions that collapse to centimetres still reject. No property
boundary is snapped away. Changed projected self-crossings reject as before.

New metadata uses `connection_profile=explicit-position-v1`, with each reference's
original `at`, `resolved_at`, nullable original `vertex`, and `displacement_m`.
Original source fractions/count, ordered road spans and node positions survive
review, adoption and project/package I/O. The GDScript boundary checks the new
profile, ordering, displacement bound, index/fraction mapping, endpoint identity
and budgets before native validation. Older vertex-based provenance stays readable.
Non-exact references share a maximum of 65536 edge comparisons per snapshot;
source/output/road/rule/IPC limits and atomic whole-input rejection remain.

Official [connectivity](https://docs.overturemaps.org/guides/transportation/segments-and-connectors/)
and [linear-reference](https://docs.overturemaps.org/guides/transportation/linear-referencing/)
contracts were checked 2026-09-10: geometry determines the physical connection and
an off-geometry connector uses the closest position. Our tight tolerance deliberately
rejects wider repairs instead of inventing an intersection shape.

Verification: 12 Python tests and rendered Mac compiled-PCK transportation (83
checks), import-layer, worker-lifetime and document-history validators passed with
no diagnostics. Covers off-vertex shared junctions, fractional physical boundaries,
0.5 mm correction/2 mm rejection, ambiguous positions, comparison admission,
source preservation, native generation, recovery/package I/O and cancellation.
Use the preceding focused command with the three safety validators. Native code,
ABI and MapKit pin are unchanged. Windows/Linux standalone builds, actual provider
accuracy, user driving and performance/final integration remain deferred.



## Overture land_cover vegetation — 2026-09-10

The bounded local `overture-land-cover-v1` adapter retains `forest-high-detail-v1`.
Choose **Overture land cover snapshot** in **Import vector** and select an existing
`.overture-land-cover.json` with a dated release/bbox, full feature/source metadata
and license. Set explicit WGS84/local origins and recipe **3 or newer**, then
review/adopt. The full snapshot retains excluded classifications. No remote
land-cover reader or theme acquisition workflow remains.

Only `forest` with `cartography.min_zoom=8, max_zoom=15` maps to existing forest
zones. Known nonforest subtypes (barren, crop, grass, mangrove, moss, shrub, snow,
urban, wetland) and lower-detail records with max_zoom<8 are explicitly excluded
with per-source disposition and no authored IDs. Unknown classes, missing zooms,
other overlapping resolution profiles or zero selected forests reject the whole
candidate. No crop-to-orchard, wetland-to-forest or mangrove inference is made.
This conservative mapping does not implement every vegetation class or base theme.

Polygon/MultiPolygon parts, exclusion holes and islands remain complete, including
parts outside the query envelope; the bbox is not a crop. Simple non-touching
source/projected rings, declared hole owners and centimetre collapse are checked
without repair. Current map bounds and native validation must admit every selected
part. Maximum 256 source features, 8192 source positions, 256 parts per feature,
16 holes per part, existing 2-million topology comparisons, 32 MiB input and
12 MiB typed output remain enforced. These local admission limits do not claim
a whole-process memory cap.

Provenance retains IDs, version, sources/licenses, class, zooms, disposition,
source/selected counts, all source-to-zone IDs and per-part exclusion counts.
The GDScript boundary rechecks classification, mapping, counts, attribution,
fixed estimates and namespace before native admission. Adoption remains one fresh
layer/Undo command; discard, failed imports and updates preserve original files,
accepted documents and prior packages. Reimports require explicit new adoption.

8m spacing and 750-per-mille density are reviewed estimates. Recipe-3+ tree shape,
species, lattice placement and terrain attachment are generated, not observations.
WorldCover's 10m raster classification does not provide measured tree locations or
centimetre accuracy. Source accuracy remains explicit/unknown; inspect alignment.
The complete ODbL base notice and ESA WorldCover CC BY 4.0 attribution are retained
in snapshot, typed layer, project and package; adapter source remains MIT.

Official references checked 2026-09-10:
[land-cover schema](https://docs.overturemaps.org/schema/reference/base/land_cover/),
[subtypes](https://docs.overturemaps.org/schema/reference/base/types/land_cover_subtype/),
[high-detail selection example](https://docs.overturemaps.org/blog/2024/05/16/land-cover/),
[base attribution](https://docs.overturemaps.org/attribution/#base).

Verification: 33 Overture Python tests passed, including six new land-cover tests
with real synthetic Arrow/WKB capture. Rendered Mac compiled-PCK land-cover,
import-layer, worker-lifetime, document-history and transportation regressions
passed without diagnostics. Native forest generation/exclusions, preview, source
review/adoption, reimport, recovery/package I/O and cancellation are covered.
Reproduce from this public repository:

```sh
rtk proxy /path/to/import-python -B -m unittest discover -s tests -p 'test_overture*.py' -v
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/import-python --script overture_land_cover_validator --script import_layer_validator --script import_job_validator --script document_history_validator --script overture_transportation_validator --resource-pack --rendered --log-dir /new/land-cover-checks
```

MapKit source/ABI/recipe/pin are unchanged; the existing matching native build was
reused. Mac resource packing does not establish Windows/Linux standalone install
acceptance, actual provider accuracy, user driving or representative performance.
Those and full final integration remain deferred. Whole I02 and cutover are open.
Next independent unit: bounded large-source **OSM PBF selected-area extraction**;
read existing `osm_extract.py`, input/worker budgets and preservation contracts
before designing streaming passes. The current 32 MiB source limit remains until
an explicit replacement profile is implemented and validated.

## OSM PBF selected-area streaming — 2026-09-10

Implemented and scoped Mac automatic checks passed. **Import vector → OSM PBF →
OSM crop area** now offers **PBF streaming**, with crop enabled and an explicit
WGS84 bbox (at most 0.02° per side). It keeps `osm-extract-v1` and adds provenance
profile `pbf-area-stream-v1`; MapKit contracts/recipe/native ABI are unchanged.
The old bounded whole-source PBF/XML path remains available. Streaming is explicit
even for small PBFs so candidate-selection semantics never change merely with size.

This replaces the former 32 MiB whole-source/no-streaming restriction only for
local current PBF snapshots. GeoJSON/XML/Overture snapshot admission remains
32 MiB. Direct provider acquisition is outside product scope.
Streaming requires osmium 4.3.1, shapely 2.1.2 and pyproj 3.7.2; the disk index uses
Python's public SQLite module. Data remains ODbL, while the new adapter is MIT.

### Capture, selection and completeness

The worker opens a regular source read-only, copies in 1 MiB chunks to its unique
job directory, and calculates the SHA-256 of every captured byte. It checks source
identity, length and modification/change timestamps before and after capture.
Changes during capture reject; later source edits do not alter the frozen candidate.
An exclusive hard link publishes only the private captured snapshot. Original
files are never overwritten/deleted and source hashes never describe the cropped
geometry in place of the original. The final layer retains full source bytes/hash,
three-pass identity, scanned/selected counts and existing bbox/crop/library metadata.

Three passes read complete bounded PBF frames: nodes into SQLite; way references
and envelopes using indexed node lookups; relation envelopes and area ownership
using indexed way/node lookups. Input entity ordering need not be sorted. There
is no whole-source Python dictionary or automatic libosmium location/area cache.
Supported feature way envelopes and feature relation envelopes intersecting the
bbox become candidates; whole member ways and every referenced node are loaded
before normalization/crop. This includes crossing roads and enclosing polygons
with no vertex inside the bbox, split multipolygon members, holes and islands.
Envelope false positives are intentional: a complete candidate can still reject
or crop away. This is conservative selection, not exact prefiltering or geometry repair.

Global admission rejects history/deleted/duplicate IDs, malformed frames/tags,
missing node references in any way and missing node/way relation members. Nested
feature or area relations reject globally because this profile cannot establish
their spatial/ownership closure. Non-area/non-feature relation-to-relation
semantics remain disclosed omissions. Empty feature geometry also rejects.
Unsupported feature semantics in candidate envelopes reject as before; geometry
outside those envelopes is not normalized, unlike the old whole-source path.
Ignored area ownership and overlapping/shared multipolygon ownership cannot
silently convert selected member ways into standalone filled polygons.

The shared normalizer retains explicit road heights, nonzero required ground
approaches, hole/island ownership, topology and crop safety. The ground-crop and
partial structure extensions below also apply to this streaming path. An indexed
one-hop selection adds every ground-highway way sharing either original endpoint
of a selected structural way, including off-window approaches, before normalization.
This preserves complete original source validation when a span is cut. A missing
original approach or removal of a retained original ground junction still rejects.
No inferred heights, missing members, partial graph success or routing/access
interpretation is introduced. Native validation precedes atomic new-layer adoption;
existing documents, previews and prior packages survive failures, Undo and reimport.

### Resource and worker limits

| Resource | Streaming limit / behavior |
| --- | --- |
| Whole captured source | Nonempty regular PBF, at most 2 GiB |
| Workspace admission | Free bytes ≥ source size + 2 GiB index + 64 MiB; later I/O/disk-full failure still rejects |
| Disposable SQLite file | 2 GiB maximum page count, 4096-byte pages, 8 MiB suggested cache, mmap off, journal off |
| PBF envelope | 64 KiB header; 32 MiB compressed/raw blob and 32 MiB expanded payload; raw/zlib only |
| Reader concurrency | One explicit worker and one queued task, one bounded frame at a time |
| Whole-source work | 20 million entities; 80 million references; 20,000 references per way/relation |
| Tags | 128 per entity, 512 characters per key/value and relation role |
| Complete selected input | 250,000 entities, 200,000 nodes/references, 20,000 candidate features, 32 MiB scalar JSON payload |
| Conversion/adoption | Existing 200,000 points / 60,000 patches / 12 MiB output plus native/history/topology quotas |
| Deadline | 900 seconds in both Editor and streaming helper; other jobs retain 120 seconds |
| IPC | Existing 4 KiB event, 1 MiB total, 16 KiB per pipe/frame drain; incomplete stages/regressing counters reject |

SQLite holds only disposable worker-owned data: journaling is disabled because a
partial index is never resumed or adopted. Selection walks primary keys and loads
one payload at a time before byte admission, avoiding whole-payload query sorting.
These application/record/file bounds are not a whole-process RSS cap. Pyosmium's
decoded block expansion, Python object overhead, SQLite cache behavior and OS
cache need representative measurement; a bounded compressed input is not itself
a memory measurement. No representative speed, latency or peak-memory claim is made.

`read`, `index_nodes`, `index_ways`, `index_relations` report actual completed
source bytes (zero to source length for each pass, throttled at 8 MiB/frame ends).
`select` counts completed candidate way/relation records; `parse` marks bounded
normalization/crop entry and completion; `convert` reports features; write/complete
report encoded bytes/hash. Per-stage counters are not overall-time percentages.

Normal completion/errors remove the private snapshot/index in `finally`. Cancel,
deadline and normal owner shutdown kill/reap the child before `ImportJob` removes
its known files. Parent-pipe EOF stops a helper even after Editor crash. As with
existing I03, abrupt process/app termination or failed OS deletion can retain
known files in that request's `user://import-jobs/<token>`; they are never resumed
or adopted automatically. Inspect/remove only a confirmed stopped job's known
scratch, never user PBFs or broad data folders. No grandchildren are created.

### Verification and next unit

`test_osm_stream.py` covers actual >32 MiB raw PBF, zlib parity, geometry enclosing/
crossing a bbox, complete multipolygons/structures, malformed/oversized/expansion
frames, input/index/scan/selection quotas, source mutation/frozen capture,
interruption cleanup, history, parent EOF and exclusive result publication.
`osm_stream_validator` exercises the >32 MiB fixture through compiled public
Editor + native MapKit: source review, bounds/provenance refusal, atomic adoption,
save/package reopen/generation, Undo/Redo, indexing cancellation, controlled
deadline, late restored-bbox responses, retry, stale document and owner shutdown.
Existing OSM area/structure/import-layer/worker/history checks also pass.

```sh
rtk proxy /path/to/import-python -B -m unittest discover -s tests -p 'test_osm*.py' -v
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/import-python --script osm_stream_validator --script osm_area_validator --script osm_structures_validator --script import_job_validator --script import_layer_validator --script document_history_validator --resource-pack --rendered --log-dir /new/osm-stream-checks
```

Mac resource packing is not Windows/Linux standalone installation acceptance.
Representative local sources, target platforms, performance and user driving
remain deferred; whole I02/cutover stays open. Direct provider acquisition and its
Internet acceptance were removed from scope on 2026-09-10. Further local input
work is selected separately after this removal; no new local adapter is bundled.

Official interfaces checked for this implementation:
[PBF Blob/BlobHeader wire contract](https://raw.githubusercontent.com/openstreetmap/OSM-binary/master/osmpbf/fileformat.proto),
[pyosmium FileBuffer/Reader/thread pool](https://docs.osmcode.org/pyosmium/latest/reference/IO/),
[SQLite page-count quota](https://www.sqlite.org/pragma.html#pragma_max_page_count).


## Local-only delivery — 2026-09-10

The Editor now exposes only existing local inputs. `DemJob` shares ImportJob's
process lifetime, deadline and cleanup but dispatches only `dem-plan` / `dem` local
operations. GeoJSON/PBF/XML and all three captured Overture snapshot formats use
the original ImportJob. The removed network-only `overturemaps` requirement is no
longer installed; `shapely` remains necessary for local topology/crop, and pyosmium's
transitive dependencies are retained by its public distribution.

Reproduce affected Python checks and standalone compiled-resource regression with
an isolated selected Python containing `requirements-import.txt`:

```sh
python -B -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/local-python --script local_only_validator --script osm_stream_validator --script osm_area_validator --script osm_structures_validator --script overture_validator --script overture_geometry_validator --script overture_vertical_validator --script overture_transportation_validator --script overture_land_cover_validator --script dem_validator --script dem_mosaic_validator --script import_job_validator --script import_layer_validator --script document_history_validator --resource-pack --rendered --log-dir /new/local-only
```

Detailed historical counts above describe their dated revisions. The current
local-only regressions replace remote transport/SDK cases with local fixtures and
retain geometry, native adoption, source/package hashes, stale response, controlled
deadline, cancellation/retry and owner-close checks. Mac verification additionally
runs with outbound IP connections denied; installed target-platform and final
integration acceptance remain separate. No user source/receipt/project migration
or cleanup runs on startup. Read-only interrupted-work discovery is described below; interrupted work is
never automatically resumed or adopted.

Scoped Mac result: 89 distinct Python tests passed across the initial run and
focused corrected reruns; 21 rendered Godot validators passed with the native
MapKit binding and compiled host resources. The accepted build contains no remote
provider entries. A fresh selected Python has no `overturemaps`/`pyarrow`; outbound
IPv4/IPv6 probes fail with EPERM under the verification sandbox. Real map providers
were not contacted. Python's Rasterio/NumPy 2.5 deprecation warning is recorded;
numerical/PNG/seam checks pass, and no Godot diagnostics remain.

The existing crash-recovery test now passes the isolated project/PCK explicitly to
its child and writes a phase marker before killing it. This proves actual save
boundary interruption instead of mistaking a child startup failure for a crash.
Target-platform distribution, user driving, representative accuracy/performance
and final integration remain deferred under the existing acceptance plan.


## Interrupted local import work — 2026-09-10

On startup, the **Import work** button checks the local work folder and reports
responding Editors and entries to review. Opening it or selecting **Scan again**
starts a fresh bounded scan. The report is a snapshot and has a selectable folder
path. To retry, close the earlier Editor and import the original source as a new
request. There is no delete, resume or adopt action. Reading/dismissing a report
cannot change the current map, history, original source or existing package.

After exclusive directory reservation, vector, DEM-plan and DEM jobs publish a
version-1 `owner.json` through `owner.json.part`, flush and rename, before staging
helpers or launching Python. The bounded record contains only the format/version,
request token, random 128-bit owner identity, operation kind, loopback port and
creation time. It contains no source path, dataset, project content or credentials.
A loopback listen/record publication failure refuses startup and follows the same
newly-owned scratch cleanup. Ordinary successful disposal removes the record; if
unknown files or failed removals leave work behind, the record remains and the
presence endpoint closes. Directory creation before record publication or a torn
record is explicitly unknown. Flush/rename is not a power-loss durability guarantee.

The in-memory owner listens only on `127.0.0.1` with an OS-selected port. A discovery
probe sends a fresh random 128-bit nonce; a live owner returns its own identity and
that nonce. A matching response confirms that this request's Editor responded at
that time. Reused ports, a different owner or replayed responses do not confirm it.
No response means **possibly interrupted or temporarily unavailable**, never proof
that the Editor/worker exited. Busy, suspended or firewall-blocked Editors and a
worker left after failed termination must be preserved. PID, age and directory
names are not liveness/cleanup authority. The record/probe is not authentication
against a malicious process running as the same user and never grants file deletion.

The scanner only reads the immediate `user://import-jobs` directory. It refuses a
linked/unavailable root and skips directory/record links, missing/torn/oversized
records, unsupported versions and mismatched request identities as unknown. It
never traverses child directories, loads importer results/originals, hashes source
files or trusts a host/path from metadata. All probes target fixed IPv4 loopback.
Application-owned bounds are 8 entries per frame, 256 inspected entries, 64 report
rows, 1 KiB per record, 4 concurrent probes and 5 seconds per scan. Every entry
currently occupies a row, so the 64-row limit is normally reached first. The report
explicitly says **partial** at a cap/deadline, including when unlisted work may remain;
rescan is a fresh enumeration, not a cursor or guarantee to reach every old entry.
The user may inspect the displayed folder manually. Filesystem calls themselves
remain synchronous and can exceed a frame/deadline on a stalled filesystem.

Each owner admits at most 4 sockets and one new connection per poll, with 800 ms
per connection, 33 request bytes and 66 response bytes. Discovery has the same
800 ms per-probe deadline. Socket I/O is partial/nonblocking. Cancellation, rescan
and closing the report's Editor release discovery handles. Ordinary worker progress,
parent EOF/watchdog, source hash/native review, cancellation/retry and atomic adoption
keep their existing contracts. Map-provider network acquisition remains absent.

`import_recovery_validator` uses separate actual Editor processes killed at a
record-published boundary and after the production parent-watchdog worker is ready.
It also checks simultaneous live ownership, wrong-owner/replayed responses, idle/
oversized probes, unknown/linked/bounded records, controlled deadline/cancellation,
cleanup remnants, unchanged source/package hashes and report/document preservation.
The public runner now reuses one import/PCK while isolating `user://` per validator;
each loose or packed script's effective user path is checked before execution.

Run the affected standalone build and regressions with synthetic data:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/local-python --script import_scratch_validator --script import_recovery_validator --script import_job_validator --script import_layer_validator --script dem_validator --script dem_mosaic_validator --script osm_stream_validator --script editor_ux_validator --script document_recovery_validator --resource-pack --rendered --log-dir /new/import-recovery
```

Mac results and exact revisions are recorded with delivery evidence. Actual installed
Windows/Linux behavior, power-loss/disk-full faults, representative inputs and final
platform acceptance remain separate; automatic discovery does not complete all I03.
The local IPC API follows the public Godot [TCPServer](https://docs.godotengine.org/en/stable/classes/class_tcpserver.html)
and [StreamPeerTCP](https://docs.godotengine.org/en/stable/classes/class_streampeertcp.html)
interfaces. No native/package/runtime protocol or Python dependency is added.


## Explicit-height ground-road crop — 2026-09-10

The partial-structure extension below supersedes this profile's whole-span refusal.
This v2 profile remains emitted when no retained structural source way is partial.

Local PBF/XML bbox imports, including selected-area PBF streaming, now crop
explicit-height **ground roads and structure approaches**. This replaces only
the earlier refusal of every partial or outside explicit-height road. The existing
OSM dialog/worker/review/adopt flow is used; no network source acquisition returns.

- Ground centerlines clip to the closed WGS84 rectangle in source traversal order.
  Every original vertex retains its node ID and supplied elevation. A boundary cut
  interpolates the two supplied endpoint heights at the same longitude/latitude
  segment fraction, then the existing UTM/centimetre projection applies. Boundary
  coordinates are set to their exact selected planes. No missing height, terrain
  alignment, vertical offset, geodesic interpolation or datum conversion is inferred.
- A source excursion outside the box creates separate roads, even on a later visit
  to the same boundary coordinate. New cut IDs identify the source feature/segment
  within this candidate and do not weld separate roads; original shared OSM IDs
  still connect. Interior crossing coordinates create no new junction. Explicit
  lines use a bounded segment traversal without GEOS overlay/noding output. Polygon
  and untagged 2D road intersections keep their existing Shapely behavior.
- A retained bridge/tunnel must include its **entire original OSM way**, including
  pieces previously split at shared graph nodes. Original required ground junctions
  must retain a nonzero ground approach after clipping. A point-only approach is
  insufficient. Partial spans, clipped-away connections and later native geometry/
  centimetre-collapse/budget failures reject the whole candidate. No synthetic
  ramp, ground connection or tunnel portal is created at the crop boundary.
- Supported explicit features wholly outside the selected box are counted and
  omitted; point-only contacts also count as boundary contacts. Source validation
  still precedes crop (whole snapshot or the streaming candidate selection), so
  unsupported selected source semantics cannot be hidden by a small bbox.
- Ground-road elevations remain **source reference heights**. MapKit ground roads
  follow the existing terrain; clipping does not raise a ground deck or align it
  with OSM EGM96. Retained structures still undergo actual native terrain/apron,
  width, clearance, graph and generation checks. Users must review map alignment.

When normalized input contains explicit-height roads, crop metadata uses
`policy=geometry-intersection-v2` and `vertical.profile=explicit-ground-crop-v1`,
with `clipped_ground_features`, `outside_explicit_features` and
`retained_structure_features` counts. Counts refer to normalized, junction-split
features; the retained-structure count is checked against output road records.
Legacy v1 metadata remains readable; mixing v1 with new vertical metadata rejects.
The source bytes/hash/name/license remain those of the complete captured source.
Review explicitly describes interpolation, original vs new endpoints and terrain
behavior. Source and result size, 200,000 positions, 20,000 features, worker lifetime,
12 MiB IPC result and native/Undo budgets are unchanged. These are logical limits,
not measured RSS or an overall filesystem/GEOS latency guarantee.

`test_osm_ground_crop.py` covers clipped approaches, signed heights, exact boundaries,
reversed/multiple visits, shared vs new IDs, crossing traversal, complete-way safety,
lost connections, outside/invalid data, output bounds, XML/PBF/streaming parity and
exclusive output/source preservation. `osm_structures_validator` adds real worker,
native review/adoption, forged metadata and collapsed-geometry refusal, generated
deck/tunnel roof, package export/reopen, cancellation, changed-restored bbox, retry,
Undo/Redo and streaming parity. The affected crop/stream/lifetime regressions and
compiled standalone resource build are also required:

```sh
rtk proxy /path/to/import-python -B -m unittest discover -s tests -p 'test_osm*.py' -v
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/import-python --script osm_structures_validator --script osm_area_validator --script osm_stream_validator --script import_job_validator --script import_layer_validator --script import_scratch_validator --resource-pack --log-dir /new/ground-crop
```

This scoped Mac automatic delivery does not complete general structural crop,
vertical-datum conversion, larger-area/representative-source accuracy, installed
Windows/Linux behavior, driving or performance acceptance. MapKit ABI/recipe and
native sources are unchanged. Whole I02/I03/I04 and final cutover remain open.
Partial bridge/tunnel **span** crop is implemented by the following extension.
Vertical datum alignment remains a separate implementation unit.


## Partial bridge and tunnel section crop — 2026-09-10

The existing local OSM XML/PBF and streaming import now clips explicit-height
`bridge=yes` and `tunnel=yes` centrelines to the selected bbox. This replaces the
whole-original-way containment refusal above; it does not change MapKit recipe,
ABI, package format or generation. Complete source ways still need all node
`ele` values, physical tunnel clearance and original explicit ground approaches.

- Keep source traversal order, original vertices and shared node IDs. At a segment
  cut, interpolate the two supplied EGM96 heights at the same WGS84 line fraction,
  preserve the clipping plane exactly, then apply existing UTM/cm quantization.
  Width, material and tunnel clearance are retained. Separate visits produce
  separate roads; coincident synthetic cuts never create a positional connection.
- A cut endpoint is an **open truncated cross-section**, not a surveyed entrance,
  a connection to outside geometry or a ground ramp. An exact original internal
  vertex becomes a section end if its other original-way arm was removed; its ID
  survives, including any other retained original junction. Reconnecting separately
  imported layers is an explicit author edit, not automatic boundary stitching.
- Native recipe 2+ keeps the independently elevated deck or tunnel floor, physical
  ceiling and side walls. It leaves graph endpoints open without a closing end-cap.
  It cuts intruding terrain below the tunnel ceiling and preserves terrain above
  the bore according to the existing corridor contract. A cut through an underground
  bore does not create an access path from the terrain surface. The bbox crops the
  **centreline**, not the entire width/roof/wall footprint or the map's terrain;
  native corridor geometry may extend beyond that bbox within the document bounds.
- A retained original ground junction still requires a nonzero retained approach.
  Losing an approach to a point-only contact rejects the whole candidate. The
  native terrain/apron alignment, geometry, cm-collapse and generation budgets
  also remain authoritative; an arbitrary source may still reject. No heights,
  clearance, supports, vertical datum conversion or missing source graph is inferred.

When any retained original structural way is partial, crop provenance uses
`geometry-intersection-v3` / `explicit-structure-crop-v1`. Unchanged/ground-only
crops continue to emit v1/v2, which remain readable. The v3 vertical record carries
existing normalized-feature counts plus `partial_structure_ways`,
`section_endpoints` (endpoint occurrences, not unique nodes) and `structures`.
Every output structure maps its output feature index to a normalized source feature
index, decimal-string original OSM way ID, whole-way `partial` flag, `[start,end]`
source range and two `{ref,role}` endpoints. A range value is a zero-based segment
index plus its fractional position in that normalized source feature. A source
feature index refers to the selected, sorted, junction-split collection; it is not
an index into the binary PBF. The source hash and original way ID allow tracing to
the captured input. Roles are `source-node` or `boundary-section`; refs preserve
original IDs or identify synthetic cuts. The consumer checks mapping completeness,
road/end identity, interval/count bounds, consistent partial flags and section roles.
This is structural validation of adapter metadata, not an independent survey or
reconstruction of the original source. Full metadata is stored in attribution and
retained on save/export/reopen. Warning samples summarize counts within 512 chars.

Streaming selection adds only the original source approaches needed by selected
structural way ends. Ground-way node incidence is held in a disk-backed indexed
table under the existing 2 GiB index budget; the closure is bounded to 20000 distinct
approach ways, then existing combined selection/reference/byte/point limits apply.
It does not recursively follow newly added roads. Original source bytes/hash,
three-pass progress, deadline, cancellation, exclusive publication and owned-index
cleanup remain. This index may reach its cap earlier for dense input; it is not a
new RSS or maximum-performance claim. Other unsupported off-envelope geometry
remains a disclosed omission, and added approaches undergo full normalization.

Mac automatic verification covers two-ended and one-ended cuts, signed grade
interpolation, exact source-vertex cuts and retained junctions, reentry/reversal,
non-welded cuts, complete off-window source validation, budget/cancel/retry, bounded
review, forged metadata and native collapsed-geometry rejection. XML/PBF/stream
parity, original source/prior package hashes, native deck/floor/ceiling and open ends,
original ground joins, save/export/reopen, stale bbox responses and Undo/Redo were
checked using synthetic inputs and a standalone compiled host PCK. Reproduce:

```sh
rtk proxy python3 -B -m unittest discover -s tests -p 'test_osm*.py' -v
rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/import-python --script osm_structures_validator --script osm_stream_validator --script osm_area_validator --script import_job_validator --script import_layer_validator --script import_scratch_validator --resource-pack --log-dir /new/structure-crop
```

Native MapKit source/build/recipe are unchanged; its existing Mac binary was reused
and loaded by the actual import/generation checks. Actual Windows/Linux installed
behavior, representative geodetic accuracy/driving/performance and final integration
acceptance remain unverified. Vertical datum alignment, other unsupported source
semantics and larger areas remain implementation work. No direct provider downloads
or automatic original/project/package edits were introduced.


## Local height reference and correction grids — 2026-09-10

**Import vector → OSM height reference…** controls explicit `ele` heights in local
OSM XML/PBF, including streaming/cropped structures. Choose EGM96 and the target
datum height at local zero (default 0 m), or choose EGM2008, that same zero, and an
existing local height-difference JSON grid. For an existing Copernicus DEM, match
its EGM2008 local-zero height and WGS84/local x/y origins exactly.

The supported operation is `local_m = H_EGM96 + delta_m(lon,lat) - zero_m`.
EGM96 mode uses delta=0 and forbids a grid. EGM2008 mode requires a complete local
correction surface; there is no constant guessed offset, downloaded grid, optional
fallback or terrain fitting. Missing/alternate OSM node datums remain rejected.
Relative tunnel clearance, building dimensions and authored/estimated local heights
are unchanged. This does not certify unreferenced hand-authored data or remove the
Copernicus DSM's buildings/vegetation.

Prepare the grid externally from licensed local datum material. It contains the
**height difference H(EGM2008) − H(EGM96)** in metres; when evaluated from compatible
geoid undulations at the same reference position, this is N(EGM96) − N(EGM2008).
Source model versions, preparation method, compatible reference/tide conventions,
and approximation/accuracy limits belong in `source` and `accuracy`; `unknown` is
allowed but never interpreted as zero error. This profile does not read native
GTX/GeoTIFF geoid models, infer their conventions or certify the supplied material.
No official model is bundled. A synthetic format example (not survey data):

```json
{
  "format": "miniearthure-height-delta-v1",
  "source": "Synthetic example only; replace with licensed prepared material",
  "license": "CC0 synthetic example",
  "accuracy": "unknown; not survey data",
  "horizontal_crs": "EPSG:4326",
  "source_crs": "EPSG:5773 / EGM96 metres",
  "target_crs": "EPSG:3855 / EGM2008 metres",
  "quantity": "H_EGM2008-minus-H_EGM96",
  "bbox": [9.5, 55.5, 9.504, 55.504],
  "columns": 2,
  "rows": 2,
  "values_m": [1, 3, 5, 11]
}
```

`bbox` is west/south/east/north. Samples include both edges at evenly spaced
longitude/latitude positions: each row runs west→east, rows run south→north.
Bilinear interpolation uses all four samples, including at the boundary. The
example centre is +5 m. Coverage must include **all complete explicit source road
vertices and original ground approaches before crop**, not only the selected box.
Conversion precedes clipping; cuts interpolate converted endpoint heights using
the original segment ratio, and projection rounds once to integer centimetres.
A spatially varying correction is sampled at source vertices; the importer does
not densify the road or claim continuous geodetic accuracy along each segment.

Bounds: UTF-8 JSON ≤64 KiB; exactly the displayed fields, no duplicate keys;
2..33 rows/columns; ≤1 degree per side; longitude ±180, latitude -80..84; all
samples finite within ±200 m. Nodata, incomplete rows, inverted bounds,
extrapolation, unsupported CRS/sign, unknown fields or missing source/license/
accuracy descriptions reject the whole candidate. Descriptions are nonblank,
control-free, ≤512 characters. Zero is in whole centimetres within ±10000 m;
converted local heights must also fit ±10000 m. Existing source/point/output,
process/deadline and native geometry budgets still apply. Nondefault conversion
with no explicit heights rejects rather than silently doing nothing.

At start the Editor reads the chosen grid into a bounded immutable request. Review
shows target/zero, order, source vertex/road counts, actual delta range, complete
source/license/accuracy text and grid SHA-256/byte count. `coordinates.vertical`
(`osm-vertical-v1`) retains the **exact UTF-8 source string** and hash, including
whitespace, in project/package attribution. The hash identifies supplied bytes,
not authenticity or accuracy. Later external edits do not alter the reviewed
snapshot; retry rereads it. The worker's private copy is cleaned only under the
existing owned-job rules. Original OSM/grid/DEM files and previous packages remain.

The consumer checks metadata against the captured settings. Before either vector
or DEM adoption, active explicit OSM nodes and active DEM descriptors must share
the target datum, local zero and horizontal origins. Legacy explicit OSM notices
mean EGM96 zero. Only still-active records constrain the frame; retained notices
of deleted vectors/replaced terrain do not. Equal PNG paths alone are insufficient:
cell, spacing, height offset/step and source accuracy also identify active terrain.
This is a consistency guard for retained import provenance, not a global surveyed
CRS contract for arbitrary authored maps. Existing unreferenced objects remain
local. Resolve conflicts explicitly in a separate project or by removing/replacing
conflicting content; this operation never migrates the existing map in place.

Selection changes cancel the owned helper and invalidate review even if restored.
Missing files, failed transforms, stale responses, count/hash/selection mismatch
and native errors never partially adopt data. Adoption is one Undo command;
Redo/save/package/reopen preserve the snapshot. The existing MapKit contract
remains: ground roads follow terrain and mixed structure aprons must agree within
1 cm. Datum conversion cannot fix mismatched physical measurements. No MapKit
ABI/recipe or Runtime/Client/Host changes are involved.

CLI: pass `--vertical-request /absolute/local/request.json` to `geojson.py` with
OSM/PBF input. The request has `target` (`EGM96` or `EGM2008`), `zero_m` and `grid`
(the exact JSON source string, or null for EGM96). Omission retains EGM96 zero.
Other input formats reject this option. The request itself is bounded at 128 KiB.
The Editor requires an absolute local grid path and never fetches its content.

Verification: `test_vertical.py`, `test_osm*.py`, `test_copernicus_dem.py`,
`test_projection.py`; `vertical_validator` exercises actual synthetic DEM + OSM
worker/review/native generation, both import directions, incorrect frames,
snapshot identity, cancel/restored selection, streaming crop, Undo/Redo and package
retention. Run with `scripts/check_documents.py --script vertical_validator
--resource-pack` and the documented Python/Godot arguments. Real model/regional
accuracy and Windows/Linux installations remain separate acceptance gates.
Native geoid-file ingestion, other datums/epochs, height reconstruction and chained
structure approaches remain unimplemented, not merely unverified.

References checked 2026-09-10: [OSM ele reference](https://wiki.openstreetmap.org/wiki/Key:ele),
[PROJ's additive vertical-shift formula](https://proj.org/en/stable/operations/transformations/vgridshift.html),
[Copernicus DSM description](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).
These establish source conventions; this JSON profile and its limits are Editor
contracts, not an official PROJ grid format or a certified transformation.


## Connected OSM structure endpoints — 2026-09-10

The junction profile below replaces the unique-pair/exactly-two-ground-ends
restriction in this section. Its v1 records and native admission remain supported.

This replaces the per-way mandatory ground-end rule and the one-hop streaming
closure above. All heights are still explicit; the existing datum conversion
runs on the complete selected source vertices **before** crop. No heights,
terrain fitting, positional joins, ramps, portal geometry or routes are inferred.

A structure end without a ground connection may share its original OSM node ID
with exactly one other structure **end**, of the same kind (`bridge` or `tunnel`).
There must be exactly two source-highway uses at that node. A branch, endpoint to
interior attachment, missing peer or direct mixed-kind continuation fails the
whole candidate. Joined tunnel clearances must match after the existing centimetre
quantization. Widths, surfaces, vertex order and source-way identities remain
separate. Each component of these continuation links must have two original ends
on explicit-height ground ways; an unanchored cycle fails. Existing grounded and
interior junctions remain subject to native validation; this does not newly infer
or support general structural branches or bridge/tunnel transitions.

Streaming now indexes every highway's source-node incidence, follows the complete
connected structural component from each selected structural way, and includes
**all** incident highway ways at every structural vertex, including outside the
bbox. It transits structural ways only: collected ground roads do not expand the
selection through their other nodes. Unsupported/ambiguous types encountered in
this closure cannot be hidden outside the crop. Relation ownership and complete
node/way validation still apply. The index remains within 2 GiB; closure admits at
most 20,000 distinct highway ways, 200,000 structural references, 200,000 incidence
visits and 32 MiB of structural payload, plus the existing combined selected
entity/reference/byte caps. Dense graphs fail before further accumulation. Periodic
closure events check the worker deadline/cancellation; the three PBF scans and
full immutable capture/hash, exclusive publication and owned cleanup remain.

`coordinates.osm_connections` uses `same-kind-endpoints-v1`: each original join
stores its source node ID, kind, two source-way IDs, and zero/one/two retained arms
mapped to output feature and source way. It retains off-window joins as source
context. The consumer checks identity, duplicates, retained graph incidence,
kind/clearance and crop mapping. Original source bytes/hash remain authoritative;
this metadata is neither independent source reconstruction nor accuracy proof.
Streaming additionally reports `structural-incidence-v1` closure counts.

If crop ends exactly at a source continuation and removes its peer, that endpoint
is an **open boundary section**, even when the retained source way is geometrically
complete. `geometry-intersection-v4` / `explicit-connected-structure-crop-v1`
extends v3 with `connection_sections`; actual partial-source-way flags remain
truthful and may all be false. Both retained arms keep the original shared ID;
synthetic cuts remain separate. V1–V3 metadata remains readable. The bbox form
serializes its displayed six decimal places, avoiding step-rounding noise at a
shared node. Required original ground approaches must still retain nonzero length.

**Native admission correction:** structural OSM import now requires an explicit
recipe 2 or newer. Recipe 1 can emit independent legacy surfaces without the
connected apron checks and is rejected for this profile; the map is not upgraded
silently. After document validation, all imported road corridors (including their
width/possible junction extent) undergo native generation in a disposable project
before review/adoption. A conservative per-road bounding rectangle is used, with
one maximum imported road width as margin; at most 16 distinct affected cells are
admitted before enumeration. Choose a smaller bbox if that check exceeds its cap.
Existing 64 MiB candidate-payload and native geometry/triangle budgets apply.
Native errors leave the accepted map and its loaded bridge/package intact. The
structural UI path now uses the asynchronous native supervisor described below.
Frame-latency, RSS and full-area performance acceptance remain open; native
contracts and generation budgets are unchanged.

Mixed ground/structural mouths must match actual terrain within the native 1 cm
rule. Supply terrain-level approach vertices before the grade. Unequal tunnel
ceilings and overlapping structural mouths fail generation. Previous synthetic
structure/height validators used default recipe 1, so their passing results did
**not** establish these recipe-2 junction guarantees. The validators now explicitly
select recipe 2, supply level approaches and exercise real native success and
failure paths. Python-only legacy fixtures remain useful adapter inputs; successful
normalization alone does not promise native acceptance.

Run the optional-Python `test_osm_connections.py` suite and the public runner's
`osm_connections_validator`, `osm_structures_validator`, `vertical_validator`,
`osm_stream_validator`, `osm_area_validator`, import/lifetime and area-selection
checks with `--resource-pack`. They use only synthetic data and isolated user paths.
General branching/mixed structural connections, missing-height reconstruction,
larger-area imports and installed-platform/real-region accuracy/performance remain
outside this delivered profile. Remote map-service acquisition remains excluded.

## Explicit OSM structural junctions — 2026-09-10

This replaces the non-ground unique-pair, same-kind-only and exactly-two-ground-end
restrictions above. Complete explicit OSM node heights and original shared IDs now
support bridge/tunnel branches, endpoint-to-interior and interior-to-interior
connections, and direct bridge/tunnel transitions. Interior source vertices split
the original way into ordered segments and contribute two arms. Coordinate
coincidence, `layer`, missing elevation and legal `maxheight` never infer a join,
grade or physical clearance. Every incident highway must have a supported complete
profile before crop; a dangling structural end still rejects the entire candidate.

Components linked through non-ground structural joins require at least two
**distinct original ground nodes**, including explicit interior ground contacts.
Three or more ground approaches and grounded cycles are allowed by source
admission; an unanchored/one-anchor cycle rejects. Ground roads do not transit
streaming selection to unrelated roads. Existing recursive source closure,
full immutable XML/PBF capture/hash, vertical conversion before crop, deadlines,
selection/index/payload budgets and exclusive output publication remain intact.
The graph uses linear incidence storage, not all-pairs edges. New non-ground
junctions admit at most 32 directed arms, 20,000 joins and 200,000 source arms in
total. An interior attachment counts twice. These caps are upper bounds, not a
promise that every graph under them can be generated.

`coordinates.osm_connections.profile = explicit-structural-junctions-v2` is emitted
when any join needs the expanded profile. An expanded join records:

- `ref`: original positive OSM node ID; `kind`: `bridge`, `tunnel` or `mixed`;
  `source_ways`: unique original way IDs.
- `source_arms`: each original incident side's `source_way`, `end` (`from` for the
  outgoing side in source traversal order, `to` for the incoming side), `kind`, and
  `clearance_cm` (null for bridges). Two sides of one way must have the same profile.
  All incident tunnel clearances must agree after centimetre quantization.
- `retained`: exact output `feature`, `source_way` and `end` for each remaining
  side. The consumer checks every actual road incidence, direction, kind,
  clearance, duplicate/missing arm, feature/source consistency and crop mapping.

Simple same-kind endpoint pairs keep their v1 join representation without
`source_arms` or retained `end`, including within a v2 collection. Inputs containing
only those pairs still emit `same-kind-endpoints-v1`. Both reader profiles are
supported; source metadata remains review evidence, not independent source-byte
reconstruction. The historical `structure_continuations` count now counts all
non-ground joins, including branches and mixed connections.

When crop removes any incident side but leaves others, v4 `connection_sections`
records the source join and marks its retained endpoints as boundary sections.
This includes two remaining sides of a three-arm branch; it does not falsely claim
the junction is complete or that each retained source way is partial. Zero-arm
off-window source joins remain in context. Retained sides share the original node
and rebuild their native apron together; crop does not preserve the omitted fan
sector or the full source junction footprint. Required original ground approaches
must still retain nonzero length. Older v1–v4 crop metadata remains readable.

The existing public [recipe-2 generator](../addons/mapkit/spec/FORMAT.md#recipe-2-roads-and-structures-k05)
defines the cross-section. No native code, recipe, ABI or package version changes.
Each authored arm stops at its native mouth; the apron is a convex fan through the
source node. Stable incident-road ID ownership assigns each fan face its kind and
material. Only tunnel-owned faces receive a clearance-height ceiling and the
corresponding outer non-mouth edges receive side walls. Mixed portal boundaries
therefore follow the native fan sectors, **not** a recovered real-world portal
plane. Tunnel/bridge sections, walls and ramps are geometric estimates that the
creator must inspect. Independent intersecting structures/buildings still require
creator clearance review. No pillars or automatic terrain fitting are added.

Explicit recipe 2+, at most 16 conservatively affected cells and real native
generation before review and adoption remain required. Overlapping/acute mouths,
unequal tunnel clearances, terrain-incompatible ground approaches and exhausted
subdivision/output budgets fail the whole candidate without replacing accepted
state or its loaded package. For example, stacking a second copy of the synthetic
22-road junction fixture exceeds the subdivision budget; this is a supported
failure, not a reason to increase limits. The following asynchronous native
validation contract replaces this profile's former synchronous UI execution.

`test_osm_junctions.py` and `osm_junctions_validator` cover source identity/order,
interior splitting, branch closure/cancellation/budgets, partial junctions, forged
metadata, native floor/ceiling sampling across mouths, open passage, failure
preservation, package reopen, Undo/Redo and stale requests. Run alongside existing
connection/structure/vertical/import regressions using `check_documents.py` and
`--resource-pack`. These synthetic automated checks do not complete installed
Windows/Linux, real regional/driving accuracy, responsiveness or RSS acceptance.
Missing-height reconstruction, unequal-clearance transitions, other unsupported
source semantics and larger-area imports remain unimplemented. Remote map-service
acquisition remains outside the product scope.


## Asynchronous structural candidate validation — 2026-09-10

Structural OSM review and adoption each run native document/payload loading and
all affected-cell generation in a fresh **Godot child process**. The main Editor
retains its accepted document/history and loaded bridge/package. No native session
or mutable scene object is shared with the child. The synchronous `ImportLayer`
validation API remains available to headless callers; the structural UI path does
not call it on the main thread. Other authoring/DEM validation is unchanged.

- One active operation owns a fresh request token, atomically reserved directory
  under `user://import-jobs`, ownership marker, request, candidate files and child
  handles. A request is one use; Retry creates a new job. Existing paths, links,
  user sources, unrelated files and recovery scratch are never claimed or removed.
- A bounded 24 MiB request binds the current document, layer and project/source
  paths. The child checks its SHA-256 before loading. It revalidates the import
  metadata/document, checks the original source size/hash, snapshots referenced
  payloads and generates every admitted cell, then rechecks source/payload hashes.
  Conversion's captured vertical correction metadata stays immutable and does not
  require its external correction file to remain present.
- Existing explicit recipe 2+, 16-cell admission, **64 MiB payload** and native
  geometry/output/work budgets remain unchanged. Snapshot admission checks total
  file lengths before reading; it checks actual bytes and hashes while capturing.
  Review retains an aggregate payload fingerprint. Adoption performs a new native
  validation and rejects a different payload fingerprint, even if changed terrain
  is still valid. Source files are not copied back or locked against external tools.
- The UI shows source/recheck bytes, snapshot bytes, loading stage and generated
  cells. Progress is per stage. Pipe reads are at most 16 KiB per stream per frame;
  events/results are at most 4 KiB and total IPC at most 1 MiB. Identity, sequence,
  stage, monotonic counters, units, cell bounds, completed generation/recheck and
  result size/hash/schema are checked. Native diagnostics reject the result.
- A **120-second supervisor deadline** covers each native validation. Cancel,
  changed document/selection and Editor close stop the owned process, including
  during a native call. A separate child pipe watcher terminates on parent EOF;
  successful completion requires the parent's final acknowledgement before exit.
  The parent confirms/reaps exit and then removes only known owned files and empty
  directories. If termination is unconfirmed or unknown files remain, scratch is
  retained. Import work discovery recognizes the `native` ownership kind without
  acquiring deletion or resume authority.
- Completion must match the active one-use native request, its original Editor
  generation, document/layer signatures, project path, input identity, origin and
  crop/height selections. Discard/cancel consumes that operation; late or duplicate
  results cannot publish into a newer operation. Review changes no map data.
  Successful adoption commits one normal Undo command on the main thread.

The product entry scene routes the private worker before creating any Editor UI.
It uses user arguments instead of release-disabled `--scene` overrides. Normal
installed executables use their embedded/adjacent resources. When launching a PCK
with a bare Godot engine, set `MAPEDITOR_RESOURCE_PACK` to **that same absolute PCK
path** as well as passing `--main-pack`; Godot removes the latter from script-visible
arguments. `scripts/check_documents.py --resource-pack` supplies this automatically
and tests with loose product scripts and the main scene hidden.

`import_native_validator` covers actual native generation cancellation/deadline,
parent EOF, Editor close, progress/result faults, startup/ownership/discovery,
source/payload/selection changes, late results, retry, atomic adoption/Undo and
prior package preservation. Run it with existing structural, vertical, streaming,
import ownership/recovery and authoring safety validators. macOS compiled-resource
and source runs do not replace Windows/Linux installed-build acceptance. Process
termination does not prove a fixed cancel latency; request serialization, metadata
review, final command validation and cleanup still have synchronous bounded work.
Real-map UI latency/RSS, driving/geometry accuracy and final integration gates
remain deferred. Missing elevations, unsupported source semantics and larger
regions are still unimplemented; limits were not raised.


## Local supplements for missing OSM structural heights — 2026-09-10

**Import vector → OSM height reference… → Choose missing-node heights…** accepts
one externally prepared local JSON file. Clear the optional path to disable it.
This replaces only the missing-`ele` refusal for original nodes of selected
bridges/tunnels and their incident ground approaches. Source-node IDs never fetch
extra geometry or enlarge the selected graph. All referenced profiles, including
outside-window structural peers and complete approaches, must still be valid
before clipping. Automatic elevation inference and remote acquisition remain
excluded.

Prepare a UTF-8 file of at most **256 KiB**, with **1..4096** node entries:

```json
{
  "format": "miniearthure-osm-node-heights-v1",
  "osm_sha256": "<64 lowercase hex digits for this exact OSM XML or PBF file>",
  "source": "Description of the externally prepared local height material",
  "license": "License and attribution for that material",
  "accuracy": "Declared accuracy, or explicitly unknown",
  "vertical_crs": "EPSG:5773 / EGM96 metres",
  "nodes": [
    {"node_id": "123456", "height_m": 102.25}
  ]
}
```

Replace the illustrative hash and node ID with values for your own file. Node IDs
are canonical positive decimal **strings** in the signed 64-bit range; strings
preserve IDs beyond JSON's exact floating-point integer range. Heights are finite
absolute EGM96 metres within ±10000, like supported OSM `ele` values. The SHA-256
must identify the exact raw input file, including for streaming. Re-encoding XML
as PBF requires that PBF's hash. Source, license and accuracy are nonempty bounded
text; unknown accuracy must be explicitly stated. The hash does not authenticate
the heights, license or survey accuracy.

- Only missing elevations can be supplied. Any listed node with an existing `ele`
  rejects, even when equal; original invalid `ele` or unsupported `ele:*` semantics
  cannot be repaired by this file. Duplicate JSON keys/IDs, extra keys, noncanonical
  IDs, bool/null/nonfinite heights, unsupported datums, snapshot mismatch and
  unreferenced/nonstructural nodes reject the entire candidate.
- PBF closure collects complete connected structures and all incident highways
  using the existing bounded three-pass index. After collection, supplements fill
  missing original nodes, followed by ordinary full profile/graph validation,
  EGM96→target conversion and finally crop. A missing outside node/height, missing
  physical tunnel clearance or invalid approach still rejects. All existing
  selection/index/point, 16-cell, 64 MiB payload and native generation budgets stay.
- Choose EGM96/target zero or the existing EGM2008 correction grid and target zero
  independently in the same dialog. **Supplemental inputs themselves must be
  EGM96**; EGM2008 heights, ellipsoid heights or a local offset are not auto-detected.
  A conversion grid must cover every explicit original vertex before crop,
  including supplemental vertices outside the crop. Ground roads still follow
  terrain; no terrain fit or clearance inference is added.
- The request captures the exact UTF-8 supplement once. `coordinates.`
  `osm_height_supplement` (`osm-node-heights-v1`) stores its raw JSON, byte count,
  SHA-256, full applied-node count and operation order. Review prominently shows
  source/license/accuracy, both hashes and the height reference. Original node
  IDs/heights remain available in the raw supplement even when cropped out.
  Consumer validation checks this contract, exact request identity and bound OSM
  hash. It is not an independent reconstruction of the captured OSM source or a
  survey certification.
- External edits after capture cannot change the reviewed/adopted candidate.
  Retry reads the current file. Changing or clearing the UI selection increments
  its revision, cancels an active Python/native operation and invalidates old
  review/adoption even if restored. Native review and adoption remain separate
  owned children; document/history and loaded bridge/prior package are preserved.
  Adoption is one Undo command. Attribution, project save/reopen and package
  export preserve the exact supplemental source snapshot and its license.

CLI: add `--height-supplement /absolute/local/heights.json` to `geojson.py` with
`--input-format osm` or `pbf`, WGS84/local origins and the OSM license. Combine with
`--vertical-request`, `--osm-bbox` and `--osm-stream` when needed; exclusive output
creation and parent-watch/cancel rules are unchanged. Original OSM, supplement,
correction, DEM, project and package files are never rewritten by import.

Verification: `test_osm_heights.py` exercises XML/PBF/stream equivalence to complete
explicit source, partial and entire missing profiles, structural closure before
crop, datum conversion, immutable provenance, admission failures and cancellation.
`osm_heights_validator` exercises the actual Editor selection/review/child/adoption,
source tampering, invalid provenance, Undo/Redo, saved project/package/native
surfaces, stale selection and Python/native cancellation. Use
`check_documents.py --script osm_heights_validator --script vertical_validator
--script import_native_validator --resource-pack` with the pinned public import
Python and Godot 4.7.2. Native display can run the same validator with `--rendered`.

This implementation unit does not complete I02/I03/I04. Other source semantics,
unequal tunnel-clearance junctions, native geoid ingestion and larger regions
remain unimplemented. Installed Windows/Linux, real-region accuracy/driving,
physical-memory/UI latency measurements and final integration remain separate
acceptance gates; the bounded synchronous metadata/command work is not a fixed
latency guarantee.


## Bounded vector provenance review — 2026-09-10

Vector import review shows source identity/license/accuracy, counts, projection and
processing profiles, the existing bounded estimate/warning samples, and an explicit
**Browse exact details** action. Initial text is at most 49,152 Unicode characters.
Metadata summarization visits at most 128 values, 16 children per object, three
object levels and 8,192 text characters; large mapping arrays show counts. It never
deep-copies or stringifies the complete coordinates. Height-reference/supplement
headings are cached after validating their existing bounded source JSON. The
source/native/IPC budgets and adapter warning sampling are unchanged.

Browse exact details opens a read-only view of the retained candidate, including
all coordinate/crop/connection/stream/provider mappings, patches, estimates,
retained warnings, unknown extension fields and captured source JSON. It is not a
claim that the complete original PBF/XML or discarded adapter warning stream is
embedded in the candidate. The selected original files remain unchanged.

- Objects/arrays show 24 entries per page, with counts, page number, Previous,
  Next, direct Go to page, Open value and Up. Up restores the parent page.
  Previews shorten long names/values; **Read full field name** exposes every key.
- Strings show 4,096 original characters per page. Text is JSON-quoted to preserve
  CR/CRLF, tabs, newlines, quotes, backslashes and Unicode in a TextEdit that would
  otherwise normalize line endings. **Copy exact text page** copies the original
  slice. Joining decoded slices or copied pages in order reconstructs the exact
  retained string; no source text is truncated or rewritten in storage.
- Object pages scan keys without a complete key-index allocation, yielding after
  each 128 visited entries, including skipped earlier pages. Jumping late in a
  wide object can take multiple frames. Arrays use direct indexing. Only one
  displayed page and ancestor references are retained; cancelled/older scans
  cannot publish into a newer page or review.
- Closing details returns to review without adoption. Discard, document changes,
  changed/restored import controls, replacement review, cancellation and owner
  close release detail references. The full request signature is checked on
  opening and adoption; page scans compare bounded UI/generation identities.
  Structural adoption still runs the owned native validation and commits one
  Undo command with complete attribution. Browsing never alters that payload.

This is a vector review presentation unit. Single-heightmap/DEM review, adapter
normalization, candidate validation, attribution serialization and command costs
retain their current boundaries. Input caps and operation counts are not fixed
latency, physical-memory, survey-accuracy or whole I03 acceptance guarantees.

Validation: `scripts/check_documents.py --script import_review_validator` exercises
20,000 mapping records, wide objects, exact Unicode/control text, stale page scans,
selection restoration, actual import/adoption/Undo/Redo/export, source/prior-package
preservation and minimum-window pointer navigation. Add `--resource-pack` for
compiled resources and `--rendered` for the native display. Existing Overture
validators now inspect per-feature attribution through the detail UI, while
summary checks retain release, recipe, plane and source limitation requirements.


## Asynchronous nonstructural vector validation — 2026-09-10

All vector candidates now use a fresh owned Godot child before review and another
before adoption: local/projected GeoJSON, ground-only OSM (including bbox/PBF
streaming), and supported Overture buildings, transportation and land cover.
This replaces the UI's synchronous nonstructural `validate_for()`/`adopt()`
preflight. The synchronous ImportLayer API remains available to other callers.
MapKit generation contracts and source profiles are unchanged.

The child validates the complete candidate document, snapshots referenced assets
and heightmaps, opens that disposable native project and rechecks source/payload
hashes before returning a bounded receipt. Unsaved vector documents without file
references are supported. Missing, changed or over-budget referenced payloads
reject the entire candidate. Review binds the payload fingerprint; adoption
requires it and independently revalidates the current document, layer, source
and identical payload snapshot. The accepted document/history and loaded bridge
remain in the parent. No source, saved project or previous package is rewritten.

Nonstructural candidates generate **zero cells**. Their completed zero-cell
stage means document/payload validation only; it is not surface-generation
acceptance. Structural candidates still require a positive completed generation
count within the existing 16-cell bound. Zero-cell structural success and any
nonstructural generation request are rejected by the supervisor. The 24 MiB
request, 64 MiB payload, 4 KiB event/result, 1 MiB IPC and 120-second deadline
remain; source, native work/output and 16 MiB Undo limits are not raised.

Cancel, deadline, parent-pipe EOF, failed/partial launch, crash and Editor close
retire the child before known owned scratch is removed. Unknown files and
unconfirmed termination remain preserved. Source format, coordinate mode and
origin edits now increment a selection revision and cancel active imports,
including changes restored in the same frame. Existing crop/vertical revisions,
request identity, document generation and document/layer/project signatures gate
completion. Late, duplicate and invalidated results cannot reopen review or adopt.

The parent commits successful adoption as one Undo command after revalidation.
At this delivery, `DocumentStore._commit_command()` still canonicalized the final
document synchronously. The final-command extension below supersedes that limit
for vector/DEM wizard adoption; decoding, request signatures and cleanup retain
synchronous work. This unit does not promise
fully interruptible final commit or fixed UI latency/RSS. DEM/heightmap raster
staging and binary mementos are covered for the DEM wizard by the following
extension; standalone PNG authoring remains synchronous.

Run `scripts/check_documents.py --script import_vector_native_validator --script
import_native_validator --script import_layer_validator --resource-pack` with
Godot 4.7.2 and the public import Python. The two native validators share lifecycle
faults while checking distinct zero/positive-cell contracts, file-backed terrain,
source/payload mutation, Undo/Redo, loaded bridge and prior-package preservation.
Adapter validators await the new asynchronous adoption before checking geometry,
attribution and saved packages. Add `--rendered` for native display/source launch.
Installed Windows/Linux, real-region driving/accuracy/latency/RSS and final
integration remain separate gates; this is not whole I02/I03/I04 or cutover.


## Asynchronous local DEM candidate validation — 2026-09-10

The local Copernicus wizard now starts a fresh owned Godot process after Python
sampling, and a second fresh process when **Adopt all reviewed terrain** is chosen.
PNG decoding, captured/original source hashes, existing project file snapshots,
vertical-reference checks, complete candidate native validation and required cell
generation run inside that disposable child. The UI retains the accepted document,
history and loaded native bridge. The synchronous `stage_dem()` and local PNG
`stage()`/`adopt()` APIs remain available; standalone PNG authoring is unchanged.

A review binds the request/selection revision, document generation/signature,
project directory, candidate metadata and all input file identities. The child
checks every reviewed original COG, captured COG, derived PNG and referenced
project asset/heightmap before and after validation, including replaced old tiles.
Adoption rechecks the reviewed fingerprint; missing, same-size changed, partial,
stale or duplicate results cannot activate any cell. Terrain show/lock changes,
option edits restored in the same frame, document edits and Cancel invalidate the
work. Source/capture/PNG files and previous packages are preserved on failure.

The existing limits remain: at most four COG sources totaling 64 MiB, 4×4 terrain
cells, 1,050,625 samples, 4 MiB per PNG, 64 MiB candidate project payloads and
16 MiB combined command text/binary Undo data. File identity scans independently
bound original, captured, PNG and existing-project groups to 64 MiB each; these
counts are not a process-memory guarantee. A child request is at most 24 MiB,
events and terminal JSON at most 4 KiB, total IPC 1 MiB, and the native deadline
120 seconds. A separate hash/size-bound 24 MiB binary transfer envelope contains
candidate metadata, new blob paths and bounded binary mementos; the following
final-command extension also transfers canonical document/history text within the
same envelope limit;
object deserialization is disabled. Neither source bytes nor PNG arrays go over IPC.

The child builds one complete mosaic candidate, preserving outside-neighbor seam
checks and shared quantization. With roads, it generates every affected terrain
cell (at most 16); without roads, the zero-cell result certifies document/files
and native terrain acceptance only. The supervisor requires the exact cell count.
The parent loads the successful transfer only after confirmed child exit and
installs content-addressed new PNGs before one canonical Undo command. Old/new
references and exact bytes remain retained. As before, Undo/Redo refuses externally
changed or missing referenced files instead of silently recreating them.

Cancellation at native admission, controlled deadlines, EOF/owner close,
failed/partial launch and malformed IPC use the shared vector supervisor. Only
known files in the exclusively reserved scratch directory are removed after
confirmed exit. Unknown files, links and unconfirmed termination are preserved;
interrupted jobs remain discoverable through the existing `native` ownership marker.
No cleanup adopts, resumes or deletes completed source captures.

The following final-command extension supersedes synchronous canonical command
preparation for this wizard. Request/selection/review formatting, bounded result
decoding, immutable final installation, cleanup and final history mutation remain
synchronous. Fixed UI latency/RSS and interruptibility of that final mutation are
not claimed; Windows/Linux installed-build, representative
accuracy/driving/performance and final integration acceptance remain open.

Run the public isolated runner with Godot 4.7.2, the unchanged MapKit native binding
and a Python containing the local import requirements:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script dem_native_validator --script dem_validator --script dem_mosaic_validator --script heightmap_import_validator --script vertical_validator --resource-pack --log-dir /new/dem-native-checks
```

The new raster validator includes real native cancellation/deadline, four-cell
road generation, source/capture/last-output changes, post-validation rechecks,
corrupted transfers, failed/partial launches, invalid IPC, parent EOF, scratch
ownership, stale UI selections, exact binary mementos and atomic Undo/Redo.
`import_native_validator`, `import_vector_native_validator`, `import_job_validator`,
`import_scratch_validator` and `import_recovery_validator` cover shared supervisor
regressions. Add `--rendered` instead of `--resource-pack` for native display and
source-project child launch. Only synthetic fixtures are used.


## Asynchronous final import commands — 2026-09-10

Vector and local DEM wizard reviews/adoptions now prepare their complete canonical
command in the existing fresh owned Godot child. A `prepare` stage covers final
native document validation, canonical first-before/final-after mementos, complete
attribution serialization, exact shared Undo charging and the content signature
used for dirty/savepoint tracking. Source/project inputs are checked again after
command preparation **and transfer serialization/write**. The child never changes
the live document, either history stack, loaded bridge or the saved project.

`DocumentStore._prepare_command()` and `_install_command()` separate preparation
from publication. Synchronous authoring still uses both through `_commit_command()`;
`authoring_files.apply()` can capture a prepared command while validating the whole
DEM candidate. No public package/ImportLayer format, MapKit ABI/recipe, native
library or game contract changes. These transfer methods are internal to the owned
worker; they do not make arbitrary adapter-supplied canonical documents trusted.

The private hash/size-bound binary envelope carries canonical document JSON,
canonical command JSON, savepoint signature and exact new/previous binary mementos
(plus DEM review metadata and new blob paths). It retains the existing 24 MiB
limit, disables object restoration and rejects malformed text/transfer shapes.
The receiver measures actual UTF-8 command bytes plus binary data against 16 MiB;
it does not trust a claimed byte charge. Existing 200-command/shared Undo+Redo,
64 MiB candidate, 16-cell, native/source limits, 4 KiB event/result, 1 MiB IPC and
120-second job deadline remain. Native manifest limits can reject large attribution
before Undo limits are reached; none of these limits is an RSS or latency promise.

Publication requires confirmed success/exit, preparation completion, the original
store instance, unchanged project/document/layer/selection and a monotonic command
epoch. Successful edits, history travel, replacement/recovery, save and even a
begun/cancelled gesture invalidate the epoch. Restoring the same visible document
cannot make an old command current. The owner consumes its result **before** the
changed signal, preventing duplicate or reentrant publication; cancellation also
invalidates a completed result awaiting commit. Cancel/deadline/EOF/owner-close,
partial launch, stale IPC and exclusive scratch retirement retain their existing
contracts. Unknown files and original/captured sources remain preserved.

For DEM, immutable content-addressed PNG installation precedes one complete history
mutation; file conflicts preserve the document/history. Exact old/new binary
mementos remain charged and Undo/Redo still refuses changed/missing referenced files.
Prepared dirty tracking agrees with save, Undo and reopen. Final publication does
not call native validation, rebuild attribution IDs or serialize the history
command again. It still verifies snapshot signatures, decodes bounded transfer data,
installs files and runs ordinary changed-signal/UI work synchronously. There is no
transaction across arbitrary external filesystem writers, and no fixed final-frame
or fully interruptible final-installation guarantee.

The focused `import_command_validator` uses a deterministic test-only barrier around
the real product worker's preparation stage to exercise cancel, deadline, EOF and
source mutation. It checks epochs, wrong store, cancellation after completion,
reentrant commit, malformed/hash-corrupt transfers, budgets and savepoint/reopen.
`dem_native_validator` adds preparation-stage cancel/deadline and guarded final
binary installation. Existing vector/structural, DEM/mosaic, history/recovery,
authoring safety and lifecycle regressions remain applicable. Run:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script import_command_validator --script dem_native_validator --script import_native_validator --script import_vector_native_validator --resource-pack --log-dir /new/command-checks
```

At this delivery, standalone PNG authoring was still synchronous; the next section supersedes that boundary. It was the next
separate implementation unit. Installed Windows/Linux, representative local-region
accuracy/driving/latency/RSS and final integration/clean-clone acceptance remain
open. This is scoped implementation, not whole I02/I03/I04 completion or cutover.


## Asynchronous standalone PNG authoring — 2026-09-10

Authoring → Terrain → **Stage heightmap for review…** now runs PNG decoding,
source/project-file checks, disposable native validation and command preparation
inside a fresh owned Godot child. **Adopt and activate tile** launches another
child against the reviewed identity. The window reports progress and provides
**Cancel PNG validation**; closing Authoring or changing PNG options/terrain layer
state cancels work. The former direct synchronous import button is removed from
this UI. Script callers retain synchronous `TerrainTools.import_png()` and
`HeightmapImportLayer.stage()/adopt()` and the existing terrain-brush behavior.

This explicitly replaces the UI's earlier captured-source adoption rule: the
original PNG must remain available and unchanged through review and adoption.
Both phases hash the original and all referenced project files; adoption requires
the reviewed fingerprint and original layer ID. PNG bytes read for decoding must
match the initial hash, and old binary Undo images must match their inspected
project files. Rechecks occur after native validation, canonical command and
transfer serialization. Changed originals require another review; the Editor never
rewrites them. Synchronous script-only candidates retain their captured-source
semantics. No external writer filesystem transaction is promised.

A single tile plus a new source attribution is adopted as one command. Exact old
and new PNG bytes remain in the shared 16 MiB/200-command Undo/Redo budget. Native
seam/height checks, source accuracy and axes, no implicit resampling, 4 MiB PNG,
513-sample side, 64 MiB candidate/project files, 24 MiB request/binary transfer,
4 KiB event/result, 1 MiB IPC and 120-second deadline limits remain. With roads,
one affected terrain/road cell is actually generated; without roads a zero-cell
result means native document/files were checked, not geometry generation.

`raster_native_job.gd` shares raster transfer/publication with DEM. The child writes
a bounded request-bound single-output marker before installing a content-addressed
candidate PNG, letting the parent retire that path after confirmed exit even if
cancelled during native work. Existing reservations, unknown files, invalid markers
and links are preserved; no recovery scratch is automatically adopted or removed.
Parent EOF, launch failures, deadlines and Editor shutdown use the existing native
supervisor. The final result requires original store/command epoch, document,
project and authoring selection; option/layer changes followed by restoration also
invalidate review. Ready-result cancellation and duplicate/reentrant commit refuse.

The parent only decodes a bounded hash-checked transfer, installs immutable output
and publishes the prepared command. Request/selection signatures, transfer decoding,
immutable file installation, cleanup and changed-signal/UI work remain synchronous;
this is not fixed frame-time or RSS acceptance. Ordinary brush/asset authoring and
history travel are outside this import execution unit.

Reproduce with a fresh log directory:

    rtk proxy python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/python --script heightmap_native_validator --script heightmap_import_validator --script dem_native_validator --script import_command_validator --resource-pack --log-dir /new/png-checks

Replace `--resource-pack` with `--rendered` for display/input verification. Tests use
synthetic PNGs, actual child/native work, controlled preparation barriers, original
mutation, stale UI, malformed/oversized input and IPC, owned cleanup, exact binary
Undo/Redo, save/reopen and original package/bridge preservation. Installed
Windows/Linux, real-region accuracy and driving/latency/RSS remain separate gates.
