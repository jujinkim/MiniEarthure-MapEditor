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

## Later implementation and remaining scope — 2026-10-03 review

The checks above describe the 2026-09-21 delivery. No product checks were rerun
for this documentation review. Parts of its original remaining list were delivered:

- [Driving structures](DRIVING_GIMMICKS.md): declarative motion/bounds, property
  edits and shared time preview with document history.
- [Track authoring](TRACK_AUTHORING.md), [icon workbench](ICON_WORKBENCH.md) and
  [responsive editing](TRACK_EDIT_PERFORMANCE.md): piece transforms, port snapping,
  placement/dragging, sequential worker commits and prepared preview reuse.
- Seven-map challenge authoring and course distribution were followed by
  [compact](../examples/compact-driving/README.md), [richer](WORLD_THEME_AUTHORING.md)
  and [arcade-world](ARCADE_WORLD.md) implementations. Original artifacts remain.

Still incomplete: general 3D picking/gizmos/surface-snap tools beyond Track Mode,
broader asset thumbnails/GLTF dependency adoption/collision editing, deployment-cost
profiles and PC/Android approval gates, and general camera-neighborhood streaming.
Existing proxy/material editing and cost warnings do not complete those workflows.
Track Mode preview reuse does not establish completion of general asset-transform
or prepared-render-unit deployment workflows.
The separate 49-piece commit-latency target remains missed in the October 1 report;
current-code timing was not repeated here. Runtime integration is owned by each
consumer and is not a dependency of this public Editor.
