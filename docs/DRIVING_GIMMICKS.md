# Driving structure authoring

The focused Gimmicks panel selects a library template or existing stable ID and
edits XYZ, yaw, period/phase, displacement, impulse and landing margin. Its time
slider previews shared MapKit poses and full safety bounds. Save validates through
the native current-v1 document contract; editing the same ID replaces that record.
Delete, save, undo and redo use the document store. Ordinary cell previews show
all authored structures; the selected time preview temporarily replaces its static
preview. Per-cell display work includes the declared gimmick allowance.

This is a bounded property panel, not a replacement for the full Editor UI.
Executable scripts are not supported. General 3D gizmos and the broader asset/
collision editing workflow remain separate work.

`tests/gimmick_authoring_validator.gd` passed property mutation, native save,
stable-ID replacement, time/bounds preview, ordinary cell preview and undo/redo.
`tests/test_compact_maps.py` passed deterministic creation of the seven new maps
in [compact-driving](../examples/compact-driving/README.md). Godot import/load
passed. Actual interactive editing and driving acceptance remain user checks.
