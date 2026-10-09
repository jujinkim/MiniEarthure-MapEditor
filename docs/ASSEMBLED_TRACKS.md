# Seed Track

Use **Seed Track** to choose seed, circuit/sprint, approximate duration,
difficulty, candidate special pieces and time of day. Basic geometry varies
automatically; four identical pieces is the maximum consecutive run. Dimensions,
catalogue, generation and package verification are owned by MapKit.

Generation and initial package save run through MapKit's cancellable worker.
The result opens as a new unsaved document; the original project remains on disk
and unsaved edits use the explicit Save / discard / Cancel lifecycle. A changed document epoch or
cancelled/replaced request prevents a late result from replacing the current
document. Existing Save/Export and 2D/3D preview work with the generated document.
Reopening retains seed, settings, resolved placements and generator fingerprints,
and reopening Seed Track restores those settings. No piece authoring or manual
piece-layout tool is introduced.

`tests/assembled_track_validator.gd` covers original/recovery preservation,
new-document semantics, save/reopen and settings restoration. Detailed editor
interaction and driving acceptance are user verification.

The 2026-09-28 catalogue adds left curves to the always-available basic shapes;
neither curve direction is shown as an optional gimmick. The existing generated
document/save/reopen/settings test passes against the new seeded circuit layout.

2026-09-28 short-track follow-up: time choices come directly from MapKit's
catalogue. Circuit offers 30 seconds/1 minute/2 minutes **per lap**, with maximum
3/3/2 laps; sprint offers 1/2/3 minutes. The default is a one-minute circuit.
Settings store `duration_seconds`; basic sharp corners and hairpins are automatic
geometry. The current catalogue requires regenerated packages; existing files
are preserved without automatic conversion.

2026-09-28 vehicle-scale follow-up: the existing **Cylinder** checkbox represents
MapKit's `selection_groups.cylinder` family. Variant names do not create extra
controls. The generated shape, source frames and bounds remain MapKit-owned;
the driving-structure panel asks the native `special_track_bounds` API for
bounds instead of copying shape constants, and preserves the 1 m swept bore
radius when loading it. Generation/save/reopen/settings and native swept bounds
are checked with synthetic documents. Detailed editing/preview acceptance is a
user check.

2026-09-28 catalogue-load fix: the panel checks the required `selection_groups`
dictionary before creating controls. A stale loaded native module now produces
restart guidance with generation disabled, not a Dictionary access error or an
old-catalogue fallback. Settings restore is a no-op in that state. The focused
validator covers missing groups and the current single cylinder-family control.


2026-09-28 RC venue replacement: the shared catalogue now mixes 2m/4m roads and
2m/4m curved tubes, retains one Cylinder checkbox, and exposes eight additional
choices: banked U chicane, jump hurdle, ramp/overpass shortcut, roller hills,
offset landing, slalom walls, rotating sweepers and lifting gates. Seed selects
indoor carpet, outdoor circuit or toy plastic. Shared MapKit rendering supplies
the stage and track materials; generated packages must be regenerated for the
current catalogue fingerprint. Original files are preserved. Detailed driving,
whole races, multiplayer and manual application acceptance remain user checks.

## Mandatory variety settings — 2026-09-28

The current catalogue adds the plain 32m sprint lane. Every checked family is
required, so the estimate may exceed the requested time. Descriptions explain
6/4/2m widths, seeded straight/corner balance and consecutive special sections.
Generation reports actual estimated seconds and the ordinary-road straight share.
The new document/recovery/epoch and cancellation behavior is unchanged. Focused
`assembled_track_validator` covers checkbox/result display and source preservation;
detailed authoring and driving remain user tests. See root `docs/SEED_TRACK_VARIETY.md`.

## Race-flow replacement — 2026-09-28

Current Ready/automatic-start, individual finish and sprint plaza behavior is recorded in [FREE_ROAM.md](FREE_ROAM.md). Earlier manual start and player-finish-ends-all behavior is replaced.

## Random seed extension — 2026-09-28 replacement

The panel uses the current MapKit catalogue: one required instance per selected
family, at most two consecutive family members, with ordinary slopes automatic.
Results show length, estimated seconds, measured straight share and any requested
time overrun. There is no straight-share target field or display. Every selected
family remains present even when the minimum valid layout exceeds the request.
Current v1 fingerprints require fresh generation; original files are preserved.
Focused generation/display and source preservation checks pass; detailed driving
and authoring remain user checks. Integration evidence: root
`docs/SIMPLIFIED_SEED_TRACKS.md`.

The recovery validator creates a retained v1 fixture explicitly. Production has
no automatic recovery writer; existing recovery files remain readable.

2026-09-29: The panel consumes MapKit `selection_ids`, with one **장애물** checkbox
and **질주코스 · 16m**. Both modes offer 60/90/120 seconds; 90 is displayed as
**1분 30초**. Circuit caps are catalogue-owned 3/2/2. The generated document retains
exact attachment metadata through save/reopen and recovery; original sources are
preserved. `assembled_track_validator` covers settings, native contract mismatch,
source preservation and document roundtrip. Detailed editing/driving is user work.


## New generation panel seed — 2026-10-03

Each new panel initializes one random seed without changing MapKit's API default 1.
Direct entry and New seed remain available. Reopening the same dialog preserves
cancelled or failed edits rather than restoring the document's old settings each
time; an existing assembled document is restored only when its panel is first
created. Busy/cancel/result and explicit restore preserve the entered value.
`track_settings_validator` passes the injected RNG, default contract, retention
and hourly display cases (`validation/driving-map-2026-10-02/`).


The current MapKit pin includes difficulty-weighted families and widths. Editor
passes its selection and seed directly to that public API; generation weather
remains a session choice in the game. Formats remain v1 and original documents
and generated artifacts are preserved.
## Wall generation pin and bundled practice refresh — 2026-10-03

The MapKit dependency includes valid tetrahedral wall occupancy, common surface
triangulation and bounded post-split costs. No Editor product code or format
number changes. Owning native generation/build tests pass.

**Earlier failure, resolved by the refresh below.** The only tracked assembled
current package is `examples/practice-track-pipes-2026-10-04/practice.memap`; the previous output is preserved. Compiling its stored
`source.json` with current code fails `E_TRACK_SOURCE: invalid action` (the stored
manual-flight sample references no longer fit current sampling). Regenerating
from `scripts/practice_track.py` into a new isolated directory fails
`E_TRACK_DRAFT`: `runout-04 / course-04` and `runout-05 / course-05` road clearance
collision. The authoring/sampling source responsible for these checks is unchanged
by the wall occupancy repair. Both failure logs
are retained. Original source, package, project and entry metadata are preserved;
neither action validation nor road-clearance validation is bypassed, and the
approved 8m-wide / 6m-radius practice corners are not silently redesigned.

At that attempt the artifact refresh was unresolved, separate from successful
new seeded generation. The original failures above are preserved; current scoped
refresh results follow. Detailed Editor interaction and human driving remain user verification.

## Bundled practice regenerated — 2026-10-03

MapKit `e563b8d1` includes the finite straight-ribbon clearance correction. The
approved 8m-wide / 6m-radius turns and all other authored geometry/order remain
unchanged. The script compiles temporary source and resolves checkpoints at 3m,
takeoff references at 4m before the end and landing at the first actual station.
It duplicates no sampling interval or fixed sample index. Current takeoff indices
are 17 of 21 samples, replacing the invalid stored index 32. Validation still
rejects invalid indices; the preserved old source is not converted or accepted.

The original example and consumer copy were backed up before generation. After
new-directory verification, source/project/package/courses/entry were replaced
together. Package SHA256 is
`4745728b36f1573c7f989732a6fe1c1b635779e40e41d52b34ed2a8727e5eebc`.
Evidence covers both prior
failures, three Python tests, byte-identical fresh directories, refusal to replace
an existing output, stored source recompilation, source/entry identity and strict
native Editor open/edit/save/reopen. `human_completion` remains `unverified`;
detailed editing and driving are user checks. Formats and public APIs remain v1.


## Continuous straight-clearance pin and preserved-source refresh — 2026-10-03

MapKit `47a07f13` detects continuous clearance for unjoined level, constant-width
straight pairs before sample comparisons. Editor uses that shared compiler;
there is no local collision rule or format change. The preserved practice source
recompiles successfully into a new directory, with geometry/source identical and
only seven derived identity fields changed. The new example/entry package SHA256
is `36c07f812f9436d53798e1e542f9edf2d8e6e39f4a962b7390b5148784cc652b`.
CLI/native source/save/reopen and standalone initial-screen checks pass.
Detailed editing and driving remain user checks; originals are preserved.

## Raised beam and earlier air entry — 2026-10-03

The practice authoring script now places the course8 solid beam top and independent
line45cm above road. Course9 departs2m earlier while preserving its landing and
later positions and4m width. New deterministic outputs replace the active example;
old artifacts are preserved. Focused evidence and hash.
Human completion remains unverified.

Time choice uses MapKit's shared six-preset picker (09/12/17/18/21/06). Existing minute values are preserved on load, settings restore and unrelated environment edits. The scoped settings preservation test passes.

The current MapKit pin canonicalizes final quantized endpoint ribbons and gives
the vertical loop smooth feet and a broader crown while preserving its height and
ports. Editor preview, collision/export and occupancy consume the same geometry.
Existing saved source maps are preserved. MapKit owns the geometry/validation
summary in [assembled tracks](../addons/mapkit/docs/ASSEMBLED_TRACKS.md).
