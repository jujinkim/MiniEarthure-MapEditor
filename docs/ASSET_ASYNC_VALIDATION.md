# Asynchronous asset authoring — 2026-09-10

## Execution and ownership

Assets → Apply starts one owned Godot child for static GLB/PNG/WebP and proxy or
material edits. Original source and existing project payloads are inspected and
hashed before native work. The child captures immutable candidate bytes, checks
the detached document with MapKit, prepares the complete canonical attribution
and binary/text command, serializes the transfer, and rechecks all inputs.
Metadata-only edits use existing immutable bytes and the same native checks.
Previously loaded bridges, source files, packages and live history stay intact.

The parent binds the result to the exact store instance, command epoch, document,
project and authoring selection/revision. Changing and restoring a field in one
frame still cancels the pending result. Asset selection, layer changes, close,
new gestures, save and document replacement also invalidate it. Progress and
Cancel remain in the authoring window; the existing supervisor enforces a
120-second deadline, parent EOF termination, strict IPC, child exit and reaping.
Only after successful validation does the parent install an immutable file and
publish one prepared command, consumed before `changed` callbacks. Undo/Redo
retains the exact old and new bytes. Failed validation has no document command.

An asset job accepts only asset/attribution prepared patches, one matching asset
ID and at most one new content-addressed GLB/PNG/WebP payload. Existing vector
command decoding keeps its previous field restrictions. The source is limited
by the 16 MiB shared text+binary history budget; candidate/existing payload groups
remain 64 MiB, request/transfer 24 MiB and history 200 commands. Static asset/native
limits and MapKit versions are unchanged. Native document/file validation is used;
this operation does not claim new generated-cell or rendering coverage.

Before candidate writes, the child registers its dynamic output path in a small
request-owned marker. Cleanup retires known paths only after confirmed exit.
Existing directories, links, unknown files and malformed/wrong-owner markers
remain protected. No user recovery directory is silently adopted or deleted.

`AuthoringTools.asset()` retains its synchronous API for script callers. Request
signatures, transfer decoding, immutable installation, history mutation, cleanup
and UI signals still have synchronous costs. Native preparation is killable;
this does not promise a fixed UI frame time, whole-process RSS cap or a filesystem
transaction against arbitrary external writers. No engine/ABI/recipe changes.

## Accepted checks

macOS arm64 / Godot 4.7.2.stable.mono.official.ed1daf0bf / Python 3.12. Synthetic
fixtures only. The independent runner copies public Editor/MapKit resources and
verifies distinct user-data directories. The existing native binding is reused.

- Compiled host PCK export and execution with loose product scripts/main hidden
  pass. `asset_native_validator`: 168 checks, 8.744 s, no diagnostics.
- Actual prepare cancellation/deadline/EOF/source change, ready-result cancel/save/
  owner/gesture guards, IPC corruption/stale/flood/crash, malformed transfer,
  missing executable, source/request limits and unknown scratch preservation pass.
- Preparation-free parent installation, reentrant/duplicate publication refusal,
  exact binary replacement Undo/Redo, metadata-only edit, invalid proxy, prior
  payload changes, save/reopen/package preservation and UI close/option restoration
  pass. Existing `authoring_validator` verifies pointer Apply and invalid JSON.
- Shared final-command (97), PNG native (244), DEM native (212), document history
  (571), recovery (60), import recovery (141) and scratch validators pass in the
  same PCK with no diagnostics. Native-display authoring checks also pass.

The first run found an asset UI success branch passing a successful result to
the error formatter; the branch is corrected. The validator's initial expectation
that saving changed the previously loaded bridge was also corrected to the
preservation contract. Failed logs and subsequent accepted runs are retained by
the coordinating handoff; an exit code or PASS print alone did not mask diagnostics.

Reproduce from the standalone Editor root with a fresh log directory:

```sh
rtk proxy python3.12 scripts/check_documents.py --godot /path/to/Godot --import-python /path/to/import-python --script asset_native_validator --script import_command_validator --script heightmap_native_validator --script dem_native_validator --script document_history_validator --script document_recovery_validator --script import_scratch_validator --script import_recovery_validator --resource-pack --log-dir /new/asset-pack
```

The accepted runner output originated at
`/tmp/miniearthure-remaining-asset-final-pack`; source hashes, exact commands,
exit/diagnostic/timing results and PCK hash are retained in the coordinating
superproject report. Temporary copied projects/test data are retired by the
runner. Native source/dependencies/ABI are unchanged, so unrelated Rust suites
were not rerun.

## Deferred verification and human notes

Windows/Linux installed builds need matching native bindings, Godot 4.7.2 export
templates and target OS runners. This Mac host PCK is not their distribution gate.
Run the same checks there and use the actual file picker → Apply → Cancel/retry →
Undo/Redo → save/reopen → export. Source/project changes must refuse publication,
and cancellation/closing must leave no owned process or known scratch.

A person should inspect progress and cancellation responsiveness, material/proxy
editing, original licenses and the same asset's appearance in Editor and installed
Client. Drive against edited collision proxies to confirm expected contact and
camera occlusion. Synthetic checks do not establish natural usability or driving
quality. Representative-map latency/RSS, installed-platform/final integration and
explicit player acceptance remain separate gates; no final release/cutover claim.
