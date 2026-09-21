# Authoring workspace implementation status — 2026-09-21

This is the workspace/package-restoration portion of the approved authoring,
gimmick and loading plan. The full plan is **not implemented**.

Implemented: menu/command search, central view switching/split, persistent authoring
dock, compact activity/problems panels, independent view preferences, preview
orbit/pan/zoom and framing the 2D/tree selection; `.memap`/`.mkregions` restoration
with validation, no overwrite, unsaved guard and late-result protection. Fixed
unclassified GeoJSON building use so the current native validator accepts reviewed
imports, while retaining original source and explicit estimation warnings.

Automated checks on macOS/Godot 4.7.2 using isolated user data:

- `workspace_commands_validator`: 1024×720, 1440×900, 1920×1080; 2D/3D/split,
  view persistence, search, text shortcut isolation, camera operations and unchanged history.
- `workbench_validator`, `editor_ux_validator`: selection, editing, locks,
  Undo/Redo, document replacement, recovery and import review/adoption/failure.
- `preview_export_validator`: bounded preview, cancellation, snapshot export,
  preserved outputs and payload/history copies.
- `package_restore_validator`, `regional_export_validator`: export/restore,
  canonical source and unused asset bytes, corruption, cancellation, late result,
  preserved existing destinations.
- `asset_native_validator`, `heightmap_native_validator`, `environment_validator`:
  retained import/session safety after replacing the authoring dialog with a dock.
- Python `test_importers.py` (6), `test_courtyard.py` (1), `test_overture_area.py` (6).
- Rendered standalone initial screen: no blocking load diagnostics. Detailed
  editing, OS/device interaction and game driving remain user verification.

During implementation, tests caught temporary fixture-name collisions, minimum
window overflow, a menu/button test selector collision and unsupported GeoJSON
default use. These were corrected; failing logs are retained alongside passing
rechecks in the superproject's `work/authoring-checks/`.

Still unimplemented: free placement transforms, 3D picking/gizmos/surface snap,
asset thumbnails/GLTF dependency adoption/collision editing, prepared render units,
MapKit deployment-cost profiles/gates, declaration-driven gimmicks and motion
preview, authority/runtime/race-reset/network integration, camera-neighborhood
streaming, seven-map challenge authoring and 21-course distribution regeneration.
These are implementation work, not merely user acceptance tests. Existing cost
warnings still do not constitute a PC/Android deployment approval.
