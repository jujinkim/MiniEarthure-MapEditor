# Responsive Track Mode editing — 2026-10-01

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
