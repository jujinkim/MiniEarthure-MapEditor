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

Current replacement (2026-09-26 arcade-world): `.memap` and all own
format/protocol numbers are 1, explicitly replacing the 2026-09-24 format 2 policy
unless the user explicitly approves a version change. Runtime state revisions,
epochs and request IDs are not format versions. No previous-format loaders,
automatic conversion or legacy compatibility branches. Preserve user datasets,
original files and Git history. New rules modify the current v1 definition.
