# Race flow focused verification — 2026-09-28

Godot 4.7.2 stable mono, macOS arm64; isolated temporary projects and user data.
Compressed logs and command/result JSON are adjacent. Product source overlays used
the owning Runtime/MapKit code; final gitlink consistency is a separate handoff check.

| Check | Time | Result |
| --- | --- | --- |
| assembled_track_validator | 1.454s | PASS |
| asset_native_validator | 9.982s | PASS |
| document_history_validator | 1.373s | PASS |
| heightmap_import_validator | 2.506s | PASS |
| import_command_validator | 8.59s | PASS |

Actual driving, complete AI race, Host/Join, device input and export/clean-clone
acceptance were not run. No full bootstrap/check or long performance run was used.

The asset test initially reused `user://original.memap` created by the preceding heightmap test in the same isolated invocation. Its output is now `asset-original.memap`; the exporter correctly refused overwrite. Rerun passed all 168 asset checks. No remaining failure in the affected focused checks.
