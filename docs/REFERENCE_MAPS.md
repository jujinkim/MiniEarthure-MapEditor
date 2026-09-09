# Fixed synthetic reference projects (P01 preparation)

`p01-synthetic-v1` is an original MIT, offline, reproducible authoring workload.
It is not a surveyed region, a calibrated dense-city workload, a 50 MB transfer
fixture or a performance acceptance pass. No user dataset is read or published.
MapKit owns all validation, packaging and generation; the Python tool writes only
public source documents and PNG16 payloads. Existing recipe 4 / generated 6 and
all admission limits remain unchanged.

## Frozen profile

`tests/reference_maps.lock.json` records source SHA-256, source/terrain/asset
counts, graph-centreline length, exact bounds, provenance, routes, package and
world hashes, and compressed/expanded accounting. Change the profile ID/version
and preserve old evidence when changing this workload; do not silently recalibrate
it to pass a later performance gate. Native generated hashes are recorded by the
validator; supported-OS equality remains a separate gate.

- **baseline:** unscaled 10,000 × 10,000 m (1,250 × 1,250 m at 1:8), 400 cells
  at 512 m, including 272 m outer partial cells. Four exact 5 × 5 km quadrants:
  urban / residential / rural / forest. 441 graph nodes, 840 connected road
  segments, 420,000 m planar/3D centreline, 700 buildings (400/200/100/0),
  200 orchard/forest rules, 400 terrain descriptors and no custom assets.
- All cells use explicit 257 × 257 unsigned PNG16 grids, 200 cm spacing and
  1 cm quantization. 64 interior forest cells have a repeated 12.8 m synthetic
  tent/plateau; the others are flat. Every edge is zero. Partial cells retain
  a full flat grid. Two unique payloads are shared by descriptors. Source
  accuracy is unknown/not applicable; spacing is not an accuracy claim.
- **baseline-user:** same workload plus one original static PNG and one declared
  box-proxy placement. It exercises actual custom-payload accounting; it is not
  a large-asset stress test.
- **structures:** 1,024 × 1,024 m / four default cells, connected ground junction,
  independent bridge/elevated crossings, open underpass and tunnel with grade
  entrances, walls/ceiling, seam-crossing gable building, flat building, orchard,
  repeated fence and streetlight. Bridge/elevated ends require explicit surface
  spawning; ground-to-deck driving ramps are not authored. Route points describe
  intended traversal, not evidence of physical driving.

The baseline has deliberately explicit zero-width sidewalks. Its regular street
grid and sparse buildings/vegetation are a bounded synthetic workload, not a
claim to realistic category densities. An exploratory 2,100-building candidate
exceeded existing recipe-3 placement work limits during pack. It was rejected
before freezing this profile; no generator limit was increased. Real-density
preparation must retain that failure and address the actual supported workload.

## Reproduce safely

From this standalone public Editor checkout with its pinned public MapKit addon:

```sh
rtk proxy python3 scripts/reference_maps.py /new/reference-v1
rtk cargo build --manifest-path addons/mapkit/Cargo.toml -p mapkit-cli
rtk proxy addons/mapkit/target/debug/mapkit pack /new/reference-v1/baseline /new/reference-v1/baseline.memap
rtk proxy addons/mapkit/target/debug/mapkit pack /new/reference-v1/baseline-user /new/reference-v1/baseline-user.memap
rtk proxy addons/mapkit/target/debug/mapkit pack /new/reference-v1/structures /new/reference-v1/structures.memap
rtk proxy python3 -B -m unittest discover -s tests -p test_reference_maps.py -v
rtk proxy env MAPEDITOR_REFERENCE_ROOT=/new/reference-v1 MAPEDITOR_REFERENCE_REPORT=/new/native-results.json python3 scripts/check_documents.py --godot /path/to/godot --script reference_maps_validator --log-dir /new/checks
```

The destination must not exist. Repeating creation refuses the path and preserves
all existing bytes. No download, user-data discovery, deletion or implicit
replacement occurs. CLI outputs must also be new paths. Source projects can be
opened with Editor's existing Open directory workflow. Generated projects and
packages are reproducible outputs, not files to commit into this public repository.
The renderer/native build must match the pinned addon and Godot 4.7.2.

The test runner copies code/native bindings and isolates `user://`; the supplied
source fixture directory is read-only from the validator's perspective. Exports
are written inside isolated test data. Add `--resource-pack` to compile the host
resource artifact and run with loose product scripts hidden. The fixture creator
is development tooling run beforehand, not an exported application dependency.

## Measured preparation and limits

The Mac MapKit exporter produces 29,566 bytes base; the custom variant totals
30,000 bytes (29,903 base including all ZIP/manifest overhead + 97 compressed
custom payload bytes). Structures total 1,798 bytes. Full expanded sizes and
identities are in the lock. Base target ≤50,000,000 bytes is satisfied **only for
these exact synthetic bytes**. A tiny, regular compressed map cannot substantiate
50 MB inspection/listening or real-region size acceptance.

Four standalone Python checks freeze sources/metrics, PNG sample format/edges,
connected routes and existing-output preservation. Native checks open the actual
Editor store, build the index, export/reopen and compare source/package/world and
size identities. They generate seven baseline cells spanning quadrants, hills and
the partial corner, one custom-asset cell and every structure cell. Explicit
surface queries distinguish ground/bridge and underpass/tunnel floors.

**Deferred:** all 400 baseline cells, native OS parity, renderer/physical driving,
real-region density/accuracy, ground-to-deck approach design, ≥10 minute/≥3 boundary
runs, cold/warm timing, 50 MB transfer/listening, CPU/RSS/GPU/8-player/S04 accounting,
actual Windows/Linux exports and installed Client, anonymous clone/full integration.
These are not replaced by source counts or native sample success. For full
coverage generate each cell (0..19 in both axes), retain hashes/failures and compare
on target OS. Use the fixed route coordinates with installed Client and verify
contacts/boundary transitions before timing. Repeat with a licensed representative
workload of known density/size; document any changed profile separately. Final
product/cutover approval remains outside this preparation unit.
