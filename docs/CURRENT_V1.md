# Current v1 authoring and imports

New documents, saves and exports use the current MapKit v1 definition. The recipe
selector and automatic feature-driven promotion are removed. Current road
arrangements, buildings, vegetation, environment and regional files use the same
rules. Do not increment format/protocol versions without explicit user approval.

GeoJSON uses `geojson-v1`, including disconnected multilines and collections.
OSM crop, loop and structural-connection provenance have one current v1 shape;
all structural arms, retained directions, crop sections and source kinds are
explicit. Overture transportation requires exact physical spans and positions.
Copernicus `copernicus-dem-v1` uses one bounded array contract for a single local
COG or a folder mosaic. It preserves source hashes, atomic adoption, cancellation,
Undo/Redo and source/output budgets. No previous import shape is auto-converted.

Normal projects, regional packages, supported external map inputs and current
recovery snapshots remain supported. Original files and already generated user
artifacts are never removed. Historical examples retain their map names; their
owned package definitions now use current v1. Historical reports document their
original revisions and do not impose compatibility requirements.

## Verification

Affected Python importer/source fixture tests and Godot OSM connection/loop/
junction, Overture transport, DEM/native adoption, environment, authoring safety
and document history/recovery validators passed. Current fixtures keep bounded
geometry and explicit source provenance. Standalone startup and the initial
canvas loaded without blocking diagnostics. Detailed editing, test driving and
platform acceptance remain user verification.
