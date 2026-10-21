# Automatic city optimization

PBF streaming enables **Automatic city optimization** by default; turn it off
for the exact profile in [IMPORTS](IMPORTS.md). This is an Editor-owned derived
approximation with no city-specific coordinates and no change to the original PBF.
It separates larger bounded source work from the smaller output MapKit accepts.

## Map scale 1:D

**City map scale 1:** chooses the denominator D, an integer from 1 to 8 (default 3;
smaller numbers make the city larger). The request carries `osm_scale`, the worker
`--osm-scale D` (CLI default 8). Once a map has OSM layers the control is locked to
their stored D: a map has one OSM scale, and adoption into a map with another scale
is refused. The exact profile stays 1:8. The same area covers (8/D)² times the cells
it covers at 1:8, so the crop dialog warns early when the area exceeds 256 cells at
the map's cell size (the city check refuses more than 16,384).

The profile id stays `scale-aware-city-v1` with `scale_denominator: D`. One map
centimetre is D/100 source metres; every map-unit value below derives from it.
Simplification levels, tolerances, the 256 m record tiles, barrier heights,
vegetation spacing and structure estimates (6 m levels, 8 % ramps) stay in source
metres. 1:8 keeps its
original working frame; at other scales the frame is shifted by the local origin's
remainder so lattice points are whole map centimetres.

## Roads and vegetation

- Compatible ordinary ground chains join where exactly two driving roads meet
  (painted ways do not count). Chains continue across width, lane, name and ref
  changes with per-segment widths; highway class, structure, access, surface,
  oneway and sidewalk changes still break them. Building trims, gap-filling
  barriers and junction clearance use each segment's own width (and sidewalk). Simplification keeps junction positions,
  semantic boundaries and crossings; coincident independent IDs are not welded.
  Ordered source positions and traversal ranges are retained. Structures and
  explicit heights keep the exact rules.
- Equal adjacent centimetre vertices are removed after the single 1:D quantization;
  nonempty holes are never discarded.
- Missing road widths come from `lanes` (lanes × 3.25 m + 0.5 m) or else disclosed
  highway-class estimates, widened to at least 20 map cm (0.2·D source m);
  source surfaces map to game materials.
- Dual carriageways (one-way motorway, trunk, primary, secondary or tertiary
  pairs, not links or roundabouts) merge into one two-way road. A pair runs
  anti-parallel (direction dot < −0.9) with the same class and, where both are
  tagged, the same name and ref; its inner edges, sampled every 5 m, are 0.5–25 m
  apart (an estimated carriageway counts as one 3.75 m lane) over at least 70 % of
  each side and 50 m. A merge runs between rungs: a shared converge node, one
  vehicle piece (median or diagonal turn link) no longer than 3 × the separation,
  or aligned nodes across the median (along-road offset within max(10 m, the
  separation)). Each merged run needs one real rung (converge node or piece);
  motorway and trunk sections between ramps may merge between aligned nodes
  alone. A slip road beside its carriageway runs the same way and never pairs. No building, water or
  other road may lie between the carriageways; median links, U-turns and junction
  pieces joined only to the pair are absorbed. The merged centreline is the
  midline: the first carriageway's nodes move to it with every incident road, the
  second's rung nodes are renamed to them and a side road meeting only the second
  carriageway gets its own midline node. Width is both carriageways plus the
  median per segment, `lanes` their sum (at most 8), `oneway` is removed. Every
  absorbed way stays in the merged road's sources, as does a road looping back onto
  one merged node (a jughandle U-turn, up to 150 m; a longer loop stops the merge).
  Merging stops a lead length (8 m) before any structure anchor, explicit-height
  node or structure/explicit-height road between or beside the carriageways;
  structure pairs never merge.
- Every ground road has an explicit sidewalk: none for motorway, trunk, `*_link`,
  service and track or `sidewalk=no`; otherwise 3 m (primary, secondary) or 2 m
  (other classes) when tagged `sidewalk=both|left|right|yes|separate` or for
  primary to residential roads in residential, commercial, retail, industrial,
  education or religious land. A parallel `footway=sidewalk` within 8 m of the
  road edge on at least half of the road widens it to that footway's outer edge
  (0.25 m steps); a sidewalk footway wholly inside the sidewalk is absorbed into
  the road's sources instead of being painted. Widths are whole map centimetres,
  0 or 20..1000. Building trimming and junction clearance include the sidewalk.
- Road markings: `lanes` (merged: the sum), else 4 lanes for motorway, trunk and
  primary and 2 for secondary and tertiary; none for lower classes without
  `lanes`. Center lines on two-way roads with an even lane count, no edge lines,
  asphalt or concrete only. A junction end (three or more roads) gets a crosswalk
  when a `highway=crossing` node on the road or a `footway=crossing` way across it
  lies within max(15 m, √2 × the widest half width + 10 m). A marked road and its
  marked two-arm neighbours stay within the 128 paint segments MapKit draws joined
  per road and cell, counted as MapKit does (a fillet arc per vertex, half a join
  arc at two-arm ends) over whole records, so for any cell size: longer records
  split at source nodes (at most 42 segments beside marked neighbours), a record
  that cannot split keeps no markings, and adoption refuses a layer over the bound.
- Parking aisles, driveways, drive-throughs and dead-end service stubs under 15 m
  become asphalt ground paint and tracks dirt paint (a tagged surface wins), like
  footways: drivable terrain mapped to their sources. A service way or track that
  alone links remaining roads or a structure's approach stays a road.
- Ground paths, footways, cycleways, pedestrian streets and steps become painted
  ground (`surface_areas`), not roads; cars cross them as terrain. Steps keep their
  class; bridge, tunnel, layered or conveying steps (escalators) are excluded. A
  ground walking way's `incline` is its slope and is ignored on the flat map, as
  is the `level` of an entrance node (a building floor, not road height). Their source-width
  ribbons are united on the map-centimetre lattice and cut per 32 m map cell, and
  through any enclosed hole, into hole-free pieces of ≤256 vertices. Each piece maps
  to every source way it covers and takes the surface covering most of it (untagged:
  concrete). The ways still stop building gap filling and keep road clearance from
  buildings. Pedestrian bridges, tunnels, explicit-height ways and closed loops sharing
  their nodes stay roads.
- City ground roads lie on the flat map plane (0 m; other profiles estimate 0.2 m).
  Adoption adds the map's terrain base to city heights outside the explicit
  source-height graph, so estimated structures meet flat terrain. They are not
  fitted to a DEM; adopting one afterwards fails at their junction aprons
  ([IMPORTS](IMPORTS.md) known limits).
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
  building clearance plus 20 map cm (0.2·D m) of safety furniture each side (also when widened) and are
  listed in `osm_estimated_structures`. Other crossing structures need explicit
  heights and are otherwise excluded.
- Compatible vegetation polygons are unioned. Illustrative trees use a 32 m source
  lattice (32/D m on the map: 4 m at 1:8, about 10.7 m at 1:3) at 750 ‰ density;
  they are estimates, not surveyed trees.
  The exact profile keeps an 8 m source lattice.

## Buildings

- Buildings are never gap-filled or fused: every source keeps its own footprint,
  simplified by at most 1 m (never growing into road space or a courtyard) and
  snapped to a D/100 m source grid (one map centimetre; 0.08 m at 1:8).
- Records group objects, not vertices. Buildings of one site and category share one
  record whose solids are MapKit `Building.parts` (at most 256 solids, in 32 m cell
  Z-order); each solid keeps its own height and base and stays a separate prism.
  The site is a `type=site` relation the building belongs to, else the smallest
  enclosing landuse residential/commercial/retail/industrial or
  school/hospital/university/college polygon, else the 256 m source tile; the
  category is the `building` value. Names of grouped buildings are kept as the
  record's names. Landmarks (historic, tourism or amenity tags, ≥40 m,
  public/hospital/school/church use) and named buildings outside a site stay their
  own records, unsimplified; a landmark's native pieces share its record.
- Levels (0–64 m) set the simplification: lines ≤ level/4 (at most 4 m), areas ≤
  level/4 (at most 8 m), buildings ≤ level/4 (at most 1 m). A level repeating the
  tolerances of a larger one (32 m after 64 m) is not built. Levels whose line
  tolerance is equal (16–64 m) share one derived road space: road-trimmed sources,
  landmark records and paint are built once and charge the same work budget.
- Levels are built largest first; the first that converts is kept, with limit
  warnings when it misses a target (output counts, Editor bytes, work or partition
  budgets), since a smaller level only keeps more vertices. A smaller level is built
  only when a larger one fails conversion or a typed topology check (for example an
  unreviewed building inside road space); a hard ceiling fails the whole import.
  Building a new road space drops the exclusions of the replaced one, so review
  lists only the kept candidate's exclusions.
- A building above other features (a positive integer `layer`, for example over
  tracks or a stream) stands on the ground and is counted as an estimate in review.
  It is also cut around source-height bridge and tunnel corridors (their width plus
  2 × 20 map cm for safety furniture), and no building grows back into those corridors.
  Outline ways of such a building relation are lifted with it. Roof canopies,
  barriers such as toll booths, structures and underground (negative-layer)
  buildings stay excluded.
- Buildings are cut around road space with 10 map cm clearance (0.1·D m; 0.8 m at
  1:8), including a disk of √2 × the widest half width + that clearance around every
  junction node (the extent of a junction surface; its 16-gon circumscribes the
  circle) and, at every inside corner between adjacent road arms, MapKit's curb
  fillet (radius clamp(0.15 × width, 20, 100) map cm, tangent R / tan(φ/2) from
  the edge corner) plus that clearance; simplification never regrows
  into either. Overlapping or touching footprints of different sources are
  partitioned with 2 map cm clearance (0.02·D m), favouring taller/named geometry,
  so they stay visibly separate; an enclosed source keeps its ID/name in the
  enclosing volume with an estimated height. Complex polygons split into native
  pieces with 4 map cm separation (0.04·D m); pieces meeting at a point keep 2 map
  cm. Region crops drop cut pieces shorter than one map centimetre.
  Numeric failures keep the original geometry; a source erased by quantization
  returns as its road-trimmed shape on the map-centimetre lattice.

## Urban ground and barriers

- Adoption sets the map's `ground_surface` to concrete when it has none, so
  unpainted city terrain is paved; a map with another surface keeps it (warning).
  Undo restores the previous value.
- Green land paints grass: `leisure` park, garden, playground and pitch, `landuse`
  grass, meadow, recreation_ground, village_green, cemetery, farmland, orchard and
  forest, and `natural` grassland, scrub and wood. `amenity=parking` (not
  underground, multi-storey or rooftop) paints asphalt. A tagged hard surface
  (asphalt, concrete, gravel, dirt) wins over grass. City-only areas (green leisure,
  parking, school/hospital/university/college grounds) are rule inputs: they map to
  their paint and barriers but are not generation regions; ones off the ground
  (bridge, tunnel, layer, level) are not selected, and ones that cannot be imported
  are skipped, never excluded.
- Area paint simplifies like other areas (level/4, at most 8 m) and shares the
  pedestrian paint cells and limits: pedestrian ribbons first, then asphalt,
  concrete, gravel, dirt and grass, each minus water and everything painted before
  it with a 2 map cm margin (lattice snap rounding never closes it), so pieces never
  overlap. Area pieces under one map square metre are not painted, and exactly
  collinear vertices are dropped from every piece. Buildings stand on top and roads
  keep precedence natively. Each piece maps to the area sources it covers.
- MapKit checks surface areas pairwise within touching bounds and charges that work
  to the shared road work budget the game enforces; a large green city can exceed
  it (the Editor warns that the game refuses the map).
- Explicit barrier ways become `barriers`: `hedge` 0.8 m, `wall` and
  `retaining_wall` walls 2.0 m, `fence` its `height` tag or 1.2 m (fence types
  such as chain_link keep 1.2 m), `guard_rail` a 0.8 m fence, skipped where at least
  half of it lies on a bridge deck. Barrier ways off the ground are not imported.
- Every barrier opens where a walking or painted way (footway, path, painted
  driveway or aisle) crosses it, by half that way's width + 2 m each side, and at
  gate nodes on its way or site outline (`barrier` gate, lift_gate, swing_gate,
  sliding_gate 3 m; entrance, kissing_gate, turnstile, stile, bollard,
  cycle_barrier 1.5 m; a `width` tag wins). Explicit stubs under 0.5 m are dropped.
- Inferred perimeters: landuse=residential with at least two `building=apartments`
  (or residential buildings ≥ 20 m tall by `height` or 3 m per level) and ≥ 15 %
  building coverage gets a 1.2 m fence; school, hospital, university and college
  grounds a 2.0 m fence; industrial land a 2.0 m wall. The perimeter follows the
  source outline (never a crop cut) with the same openings, minus building
  footprints (0.3 m) and within 3 m of an explicit barrier; pieces under 2 m are
  dropped. MapKit gates vehicle roads.
- Heights are source metres ÷ D (whole map cm, 10–1000); thickness is hedge 0.6 m,
  fence 0.1 m and wall 0.3 m ÷ D within 5–100 map cm. Lines simplify by 0.5 m and
  snap to the map lattice. Each barrier is one object and maps to its way or site.
  A skipped guard rail, a way wholly inside its openings or one shorter than a map
  centimetre is listed as dropped; review shows dropped sources and the skipped
  barrier ways and city-only areas, and adoption checks that dropped sources are
  never imported and come from the cropped barriers.

## Review and adoption

Review reports before/after objects and positions, gaps/tolerances, building records, barriers and ground paint, width/material
estimates, painted pedestrian ways, road cuts and overlap changes. A compact table maps every supported source
to contiguous output records; missing, duplicate or excluded claims fail validation.
No supported source is dropped to fit a limit. A building entirely inside derived road
space fails that candidate with its source ID unless exclusion review is enabled; then
the whole source is excluded with a warning and the inspected-exclusions checkbox is
required.

Every map cell is generated sequentially before review and adoption (warning above
256 cells, at most 16,384); after 120 s a running-time warning appears and Cancel
remains. Batches of 16 reuse native preparation. The Map authoring
page exposes cell size: smaller cells reduce per-cell work without changing extent or
scale. Terrain tiles and assembled tracks block resizing. Resizing is one Undo command.
If protected geometry cannot be preserved, the whole candidate fails.

## Limits

| Bound | City profile: warning above |
| --- | --- |
| Source work | 250,000 features, 2 million positions/entities, 4 million references, 256 MiB selected JSON |
| Output | 100,000 features, 800,000 positions, 180,000 records, 32 MiB wire and Editor JSON |
| Partition depth | 16 building / 32 paint levels (refused at 24 / 48) |
| Shared | 50 warning samples (limit warnings always kept), whole-candidate native validation, 16 MiB retained Undo |

Exceeding a bound records a limit warning; a larger adoption is applied without
Undo ([DOCUMENTS](DOCUMENTS.md)). Output above the 32 MiB document warns that the game
refuses the map; MapKit's native 200,000-object / 1 million-vertex document gate
still refuses. Large-PBF scanning shares the disk index of the exact profile; the
20,000-feature selection warning applies only to exact mode. City approximation never
supplies missing structural heights or repairs invalid original topology.
