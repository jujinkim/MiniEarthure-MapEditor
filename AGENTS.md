# map-editor

Independent public MIT code. No private repository dependency. Preserve source and
asset licenses. Use synthetic fixtures only.
Use `rtk` for shell commands when available. Never publish user datasets or secrets.

Validation: run affected feature/unit tests and needed
syntax/build/load checks; preserve relevant safety regressions. Do not rerun
unaffected suites for commits or docs. Docs-only work needs diff/reference/pin
checks. Application checks stop at basic standalone startup and initial-screen/
load-error checks. Detailed interactions, game test driving, Godot Editor
execution, OS/device and platform acceptance are left to the user. Full
integration, recursive clean-clone, export matrices and prolonged performance
runs require an explicit user request. Record known failures and user checks
separately; this supersedes earlier automatic full-suite/final-acceptance rules.

Current formats: `.memap` and all own format/protocol numbers are 1.
Version changes require explicit user approval. Runtime state revisions,
epochs and request IDs are not format versions. No previous-format loaders,
automatic conversion or legacy compatibility branches. Preserve user datasets,
original files and Git history. New rules modify the current v1 definition.

Validation scope: check only changed areas and directly/indirectly related areas.
Full checks of any kind require an explicit user request. This scope applies to
documentation, preparation and implementation work alike.

Documentation: use the local document index/current owning documents. Keep only
current contracts, usage, open issues and essential validation there; replace
existing sections instead of appending dated updates. Necessary historical
decisions/comparisons belong in `docs/history/` with a current-document link.
History is optional reading. Active task notes belong in root ignored
`docs/tasks/`; integrate results and delete finished notes/raw logs, without
archiving them. Preserve user data/maps, generated artifacts, models and fixtures.
Commit each verified task locally on main in dependency order, including consumer
pins and root lock. Push after the approved scope and checks finish. Never
force-push or rewrite history.
