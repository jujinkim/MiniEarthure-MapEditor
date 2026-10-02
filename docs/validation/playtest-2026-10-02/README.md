# Practice revision — 2026-10-02

MapKit fe399d7, root Python3.12 venv, macOS Godot4.7.2 Mono.
Three [Python tests](practice-source-tests.log) PASS: dimensions, real end walls,
ordered checkpoints, manual flight/beam, new-directory-only generation, two
byte-identical exports, package verification and no human completion evidence.
[Editor source validator](editor/editor-practice_source_validator.log) PASS: unpack,
open, recompile, save/reopen and exact editable-source identity.
The initial coordinate assertion used scene Z rather than source Z; corrected
test passed without changing geometry.

Package SHA256 at this validation `12b0bdbaf2bbbb4b44b81c3e9786683a1217b242ed16857d99c626a9b5512373`. Bundled consumer entry/hash equality verified.
Consumer physics/progression results belong to its owning repository.
No public source contains private consumer code or user datasets.
The [2026-10-03 regeneration attempt](../../ASSEMBLED_TRACKS.md#wall-generation-pin-and-bundled-practice-refresh--2026-10-03)
failed on stored action samples and freshly generated corner clearance. The passes
above retain their original source/package scope; they are not a current refresh pass.
Human completion remains unverified; device/editor interaction is unperformed.
