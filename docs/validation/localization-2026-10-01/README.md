# Localization delivery — 2026-10-01

## Implemented

The independent editor owns English, Korean and Japanese catalogs and starts in
English unless this app has a valid saved preference. View → Language saves the
next-start language atomically and reports success/failure in the current language.
Menus, palettes, commands, properties, authoring/import/export/recovery UI and
known diagnostics translate at display boundaries. Commands retain their original
IDs and support translated/original/ID search. User content and document bytes
remain unchanged. Noto Sans CJK 2.004 KR/JP fonts, source hashes and OFL are bundled.
See [the owning document](../../LOCALIZATION.md).

## Automated results

The tested changes are contained in the commit introducing this report. Baseline,
MapKit and engine revisions are in [source-revisions.json](source-revisions.json).
Tests use Godot 4.7.2 Mono on macOS Apple M1, disposable projects and isolated
user directories. No real preferences or user documents were modified.
Each validator's [logs](logs) include its exact command, duration, exit status and
unexpected diagnostics in the adjacent JSON file; raw logs are gzip-compressed.

| Check | Result and scope |
| --- | --- |
| `scripts/check_translations.py` | PASS: 1,811 keys; duplicate/empty/parity, interpolation, limits, source/helpers/scenes/commands/built-ins/diagnostics, font hashes |
| Import and user-path isolation | PASS: scripts load, no import diagnostics, separate temporary user directory |
| `localization_validator` | Strict PASS: English default, actual Locale recreation, deferred selection, failed save/file preservation, corrupt/unknown preference fallback, three-language UI and search, document/command/shortcut identity, authored text, formatted diagnostics and filter arguments, all catalog non-ASCII glyphs with system fallback disabled |
| `editor_ux_validator` | Strict PASS: existing workspace/command UI behavior |
| `workbench_appearance_validator` | Strict PASS: six synthetic rendered icon states; no detailed OS interaction |
| Standalone application, en/ko/ja | PASS: workspace/command registry exists, expected startup language, no blocking load errors or warnings; no detailed editing |

[Catalog output](catalog-audit.txt); initial screens:
[English](startup-en.png), [한국어](startup-ko.png), [日本語](startup-ja.png).
The startup checks used a temporary observation autoload and reused imported
resources. It asserted the workspace and Locale, captured one frame and quit;
the product has no observation hook. Each language used its own temporary
preferences, with no preference file for English.

In the superproject, affected checks can be reproduced with
`rtk proxy .venv/bin/python scripts/run_godot_checks.py --project editor --script <validator> --log-dir <temporary-directory> --strict-diagnostics`.
Use a sequential isolated import cache; `workbench_appearance_validator` needs
`--rendered`. The standalone catalog audit is `python3 scripts/check_translations.py`.

## Known failures, preserved separately

Update 2026-10-03: all four validators below were individually reproduced and
repaired for the current workspace/fixture contracts. [Current revisions,
classification and strict passing results](../test-failures-2026-10-03/README.md)
are separate from this historical localization run; these logs remain unchanged.

These existing assertions also fail in a temporary projection of the original
Editor HEAD with the same MapKit pin and engine:

| Validator | Failure | Baseline evidence |
| --- | --- | --- |
| `palette_entry_validator` | `ramp_low` obstacle preview rejected | [log](logs/map-editor-baseline-palette_entry_validator.log.gz) |
| `authoring_validator` | Fixture revision conflict and authoring button/tab expectations | [log](logs/map-editor-baseline-authoring_validator.log.gz) |
| `course_authoring_validator` | Save unverified public course | [log](logs/map-editor-baseline-course_authoring_validator.log.gz) |
| `import_review_validator` | Reviewed provenance native package export, 1 of 51 checks | [log](logs/map-editor-baseline-import_review_validator.log.gz) |

They are not marked fixed. This is not a full-suite pass. Initial visual checks
found an untranslated section heading and unsupported small triangle glyphs;
both were corrected and the final catalog, full glyph and startup checks passed.

## User verification

Detailed authoring, game test driving, IME, touch, device-specific UI acceptance
and platform export matrices were not run. Actual app verification stops at the
initial workspace. These user checks and known baseline failures are separate
from implemented localization and do not constitute release certification.
