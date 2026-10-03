# Authored tutorial course update — 2026-10-03

MapKit `47a07f13`, Godot 4.7.2 Mono/macOS arm64; unchanged compiler/native code.
Authoring script changes only: beam center +45cm (top .45m above road) and both
independent line endpoints +45cm; course-09 approach 30→28m and flight-relative
endpoint (4m,4m)→(4m,6m). The landing and every subsequent world position, 4m
width, course order and manual-flight semantics remain unchanged.

Generated into a new directory. Previous example/source/package preserved locally
and in Git history. Updated this repository's example from generated output;
never patched generated collision geometry. Source/protocol/format remain v1.
Package/entry SHA256:
`2eb57e620efb1dd41c3c29b99e0c506e35a72982913a37c5bd73a6b36cb417c8`.

`MAPKIT_CLI=<pinned cli> .venv/bin/python -m unittest discover -s map-editor/tests
-p test_practice_track.py`: 4 tests PASS, .359s. Includes new dimensions, two fresh
byte-identical exports, recompilation identity, verify-track, gate/action distance
references, hash, old-output refusal and unchanged human_completion=unverified.
`practice_source_validator`: strict PASS, source extraction, original project
reopen, recompile, save and reopen. Exact native command/timing retained in
`editor/`. No interactive Editor or human driving completion was performed.
