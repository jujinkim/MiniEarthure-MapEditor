# Preserved reference-world history

These are synthetic MIT fixtures, not the current default-world catalogue.
Use [current default worlds](../ARCADE_WORLD.md), [authoring](../AUTHORING.md)
and [world themes/signs](../WORLD_THEME_AUTHORING.md) for current implementation.
The v2–v6 names below identify fixture generations, not supported format versions;
all current own formats are v1. Original sources, packages and locks remain intact.

## Driving School Town

The preserved `examples/driving-school/` source and `examples/driving-school.memap`
contain a 576 × 192 m town: western practice courses, a Korean district and a
high-rise district. Its 432 cells are 16 m fixture cells, not the current default
execution-cell size. `driving.json` owns the sixteen exact start poses, heights
and course order; `overview.svg`, `village-freeway.svg` and `village-finger.svg`
show the layout. The map contains 622 roads, ten courses and 197 city buildings.

| Fixture generation | Purpose |
| --- | --- |
| v2/v3 | Preserved scale/layout comparisons; historical coordinate transforms apply only to their authoring script, never to arbitrary imported maps. |
| v4 | 41 city lots, 164 added buildings, 65–80% lot coverage. |
| v5 / Hanbit | Six original shops on `korea-1-1` (X 238–272 m, Y 48–80 m), 60.9% lot coverage. `scripts/shop_block.py` owns the geometry and Korean stroke lettering. |
| v6 | The Hanbit lot remains; the other forty lots use shopping, residential, market, office, hotel and plaza layouts. These are land-use variants, not the seven worldwide default themes. |

`scripts/driving_school_map.py`, `city_expansion.py`, `city_assets.py`,
`city_themes.py` and `compact_vegetation.py` own reproduction. The shared city tree
is 3.25 m tall with a 1.15 m crown; its trunk and planter collide, foliage does not.
The preserved vegetation run produced 27 practice trees from 37 zones and retained
237 authored city trees. Counts are fixture observations, not generation quotas.

Use a new output directory; never overwrite preserved packages. The authoring
script needs Shapely 2.1.2; it is not an Editor runtime dependency.

```sh
rtk proxy python3 scripts/driving_school_map.py /new/town
rtk proxy addons/mapkit/target/debug/mapkit pack /new/town /new/town.memap
rtk proxy python3 scripts/check_driving_school.py --mapkit addons/mapkit/target/debug/mapkit --project /new/town --output /new/town-check
```

`tests/driving_school.lock.json` records source/package/cell hashes;
`tests/driving_school_validator.gd` covers open, Save As, reopen and export.
Historical Python/Editor checks passed scoped determinism, source preservation,
graph/route, asset, vegetation and roundtrip checks. A consumer PC 1 GiB tour
passed six sampled themes; its forced 512 MiB run rejected the next dense window
from `korea-0-0` while retaining live collision. These are old fixture/profile
results, not current budget defaults or device acceptance. Detailed art, driving
and device checks were not accepted by those automated results.

## Practice package revisions

`examples/practice-track/` and the dated practice directories retain original
source/package identities in `entry.json`. October 2026 recompilations covered
wall preparation, finite straight-road clearance, ring defaults, panel fields,
curve sampling and the 2 m pipe minimum. Repeated intermediate hashes and run
logs are available through Git rather than duplicated in usage documentation.
The active practice generator and current workspace are described in
[track authoring](../TRACK_AUTHORING.md#reproducible-practice-course).
Preserved files are never automatically upgraded; `human_completion` remains
unverified unless an actual user completion is recorded.
