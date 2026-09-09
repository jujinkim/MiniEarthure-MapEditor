# Import boundary and adoption

Editor-owned MIT adapters depend only on public tools. No MapServer/game module,
private data or runtime generator is imported. `scripts/importers/import_layer.py`
defines the version-1 typed interchange; `scripts/import_layer.gd` revalidates
untrusted results before native MapKit checks and explicit adoption.

Adapters include `geojson-v2` below and the bounded `osm-extract-v1` snapshot profile
at the end of this document. Select the format explicitly in **Import vector**.
`geojson-v2`: explicit local-metre or WGS84 LineString and single-ring Polygon input.
The local-metre extension is not RFC 7946 geographic GeoJSON. Legacy `crs`, Z, polygon
holes, other geometry and invalid/duplicate JSON keys are rejected, never silently
flattened. Road endpoints remain disconnected; building/vegetation defaults are
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
OSM downloads and Overture/DEM workflows remain I02.

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

Additional checks:

```sh
python3 scripts/check_documents.py --godot /path/to/godot --script import_job_validator --script import_layer_validator --log-dir /new/path/lifetimes
python3 scripts/check_documents.py --godot /path/to/godot --script import_layer_validator --resource-pack --log-dir /new/path/resource
```

The resource mode compiles a host PCK then hides loose Editor product scripts/main
scene before executing the validator. It is not a native OS distribution and does
not require repeating known missing-template exports. Supported-platform process,
Python discovery/installation, native file dialogs and exported UI need actual OS
runners. No network/download progress is claimed before external adapters exist.

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
vertical datum conversion, multipart/holes and raster reprojection are not claimed.
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
External OSM downloads/Overture/DEM adapters remain separate units.

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
latency acceptance. Cancel applies to the pending review. Larger/reprojected DEM
and external adapters still require I03 process ownership and stage progress.
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
closed building ways to footprints, and forest/wood/orchard ways to zones. Ways
are sorted by OSM ID before assigning fresh layer IDs. Shared OSM endpoints are
still disconnected authored endpoints; this is geometry, not a routable graph.
Plain positive decimal metres (optional ` m`) are accepted for width/height.
Defaults and omitted tags are explicitly reviewed: no access/oneway/restriction
semantics, POIs, roof/level-derived heights or survey elevation inference. Tagged
nodes and unrelated ways/relations are counted as omitted. Unknown source accuracy
stays unknown, independent of centimetre quantization. Ground/base elevations,
missing dimensions, vegetation and material/roof values remain estimates.

Missing selected-way nodes, repeated IDs/deletions/history, unsupported highway
classes/area or closed roads, nonclosed polygons, ambiguous categories, selected
feature relations and selected ways in boundary/multipolygon relations reject the
whole import. Bridge/tunnel/nonzero layer and explicit unsupported vertical tags
also reject it. They are never silently flattened or repaired. This deliberately
limited profile does not claim general OSM multipolygon or structural support.

Admission includes **all input entities**, even omitted ones: 32 MiB captured
source, 250,000 entities, 200,000 nodes, 200,000 total way/member references,
20,000 selected ways, 128 tags/entity and 512 characters/tag key/value. Existing
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
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script osm_import_validator --script import_layer_validator --script import_job_validator --script projection_validator --log-dir /new/path/osm-core
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/path/.venv-import/bin/python --script osm_import_validator --resource-pack --log-dir /new/path/osm-pack
```

Synthetic XML and real PBF serialization exercise parity, bounds, malformed input,
omissions, process/native load, adoption/Undo/Redo, source/package preservation,
recovery, cancellation and stale review. Downloads/remote extent selection,
large-area processing, actual supported OS dialogs and representative source
accuracy/performance remain unimplemented or unverified as separately named work.

Official contracts checked 2026-09-09:
[pyosmium inputs](https://docs.osmcode.org/pyosmium/latest/user_manual/07-Input-Formats-And-Other-Sources/),
[FileProcessor](https://docs.osmcode.org/pyosmium/latest/reference/File-Processing/),
[Geofabrik extract boundaries](https://download.geofabrik.de/technical.html),
[OSM copyright/ODbL](https://www.openstreetmap.org/copyright).
