# Partial panels (02/07) — 2026-10-04

Godot 4.7.2 macOS arm64, isolated user data. `track_workbench_validator` and
`track_edit_validator` pass strict diagnostics. The checks cover default50/center,
existing attachment25/right, shared preview, cancellation, Undo/Redo, save/reopen,
exact regenerated geometry, stale work and existing editing safety.

Action ghosts retain only the attachment meshes; connected roads contribute
support to fitting but are not retained as extra ghost road copies. The shared
marking remains visible while placing the panel.

Development fixture failures were corrected: redo validation must settle before
saving, and reopened JSON numbers need normalized comparison. An additional
run encountered texture import remaps from a different owning-source project;
refreshing the isolated Editor import repaired it and both final checks passed.
No detailed interactive/device or driving acceptance was performed.
