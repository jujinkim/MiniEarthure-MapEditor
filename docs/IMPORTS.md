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
I01 boundary accepts them. Parsing/native adoption remain bounded synchronous
work; these quotas do not establish whole-frame latency or process RSS.

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
vertical datum conversion and raster reprojection are not claimed. Multipart and
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
EGM96 zero**, without offset or datum conversion. Review this against the existing
map before adoption; Copernicus EGM2008 is a different datum and is not converted.
Missing elevations are rejected, never interpolated from neighboring node tags.
The generated road linearly grades between fully supplied vertices.

- `bridge=yes` maps to MapKit `bridge`; no invented piers, deck thickness or
  under-bridge clearance. `height`/`min_height` cannot substitute for deck elevation.
- `tunnel=yes` maps to `tunnel` and requires `maxheight:physical` in 2..50 m.
  This becomes a constant clearance above the graded floor. The rectangular
  cross-section is an explicitly reviewed estimate. Legal `maxheight` is never
  used as physical geometry; access/vehicle restrictions are not implemented.
- Each structure endpoint must be shared with an explicit-height **ground** way.
  Missing approaches and structures connected only to other structures reject.
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
alignment, chained structure approaches, other source
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
