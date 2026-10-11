# Automatic city optimization

PBF streaming enables **Automatic city optimization (1:8)** by default; turn it off
for the exact profile in [IMPORTS](IMPORTS.md). This is an Editor-owned derived
approximation with no city-specific coordinates and no change to the original PBF.
It separates larger bounded source work from the smaller output MapKit accepts.

## Roads and vegetation

- Compatible ordinary ground chains join at degree-two source nodes. Simplification
  keeps junction positions, semantic boundaries and crossings; coincident
  independent IDs are not welded. Ordered source positions and traversal ranges
  are retained. Structures and explicit heights keep the exact rules.
- Equal adjacent centimetre vertices are removed after the single 1:8 quantization;
  nonempty holes are never discarded.
- Missing road widths use disclosed highway-class estimates (≥1.6 source m);
  source surfaces map to game materials.
- Compatible vegetation polygons are unioned. Illustrative trees use a 32 m source
  lattice (4 m on the map) at 750 ‰ density; they are estimates, not surveyed trees.
  The exact profile keeps an 8 m source lattice.

## Buildings

- Ordinary buildings group within 256 m source tiles (≤128 per group). Candidates
  fill 0–64 m gaps, simplify lines ≤4 m and polygons ≤8 m, then snap to a 0.08 m
  source grid (one map centimetre).
- Named, public, landmark and tall buildings are protected from aggregation. Road
  corridors, protected land and courtyards block filler.
- Buildings are cut around road space with 0.8 m clearance; overlapping volumes are
  partitioned with 0.16 m clearance, favouring taller/named geometry. Enclosed
  sources keep their IDs/names and an estimated height. Complex polygons split into
  native pieces with 0.32 m separation. Numeric failures keep the original group.

## Review and adoption

Review reports before/after objects and positions, gaps/tolerances, width/material
estimates, road cuts and overlap changes. A compact table maps every supported source
to contiguous output records; missing, duplicate or excluded claims fail validation.
No supported source is dropped to fit a limit. A building entirely inside derived road
space fails with its source ID unless exclusion review is enabled; then the whole
source is excluded with a warning and the inspected-exclusions checkbox is required.

Every map cell (≤256) is generated sequentially before review and adoption with the
120-second child timeout; batches of 16 reuse native preparation. The Map authoring
page exposes cell size: smaller cells reduce per-cell work without changing extent or
scale. Terrain tiles and assembled tracks block resizing. Resizing is one Undo command.
If protected geometry or budgets do not fit, the whole candidate fails.

## Limits

| Bound | City profile |
| --- | --- |
| Source work | 250,000 features, 2 million positions/entities, 4 million references, 256 MiB selected JSON |
| Output | 100,000 features, 800,000 positions, 180,000 records, 32 MiB wire and Editor JSON |
| Shared | 50 warning samples, whole-candidate native validation, 16 MiB retained Undo |

Output is also bounded by MapKit's 32 MiB document, 200,000 objects and 1 million
vertices. Large-PBF scanning shares the 2 GiB disk index of the exact profile; the
20,000-feature selection ceiling applies only to exact mode. City approximation never
supplies missing structural heights or repairs invalid original topology.
