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

Quarterpipe inner-face roles now come from the pinned MapKit current-v1 source,
using the shared renderer/resolver. Initial-screen validation locates visible
Driving tools by the selected tab, rather than assuming the first registered
command is visible; the new Grind Line command belongs to the Gimmick tab.

2026-10-04 pipe replacement (03/08): new standalone cylinders use a 2.5m bore and
16m body, with `#596168` / roughness0.82 / metallic0.65 / no emission from MapKit.
Radius input starts at0.50m and keeps centimetre values. Existing sizes/colours
are never converted. Loops and halfpipes are unchanged. See the scoped
[authoring results](TRACK_AUTHORING.md#pipe-material-and-dimensions-0308-2026-10-04).
