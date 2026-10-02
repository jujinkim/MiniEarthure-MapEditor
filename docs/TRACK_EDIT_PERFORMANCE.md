# Responsive Track Mode editing

## Fixed-input latency improvement — 2026-10-03

MapKit now prepares connected-road clipping planes once per piece, the opposite
branch once per path, and reuses ribbon edges, outward offsets and rotation
bases. The sequential worker, full external validation, request/session/epoch
checks, exact-once installation, selection and Undo contracts are unchanged.
The 49-piece commit p95 improved **728.987 → 557.715 ms (23.5%)**, but the
**500 ms completion target remains failed**. Drag and main responsiveness pass
within the measured scope; this is not detailed interactive/platform acceptance.

The [fixed synthetic source](../tests/fixtures/track_bench_seed42_90s.json) is the
current seed 42 / 90-second authoring source: **48 pieces, 19 preset kinds**.
[Provenance and shape counts](../tests/fixtures/track_bench_seed42_90s.provenance.json)
identify its generator. File SHA256 is
`05bd86f917026f3dacf130c8d3d36cc4233ae4b415a94631ab4f5df4dd2508a4`;
canonical Godot source SHA256 is
`729a30de280782a70d76e34f77ab10c98e7e64f44def357e1f049d83df91df52`.
The old 2026-10-01 input had 20 pieces: no speedup is calculated against 977 ms.

`TRACK_BENCH_SOURCE` loads the fixed input without running generation. The probe
prints source/file hashes, piece/preset counts, Editor/MapKit revision labels and
the loaded native library SHA. Every derived fixture hash matched before/after;
the edit sequence was unchanged. Each of six cases ran once before and once
after: three cycles, 18 commits, three selections and 90 drag samples. p95 uses
nearest rank. No profiling, concurrent builds or other validation ran during
these timing samples. This small headless sample is a diagnostic, not a rendered
or statistical acceptance claim.

Platform: Apple M1/macOS arm64, Godot 4.7.2 Mono, optimized debug native.
Baseline Editor `ff11682c` plus the fixed-input harness, MapKit `930ee37b`;
after uses the same Editor product code/harness and MapKit `425d67b02675e191f4e786ed14cf1a5d791e7d1b`.
Native SHA256 before/after:
`0c7b037745e3d095fed6cd63a6894adc182ad5bb35b6d2b823ef5e1dc7d6e499` /
`2a640fbf5955d4faa45666abcb6037b86c73cdf8347f01b41a11e4e62e5c7dc9`.

| Fixture | Pieces | Before commit p95 | After commit p95 | After drag p95 | After main max | After frame gap max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual straight | 10 | 77.420 ms | 71.081 ms | 0.578 ms | 18.663 ms | 27.033 ms |
| Manual straight | 25 | 143.978 ms | 128.172 ms | 0.611 ms | 19.694 ms | 29.511 ms |
| Manual straight | 49 | 255.157 ms | 215.746 ms | 0.674 ms | 21.979 ms | 33.425 ms |
| Fixed seed-derived | 10 | 126.377 ms | 120.728 ms | 0.579 ms | 19.817 ms | 28.705 ms |
| Fixed seed-derived | 25 | 558.067 ms | 392.706 ms | 0.893 ms | 26.511 ms | 40.322 ms |
| Fixed seed-derived | 49 | 728.987 ms | **557.715 ms** | 0.966 ms | 33.956 ms | 51.028 ms |

Main max separates admission/application from worker completion. Frame gaps
include deferred inspector work and scene retirement. Before the change, one
49-piece delete recorded **271.085 ms** despite a 22.019 ms main application;
that observed baseline failure is retained, with no unsupported causal claim.
All after frame gaps are below 100 ms; all drag p95 values are below 16.7 ms.

Remaining 49-piece costs (three samples per operation; worker columns are ranges):

| Operation | Before complete p95 | After complete p95 | After document preparation | After preview preparation |
| --- | ---: | ---: | ---: | ---: |
| Move | 717.031 ms | 540.620 ms | 291.515–295.361 ms | 189.531–195.714 ms |
| Add | 722.308 ms | 549.307 ms | 288.274–294.177 ms | 193.884–195.590 ms |
| Property | 722.327 ms | 549.816 ms | 291.109–297.085 ms | 195.007–197.206 ms |
| Delete | 707.720 ms | 533.911 ms | 289.875–293.681 ms | 192.684–194.031 ms |
| Undo | 727.914 ms | 557.715 ms | 299.476–301.715 ms | 194.688–195.915 ms |
| Redo | 728.987 ms | 550.203 ms | 300.557–303.804 ms | 192.881–193.270 ms |

Document preparation remains the largest measured worker stage. No request-level
incremental compiler cache was added and no remaining substage is claimed from
unmeasured profiling. Targets, tolerances, assertions and budget limits were not
relaxed. Raw logs and per-operation samples remain local in the integration
workspace's `docs/tasks/runs/editor-latency-20261003/`.

Strict affected validators pass: `track_edit_validator` (100 assertions),
`track_workbench_validator`, `icon_workbench_validator`, `assembled_track_validator`,
`document_history_validator`, `document_recovery_validator`, and
`import_command_validator`. This covers busy rejection, cancellation/failure/late
results, exact-once/session/epoch handling, selection, Undo/Redo and save/reopen.
MapKit's 35 affected native tests, geometry golden and build are recorded in its
[preparation contract](https://github.com/jujinkim/MiniEarthure-MapKit/blob/main/docs/TRACK_AUTHORING.md#piece-local-wall-preparation--2026-10-03).

The active practice example was recompiled from its preserved `source.json`
(SHA256 `c16366805ec603db9eabb38d42f9ac13acd4e5a409b836ff02dc21c5c84b12a5`).
Its new package/entry SHA256 is
`8de012b0c189449c14f8f6826c178904497f480ae2f8c87a8985407e0d039727`.
Only seven document fingerprint/derived identity fields differ; all authored
geometry, courses, samples, 8 m widths and 6 m radii remain identical. Original
packages are preserved locally and in Git history. CLI package validation and
strict `practice_source_validator` source extraction/save/reopen pass. The Editor
standalone initial screen was captured and visually inspected with no blocking
diagnostics. Human completion remains unverified. An initial comparison assertion
incorrectly included the expected changed generator fingerprint; comparison was
corrected to enumerate the seven identity fields, without changing product code
or any geometry assertion.

Reproduce the bounded timing run from the integration workspace:

```sh
rtk proxy env TRACK_BENCH_SOURCE=/absolute/map-editor/tests/fixtures/track_bench_seed42_90s.json TRACK_BENCH_EDITOR_REVISION=EDITOR_SHA TRACK_BENCH_MAPKIT_REVISION=MAPKIT_SHA .venv/bin/python scripts/run_godot_checks.py --project editor --script track_edit_benchmark --import-cache /tmp/track-edit-fixed-cache --log-dir /tmp/track-edit-fixed-results --strict-diagnostics
```

`TRACK_BENCH_SAVE_SOURCE` writes a newly generated synthetic source only to a new
path and exits; existing files are rejected. `TRACK_BENCH_PROBE=1` remains a
single-cycle diagnosis, never the final p95 evidence.

## Previous delivery — 2026-10-01

Implementation and affected automated checks are complete. The 500 ms commit
completion target is **not met for the 49-piece seed-derived fixture**. Detailed
mouse/keyboard use, long editing sessions, OS focus and device acceptance remain
user verification. No format version, user data or original history was changed.

## Interaction and ownership

Existing pieces now use the placement solver while dragging: the original grab
offset/elevation, current full orientation and the existing 3 m entry-to-exit rule
are retained; the dragged piece is excluded. Moving out of range releases the
snap. A drag hides only the original piece and its owned action/obstacle visuals,
then transforms a translucent copy of their existing meshes. Floor/supports stay
in place until commit. The entry/exit and snapped port guides reuse their node
and mesh. Pointer events retain only the latest position each frame, and release
samples its own position before submitting exactly one command. A stationary
click or return to the press point is a no-op. Escape, focus loss, tool/view
changes and popups restore the originals without editing. Camera gestures also
cancel an unfinished move. Other pieces and route ordering never move implicitly.

Selection changes materials and one property panel; they do not compile or
recreate the track preview. Inspector button creation updates the new control
instead of rescanning the whole command registry for every button. Successful
edits trigger one document refresh. Camera and plan navigation use the document
session identity, so content-derived `map_id` changes do not reset them.

Track add/move/properties/delete and UI Undo/Redo submit one immutable request to
`track_edit_job.gd`. Its thread creates an independent store/MapKit bridge,
prepares validation, history and preview data, then publishes on the main thread.
Only a matching store/session, command epoch and request ID may install once.
Failed, cancelled, superseded and already-consumed responses cannot alter the
live document or either history stack. Cancellation uses a native work token and
checks between preview objects. Shutdown cancels and joins the owned worker.

Commits are sequential. A second edit/save/export is disabled and rejected, never
queued. Camera and selection remain usable; a selection made during work wins over
the submitted selection. The running-operation Cancel button cancels preparation.
Autosave defers until the committed document is available. The shared 200-command /
16 MiB serialized Undo budget and full source/compiled/course mementos remain.
Whole-document command preparation avoids repeated JSON copies and before-state
signatures. Ordinary external/native document validation is retained.

MapKit's shared preview separates worker-safe arrays/normals/poses from scene
application. It retains immutable preparation for unchanged gimmicks and only
replaces objects whose prepared signature changed. Dragging reuses those meshes.
Cold new-tool previews still prepare an isolated single-piece template; they do
not compile the edited document. Templates are bounded to 24 entries.

## Timing evidence

[Raw samples and summary](validation/track-edit-2026-10-01/results.json) retain
per-operation before/after data for selection, move, add, properties, delete,
Undo/Redo, placement and drag. Platform: Apple M1, macOS arm64, Godot 4.7.2 stable
mono, optimized native debug builds. Baseline Editor was
`3eff622b07201d84217ad09f521a75759d46c0be`, MapKit
`ccead3e31ec469f5fde93103b369d7a2a8f29c8e`; the old source was read into an isolated
project, with its original installed native library. No checkout was rolled back.

Each size/fixture has three edit cycles (18 commits, three selections and 90 drag
updates). p95 is nearest rank; this small sample is a diagnostic, not a statistical
or rendered acceptance claim. The extra baseline seed probe shared CPU time with
other checks, so no exact speedup factor is claimed. The original quiet all-straight
baseline had 49-piece selection around 87 ms and add around 387–388 ms.

Manual controls are connected straight roads. Seed controls use actual seed 42 /
90-second source (20 pieces), cropped to 10 or extended to 25/49 with isolated,
translated copies of those seed shapes/heights. Original seed settings and grounded
support policy remain. These fixtures include large swept/curved gimmicks and
supports, but do not represent all user maps.

| Fixture | Pieces | Before selection p95 | After selection p95 | Before commit p95 | After commit p95 | After drag p95 | Main block max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual | 10 | 65.0 ms | 10.7 ms | 237.6 ms | 53.1 ms | 0.42 ms | 15.9 ms |
| Manual | 25 | 116.8 ms | 10.9 ms | 884.5 ms | 82.9 ms | 0.45 ms | 17.1 ms |
| Manual | 49 | 119.3 ms | 12.3 ms | 955.2 ms | 135.1 ms | 0.50 ms | 19.2 ms |
| Seed-derived | 10 | 310.7 ms | 11.1 ms | 987.9 ms | 135.7 ms | 0.43 ms | 17.3 ms |
| Seed-derived | 25 | 435.9 ms | 14.6 ms | 1918.1 ms | 490.4 ms | 0.49 ms | 23.8 ms |
| Seed-derived | 49 | 725.9 ms | 16.2 ms | 3423.9 ms | **977.3 ms** | 0.55 ms | 33.5 ms |

Main block max covers admission and result installation (including document-change
listeners). A separate 49-piece event-loop probe includes deferred inspector work
and node retirement: maximum frame interval **43.870 ms**, under 100 ms. Drag p95
is under 16.7 ms. The old implementation had no moving-piece preview, so no before
drag response was invented. Selection/drag regressions assert zero whole-preview
preparations and mesh creations; a drag does not enter the source compiler.

The remaining 49-piece miss is worker time: document preparation about 589–625 ms
and shared preview preparation about 285–291 ms. The first worker version took
about 1.6 s; immutable gimmick reuse reduced it to the recorded result. Further
incremental compiler/grounding work would need a separate dependency-invalidation
change with equivalent geometry and clearance validation; that is not claimed here.

## Automated checks and limitations

- `track_edit_validator` (100 assertions): real-time snap/self exclusion/release/no-op, grab offset,
  owned ghost visuals, per-frame coalescing, latest release, one Undo and budget,
  neighbouring pieces/routes retained, all cancellation routes, busy admission,
  selection during work, exact-once/stale request/epoch/session handling, failure,
  immutable inputs, reused/fresh preview equality, save/reopen/recovery and shutdown.
- `track_workbench_validator`, `icon_workbench_validator`,
  `assembled_track_validator`, `document_history_validator`,
  `document_recovery_validator`, `import_command_validator`: passed with strict
  diagnostics. Existing synchronous store APIs remain available to import/tests;
  interactive Track Mode uses the worker path.
- MapKit native build, compiler-cache equivalence/tamper/cancellation unit test,
  eight completed core track-authoring tests and three focused package tests passed.
  The 42-combination generation matrix was stopped after several minutes because
  it exceeded this edit-focused scope; the whole test binary is not reported passed.
- An initial unfiltered Rust test discovery hit a pre-existing `tests/water.rs:22`
  initializer missing `contact_class` / `snow_retention_percent`. Focused library
  and track targets compile and pass; unrelated water code was not changed.
  This historical compile failure was repaired on 2026-10-03 in MapKit; the three
  core water tests now pass. [MapKit fixture-repair record](https://github.com/jujinkim/MiniEarthure-MapKit/blob/930ee37b5760c4883e439643ef5d106382ef334c/docs/validation/test-failures-2026-10-03/README.md).
  [Restored Editor validators](validation/test-failures-2026-10-03/README.md) are separate; it does not remeasure track-edit latency.
- Corrected test setup failures: canonical JSON numeric types in the new source
  comparison; optional empty `courses`; seed fixture length (20, not 49); the import
  validator required `MAPEDITOR_TEST_IMPORT_PYTHON` pointing to the development venv.
  These are recorded separately from product failures.

Logs and native hashes are in [the evidence directory](validation/track-edit-2026-10-01/).
The standalone initial-screen check is recorded there. Detailed actual editing,
visual snapping feel and long-session acceptance belong to the user. No full
bootstrap, clean-clone, export matrix, detailed Client or prolonged driving test
was run. Native code changes require rebuilding installed native binaries; no
compatibility fallback or old file converter was added.

Reproduce from the integration workspace (using an isolated import cache):

```sh
rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --script track_edit_validator --script track_workbench_validator --script icon_workbench_validator --script assembled_track_validator --import-cache /tmp/track-edit-cache --log-dir /tmp/track-edit-checks --strict-diagnostics
rtk proxy env TRACK_BENCH_SEED=1 .venv/bin/python scripts/run_godot_checks.py --project editor --script track_edit_benchmark --import-cache /tmp/track-edit-cache --reuse-import --log-dir /tmp/track-edit-timing --strict-diagnostics
```

`TRACK_BENCH_PROBE=1` selects one 49-piece seed cycle with frame-gap and worker-stage
measurements. Keep validation data separate from user projects. Delivery follows
MapKit → its Runtime/Editor consumers → Client/Host nested Runtime → root pins on
`main`; exact revisions are recorded by the parent gitlinks and compatibility lock.
