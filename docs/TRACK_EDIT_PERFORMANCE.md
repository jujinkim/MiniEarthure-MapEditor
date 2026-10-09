# Responsive road and track editing

## Drafts and operation ownership

Road/track edits retain the current document and its landscape. Automatic
validation permits continuous source drafts. Release records one Undo
command immediately; a single running worker plus the latest pending snapshot
coalesces calculation. Only a matching document session, revision, request ID and
command epoch may install once. Failure, cancellation, supersession and a replaced
document cannot publish stale results or change the source/history. Shutdown
cancels and joins the owned worker. [Document contract](DOCUMENTS.md).

Save, Save As and export freeze the submitted revision and lock edit entrypoints
through validation/publication; failure retains the draft. Selection and camera
navigation remain independent of content-derived map IDs. History stores changed
record/scalar fields, including road design, overlay source and shared surface
attachments, within the existing 200-command / 16 MiB serialized budget. A road
edit and its derived terrain, connections and attachments form one Undo unit.
Original terrain PNGs and unrelated document collections are not history copies.

Moving a selected track piece reuses its meshes and owned attachment ghost. The
original grab offset/full orientation are retained, pointer updates coalesce to
the latest frame, and release samples its final position. Self ports are excluded;
a snap releases outside its range. Escape, focus loss, tool/view changes, popups
and camera gestures cancel without editing. A stationary click is a no-op.
Selection changes materials and inspector state without recompiling geometry.

MapKit prepares immutable preview arrays away from the scene thread and reuses
unchanged signatures. Road/landscape preview uses `road_preview_job.gd`: a
camera-centred 3 × 3 window of 32 m cells, original height payloads and real assets.
Stale sessions/camera requests are discarded; replacement remains hidden until
ready. Scene installation yields after its 3 ms frame slice. Picking is bounded
to 40,000 triangles. Source and asset admission retain their existing limits;
preview resources retire with their owners. Special-piece templates are bounded
to 24 entries. These bounds are not a device frame-rate guarantee.

## Current latency issue

The last measured fixed seed-derived 49-piece completion p95 is **532.745 ms**,
above the **500 ms** target. This road/composite change did not repeat the
performance benchmark, so these values are prior evidence, not measurements of
its new compiler or terrain preview.

| Metric | Last measured result | Target/status |
| --- | ---: | --- |
| Drag p95 | 1.062 ms | ≤16.7 ms, passed in measured scope |
| Draft submission/display state p95 | 42.074 ms | Event-to-photon not measured |
| Main admission/application maximum | 42.074 ms | <100 ms, passed in measured scope |
| Frame interval maximum | 64.020 ms | <100 ms, passed in measured scope |
| Validation/preview completion p95 | **532.745 ms** | ≤500 ms, failed |

The 2026-10-03 diagnostic used Apple M1/macOS ARM64, Godot 4.7.2, optimized debug
native, three quiet cycles, 18 commits, 90 drag samples and nearest-rank p95.
Its native SHA was
`2a640fbf5955d4faa45666abcb6037b86c73cdf8347f01b41a11e4e62e5c7dc9`;
derived source SHA was
`3a45dc5e06d0aae703efc2a1e6102921b0735901437ec14a074b00025d827ea5`.
Worker document preparation was 239.804–253.494 ms and preview preparation
185.529–196.767 ms. Nonblocking drafts do not establish completion-target or
interactive/device acceptance.

The [fixed source](../tests/fixtures/track_bench_seed42_90s.json) and
[provenance](../tests/fixtures/track_bench_seed42_90s.provenance.json) remain the
reproducible benchmark input. It contains 48 original pieces of 19 preset kinds;
the benchmark derives the 49-piece case without new random generation.

```sh
rtk proxy env TRACK_BENCH_SOURCE=/absolute/map-editor/tests/fixtures/track_bench_seed42_90s.json TRACK_BENCH_ONLY_49=1 TRACK_BENCH_EDITOR_REVISION=EDITOR_SHA TRACK_BENCH_MAPKIT_REVISION=MAPKIT_SHA .venv/bin/python scripts/run_godot_checks.py --project editor --script track_edit_benchmark --import-cache /tmp/track-edit-fixed-cache --log-dir /tmp/track-edit-fixed-results --strict-diagnostics
```

`TRACK_BENCH_PROBE=1` is a single-cycle diagnosis, not final p95 evidence.
`TRACK_BENCH_SAVE_SOURCE` writes only to a new path. Keep test data isolated from
user projects; this benchmark is not an automatic delivery gate.

## Affected verification

Strict `composite_road_validator`, `track_workbench_validator` and
`document_history_validator` pass with the current native build. They cover
ordinary roads and overlay edits, shared attachments, restoration, bounded
history, save/reopen, failed/cancelled publication, late-document rejection and
preview mesh reuse. Existing held-worker tests cover continuous draft coalescing
and explicit publication locks; previously measured timing does not replace those
functional assertions. General asset gizmos and detailed mouse/keyboard use,
long editing sessions, OS focus and platform acceptance remain user work.

Implementation/native contracts are in MapKit's
[track authoring](https://github.com/jujinkim/MiniEarthure-MapKit/blob/main/docs/TRACK_AUTHORING.md)
and Editor's [world authoring](ARCADE_WORLD.md). All own formats remain v1;
no automatic source converter or old execution fallback is introduced.
