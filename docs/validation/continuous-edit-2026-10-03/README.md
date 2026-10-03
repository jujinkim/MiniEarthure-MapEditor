# Continuous editing and explicit operation locks — 2026-10-03

Implemented in MapEditor and shared MapKit GDScript; current own formats remain v1.
The [document contract](../../DOCUMENTS.md) and [performance report](../../TRACK_EDIT_PERFORMANCE.md)
describe current behavior. [Results](results.json) retain source/native hashes,
fixed fixture identity, all 18 commit samples and scoped validator outcomes.

The deterministic `continuous_edit_validator` passes 271 checks using held workers
and an injected clock.
It covers release display retention, A/B/A editing, stable-ID selection and current
snapping/attachment paths, coalescing without history merging, no-op/redo, deletion,
Undo/Redo, cancelled/stale/duplicate/session results, invalid drafts and correction,
200-command/16 MiB limits, reduced motion and the continuous 500 ms indicator timer.
It also checks immediate Save/export dim and direct API/command/pointer locks,
destination-picker locks, revision-targeted invalid Save errors, recovery while
unconfirmed, payload/adoption entrypoint locks, file failure,
cancellation before publication, successful publication winning a late cancellation,
external write conflicts and execution-only course validation.

Real workers pass the affected track/workbench/icon/assembled-track/history/recovery/
import/export/grind validators. Test-drive uses an injected process launcher; no real
Client was launched or driven. Shared progress and all 1,834 English/Korean/Japanese
catalog keys pass. Independent Editor startup and initial screen were rendered,
captured and inspected; there were no blocking load diagnostics.

The fixed seed-derived 49-piece probe uses the same source, derived fixture and
native binary as the earlier 557.715 ms result: 3 cycles, 18 commits, 90 drag samples.
This run has no request coalescing during timing; coalescing is tested separately.
Drag p95 1.062 ms, synchronous draft submission/display-state update p95 42.074 ms,
main maximum 42.074 ms and frame gap maximum 64.020 ms are within the applicable
16.7 ms drag / under-100 ms main goals. Completion p95 **532.745 ms fails 500 ms**.
The old 557.715 ms miss remains historical evidence, not a closed acceptance item.
Rendered event-to-photon latency and detailed interaction/platform acceptance were
not measured. No native source, dependency, ABI or build setting changed; the valid
installed native build was reused.

During implementation, an accidental source insertion caused a parser failure;
a nullable missing metadata lookup caused strict diagnostics; both were corrected.
Export's old test setup clicked a hidden track-workspace button, and several old
assertions required failed edits to vanish or allowed editing during explicit export.
The fixtures now use the owning workspace/API and the approved retention/lock contract.
A deferred UI decorator referencing already-freed controls was corrected to resolve
instance IDs at consumption. The final affected runs pass with strict diagnostics.
These preliminary failures are distinct from the remaining 500 ms target miss.

Raw task logs, isolated data and the startup capture remain local in the integration
workspace's `docs/tasks/runs/editor-continuous-edit/`; they are not repository inputs
or committed artifacts. Detailed mouse/keyboard, long editing, platform/filesystem
and actual Client acceptance belong to the user. No full suite, clean-clone,
export matrix, prolonged benchmark or CI automation was run or added.
