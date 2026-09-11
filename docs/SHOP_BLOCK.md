# Q01 — Hanbit shopping block

The Korean names below are map-specific lettering embedded as mesh strokes,
not reusable language-neutral base assets or a multilingual texture system.
The future common/sign separation is described in
[WORLD_THEME_AUTHORING](WORLD_THEME_AUTHORING.md); this preserved baseline is
not changed by that plan.

This is the preserved v5 baseline. Q03 keeps this lot intact and expands the
other neighbourhoods in [town v6](CITY_THEMES.md). Q02's consuming Runtime
resolved the original single-worker reservation denial; device acceptance is
still separate. The historical measurements below describe Q01 at delivery.

`driving-school-town-v5` replaces only the `korea-1-1` lot (X=238–272m,
Y=48–80m) with six original shops: 한빛서점, 골목커피, 봄약국, 은하식당,
온유공방 and 다온문구. The author is [shop_block.py](../scripts/shop_block.py).
The package remains Recipe 6 / format 1, at 576×192m with 432 cells.

Widths, heights, setbacks and opposing frontages vary. Shop windows, doors,
Hangul stroke signs, striped awnings, balcony rails, parapets, roof services,
conduits and repair patches give the block a consistent small-town palette.
Brick/tile coursing and recessed frames are geometry. Glass and metal use the
existing GLB PBR parameters; opaque glazing avoids transparent sorting.
Applied thin panels omit faces hidden inside their supporting walls.

Two local north/south streets split exactly at Y=64.5m, preserving the old ID
on the southern half and its existing spawn. A 2m service lane joins those
explicit nodes. MapKit generates the grade-level junctions and curb openings.
The remaining roads, all original courses/spawns, buildings, terrain and existing
asset bytes are preserved. Cafe furniture, planters, a bus shelter, drain/cover
plates, courtyard parking markings and an arrow leave the lane clear. Thin
surface plates have explicit centimetre-scale proxies; physical walls retain
their full mass. Decorations never replace wall collision.

This lot has six buildings over 60.9% of its buildable area. The other 40 lots
keep their v4 arrangement and 65–80% coverage. There are now 166 new-district
buildings, 586 roads and 16 unchanged starting locations in the whole map.

All new geometry, lettering and materials are original MIT work. No external
fonts, textures, extracted models or user data are used. The source attribution
`mapeditor-q01-hanbit-block` is stored both on the document and each new asset.
The prior [v4 source](../examples/driving-school-v4/), [package](../examples/driving-school-v4.memap)
and [hash lock](../tests/driving_school_v4.lock.json) are retained.

The selected package is 286,339 bytes (including every map asset), with
1,437,824 asset bytes and 2,121,577 expanded bytes. Its logical inspection peak
is 357,187,232 bytes; this is not process RSS. Six model files and eight detail
models are added, using 75 material groups in total. Material groups shared
within one GLB do not imply cross-cell GPU resource deduplication.

An embedded 64px PNG prototype was compared locally: the current reader reserves
the full image-decoder allowance for GLBs containing images, producing a
574,606,690-byte inspection peak. It was not selected. The selected geometry
keeps close-range relief while avoiding unused faces. General asset reuse,
pre-generation, instancing and LOD remain the separate Q02 unit.

Validation covers deterministic regeneration, original v4 preservation outside
the explicit lot/junction changes, graph connectivity, free lane, native package
admission and all 432 generated cell hashes. The Editor test also verifies
Save As → reopen → export produces the exact same package, including GLBs.
Use the [town validation commands](DRIVING_SCHOOL.md#재생성과-검증).

The consuming Client's actual PC driving/visual and memory observations are
separate from public authoring validation. A 512MiB forced-pressure scenario
can reject a subsequent region while preserving current collision; removing
that limitation is Q02 implementation work, not merely device verification.
Android, other OSs, sustained performance and human art/driving acceptance remain
unaccepted. This is a representative block, not a city-wide quality rollout.
