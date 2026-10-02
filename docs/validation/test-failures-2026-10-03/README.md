# Authoring validator repair — 2026-10-03

Starting Editor `961f5e284f3d59c266045343df5851a5bf2062a7`, MapKit
`e563b8d1d4e2bc4278419627d2fe0bcbb73d9c03`. [Source/native hashes](sources.json)
identify the tested sources in the commit adding this report. Godot 4.7.2 Mono,
macOS arm64 / Apple M1. Production Editor/MapKit code and v1 formats are unchanged.

| Check | Reproduced cause | Final correction and evidence |
| --- | --- | --- |
| `palette_entry_validator` | [Before](palette-before/editor-palette_entry_validator.log.gz): `ramp_low` preview failed. The test started the next tool before the first asynchronous placement completed. The old short straight also could not support every obstacle's clearance/width/corner requirements. | Wait for owned placement completion and expected piece count. Use a wide approach and a separate corner, and verify actual obstacle geometry in cached previews, immutable document/history, ray mapping and no duplicate placement. [Strict PASS](palette-geometry/editor-palette_entry_validator.log.gz). |
| `authoring_validator` | [Before](authoring-before/editor-authoring_validator.log.gz): old default cell-size before-value conflicted; obsolete button/hidden-tab access assumed general authoring at startup. | Explicit free-roam document, current before-values, Create/New Map commands, authoring page picker and icon action metadata. Use the 2D workspace for shape gestures, then split view for preview. [Strict PASS, 138 checks](authoring-workspace/editor-authoring_validator.log.gz). |
| `course_authoring_validator` | [Diagnostic](course-diagnostic/editor-course_authoring_validator.log.gz): `E_CHECKPOINT`, because the old fixture positions were outside the new empty track's derived bounds. Unverified-course saving itself was not prohibited. | Explicit free-roam fixture; report actual panel errors on failure. [Strict PASS](course-after/editor-course_authoring_validator.log.gz): unverified course, draft/map Undo/Redo, native reload, opaque evidence import and Save As payload preservation. |
| `import_review_validator` | [Diagnostic](import-diagnostic/editor-import_review_validator.log.gz): native export returned `E_TRACK_DRAFT` for the default unfinished track, not a provenance-validation failure. | Explicit free-roam fixture and full native failure details. [Strict PASS, 51 checks](import-after/editor-import_review_validator.log.gz): exact provenance, bounded pages, stale scans/requests, atomic adoption, Undo/Redo, export and cancellation. |

The authoring check also retains stale-before rejection, immutable raster/asset
payloads, shared seams, history byte charging, cancel/late release, focus-loss
cancellation, invalid seams/proxies, original-file preservation, recovery, native
export/reopen and asynchronous asset completion. No persistence, revision guard,
worker deadline or provenance-validation product code was loosened.

Intermediate evidence is retained. [Authoring dispatch](authoring-dispatch/editor-authoring_validator.log.gz)
showed the default track layout leaving a 100 px navigation canvas: two bridge
points only 3.9 px apart snapped to the same existing endpoint. Selecting the
current 2D authoring workspace fixes the fixture without changing snap behavior.
The earlier `authoring-after`/`authoring-layout` runs remained failed; only
`authoring-workspace` is final.

`palette-after` passed the old shallow preview checks, so final coverage was
strengthened to require obstacle meshes. Two exploratory negative checks in
`palette-final`/`palette-verified` incorrectly expected an unsafe attachment to
reject preview creation. The current compiler preserves such a draft, emits a
clearance issue and omits unsafe obstacle geometry. The final test asserts that
contract, uses appropriate positive fixtures, and passes in `palette-geometry`.
It does not claim that a preview certifies execution eligibility.

From the superproject, run one script per invocation (in the table's order):

```sh
rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --script palette_entry_validator --import-cache /tmp/miniearthure-failure-repair-20261003-editor --log-dir /tmp/palette-repair-run --strict-diagnostics
rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --script authoring_validator --reuse-import --import-cache /tmp/miniearthure-failure-repair-20261003-editor --log-dir /tmp/authoring-repair-run --strict-diagnostics
```

Substitute `course_authoring_validator` or `import_review_validator` and a fresh
log directory for the remaining checks. Adjacent JSON records exact engine
commands, durations, exit codes and diagnostics. The initial import and all final
behavioral runs are clean. Only GDScript tests changed, so subsequent runs reused
the isolated import cache and existing native libraries. Each run had its own
temporary user directory and synthetic fixtures.

[10-01 failures](../localization-2026-10-01/README.md#known-failures-preserved-separately)
remain historical evidence. No full suite, performance rerun, detailed authoring,
driving or platform/export acceptance was performed. Editor product code did not
change, so no new standalone Editor launch was required.

Raw logs are gzip-compressed without altering their bytes; original local run logs remain retained.
