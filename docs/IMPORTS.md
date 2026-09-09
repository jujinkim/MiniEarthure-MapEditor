# Import boundary and adoption

Editor-owned MIT adapters depend only on public tools. No MapServer/game module,
private data or runtime generator is imported. `scripts/importers/import_layer.py`
defines the version-1 typed interchange; `scripts/import_layer.gd` revalidates
untrusted results before native MapKit checks and explicit adoption.

Current adapter: explicit local-metre LineString and single-ring Polygon input.
This local extension is not RFC 7946 geographic GeoJSON. Legacy `crs`, Z, polygon
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

I01 Mac import/native/document and rendered adoption evidence is scoped. Child
progress/cancel/retry remains the next I03 local workflow unit; geographic/heightmap
adapters and external OSM/Overture/DEM source workflows remain I02. Actual supported
Windows/Linux exported filesystem/UI and installed Client acceptance remain open.
Official geographic coordinate reference: https://www.rfc-editor.org/rfc/rfc7946
