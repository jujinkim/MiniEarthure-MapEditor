# Import boundary and adoption

Editor-owned MIT adapters depend only on public tools. No MapServer/game module,
private data or runtime generator is imported. `scripts/importers/import_layer.py`
defines the version-1 typed interchange; `scripts/import_layer.gd` revalidates
untrusted results before native MapKit checks and explicit adoption.

Adapters include `geojson-v2` below and the bounded `osm-extract-v1` snapshot profile
at the end of this document. Select the format explicitly in **Import vector**.
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
The bounded OSM/Overture download and Copernicus DEM profiles below are implemented.

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
into the existing owned import/download child and included in compiled resources;
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
recovery, cancellation and stale review. Downloads/remote extent selection,
large-area processing, actual supported OS dialogs and representative source
accuracy/performance remain unimplemented or unverified as separately named work.

Official contracts checked 2026-09-09:
[pyosmium inputs](https://docs.osmcode.org/pyosmium/latest/user_manual/07-Input-Formats-And-Other-Sources/),
[FileProcessor](https://docs.osmcode.org/pyosmium/latest/reference/File-Processing/),
[Geofabrik extract boundaries](https://download.geofabrik.de/technical.html),
[OSM copyright/ODbL](https://www.openstreetmap.org/copyright).

## Geofabrik region download wizard (I02 remote acquisition)

From **Import vector → Download Geofabrik region**, paste a public `.osm.pbf`
URL from [the provider region list](https://download.geofabrik.de/), then choose
**Check region and size**. The review shows the complete provider region path,
resolved dated URL, Content-Length when supplied, modification time, ODbL and
contributor attribution. Unknown length is explicitly unknown; progress then
uses the 32 MiB hard cap, not a promised final size or ETA. **Download reviewed
region** is the separate acquisition action. Completed files appear under
`user://import-sources`; set the WGS84/local origins and use **Import / retry last
source** to reach the existing omission/estimate review and explicit adoption.
The provider URL survives in source provenance; an adjacent JSON receipt retains
headers, requested/resolved URLs, transfer bytes and SHA-256. A downloaded file
is not automatically a valid/adopted map. The existing whole-input 32 MiB,
20 km projection and the bounded way/multipolygon geometry limits still apply.

This profile selects a whole predefined provider region by URL. The OSM area extension below adds a catalog browser and derived bbox crop; it
does not increase whole-source download or large-region admission. Completed snapshots use the multipolygon assembly profile above. [Geofabrik's technical contract](https://download.geofabrik.de/technical.html)
uses buffered polygons and complete crossing ways/multipolygons, so content may
extend beyond nominal borders. Many regions therefore cannot yet be converted
by the bounded local adapter. [Provider licensing](https://www.geofabrik.de/data/download.html)
and [OSM attribution](https://www.openstreetmap.org/copyright) remain mandatory.

Only HTTPS on `download.geofabrik.de`, bounded plain region PBF paths and at most
three same-host redirects are allowed. No credentials, URL queries/fragments,
proxies, encoded paths, compressed HTTP bodies or partial-content responses.
HEAD checks size before acquisition. GET must match the reviewed URL, size and
validators, with If-Match or If-Unmodified-Since; absent validators reject.
Review expires after ten minutes. Transfer and IPC have byte limits, a 15-second
socket timeout and the existing 120-second parent/child deadline. No automatic
retry, parallel download or range resume; retry begins a new request from zero.

The owned job streams to `download.part`, checks exact declared length/EOF and
hashes bytes. It creates a receipt exclusively and atomically hard-links the
completed source to a fresh destination without replacement on the same user-data
filesystem. Failure to publish does not fall back to a non-atomic write. Existing
sources/receipts are never removed. A crash between receipt/source publication
can leave a receipt without its source; it is not a successful import. Cancellation,
owner close, stale URL or changed document cannot start adoption; a fully published
source is retained even if cancellation races with publication. Only request-owned
partial/helper files are cleaned. Crash-abandoned job directories are not scanned
or automatically resumed. Discard/reimport retain earlier documents and packages.

Synthetic HTTP/PBF, owned native process, UI and resource-pack evidence lives in
the root I02 download report. Actual provider HEAD was checked separately; the
synthetic transport fixture is not a real regional import or performance result.


## Overture building area input (I02 scoped provider unit)

**Import vector → Download Overture building area** selects an explicit dated
release and west/south/east/north bbox, at most 0.02 degrees per side. The form
shows the source/license, unknown transfer/count, 32 MiB snapshot/20,000 feature
limits and preserved crossing footprints before **Download this area**. It does
not guess the newest release, clip geometry or adopt a document automatically.
Install the optional public `overturemaps==1.0.2` dependency from
`requirements-import.txt` in the selected Python; no automatic installation.
The official reader is called with the exact release, building type, STAC enabled,
anonymous S3 and 15-second connection/request timeouts. Its API is pinned and
exercised with real Arrow batches and WKB using synthetic sources.

The default profile queries **buildings/building only**; the explicit vertical
profile below also queries `building_part`. Transportation, connectors,
base/vegetation, places and large-area processing are unimplemented. They are not silently included, flattened or declared verified.
The building footprint unit establishes remote area → preserved snapshot → typed
review/adoption; it is not completion of all possible Overture theme adapters.

The owned I03 helper captures returned properties (including GERS ID/version and
full sources) and WKB-derived 2D geometry in a version-1 `.overture.json` snapshot.
Dates serialize as ISO strings. All selected IDs must be unique. More than 20,000
rows, a batch above 32 MiB, a WKB above 4 MiB, or serialized snapshot above 32 MiB
fails before publication. Empty/failed queries do not publish. Completed snapshots
are atomically hard-linked without replacement under `user://import-sources` and
retained on later conversion failure, cancellation or discard. They are derived
source captures, not byte-identical copies of upstream Parquet files; SHA-256 and
byte count identify the captured snapshot. The snapshot embeds its query/license.
No user source, older snapshot, document or package is overwritten or deleted.

The provider's internal STAC/Arrow discovery, batches, read-ahead, retry behavior
and transfer/RSS costs are **not bounded by the snapshot byte cap**. The helper's
120-second deadline and parent EOF watchdog terminate the process, including a
stalled provider call. The client can fall back to dataset discovery if STAC fails.
There is no application retry/resume; user Retry creates a fresh owned request.
Progress counts serialized snapshot bytes against the cap, not network bytes,
estimated time or percent-complete. Partial cleanup removes only owned job files;
crash-abandoned directories are not automatically scanned. Hard-link support on
the same filesystem is required. This is admission control, not performance acceptance.

After download, set explicit WGS84/local origins and choose **Import / retry last
source**. Saved captures can also be selected with **Overture building area
snapshot** in the format picker. Offline reimport needs pyproj 3.7.2, but does not
need the network reader. The existing one-strip/hemisphere/20 km UTM profile and
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

Changing the area while acquisition runs rejects late selection. Document changes,
cancellation and owner close reject adoption, while completed sources remain.
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
python3 scripts/check_documents.py --godot /path/to/godot --import-python /path/to/.venv-import/bin/python --script overture_validator --script import_job_validator --script download_validator --script osm_import_validator --log-dir /new/overture-core
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

Choose a local **2021 GLO-30 COG** or explicitly enable an AWS download.
Enable **Multi-source / multi-cell mosaic** to select a rectangle starting at Cell
x/y, with 1..4 columns and rows. In this mode choose a folder of official GLO-30
filenames (the final filename from each reviewed tile URL), or allow downloading.
Local GLO-90 filenames are not inferred. Cell counts are disabled in single-cell
mode. The source review enumerates all sources, sizes, identities, fallbacks,
origins and cells before acquisition; adopting the later terrain review activates
all listed cells in one operation. Local
source identity is user-declared, not authenticated by filename or fingerprint.
**Review area, source size and license / retry** calculates the projected full-cell
area and captures local size/SHA-256, or HEADs the exact official GLO-30 tile.
If explicitly enabled, only GLO-30 **HTTP 404** selects GLO-90. Review displays the
actual resolution/fallback, tile URL, size, ETag, license, DSM warning and origins.
403, rate limits, timeout, invalid data and missing sample support never trigger
fallback or fabricated zero terrain. The optional GLO-90 choice applies to remote
acquisition; local files in this profile are GLO-30.

**Acquire reviewed source and sample** rechecks the plan, uses If-Match for a
complete GET and captures bytes in an exclusive file in `user://import-sources`.
Known source size is required, at most **64 MiB combined** (also per-source). No redirects, transparent HTTP
encoding, automatic retries or credential/proxy discovery are used. Reviews expire
after ten minutes; changed size/identity/options require a new review. A complete
COG and adjacent receipt are preserved even if later raster/native checks fail.
Partial files belong only to the request; cancellation/owner close/parent EOF and
the existing 120-second watchdog stop the child. Retry creates a new request and
source identity; no existing original, capture, project or package is overwritten.
The PNG is also published exclusively, after complete encoding. Cancellation after
publication may retain a complete source/PNG without selecting or adopting it.

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
The HTTP tests replace transport, not parsing/normalization. They test conditional
GET, 404-only fallback, framing/size/identity/truncation/cancellation and exclusive
publication. Actual live provider downloads, real terrain accuracy/DSM semantics,
large areas, Windows/Linux native exports and installed Client driving remain
separate acceptance. Run with an isolated user directory; never use user datasets
as fixtures or clean up completed COG captures as test scratch.

```sh
.venv-import/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_documents.py --godot /path/to/godot --import-python /absolute/.venv-import/bin/python --script dem_validator --script heightmap_import_validator --script import_job_validator --script download_validator --script overture_validator --log-dir /new/dem-core
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

In Import, choose **Download Overture area…** (Buildings). Enter a dated release and
W/S/E/N coordinates, then **Fit coordinates** to inspect the envelope. Drag in the
offline coordinate diagram in either direction to replace the bbox; numeric fields
remain the precise keyboard path. **Area at import origin** explicitly seeds a
0.001-degree box at the geographic import origin. It never changes geographic or
local import origins. The diagram is not a geographic basemap, equal-distance map,
provider coverage promise or a feature preview. Latitude increases upward.

**Review selected area** validates the calendar date, positive non-crossing box and
existing 0.02-degree-per-side provider limit before any helper starts. A separate
**Download reviewed area** shows the exact release/bbox, unknown transfer/count,
32 MiB captured-snapshot / 20,000-feature caps, 120s deadline and ODbL attribution.
Network bytes and reader memory can exceed the snapshot cap. Returned buildings,
including complete multipart/courtyard footprints, are not clipped to the box.
Courtyards require the existing explicit recipe-5 import choice; vertical or
underground parts remain unsupported. Then select explicit origins, import the
preserved source, review the candidate and adopt as a new layer.

Any release/coordinate edit invalidates confirmation and increments a selection
revision: changing away and back also rejects a pending download's auto-selection.
Cancel on the confirmation returns to selection. Cancellation, deadline, owner
close and document-generation checks retain the existing source/partial ownership
rules. Selection/review do not mutate the document or Undo history.

This unit supports the existing Overture query profile. The OSM area extension
below separately adds region catalog selection and derived geometry cropping.
Copernicus uses its separate single-cell or bounded mosaic workflow below. Tiled
basemaps, large-area queries and OSM region/crop support remain separate work.
Validation: `area_selection_validator`, existing `overture_validator` (including
changed-then-restored selection), `download_validator`, `import_job_validator`,
and the standalone compiled-resource path in `scripts/check_documents.py`.


Mosaic regression entry points: `tests/test_copernicus_dem.py` and
`dem_mosaic_validator` via `scripts/check_documents.py`. Tests generate four
original synthetic COGs and exercise mixed resolution/corner interpolation,
shared edges, aggregate caps, completed-source preservation, complete native
adoption/history, outside-neighbor seam rejection, stale selection and shutdown.


## OSM bbox crop and region selection (I02)

**Import vector → Download Geofabrik region → Load official region list** explicitly
fetches the official `index-v1-nogeom.json`, with a 2 MiB / 5,000-entry cap and the
owned 120-second worker / 15-second socket deadline. Search name, ID or parent;
select a row to set its public PBF URL, then **Check region and size** and separately
**Download reviewed region**. There is no inferred coverage, expected size or
automatic download from catalog selection. Manual URL input remains available.
Only the exact official catalog endpoint is admitted for the index; public PBF
URLs retain the existing same-host/conditional identity/32 MiB transfer rules.
A region edit, including changing away and back, rejects a late probe or download
selection. Completed originals remain on disk even when auto-selection is rejected.

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
separate imported lines; widths may extend outside the bbox and endpoints remain
unconnected until edited. Building/forest/orchard polygons retain holes and split
parts, with shared topology checks before native validation. Artificial walls at
cut building edges are a crop consequence, not surveyed building geometry. Boundary
point/line contacts without the required dimension are omitted and counted; no
repair, padding, flattening or invented structural heights. Polygon/line output
uses the existing 200,000-position, 20,000-feature, 12 MiB result and native/Undo
budgets. Complex GEOS work is cancellable by terminating the owned process; these
caps are not a measured native-memory guarantee or a cross-GEOS byte-hash promise.

Review/provenance retain original source bytes/hash/name/ODbL, selected bbox,
`geometry-intersection-v1`, Shapely/GEOS versions and input/outside/changed/output/
boundary-contact counts. The ImportLayer consumer rechecks crop identity/counts
against the request. Reimport creates a new layer. Existing sources, project and
packages are never rewritten by crop; adoption/Undo/Redo retain existing atomic
history and native geometry checks. Building courtyards still require recipe 5.

Verification: `test_osm_area.py`, `test_osm_catalog.py`, existing OSM Python tests,
`osm_area_validator`, `download_validator`, `osm_import_validator`,
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
- Bbox selection must contain **all** explicit-height roads and their approaches.
  Their original coordinate order/graph/profile is retained exactly. Partial or
  wholly outside explicit-height roads reject, since ordinary 2D crop would lose
  vertical and connection semantics. Legacy ground/polygon crop is unchanged.

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
alignment, partial structural crop, chained structure approaches, other source
profiles and target-platform acceptance remain separate work.


## Overture vertical building parts — 2026-09-10

In **Download Overture building area**, enable **Include vertical building parts**
and review **Common ground altitude (m)**. Both `building` and `building_part`
readers use the same dated release and bbox. The stricter profile allows 256 total
source features and 8192 ring positions, within the existing snapshot/IPC/native
caps. Both readers must finish before exclusive snapshot publication; cancellation
or a second-reader failure cannot publish a partial family.

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

Actual provider accuracy/Internet acquisition, installed target platforms and
performance acceptance remain deferred. Larger areas, incomplete family handling,
underground solids, automatic terrain alignment and other themes are unimplemented.


## Overture transportation ground graph — 2026-09-10

`overture-transportation-v1` is a separate, bounded adapter; building snapshots and
`overture-buildings-v1` keep their existing contract. In **Import vector → Download
Overture area…**, select **Transportation · ground roads + connectors**. Choose a
dated release, bbox and explicit road reference plane, review, then download.
The acquisition uses `overturemaps 1.0.2` segment and connector readers for exactly
one release/bbox. Both readers must finish before the immutable
`.overture-roads.json` snapshot is exclusively published. Select that format for
local snapshots too; choose geographic/local origins, import, review and adopt.
The scrollable source form keeps Cancel and Review accessible at 1024×720.

Supported profile:

- Source cap: 32 MiB, 1024 total segment/connector features, 8192 source positions,
  at most 2048 split roads. Existing 12 MiB output/16 MiB history/native admission,
  owned worker deadline/pipe/parent lifetime and exclusive publication remain.
  Provider Arrow/STAC/network allocations are not bounded by the snapshot cap.
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
a new graph; source and previous package bytes remain unchanged. Selection changes,
even changed then restored, invalidate acquisition review. Cancel/deadline/owner
close stop only the owned child; late document/selection results cannot be adopted.

Official contracts consulted 2026-09-10:
[segment/connector identity](https://docs.overturemaps.org/guides/transportation/segments-and-connectors/),
[geodetic linear references](https://docs.overturemaps.org/guides/transportation/linear-referencing/),
[segment schema](https://docs.overturemaps.org/schema/reference/transportation/segment/),
[road surfaces](https://docs.overturemaps.org/schema/reference/transportation/types/segment/road_surface/),
[transportation attribution](https://docs.overturemaps.org/attribution/#transportation).
Theme notice retains ODbL, OpenStreetMap contributors, TomTom and Overture, together
with the original per-feature source notices. Only synthetic fixtures are tested.

Mac verification: Python transportation tests (7) plus existing Overture tests
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
rail/water paths, partial graph/large-region acquisition and terrain/datum alignment.
The physical-interval and explicit-position sections below supersede the earlier
vertex/uniform-only limits. This delivery is not whole-I02 or final acceptance.
Real provider/Internet/accuracy, installed Windows/Linux and Client driving,
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

Next independent unit: **I02 Overture land_cover vegetation input**. Determine
which explicit source classes can map to the existing vegetation contract, retaining
source classification, reviewed estimates, polygon holes and whole-input rejection.
This is a new theme/acquisition/area-normalization unit, not another connector case.
