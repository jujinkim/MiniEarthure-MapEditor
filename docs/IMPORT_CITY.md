# Automatic city optimization

PBF streaming enables **Automatic city optimization** by default; turn it off
for the exact profile in [IMPORTS](IMPORTS.md). This is an Editor-owned derived
approximation with no city-specific coordinates and no change to the original PBF.
It separates larger bounded source work from the smaller output MapKit accepts.

## Real-city maps: wizard and recipe

**Create → New real-city map…** (`real_city_wizard.gd`) and the headless
`-- --real-city-recipe recipe.json [--report report.json]` user argument run the
same steps (`real_city_recipe.gd`, Editor tool format v1): new free-roam map
(terrain 0, `cell_cm` default 12800) → PBF areas found by exact name (optional
`source_id`/`admin_level`) → city import at 1:`scale` with review exclusions and
`traffic` → adopt → optional facility CSV (`facilities`) → optional Copernicus
`dem` folder (mosaic over the imported frame, grounded buildings) → save to
`project` → Export to `package` (`full_check` default true; `mobile_check` opens it
under the 1.5 GiB phone budget). Recipe keys outside that list are refused; paths
are relative to the recipe file. Every step keeps its review and limits; a step
that fails stops the run with `failed_step` and the status text (exit code 1). The
wizard saves its settings as a recipe. Recommended: 1:3, 128 m cells, one district.

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
Simplification levels, tolerances, the 256 m record tiles, barrier heights and
structure estimates (6 m levels, 8 % ramps) stay in source metres; city tree
spacing is in map metres like the trees. 1:8 keeps its
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
- Vehicle roads take game road-class profiles in map centimetres (the car is
  about 61 cm wide), applied after dual carriageways merge on their source widths:
  lanes × 120 cm + both edges, at least the class floor. Lanes come from `lanes`
  (capped per class) or the class default; `width` tags do not set vehicle roads.
  One-way roads use half the default and maximum lanes (at least one). Painted
  lanes are always 120 cm; the rest of the width is shoulder, so minor classes
  get wide edges, and estimated bridges and tunnels add 60 cm per side
  (source-height structures keep their class width: their junction mouths are
  separated by the source geometry).

  | Class | Default / max lanes | Edge | Floor |
  | --- | --- | --- | --- |
  | motorway, trunk | 4 / 8 | 40 | 520 |
  | primary | 4 / 8 | 30 | 500 |
  | secondary | 4 / 6 | 30 | 500 |
  | tertiary | 2 / 4 | 30 | 300 |
  | unclassified, residential, road, busway | 2 / 2 | 80 | 400 |
  | living_street | 2 / 2 | 65 | 370 |
  | service | 1 / 2 | 60 | 240 |
  | track | 1 / 1 | 50 | 220 |
  | `*_link` | 1 / 2 | 25–30 | 200 |

  A one-way floor is max(one lane + edges, half the floor + one edge). A merged
  road keeps its source median gap plus two one-way profile carriageways. Walking
  ways and other classes keep `width` or lane estimates (lanes × 3.25 m + 0.5 m,
  else class estimates), widened to at least 20 map cm (0.2·D source m); source
  surfaces map to game materials.
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
  alone, as may any pair whose centres lie closer than half their summed one-way
  profile widths (they would overlap on the map). A slip road beside its carriageway runs the same way and never pairs. No building, water or
  other road may lie between the carriageways; median links, U-turns and junction
  pieces joined only to the pair are absorbed. The merged centreline is the
  midline: the first carriageway's nodes move to it with every incident road, the
  second's rung nodes are renamed to them and a side road meeting only the second
  carriageway gets its own midline node. Width is both carriageways plus the
  median per segment (then profiled as above), `lanes` their sum (at most 8), `oneway` is removed. Every
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
- Road markings paint the profile's lane count (merged: both carriageways) at
  `lane_width_cm` 120 on motorway to tertiary, `*_link` and two-way residential
  streets; unclassified roads only when tagged with `lanes`. Center lines on
  two-way roads with an even lane count, edge lines (bounding the lanes, shoulder
  outside) on motorway, trunk, primary and every bridge and tunnel, asphalt or
  concrete only.
  Residential streets carry no junction stop lines, arrows or generated signals.
  A junction end (three or more roads) gets a crosswalk when a `highway=crossing` node on the road or a `footway=crossing` way across it
  lies within max(15 m, √2 × the widest half width + 10 m). A marked road and its
  marked two-arm neighbours stay within the 128 centre-line paint segments MapKit
  draws joined per road and cell. The importer counts whole records (a fillet arc
  per vertex, half a join arc at two-arm ends), an upper bound on MapKit's count,
  which also merges every road's almost-collinear samples within one source
  centimetre, so for any cell size: longer records split at source nodes (at most
  42 segments beside marked neighbours), a record that cannot split keeps no
  markings, and adoption refuses a layer over the bound. Edge-line exteriors are
  not counted. A road whose paint still exceeds 128 segments in a cell loses its
  paint there (Authoring warning `road_paint_segments`; an over-cap join falls
  back to each road's own path, `road_paint_join`) and the cell still loads.
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
  source-height graph, so estimated structures meet flat terrain. Adopting a DEM
  afterwards fits them to it ([IMPORTS](IMPORTS.md) DEM mosaics); importing such a
  city onto a map that already has terrain heightmaps is refused.
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
  An estimated bridge end that meets no other vehicle road gives the outer part
  of its level lead to a ground road (split at a synthetic node ref 8·10¹⁸ + the
  end ref), so no deck cap rail crosses a ramp foot; the deck keeps half its own
  end width + 1 m of level lead for its junction mouth, and a shorter lead stays
  whole.
  Estimated structures join ordinary ground roads, stay whole at crop edges with
  every way of their chain, keep
  building clearance plus 20 map cm (0.2·D m) of safety furniture each side (also when widened) and are
  listed in `osm_estimated_structures`. Other crossing structures need explicit
  heights and are otherwise excluded.
- Compatible vegetation polygons are unioned. Illustrative city trees
  (`builtin:city_tree`, MapKit's widest 200 cm zone footprint with 30 cm clearance,
  drawn as broad park crowns about 3.1–3.9 m across; placed city trees keep
  120 cm) grow
  in MapKit vegetation zones: forests and orchards every 5 map m at 750 ‰, parks (park,
  garden, recreation ground, village green) every 7 map m at 450 ‰ and grass areas
  of at least 300 source m² every 9 map m at 300 ‰, on their grass paint and clear
  of paths, roads, water and buildings; they are estimates, not surveyed trees.
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
  category is the facade below. Names of grouped buildings are kept as the
  record's names. Landmarks (historic, tourism or amenity tags, ≥40 m,
  public/hospital/school/church use) and named buildings outside a site stay their
  own records, unsimplified; a landmark's native pieces share its record.
- Facade (`material`, `usage`, `roof`; the MapKit v1 values) follows the first
  matching rule on the `building` value, use tags, height and enclosing site:
  public (`public`, `civic`, `government`, school/university/college/kindergarten,
  hospital, places of worship, stations, stadiums, museums, libraries, or an
  `amenity` of those kinds) → concrete public; `apartments`, `dormitory` or
  `building:flats` → concrete residential; `house`, `detached`, `terrace`,
  `semidetached_house`, `bungalow`, `villa`, `cabin`, `hut` → brick residential;
  `commercial`, `retail`, `office`, `hotel`, `supermarket`, `kiosk`, `shop`,
  `mall`, any `shop`/`office` tag or other `amenity` → concrete commercial;
  `industrial`, `warehouse`, `factory`, `manufacture`, `service`, `garage(s)`,
  `hangar` → concrete industrial and `greenhouse`, `barn`, `farm_auxiliary`,
  `shed` → wood industrial; otherwise the enclosing site decides
  (commercial/retail → commercial, industrial → industrial, school/hospital/
  university/college → public, residential below 12 m → brick residential), and
  everything else is concrete residential. A tagged `building:material` replaces
  the rule's material (brick → brick, wood/timber framing → wood, concrete,
  plaster, stone, glass, metal → concrete). A missing `height` is estimated as
  3 m × `building:levels`. Inside an apartment complex (a residential site with
  at least two `building=apartments`), an untagged apartment, residential or `yes`
  building of at least 250 m² gets a seeded storey count instead: the site's base
  (15–35 storeys) varied by its seeded spread (±5–10), clamped to 10–50 storeys of
  3 m. Every other untagged building gets seeded storeys of its category (stable
  per source ID): houses 1–2, residential under 250 m² 2–5 and larger 3–7,
  commercial under 200 m² 2–4, under 1,000 m² 3–6 and larger 4–8, public 2–5,
  industrial 1–3; the facade rule then sees that height, so a low untagged
  residential building can become brick. Tagged `height` or `building:levels`
  always wins. `roof:shape=gabled` keeps a gable roof only on a solid
  whose final footprint is an axis-aligned rectangle (MapKit's gable rule); other
  solids and records are flat. Rule-assigned uses, level heights and every
  material/roof count as estimates in review; the source value stays in the
  source file. The renderer draws storeys, panes, night windows, a 1.5-floor shop
  storey on commercial buildings (door, mullioned display windows and a fascia
  sign per slot) with whole storeys fitted below the eaves (a commercial solid of
  L ≥ 3 whole levels shows the shop storey and L − 2 taller storeys, two levels a plain
  parapet), and a record palette (one site and category shares
  its wall body, roof colour, pane pattern and, for apartment complexes, accent
  columns and base storey) that the distant mesh keeps at every distance
  ([MapKit materials](../addons/mapkit/docs/RICHER_MATERIALS.md)).
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
  circle) and, at every inside corner between adjacent road arms (junction
  arms and the two segments at a bend within a road), MapKit's curb
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
- Water: OSM water areas (`natural=water`, `landuse=reservoir|basin`) plus
  waterway lines (`waterway=river|canal|stream|drain|ditch`, on the ground; culverts
  and other off-ground ways are skipped) as ribbons of their `width` (else river
  12, canal 8, stream 3, drain 2, ditch 1.5 m; at least 150 map cm) become
  `water_bodies`. Ground vehicle roads with their sidewalks and clearance and
  walking ways are cut out, the union is cut per 128 map m like paint into
  hole-free pieces of at most 256 vertices (under one map square metre dropped),
  and each piece maps to the sources it covers. Surfaces are 8 map cm below the
  ground and 60 cm deep (estimates), so water never floats above its bank; MapKit
  sinks an earth basin under OSM-city water when it generates ground
  ([MapKit water](../addons/mapkit/docs/WATER.md#real-city-earth-basins)). A DEM
  then sets the levels and cuts sloped narrow streams into stretches that step
  down their course over earth lips ([IMPORTS](IMPORTS.md)). A waterway wholly under roads is
  disclosed as dropped.
- Places: tagged standalone OSM nodes inside the crop rectangle are collected
  while streaming. Named ones (stations, attractions, historic sites, hospitals,
  universities, public offices, schools, shopping, parks and sports, worship,
  hotels, fuel, food, shops) and named landmark buildings (historic, tourism or
  amenity tags) inside the crop window become map `pois` (category, OSM name;
  ranked by category weight, one per name, at most 400; IDs keep the rank order).
  Bus stops, stations, subway entrances, traffic signals, stop/give-way nodes and
  `natural=tree` nodes are kept by position in `osm_street_points` for generated
  street furniture, road signs and street trees; a tree carries a species hint
  from its genus, species, taxon or name (ginkgo, zelkova, plane, cherry, pine;
  `leaf_type=needleleaved` → pine; else `tree`). Places outside the final map
  rectangle are dropped. A road's `maxspeed` (km/h or `KR:urban`; a chain takes
  the speed covering most of its length and never breaks at a speed change), OSM
  class and name reach the road-sign and street-tree rules in memory only; the
  layer stores none of them.
- Road convention: the OSM panel's driving side (right/left) and signal style
  (horizontal/vertical) become `MapDocument.traffic` on a map without one. Marked
  roads above residential get `stop_lines` (stop lines and lane arrows at junction
  ends); marked roads keep their `one_way` direction.
- Street furniture (`osm_furniture.py`, MapKit builtins at game scale, fixed
  seeds, positions from OSM): a signal pole per inbound arm at junctions of
  three or more vehicle roads where two roads with stop lines meet or an OSM signal node lies
  within 15 m (the driver's near-side corner, the head over the road); a bus shelter
  facing the road at each bus stop, subway entrances and station signs beside the
  nearest road; parks (park, garden, playground, recreation ground, village green)
  get benches and shrubs on seeded jittered grids (their trees are zones above). Every piece keeps clear of
  road corridors with sidewalks (+30 map cm), junction mouths, buildings, water and
  other pieces (+10 cm); a candidate without a free spot is skipped and counted
  (at most 24,000 placements per layer, `over_limit` beyond). Places and furniture
  follow the mapped records in the layer.
- Road signs (`Furniture.road_signs`, after the street furniture and before the
  street planting, so earlier placement IDs never move; a solid post or pole, the plate facing the arriving traffic on
  the driver's side, never beside bridges, tunnels or elevated roads; set back
  along the road's centreline, not its first segment, and facing its tangent
  there), in order: OSM stop/give-way nodes on the arm they stand on (at most 40
  map m before its junction, else skipped and counted); overhead guide signs 20 map m
  before signalled junctions of two or more arterials (stop lines and 4+ lanes,
  2+ one-way lanes or edge lines) on approaches of 30 m or more with sidewalks up
  to 1 m whose half carriageway the 2.6 m arm spans (right-hand traffic only: the
  arm reaches along local +x); crossing signs before painted crosswalks of
  unsignalled junctions; stop signs (yield on oblique or one-way arms) on the minor
  arms of unsignalled junctions of three or more painted roads with a through pair
  (Y junctions get none); children-protection signs where painted roads other than
  motorways and trunks (and their links) enter a school zone (school sites +30 m,
  school places +40 m), with a 30 sign 4 m inside on roads with stop lines;
  speed-limit signs on roads with stop lines, 10 m after
  each record's start and every 250 m per direction: the OSM `maxspeed` rounded
  down to 30/40/50/60/80/100 (below 30 none), else the class default (motorway 100,
  trunk 80, primary to tertiary 50, links 40; residential and service roads none),
  30 in school zones (not on motorways and trunks). Speed, children and guide sign
  poles keep 5 m from signal poles and skip a same-kind sign facing the same way
  nearby (120 m speed and guide, 60 m children). Per-kind caps (guide 250, crossing 400, stop 250, yield 150, children
  250, speed 700) and 1,500 signs per layer count `skipped_<kind>_limit` and
  `skipped_road_signs_limit`. The summary reports road-sign skips (no free spot,
  limits, stop/give-way nodes without a junction road in reach) on its road-sign
  line, apart from the street furniture.
- Street trees and flower beds (after the road signs, in this order, so earlier
  placement IDs never move; generated, not surveyed):
  - Street trees (`Furniture.street_trees`, MapKit `builtin:street_tree_*`): on
    vehicle ground roads with a sidewalk of at least 60 map cm whose OSM class is
    trunk, primary, secondary or tertiary (painted lanes ≥ 2 when the class is
    unknown; links excluded) and at least 5.4 map m long. Pits stand on both sides
    every 270 map cm from the record's start (facing pairs), centred 28 map cm
    beyond the carriageway edge of the segment at the station (MapKit sidewalks
    follow each segment's width) and turned with the road (the 40 cm pit square
    MapKit reserves turns with the placement). The first and last stations keep
    the junction mouth + 60 map cm (+2.5 m before a painted crosswalk) or 135 map
    cm at a free or two-arm end. A pit must be clear of every carriageway (not
    sidewalks), buildings + 10 cm, water, barriers, junction mouths and other
    pieces. Skipped and counted (`skipped_street_trees_<reason>`): the median side
    of a one-way road facing an opposite one-way carriageway within 6 map m
    (`median`), within 3 map m of a bus shelter, subway entrance or station sign
    (`stop`), within 1.5 map m of a road-sign post (`post`), within the crown +
    1.5 map m of a signal or guide-sign pole (`pole`), a crown disc touching a
    building, a bridge/tunnel/elevated corridor (+50 cm) or tall furniture, or an
    earlier street tree or median pine closer than the larger of the two crown
    reaches, as on the inside of bends and across joins (`crown`), a pit not
    clear (`blocked`). One species per street (the OSM name,
    else the record): ginkgo 30, zelkova 22, cherry 20, plane 18, pine 10 by fixed
    seed, pine only on sidewalks of 1 map m or more (else ginkgo); a record whose
    free pits fit the preferred crown less than 75% of the time takes the narrow
    ginkgo. OSM trees within the sidewalk + 3 map m of such a road are placed
    first at their own position along it (`street_trees_osm`, the species hint
    kept, else the street's; `skipped_street_trees_osm_reach` beyond) and drop
    stations within 0.6 × 270 map cm.
  - Median beds (`Furniture.median_beds`, `builtin:median_bed`, and
    `builtin:median_bed_pine` on alternate pieces where a pine crown fits): one-way
    painted ground roads with 2+ lanes that face an opposite one-way carriageway
    within 6 map m on the median side (left of travel, right in left-hand
    traffic) get 300 × 80 map cm beds every 330 map cm, 18 map cm beyond their
    sidewalk (at the segment's width), 15 map cm clear of every carriageway and
    off every sidewalk, the partner's median-side sidewalk included
    (`skipped_median_beds`); a pair fills its median once (pieces over the
    partner's bed are left out).
  - Planters (`Furniture.planters`, `builtin:planter`): on the street-tree roads,
    midway between tree stations every fourth gap, on each side by fixed seed (one
    in two), where a building lies within 3 map m behind: inside the outer band of
    sidewalks of 1 map m or more (5 map cm from the edge), else just beyond the
    sidewalk (at the segment's width), off other roads' sidewalks. Closed pedestrian areas (plazas) reach the importer only as ground
    paint, so they get no planters (`builtin:planter_square` stays unused by the
    importer).
  - Caps: street trees 14,000, median beds 1,500, planters 1,500 per layer
    (`skipped_<kind>_limit`). The summary reports them on a line of their own.
  DEM adoption with building grounding also stands imported furniture on the terrain.
- Play area: with selected administrative areas, the crop window (rectangle ∩
  areas; its 16 largest outer rings, holes dropped) is simplified to at most 512
  vertices per ring on the 1:D lattice (`osm_play_area`). Adopting onto a map
  without a play area sets `play_area` to those rings ÷D, clipped to the final map
  rectangle; vehicles stop and the edge is drawn at it. An empty free-roam map,
  like an empty track project, fits its rectangle to the data (+16 m, whole cells).
- MapKit checks surface areas pairwise within touching bounds and charges that work
  to the shared road work budget the game enforces; a large green city can exceed
  it (the Editor warns that the game refuses the map).
- Barrier heights on the map are the source heights below ÷D (at least 10 map cm),
  at the scale of the city around them (at 1:3 a 1.2 m fence is 40 map cm, a 2 m
  wall 67 map cm and a 0.8 m hedge or guard rail 27 map cm).
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
space, or road-trimmed to a remainder smaller than the map lattice, fails that candidate with its source ID unless exclusion review is enabled; then
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
