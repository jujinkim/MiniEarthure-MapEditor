# Richer miniature living regions

These seven original MIT sources are authored at their final metre dimensions.
Historical examples and packages are preserved. The intent is a little more
material realism, with miniature proportions and readable, simplified shapes.
Abstract coloured signs do not require real lettering or fonts.

| Region | Size (m) | Intro / technical / sprint (m) |
|---|---|---|
| Haeon | 320 × 320 | 226.14 / 329.10 / 421.60 |
| Belmont | 384 × 288 | 236.03 / 357.34 / 423.39 |
| Nord | 416 × 208 | 244.89 / 375.00 / 422.29 |
| Safra | 288 × 288 | 223.36 / 341.34 / 425.04 |
| Red Wadi | 416 × 256 | 232.63 / 358.16 / 426.69 |
| Kanupi | 384 × 288 | 244.15 / 348.68 / 423.61 |
| Bansai | 352 × 256 | 264.46 / 351.31 / 429.40 |

The source contains connected main streets, residential/technical lanes and
outer exploration roads; uneven parcels and access aprons; separate farms,
cargo yards and clearings; global 2m terrain samples; variable banks, ponds,
coasts, a dry wadi and Kanupi's small cascade. Buildings and groves use the
shared MapKit library. Water geometry is made by MapKit's common mesh helper
from the Editor's authored bank polygons. Bank vertices are shared along a
curve, and confluences are unioned before cell tessellation. Bridge approaches
are graded to the same levels used by the common road/safety renderer.

From the superproject, using its existing Python environment:

```sh
rtk proxy .venv/bin/python map-editor/scripts/richer_world.py /tmp/new-richer-world --kit map-kit
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-richer-world/haeon /tmp/new-richer-world/haeon.memap
rtk proxy map-kit/target/debug/mapkit validate-cells /tmp/new-richer-world/haeon.memap
rtk proxy .venv/bin/python -m pytest map-editor/tests/test_richer_world.py -q
```

The destination must be new. `region.json` records source hashes, exact starts,
route geometry, parcels, water bodies and fixed review cameras. Three routes
per region are suggestions without completion evidence. The Client uses its
existing Runtime API to seal courses and test eight-player starting grids.
`.memap` stays format 2; all other own versions stay 1. Native cell validation,
deterministic regeneration, seam/connectivity checks, bounded package renders
and Client admission checks are separate from user driving/art acceptance.

No external imagery, surveyed data, private game code, font payloads or user
datasets are embedded. Geometry and textures are original MIT work.
