# Driving structure authoring

The Gimmicks panel selects a library template or existing stable ID and edits XYZ,
yaw, period/phase, displacement, impulse and landing margin. Its time slider previews
shared MapKit poses and safety bounds. Save validates through the native v1 contract;
editing the same ID replaces that record, and delete/Undo/Redo use the document
store. Grind Line belongs to the Gimmick tab. Pipe and cylinder sizes are listed in
[TRACK_AUTHORING](TRACK_AUTHORING.md#pipes-and-rings). Executable scripts and general
3D gizmos are not supported.

`tests/gimmick_authoring_validator.gd` covers editing, save, replacement, preview and
Undo/Redo. `scripts/driving_features.py` builds the `examples/special-driving/demo`
fixture.
