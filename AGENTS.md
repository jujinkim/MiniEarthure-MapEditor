# map-editor

Independent public MIT code. No private repository dependency. Preserve source and
asset licenses. Use synthetic fixtures only.
Use `rtk` for shell commands when available. Never publish user datasets or secrets.

User-approved test scope (2026-09-20): run affected feature/unit tests and needed
syntax/build/load checks; preserve relevant safety regressions. Do not rerun
unaffected suites for commits or docs. Docs-only work needs diff/reference/pin
checks. Application checks stop at basic standalone startup and initial-screen/
load-error checks. Detailed interactions, game test driving, Godot Editor
execution, OS/device and platform acceptance are left to the user. Full
integration, recursive clean-clone, export matrices and prolonged performance
runs require an explicit user request. Record known failures and user checks
separately; this supersedes earlier automatic full-suite/final-acceptance rules.
