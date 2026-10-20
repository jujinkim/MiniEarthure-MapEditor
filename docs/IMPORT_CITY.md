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
- Ground paths, footways, cycleways, pedestrian streets and steps become painted
  ground (`surface_areas`), not roads; cars cross them as terrain. Steps keep their
  class; bridge, tunnel, layered or conveying steps (escalators) are excluded. A
  ground walking way's `incline` is its slope and is ignored on the flat map. Their source-width
  ribbons are united on the map-centimetre lattice and cut per 32 m map cell, and
  through any enclosed hole, into hole-free pieces of ≤256 vertices. Each piece maps
  to every source way it covers and takes the surface covering most of it (untagged:
  concrete). The ways still stop building gap filling and keep road clearance from
  buildings. Pedestrian bridges, tunnels, explicit-height ways and closed loops sharing
  their nodes stay roads.
- City ground roads lie on the flat map plane (0 m; other profiles estimate 0.2 m).
  Adoption adds the map's terrain base to city heights outside the explicit
  source-height graph, so estimated structures meet the terrain.
- Bridges, tunnels and layered ways without source heights that cross no other
  road (river bridges, culverts, building passages) are drawn at ground level on
  the flat map, counted as estimates in review.
- Those crossing another road get estimated heights: a chain of bridge (tunnel)
  ways joined end to end rises (sinks) 6 m per layer with ramps of at most 8 % and
  an 8 m level lead at each ground anchor. Where the chain is too short, whole
  ground ways continuing it up to a junction or dead end join it as the same
  structure; vertices are added where the profile bends. Chain ways have no side
  roads along them, no closed-road contact and no bend over 60° (a bend of θ needs
  neighbouring segments of 12 m · tan(θ/2) + 2 m, so native structure mouths stay
  separate); every crossing keeps 5 m of separation; tunnels use 4.5 m clearance.
  A chain crossing only excluded structures is drawn at ground level instead, as is
  one that cannot be estimated but crosses only open ground walking paint (not a
  closed way or one touching it, a ramp of an estimated chain or a way with source
  heights).
  Estimation sees only importable ways: a way excluded anyway (with its height tags
  removed, as an estimated way would be) or consumed by a relation is neither
  crossed nor absorbed, and a chain ending where such a way continued it is
  excluded, so no structure ends in the air or underground.
  Estimated structures join ordinary ground roads, stay whole at crop edges with
  every way of their chain, keep
  building clearance plus 1.6 m for safety furniture (also when widened) and are
  listed in `osm_estimated_structures`. Other crossing structures need explicit
  heights and are otherwise excluded.
- Compatible vegetation polygons are unioned. Illustrative trees use a 32 m source
  lattice (4 m on the map) at 750 ‰ density; they are estimates, not surveyed trees.
  The exact profile keeps an 8 m source lattice.

## Buildings

- Ordinary buildings group within 256 m source tiles (≤128 per group). Candidates
  fill 0–64 m gaps, simplify lines ≤4 m and polygons ≤8 m, then snap to a 0.08 m
  source grid (one map centimetre).
- Candidates whose line tolerance is equal (16–64 m gaps) share one derived road
  space: road-trimmed sources, protected buildings, aggregation groups and
  pedestrian paint are built once and charge the same work budget as a fresh
  build. Only gap filling and the overlap partition are rebuilt per gap.
- Candidates are built largest gap first and the first one that fits the output
  limits and converts is kept. A smaller gap is built only after a failure: a work
  budget, an unreviewed building inside road space, the output limits or conversion.
  Building a new road space drops the exclusions of the replaced one, so review
  lists only the kept candidate's exclusions.
- Named, public, landmark and tall buildings are protected from aggregation. Road
  corridors, protected land and courtyards block filler.
- Buildings are cut around road space with 0.8 m clearance, including a disk of
  √2 × the widest half width + 0.8 m around every junction node (the extent of a
  junction surface); gap filling never regrows into either. Overlapping volumes
  are partitioned with 0.16 m clearance, favouring taller/named geometry. Enclosed
  sources keep their IDs/names and an estimated height. Complex polygons split into
  native pieces with 0.32 m separation; pieces meeting at a point keep 0.16 m.
  Numeric failures keep the original group; a source erased by merging or
  quantization returns as its road-trimmed shape on the map-centimetre lattice.

## Review and adoption

Review reports before/after objects and positions, gaps/tolerances, width/material
estimates, painted pedestrian ways, road cuts and overlap changes. A compact table maps every supported source
to contiguous output records; missing, duplicate or excluded claims fail validation.
No supported source is dropped to fit a limit. A building entirely inside derived road
space fails that candidate with its source ID unless exclusion review is enabled; then
the whole source is excluded with a warning and the inspected-exclusions checkbox is
required.

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
