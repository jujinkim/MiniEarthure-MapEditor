# Responsive road and track editing

Draft, worker and publication ownership is defined in [DOCUMENTS](DOCUMENTS.md).
Moving a selected piece reuses its meshes and attachment ghost; pointer updates
coalesce to the latest frame and release samples the final position. Escape, focus
loss, tool/view changes, popups and camera gestures cancel without editing.

Road/landscape preview (`road_preview_job.gd`) uses a camera-centred 3 × 3 window of
32 m cells with original height payloads and real assets. Stale requests are
discarded, scene installation yields after 3 ms per frame, picking is bounded to
40,000 triangles (later cells are not pickable, with a warning) and special-piece
templates to 24; display resources above 128 MiB warn. These are not frame-rate
guarantees.

## Current latency issue

The fixed seed-derived 49-piece completion p95 missed its target on the previous
fixture (not yet re-measured on the Medium fixture below):

| Metric | Last measured | Target/status |
| --- | ---: | --- |
| Drag p95 | 1.062 ms | ≤16.7 ms, passed |
| Main admission/application max | 42.074 ms | <100 ms, passed |
| Frame interval max | 64.020 ms | <100 ms, passed |
| Validation/preview completion p95 | **532.745 ms** | ≤500 ms, **failed** |

## Benchmark

The [fixed source](../tests/fixtures/track_bench_seed42_medium.json) and its
[provenance](../tests/fixtures/track_bench_seed42_medium.provenance.json) contain 84
pieces (catalogue defaults, seed 42, Medium); the benchmark crops the 49-piece case.

```sh
rtk proxy env TRACK_BENCH_SOURCE=/absolute/map-editor/tests/fixtures/track_bench_seed42_medium.json TRACK_BENCH_ONLY_49=1 TRACK_BENCH_EDITOR_REVISION=EDITOR_SHA TRACK_BENCH_MAPKIT_REVISION=MAPKIT_SHA .venv/bin/python scripts/run_godot_checks.py --project editor --script track_edit_benchmark --import-cache /tmp/track-edit-fixed-cache --log-dir /tmp/track-edit-fixed-results --strict-diagnostics
```

`TRACK_BENCH_PROBE=1` runs one diagnostic cycle; `TRACK_BENCH_SAVE_SOURCE` writes
only to a new path. The benchmark is not a delivery gate. Functional coverage is
in `composite_road_validator`, `track_workbench_validator` and
`document_history_validator`.
