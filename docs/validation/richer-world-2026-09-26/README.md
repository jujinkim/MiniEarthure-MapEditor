# Richer miniature regions — 2026-09-26

Implemented in [richer_world.py](../../../scripts/richer_world.py), with seven
original sources in [examples/richer-world](../../../examples/richer-world/README.md).
The intended finish is modest material realism on miniature shapes, not
photorealism. Sources are authored directly in metres and use MapKit's common
MIT assets and water mesh helper. No original examples were replaced.

## Automated results

- `python -m pytest tests/test_richer_world.py -q`: **2 passed**, 34.65 s.
  Exact regeneration of all seven directories, refusal to overwrite an existing
  destination, original source preservation, source digests, connected roads,
  route lengths, 2m terrain seams, pond depth and parcel variation passed.
- MapKit `scripts/test_richer_assets.py`: **2 passed**. Deterministic shared
  assets/tiles and rejection of integer-collapsed water collision slivers passed.
- Current debug MapKit CLI `pack` and `validate-cells`: **7 packages / 2,694 cells
  passed**. [Source and cell manifest](source-and-cells.json) records package
  digests, source manifests and digests of complete cell hash output.
- Rendered `richer_material_validator` and `rain_surface_validator`: **PASS**,
  1.064 / 1.555 s. Imported GLB channels, GPU shaders, weather and shared texture
  admission/last-borrower lifetime were checked using MapKit `ac74f9a` rendering
  sources (the later commit only corrected the Python water proxy helper).
- Actual final package `render_regional_maps`: **PASS**, 24.227 s, no unexpected
  diagnostics. Seven overview, ground, waterfront and district views were
  inspected. Whole-map documentation capture coalesces surfaces; it is not a
  runtime streaming/performance test. Product cache limits remain unchanged.

The adjacent `.log` and `.json` files retain commands, durations and diagnostics.
Environment: macOS Apple M1, Godot 4.7.2 stable Mono, OpenGL Compatibility, Python
with Pillow 11.3 / Shapely 2.1.2. The superproject's existing virtual environment
and native debug build were reused; native code was unchanged.

## Corrections and scope

Native validation caught bridge apron/terrain conflicts and zero-area water
proxies after centimetre rounding. Approaches were graded and the degenerate
proxy triangles are now filtered in MapKit. Visual review corrected dry wedges
between river reaches by sharing bank vertices, removed water self-shadowing,
raised crop surfaces out of coplanar ground, and added clustered forest canopy.
No known failure remains in these affected checks.

One intermediate render failed because sequential Client/Editor source overlays
had conflicting Godot texture import remaps. Reimporting the Editor project
resolved it; final rendered checks passed. Do not share an import cache or
simultaneously import source overlays with different addon prefixes.

Actual driving, completion proofs, final art approval, detailed editor usage,
devices and exports were **not tested**. Suggested courses carry no completion
evidence. Client performs package/course/grid admission separately. The small
Kanupi cascade is static authored geometry; no fluid simulation was added.

## Reproduction

See the source README for generation into a **new** directory and native package
validation. To capture packages, set `REGIONAL_SOURCE` to a directory containing
`<id>.memap` and `<id>/region.json`, set `REGIONAL_DESTINATION` to a new capture
directory, and execute `res://tests/render_regional_maps.gd` with Godot. Fixed
review cameras are in each source's `region.json`. Generated files under the
historical examples are preserved.
