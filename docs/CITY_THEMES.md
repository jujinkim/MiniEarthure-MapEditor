# Q03 — Town v6 neighbourhoods

Scope correction: these six categories are land-use/layout variants in a Korean
sample town. They do not fulfill the requested worldwide regional/environment
themes. The initial seven and the language-neutral common asset / map-specific
sign boundary are planned in [WORLD_THEME_AUTHORING](WORLD_THEME_AUTHORING.md).
The current models have not yet been refactored into that common library.

`scripts/city_themes.py` expands the Q01 modelling vocabulary to the other 40
city lots. The Hanbit lot remains byte-identical in layout, assets and collision.
The map stays 576×192m, with 432 16m cells, Recipe 6 and package format 1.

| Land-use variant | Lots | Shape and use |
| --- | ---: | --- |
| Shopping | 9 | Five/six shops, frontage setbacks, width-aware spacing, signs, awnings and café yards |
| Residential | 10 | Five/six homes, two/three floors, recessed four-sided windows, balconies, doors, services and benches |
| Market | 5 | Three pitched roof bays, clerestory/loading fronts, produce stalls and small surrounding shops |
| Office | 6 | Two staggered 21m towers, stepped podiums, lobby canopies, vertical fins, shops and a clock |
| Hotel | 5 | 17m balcony tower, separate low arcade, dining/bookshop court and stone basin |
| Plaza | 5 | Asymmetric tower/arcade/café, open paved forecourt, clock, basin and seating |

The preserved Hanbit block is the 41st lot. Total city buildings are 197, with
three to six buildings per block. Korean lot coverage is 42.8–60.9%; sky district
coverage is 26.4–39.1%, leaving deliberate plazas and hotel forecourts. These
are reported changes from v4's uniform 65–80% four-building layout, not equivalent
density or a large-map performance claim. Building count alone is not the quality
criterion: entrances, relief, roof form, street use and navigable space differ.

Fifteen 2m market/residential lanes connect through explicit splits of the actual
north/south streets. Their junctions open the curbs. All old road geometry and
widths, sixteen spawn poses, western practice circuits, terrain and intentionally
buried structures remain unchanged. Only old furniture crossing a new opening
is retired. Existing tree/bench/lamp/stop furniture elsewhere is preserved.

Nine new GLBs reuse the Q01 opaque PBR palette, thin applied panels and material
grouping. Building masses, roof services, arcade posts, produce tables and basin
walls retain explicit collision. Windows, lettering and balcony rail detail do
not create extra physics bodies. Original MIT geometry/stroke lettering is
attributed to `mapeditor-q03-city-themes`; there are no downloaded models, fonts,
textures or user datasets. Source asset references are shared; this does not
claim cross-cell GPU deduplication, MultiMesh, LOD or a new renderer contract.

Twenty-four v4 building assets have no remaining placements. They are omitted
from the active document/package, preserving the exact old sources and package
in `examples/driving-school-v5/`, `examples/driving-school-v5.memap` and
`tests/driving_school_v5.lock.json`. Their original loose files also remain in
the current source folder but are not package dependencies. No visible geometry
is removed by this dependency cleanup. The package includes all assets it uses:
262,980 bytes, 1,237,204 asset bytes and 1,931,215 expanded bytes. Inspection's
332,374,070-byte logical peak is not RSS or a GPU measurement.

Use the regeneration/native/Editor commands in [DRIVING_SCHOOL](DRIVING_SCHOOL.md#재생성과-검증).
The Python tests cover deterministic regeneration, frozen v5/Q01 preservation,
road graph/route/height invariants, theme variation and every new lane's collision
clearance. The lock records all 432 native generated hashes. The Editor validator
checks real Save As → reopen → export and existing starts/course surfaces.

The consuming application's actual rendered driving and memory observations are
separate from standalone authoring checks. PC 1GiB traverses the six sampled
themes. A forced 512MiB client opens v6 but refuses the next dense window from
`korea-0-0`; current collision/support and retirement remain safe. Resolving that
capacity limit is implementation follow-up, not merely device verification.
Android hardware, other supported OSs,
human art/direct driving, sustained performance and final release acceptance
remain separate gates. This is the small default town, not the L01/L02 large-map
format, storage boundary or density experiment.
