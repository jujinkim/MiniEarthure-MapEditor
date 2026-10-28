# Memory preview and explicit output

Terrain, water, records and referenced resources form one detached MapKit working
snapshot. Height queries, road cut/fill, display, validation and export read that
snapshot, including unsaved height arrays. Editor owns commands and saved baselines;
MapKit owns generation, polygon operations, PNG16 and the v1 contracts. Save and
Save As are defined in [DOCUMENTS](DOCUMENTS.md#save-and-recovery).

## Preview and validation

Edits request the affected **32 m display cells** plus needed neighbours. One
running worker plus the latest pending cells bound demand. Nearby display is a 3×3 cell window.
Unchanged nodes and shared mesh/material/asset caches are reused; request epoch and
session checks stop old documents receiving results.

**3D Preview** generates a chosen storage cell from memory and refreshes 150 ms
after the last committed edit. Unchanged content signatures keep cached roots. A
hidden candidate replaces the old root only after frame-budgeted installation
(**3 ms/frame**; one indivisible engine operation may exceed it).

Preview and **Validate** never stage projects, encode PNGs or write recovery files.
Validation checks document, resources and seams from arrays; optional full 3D
validation generates cells in memory. Compressed sizes exist only after export.

| Bound | Limit |
| --- | --- |
| Unique source resources | 2 GiB; warning above 64 MiB |
| Preview work | 256 MiB allowance; larger cells generate with a warning |
| Cached storage cells | 4 / 256 MiB |

Native scratch, triangles/IDs/objects and decoded presentation are charged. After
generation, storage previews check actual triangle/object/prism counts against the
admitted upper bounds and charge those counts; larger or invalid counts reject the
result. These are admission bounds, not measured process/GPU memory. A cell over the
allowance is still generated and shown with a limit warning. Preview, density, full
check and the road workbench generate with MapKit's Authoring profile and a
2,000,000-triangle cap: a cell above the game's 500,000 triangles or its road,
placement or courtyard work budgets is shown with a warning that the game refuses it
(`cell_triangles`, `road_work`, ...). Only a cell above MapKit's raised guards still
fails, keeping the prior preview with a recoverable error.
Above 200,000 preview-index references every cell is refreshed after each edit, with
a warning.

## Chunk density

The density list reuses MapKit generation estimates and the 256 MiB preview work
calculation: it warns at 192 MiB and flags cells above 256 MiB, which are still
checked and reported as limit warnings. MapKit warnings of the analysed map are
listed below the rows. Rows include
triangle, prism, convex and presentation costs; selecting a row centres the 2D map
on that cell. Analysis runs on a worker 350 ms after the last change; edits,
Undo/Redo and cancellation clear rows immediately. Package preview/export waits for
a cancelled analysis worker before allocating another snapshot. Warnings do not
block Save/Export. Preview preparation over 5 s is recorded with its source
signature and dropped after edits.

## Export and test drive

Export and test drive accept a **new unsaved map**. They create independent outputs
from the working snapshot without saving the project or clearing dirty state;
existing package filenames are refused. Test drive launches the installed Client
through its argument-vector adapter (see the [README](../README.md)).

Only explicit output encodes changed PNGs and uses disposable staging for
validation/compression. Request/session/revision checks prevent stale publication or
launch; operation scratch is removed, while projects, packages and recovery files are
kept. Publication checks destination hashes and renames an owned pending file.
Native file, seam, inventory and spatial validation always run. A malformed worker
result ends the operation once, reports failure and unlocks editing.

The report separates compressed ZIP/base/asset bytes, expanded resources, native
memory estimates and optional full-generation results. Staging opens the snapshot
in memory under the Authoring profile, so its inspection has no package; the
reported package size and SHA-256 come from the written package. The report and the
status line list limit warnings, including MapKit's top-level warnings (merged by
code): the full check generates each cell up to 2,000,000 triangles and warns about
cells the game refuses; a cell that still fails with a per-cell generation budget
(`E_BUDGET`, past MapKit's raised guard) is counted and warned instead of failing
export, and a 2D overview above 4 MiB warns (above 64 MiB it is omitted). The `.memap`
itself keeps every v1 limit: a map the game refuses (for example above 200,000
objects) opens, edits and saves with warnings, but its export fails with `E_LIMIT`.
Whole-map queries run in 96-cell windows.
Conflict detection is single-user; it is not a filesystem lock or power-loss
guarantee.

## Regional packages

Choose **Export map** with the `.mkregions` filter (or filename) and set **Regional
export · cells per side** (1–128, initial 8). This groups storage records only; cell
size, geometry, assets and quality are unchanged. The worker exports independent
regional sources from the immutable snapshot and audits all dependencies with
`audit_authoring` and a 64 MiB overview allowance; an overview above the game's
4 MiB regional audit warns (`overview_bytes`) instead of failing. The
capacity report shows total transfer size, expanded records, shared asset bytes,
audit peak, retained index/overview and the largest source validation allowance.

**Reopen .mkregions** (and Restore package for `.memap`) allows half the machine's
RAM (1–8 GiB) for its restore/audit memory; the reader admits only the package's own
planned validation peak. It restores the canonical document and every original payload,
including unused assets, into a new adjacent `<package>.source` directory, which must
not exist. Adoption then follows the ordinary unsaved-document flow. A cancelled or
stale reopen leaves a restored directory intact and reports its path. The Editor
still authors one bounded document; regional export does not lift document/object
limits.

## Validation

Isolated validators cover memory preview/export/reopen, cache reuse, resource
budgets, density, file conflicts, cancellation, saved baselines and test-drive
snapshots; `tests/package_restore_validator.gd` also checks that an over-budget
project opens and reopens with a warning and that the report carries the written
package size; `tests/regional_export_validator.gd` covers regional export/reopen, audit,
byte-exact unused PNG recovery, corruption and refusal to overwrite. Input feel, long
sessions, device performance and Client driving are user checks.
