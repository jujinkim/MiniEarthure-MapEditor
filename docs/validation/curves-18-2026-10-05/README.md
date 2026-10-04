# Practice samples after [18] — 2026-10-05

Editor scripts/source fixtures at fd211391 plus this change, MapKit a9e2761.
Native/CLI built from the same MapKit; Runtime binaries were reused for their
owning checks. Commands use the root `.venv`.

`python -m unittest discover -s map-editor/tests -p test_practice_track.py`:
4 PASS including two deterministic fresh builds, no-overwrite, exact 3m gates and
4m action markers, execution/source/reference/hash verification.
`python scripts/run_godot_checks.py --project editor --script practice_source_validator
--strict-diagnostics --import-cache ... --log-dir ...`: PASS, behavioral diagnostics0.
Package source opens, edits/recompiles, saves and reopens: 11 checkpoints,
5 structures, 1 grind line. Import diagnostics are recorded separately.

First regenerated output failed the old 40cm gate-apron tolerance (nearest sample
2.22m). Its log is retained. Source cubic joins now own exact semantic stations;
the assertion is strengthened to1cm rather than loosened. Output and prior
practice directories remain; no saved user data is changed. New example contains
the reproducible source/document/package. SHA256 is in its README.
Detailed interactive editing, driving and human completion are unperformed user
checks. No full suite, export or clean clone. All formats stay v1; no push.
