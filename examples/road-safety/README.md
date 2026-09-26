# Road safety source revision — 2026-09-26

MapKit's common generator applies rounded street/curb edges and automatic deck
rails to all seven existing synthetic miniature street maps. Six original sources
and packages remain the active defaults. `belmont/` and `belmont.memap` are a new
source/package identity; the original `examples/miniature-streets/belmont*` files
are preserved. All sources here remain original synthetic MIT example content.

The extended curved bridge mouth of `arterial-2-s1` encountered a 5cm terrain
mismatch. `scripts/road_safety_maps.py NEW_DIRECTORY` copies the old source and
flattens terrain within 600cm of its two endpoints, blends to the unchanged
terrain at 1000cm, and writes four new content-addressed heightmaps. Roads, nodes,
widths, placements, assets, gimmicks and original heightmap files are unchanged.
The result uses map ID `road-safety-belmont`; no loader conversion is introduced.
Existing destinations are rejected. `tests/test_road_safety_maps.py` verifies
repeatability, preservation and shared height samples across tile boundaries.

Pack with the current MapKit CLI into an unused `.memap` destination. Render the
seven-map source directory using `tests/render_regional_maps.gd` with
`REGIONAL_SOURCE` and `REGIONAL_DESTINATION`. Fixed overview and ground views use
MapKit's same renderer as the editor preview. Rendering does not validate driving
or course completion. Consumers must reseal courses for the revised identity
without transferring old completion evidence.
