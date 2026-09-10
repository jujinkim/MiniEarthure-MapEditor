# Asynchronous terrain brush preparation — 2026-09-10

## Implemented

The canvas release path snapshots a complete stroke, retires the live gesture and
starts one owned Godot child. The child performs original raster reads, brush
sampling, lossless PNG encoding, detached native document/file checks, affected
road-cell generation and complete binary/text command preparation. The parent
installs immutable PNGs and consumes one prepared command. Direct synchronous
`TerrainTools.finish()` and `import_png()` remain supported.

The existing raster supervisor supplies progress, a 120-second deadline, bounded
IPC, parent-EOF termination, cancel/reap and one-shot command publication. Pending
work is bound to store identity, project, document signature/command epoch and
canvas interaction/authoring state. Tool/layer/option changes, including restoration,
new gestures, Escape/focus loss, Cancel and Editor close invalidate the result.
The old live bridge, document, history and original package/files remain untouched
until successful publication.

All existing operation limits remain: 2,048 points, 16 tiles, one million samples,
eight million distance evaluations, PNG side 513/input 4 MiB, 64 MiB candidate
payloads, 24 MiB request/transfer, 16 MiB shared Undo/Redo bytes and 200 commands.
Road-bearing documents require generation of every touched tile; otherwise native
document/files are validated without generated cells. Seams, original-neighbor
smoothing and exact restored heights retain the existing semantics. Empty or
unsupported strokes produce a useful refusal with no command.

Raster decode and retained previous Undo images are bound to the initial project
file hashes. Native snapshot and post-serialization rechecks reject intervening
mutations. Before writing candidate files, the child records at most 16 generated
PNG hashes in a bounded request-owned marker. The parent retires only those known
paths after confirmed child exit. Existing directories, links, unknown files and
malformed/wrong-owner markers are preserved. The receiver also limits a terrain
transfer to 16 touched heightmap patches with distinct IDs, exact prior descriptors,
unique used PNG outputs and only their before/after mementos. A hash-valid malformed
transfer cannot insert provenance, target a different tile or repeat installation.

MapKit native sources, ABI, recipe and dependency pins are unchanged. Request and
state signatures, transfer decoding, immutable installation, cleanup, history and
UI callbacks still have synchronous costs. This is not a fixed frame-latency/RSS
or transaction guarantee against arbitrary external writers.

## Accepted macOS checks

Environment: macOS arm64, Godot 4.7.2.stable.mono.official.ed1daf0bf,
Python 3.12, synthetic fixtures only. Implementation start: MapEditor
`aa475c50f219fdf0391b7cf35615c5be921fb2be` on `main`.
The unchanged native library SHA-256 is
`f2c955aad0c0aee6c2ee71e2034bc4a70a917ee8f41e8216d234e376806ae6bf`.
The standalone runner copied public resources and used a separate verified
user-data directory per validator. No user dataset was read or deleted.

| Final accepted check | Result | Seconds |
| --- | --- | --- |
| Host PCK compile/export with loose product scripts hidden during execution | PASS | recorded by runner |
| `terrain_native_validator` in final reviewed PCK | 247 checks; no diagnostics | 12.597 |
| `authoring_validator` in PCK | 84 checks; no diagnostics | 4.137 |
| `authoring_safety_validator` in PCK | 25 checks; no diagnostics | 0.786 |
| Native-display `authoring_validator` | 86 checks; no diagnostics | 5.254 |

The terrain validator covers actual raster-plan and command-preparation barriers,
plan/native cancellation, deadline/EOF, stale ready results after save/gesture or
wrong owner, corrupt transfers and IPC faults, unknown scratch preservation,
source mutation during decode/prepare, one-time publication before reentrant
callbacks, preparation-free commit, exact binary replacement Undo/Redo, original
package preservation, four actual road/terrain cells and Editor-close reaping.
The subsequent independent review added hash-valid malformed transfers (duplicate
outputs/tiles, extra output, foreign cell, wrong prior descriptor and attribution)
and proved exact same-frame numeric/brush-option restoration still invalidates
the job through the UI callbacks' monotonic revision.
The authoring validator exercises real pointer strokes for raise/lower/flatten/
smooth, four-way seams, native generation, save/recover/export and the shared
asset/graph authoring paths. Native terrain and authoring captures were visually
inspected at 1440×900; the canvas, terrain labels, controls and status fit.

Reproduce from the standalone Editor root, selecting fresh log directories:

```sh
rtk proxy python3.12 scripts/check_documents.py --godot /path/to/Godot --import-python /path/to/import-python --script authoring_validator --script terrain_native_validator --script authoring_safety_validator --resource-pack --log-dir /new/terrain-pack
rtk proxy env MAPEDITOR_CAPTURE_PATH=/new/terrain-rendered/authoring.png python3.12 scripts/check_documents.py --godot /path/to/Godot --import-python /path/to/import-python --script authoring_validator --rendered --log-dir /new/terrain-rendered
```

The accepted run data is retained by the coordinating superproject handoff from
`/tmp/miniearthure-terrain-final-pack`, `/tmp/miniearthure-terrain-rendered` and
`/tmp/miniearthure-terrain-audit-final`. The first two preserve the authoring/safety
and display checks; the latter binds the final terrain transfer hardening to the
247-check PCK run. Unchanged authoring/display behavior was not retested solely
because the private terrain transfer received stricter shape checks.
The runner records exact command, source/native hashes, diagnostic scan, timing,
exit status and resource-pack artifact hash. Both copied projects and isolated
test data were retired by the runner; no validation process remains.

Earlier source runs passed 194 terrain checks and then exposed a diagnostic in
the concurrently added asset UI: its success branch eagerly evaluated an error
formatter. The asset owner fixed that call; the final PCK reran the failed
authoring validator first and passed. Those historical failure logs remain at
`/tmp/miniearthure-terrain-native`; a PASS print never overrode diagnostics.
After adding the actual raster-plan barrier, the final terrain test increased to
209 checks. Independent transfer/state review then passed 245 checks and added two
assertions proving restored option values are exactly equal while revisions differ;
the final reviewed PCK passes 247. No product failure occurred in those review runs.
Passed final checks are not repeated merely for documentation/commit.

## Remaining verification and human play notes

- Installed Windows/Linux builds require those operating systems, Godot 4.7.2
  export templates and matching native bindings. They cannot be established by
  this Mac PCK. Run the same validators plus exported pointer stroke → cancel →
  Undo/Redo → save/reopen/export. Require exact seams, preserved source bytes,
  one command and no orphaned child or owned scratch.
- A person should inspect brush responsiveness, progress/Cancel feedback, all
  four brush modes across seams and the resulting roads in the installed 3D
  preview/Client. Drive over edited edges, hills and road/terrain transitions;
  require continuous collision and no sinking/floating/visible seam. Scripted
  synthetic checks do not establish natural input usability or driving quality.
- Representative-map latency/RSS, real-region accuracy and final root integration
  with recursive clean clone remain the coordinating project's acceptance gates.
  They need licensed representative maps/hardware and the retained root commands;
  no large-map performance, release or cutover claim is made here.
