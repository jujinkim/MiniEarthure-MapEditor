# Automatic city optimization

PBF streaming enables **Automatic city optimization** by default; turn it off
for the exact profile in [IMPORTS](IMPORTS.md). This is an Editor-owned derived
approximation with no city-specific coordinates and no change to the original PBF.
It separates larger bounded source work from the smaller output MapKit accepts.

## Real-city maps: wizard and recipe

**Create → New real-city map…** (`real_city_wizard.gd`) and the headless
`-- --real-city-recipe recipe.json [--report report.json]` user argument run the
same steps (`real_city_recipe.gd`, Editor tool format v1): new free-roam map
(terrain 0, `cell_cm` default 12800) → extent → city import at 1:`scale` with
review exclusions and `traffic` → adopt → optional facility CSV (`facilities`) →
optional [regional composition](REGIONAL_SOURCES.md) (`regional`) → optional Copernicus `dem` folder (mosaic over the imported frame, grounded
buildings) → save to `project` → Export to `package` (`full_check` default true;
`mobile_check` opens it under the 1.5 GiB phone budget). The extent is exactly one of `center: [longitude, latitude]` with
`radius_km` (default 2, at most 2.5 source km), `place` (a named feature supplying that
centre), `areas` (explicit administrative union) or `bbox` (explicit rectangle).
A centred extent has `shape` `circle` (default) or `square` (side 2 × `radius_km`,
so at most 5 km). The wizard ([CITY_SOURCES](CITY_SOURCES.md)) provides the centre from
web search, a map pin or typed coordinates, the shape and radius, and either downloaded
snapshots or local files that pass the same coverage check.
The circle uses WGS84 distances, keeps its full requested radius, and is stored
in existing v1 `play_area` rings with less than 1m source-distance approximation
error. The square is axis-aligned in the map's UTM frame around the centre (crop
`region` `wgs84-square-v1`) and stored as its four corners; a square crossing the
centre's UTM strip is refused. Load guidance scales measured 2km-circle runs by
source area (`real_city_auto.gd` `estimate`); a larger extent warns that
generation, loading and phone memory grow with it. Source coverage, projection and memory failures are reported explicitly.
Optional `road_overrides` supplies `{osm_sha256, ways: [{source_id, width_m, lanes, segments}]}`
(width and lanes together, segments, or both). A segment `{from_node, to_node,
max_displacement_m, points}` re-routes the way between two adjacent source nodes
through 1–256 `[lon, lat]` points that advance along the segment and stay within
`max_displacement_m` (≤5 m, measured in the map's UTM frame) of it; source nodes and connections are kept, inserted
vertices take synthetic refs (never junctions) and keep every vertex through
generalization.
Optional `regional` supplies profiles, source-bound corrections and pinned local
WorldCover/Overture snapshots; its source priority and grouping rules are described
in [regional source composition](REGIONAL_SOURCES.md). The building inference and
road-trimming rules below describe imports without that optional regional input.
Each unique OSM `way/<id>` correction must match the captured PBF SHA-256 and
a selected vehicle road; all targets are checked before any change. The report
retains original and corrected dimensions and segment geometry, and the request enters the input
fingerprint. A missing target, malformed value or changed snapshot fails generation.
PBF review waits for the source worker to finish, fail or be cancelled, without
an elapsed-time limit. A long source import retains ownership of its outputs
and cannot become a completed recipe while its worker is still active.

Recipe keys
outside that list are refused; paths are relative to the recipe file. Every step
keeps its review and limits; a step that fails stops the run with `failed_step` and
the status text (exit code 1); an ambiguous name lists `area_candidates` or
`place_candidates`. When a recipe requests a DEM, its review and adoption must
succeed; a failed fit stops the build atomically. The report records the chosen
`extent`, `place` and `traffic`
(with its `basis`). It also records what the run was built from and with:

- `inputs`: the adopted sources as role, bytes and SHA-256 (OSM PBF, facility CSV,
  each DEM tile), the OSM crop `bbox`, sorted area `source_id`s, shapely/GEOS and
  pyproj/PROJ versions, 1:D, the authored-units profile, `cell_size_cm`, the map's
  `driving_side`/`signal_style`, the facility settings without the CSV path and,
  when the recipe names a `dem` folder, `dem` (`zero_m`, `skipped`). Regional
  input descriptors, profiles and corrections are retained under each OSM input. Paths, file
  names and the check-only keys (`full_check`, `mobile_check`) are left out, and
  attribution order does not matter. `source_names` lists the file names beside it, outside the hash.
- `input_fingerprint`: SHA-256 of `inputs` as JSON with sorted keys and full
  precision; `input_id` is its first 16 hex digits. A run that stopped before OSM
  was adopted has no fingerprint (`input_fingerprint_reason: "no OSM adopted"`);
  a stop at `outputs` adds none of these fields, because the open map may be the
  user's own.
- `code`: `editor_scripts`, the SHA-256 of `scripts/*.{gd,py}` and
  `scripts/importers/*.py` with the framing of the root
  `scripts/implementation_fingerprint.py` (sorted relative names, CRLF → LF, 8-byte
  little-endian length before each name and content), the `godot` version, and
  `mapkit`, the loaded MapKit library's build fingerprint
  (`MapKitBridge.build_fingerprint()`: MapKit Rust sources, schemas and Cargo
  files; empty with `mapkit_reason` if MapKitBridge is not registered or the
  library has no such method). Python
  packages other than the versions in `inputs` are not covered. An exported Editor
  holds tokenized `scripts/*.gdc` instead of `.gd` and hashes those bytes, so its
  digest differs from a source checkout. A script that cannot be read leaves
  `editor_scripts` empty with `editor_scripts_reason`.

The same `input_fingerprint` tells runs from the same sources and settings apart
from runs with other inputs; compare `code` to see whether the Editor or MapKit
code changed. A MapKit native change keeps `input_fingerprint` and
`editor_scripts` and shows in `code.mapkit`. Reruns of one recipe usually
differ by code, not by input, so the fingerprint does not name run folders. The
wizard saves its settings as a recipe. Recommended: 1:3, 128 m cells, 2km source radius.

A failed headless run sets its outputs aside before it quits
(`set_aside_failed`): the package is renamed `<package>-failed` (`.memap-failed`,
outside the `*.memap` file filter) and then the `project` folder
`<project>-failed`, listed in the report's `failed_outputs`. Nothing is deleted.
The project moves only once the run saved its `document.json` there, so a folder
that already existed keeps its name after an earlier stop; a project folder that
is or holds the recipe or report keeps its path and records `set_aside_error`.
A stop at `outputs` (an earlier run's files) moves nothing. A step that timed out
with its job still running, or an existing `-failed` target for either output,
moves neither and records `set_aside_error`. Only those two paths are renamed;
the folder around them, the recipe and the report keep their names. The wizard keeps a failed map
open under its paths so it can be fixed and retried.

### Automatic extent, traffic and architecture

`real_city_auto.gd` turns the PBF lookup ([IMPORTS](IMPORTS.md#choosing-a-geographic-area))
into Editor defaults; explicit values always win.

- Places: the wizard's search lists matching administrative areas and named
  features whose name (or `name:ko`/`en`/`ja`, official, alternative, international,
  short or local name) is exactly the query, settlements before landmarks before
  other features. A recipe `place` takes the `source_id`, else the only candidate of
  the best kind.
- Extent of a place: a circle of the requested `radius_km` around the selected
  point, independent of administrative size. The scan rectangle is conservative;
  geometry and playable bounds use the circle. A failed budget never shrinks it.
- Traffic: a `traffic` key left out (wizard: **Automatic**) follows the country of
  the area or place: the `driving_side` tag of its country boundary, else the
  Editor's list of left-hand-traffic ISO countries; horizontal signals in Japan,
  both Koreas and Taiwan, vertical elsewhere; white centre lines in Japan, most of
  Europe (not Norway, Finland or Iceland), the UK and Ireland, Oceania, India,
  Southeast Asian Commonwealth states, Turkey, the Maghreb and South Africa, yellow
  elsewhere. `centre_line` (`yellow`/`white`) is the recipe key; the OSM panel has
  the same choice, and only white is stored in the document. The country is the containing
  country boundary, else the ISO 3166-2 code of a containing subdivision (regional
  extracts cut country boundaries), else the extract's only country; a `bbox`
  recipe looks up its centre. An unknown country keeps right-hand traffic,
  horizontal signals and yellow centre lines.
- Architecture: a `regional.profile` without `architecture` takes the country's
  catalogue architecture (`ARCHITECTURES`: Korea `korean_modern`, Japan
  `japanese_modern`, China/Taiwan `chinese_modern`, Singapore/Malaysia `shophouse`,
  France `parisian`, the UK and Ireland `british_terrace`, the Low Countries and
  Denmark `european_brick`, the Nordics `nordic_timber`, Southern Europe
  `mediterranean`, the former Eastern Bloc `east_european_panel`, Latin America
  `latin_colonial`, the US, Canada and Oceania `north_american_suburb`, …); an
  unlisted or unknown country keeps `modern`. The report's `architecture` gives
  the choice and its basis (`recipe`, `country`, `default`). The wizard's
  **Architecture** selector defaults to **Automatic architecture**: it adds a
  `regional` profile with `road_conflicts: "trim_buildings"` (the architecture
  filled when the wizard knows the country). **Plain city buildings** leaves
  `regional` out; a named architecture overrides the country.

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
  (painted ways do not count). Chains keep per-segment widths, lane count,
  painted lane width, directional split and median boundaries; names, refs and
  speeds may vary. Highway class, structure, access, surface, oneway and sidewalk
  changes break them. Directional records are never reversed during joining. Building trims, gap-filling
  barriers and junction clearance use each segment's own width (and sidewalk). Simplification keeps junction positions,
  semantic boundaries and crossings; coincident independent IDs are not welded.
  Ordered source positions and traversal ranges are retained. Structures and
  explicit heights keep the exact rules.
- Equal adjacent centimetre vertices are removed after the single 1:D quantization;
  nonempty holes are never discarded.
- Explicit source `width` sets the carriageway width before the single 1:D
  adoption. `lanes` takes precedence over the sum of `lanes:forward`,
  `lanes:backward` and `lanes:both_ways`; valid counts are never capped by class.
  Directional counts preserve an asymmetric two-way paint split. If lanes are
  absent, or the available width per lane exceeds 4.5 m, the lane estimate uses
  3.25 source metres. Counts beyond the supported 16 fail explicitly.
  With no source width, estimate lanes × 3.25 m + 0.5 m edges plus tagged
  `shoulder:left:width` / `shoulder:right:width`. Default lanes are four for
  motorway/trunk/primary/secondary, two for tertiary/residential/unclassified/
  living streets/road/busway, and one for service/track/links; one-way defaults
  halve the two-way value with a minimum of one.
  Merged medians and tagged shoulders are excluded from painted lane space;
  sidewalks are separate. The report distinguishes source and estimated widths,
  source lanes, width-based lane estimates and author corrections. Walking ways
  keep explicit width or their pedestrian defaults. The v1 quantization minimum
  is 20 map cm; city adoption applies no extra vehicle-width floor.
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
  profile widths (they would overlap on the map). A run whose carriageways part
  more than 75 m (3 × the 25 m median bound) at any vertex between its rungs, for
  example around a park, stays two one-way roads. A slip road beside its carriageway runs the same way and never pairs. No building, water or
  other road may lie between the carriageways; median links, U-turns and junction
  pieces joined only to the pair are absorbed. The merged centreline is the
  midline: the first carriageway's nodes move to it with every incident road, the
  second's rung nodes are renamed to them and a side road meeting only the second
  carriageway gets its own midline node. Width is both carriageways plus the
  median per segment, `lanes` their sum (up to 16), and `oneway=no` explicitly
  preserves both directions even for motorway records.
  Median width is measured across each merged segment; a diagonal connector's
  distance along the street does not widen its lanes. A proposal that newly
  covers an entire building or extends into water is rejected. Partial building
  overlaps use the explicit regional footprint policy, including its rejection
  default and reported cuts; rejecting every partial overlap could expose a
  larger collision on the original carriageways.
  Lane count and lane-space changes bound each paired chain. Every
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
  is the `level` of an entrance node (a building floor, not road height) and the
  `ele` of a ground area, building, barrier or waterway (its ground elevation, set
  on every footprint by bulk building imports; roads and structures keep `ele`). Their source-width
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
- Tunnels and layered ways without source heights and without road crossings
  can retain a disclosed ground-level estimate. Explicit bridges and inferred
  source-water crossings remain structures.
- Supported structures get estimated heights: a chain of bridge (tunnel)
  ways joined end to end rises (sinks) 6 m per layer with ramps of at most 8 % and
  an 8 m level lead at each ground anchor. Where the chain is too short, source
  ground sections continuing it up to a junction or dead end join it as the same
  structure; vertices are added where the profile bends. Source ways are divided
  only at existing junction nodes, retain their parent IDs and keep the remaining
  ground sections. Chain sections have no side
  roads along them, no closed-road contact and no bend over 60° (a bend of θ needs
  neighbouring segments of 12 m · tan(θ/2) + 2 m, so native structure mouths stay
  separate); road crossings keep 5 m of separation and source-water crossings
  keep 2 m of initial deck freeboard; tunnels use 4.5 m clearance. Ordinary walking
  paint below a water bridge uses the fitted terrain, while explicit-height,
  closed and estimated walking structures keep the road separation check.
  DEM fitting independently enforces deck, water and approach continuity.
  A non-bridge chain crossing only excluded structures can be drawn at ground
  level, as can a non-bridge chain crossing only open ground walking paint (not a
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
  whole. A structure end at a source junction MapKit cannot build stays joined to
  its straightest arm ([imports](IMPORTS.md)), so a ramp foot beside a diverging
  frontage or service road keeps no deck cap.
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
  record's names. Landmarks (historic, tourism or amenity tags, a source height
  ≥40 m, public/hospital/school/church use) and named buildings outside a site stay their
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
  3 m × `building:levels`, and so is a tagged `height` below 2.6 m per tagged
  level (an eave or survey height). Tagged neighbours are buildings with a
  `height` or `building:levels` (never an estimate) whose source centroid lies
  within 60 m. Inside an apartment complex (a residential site with at least two
  `building=apartments`), an untagged apartment, residential or `yes` building of
  at least 250 m² gets a seeded storey count instead: the site's base (15–35
  storeys) varied by its seeded spread (±5–10), clamped to 10–50 storeys of 3 m,
  unless at least three tagged neighbours (any use) all stand below 12 m. Every
  other untagged building with at least three tagged neighbours of its use takes
  their median height in whole 3 m storeys ± one seeded storey (at least one);
  the rest get seeded storeys of their category (stable per source ID): houses
  1–2, residential under 250 m² 2–5 and larger 3–7, commercial under 200 m² 2–4,
  under 1,000 m² 3–6 and larger 4–8, public 2–5, industrial 1–3. The facade rule
  then sees that height, so a low untagged residential building can become
  brick; review counts each height rule. Otherwise a tagged `height` or
  `building:levels` wins. `roof:shape=gabled` keeps a gable roof only on a solid
  whose final footprint is an axis-aligned rectangle (MapKit's gable rule); other
  solids and records are flat. Rule-assigned uses, level heights and every
  material/roof count as estimates in review; the source value stays in the
  source file. The renderer draws storeys, panes, night windows, a 1.5-floor shop
  storey on commercial buildings (door, mullioned display windows and a fascia
  sign per slot) with whole storeys fitted below the eaves (a commercial solid of
  L ≥ 3 whole levels shows the shop storey and L − 2 taller storeys, two levels a plain
  parapet), and a record palette (one site and category shares its wall
  finish, glass, signs and, for apartment complexes, accent columns and base
  storey; each solid's wall body, roof colour, pane pattern and bay follow its
  look, the record's or, for the key's `own_share` of solids, its own) that the
  distant mesh keeps at every distance
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
  Building a new road space drops the exclusions and height estimates of the
  replaced one, so review lists only the kept candidate's exclusions and every
  estimate comes from the source and the kept road space.
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
  cm. Region crops drop cut pieces shorter than one map centimetre, and a piece of
  a split building that adoption's whole-centimetre rounding would collapse (a
  sliver under one map centimetre wide) is left out with a warning while its
  source keeps the other pieces; a source whose every solid is such a sliver is
  excluded in review ("thinner than the 1:D map lattice").
  Numeric failures keep the original geometry; a source erased by quantization
  returns as its road-trimmed shape on the map-centimetre lattice.

## Urban ground and barriers

- Adoption sets an absent `ground_surface` to v1 `grass`. Explicit user surfaces
  stay unchanged and Undo restores the previous value. Untagged plains and mountains
  share this natural ground; imported DEM relief drives MapKit's slope-based grass,
  earth and rock shading. Untagged hills do not generate forests.
- Explicit `surface` wins, followed by parking/paved-use estimates, then natural
  land cover. Forests and orchards produce both ground paint and vegetation zones.
  Grassland, scrub, heath, fell and farmland use grass; bare rock, scree and shingle
  use gravel, and sand/beach use dirt. These existing-material approximations are
  disclosed in review. Urban, residential and university boundaries alone leave
  natural ground. Off-ground areas keep their exclusion rules.
- Pedestrian ribbons keep precedence; area paint then follows explicit surfaces,
  use estimates and natural cover, with asphalt/concrete/gravel/dirt/grass as stable
  ties. Each subtracts water and earlier paint with a 2 map cm margin. Paint
  simplifies like other areas (level/4, at most 8 m), partitions on the map lattice,
  drops pieces below one map square metre and keeps source provenance. Buildings
  stand on top and roads keep native precedence.
- Water crossings are decided against original OSM water polygons (including
  island holes) and open waterway ribbons, before road subtraction. Explicit
  bridges retain their structure even without a road crossing. Untagged roads
  crossing water along a connected source-node chain between two land anchors
  receive a disclosed bridge estimate, independent of way segmentation. Branches,
  loops, tangents and water dead ends require review. Ford, culvert/tunnel and embankment
  evidence takes precedence; conflicting tags and unresolved geometry are
  excluded through review. Estimated chains retain connected land approaches,
  bounded grades and road/structure separation. Review and recipe reports list source IDs, chain members,
  land anchors and crossing evidence, including excluded crossings and reasons. Generated road-cut land strips are never land evidence.
- Water surfaces keep their original source shape through bridge corridors;
  ground-road subtraction retains explicit embankments and original land passages,
  while fords keep water continuous. DEM water levels derive from the original
  sampled terrain. Structure fitting then constrains deck undersides above those
  fixed levels and preserves signed structure order, source heights and existing
  edit bounds. Water and structures are one atomic candidate; an infeasible fit
  is rejected without lowering or cutting water to conceal it.

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
  other pieces (+10 cm). Roads other than walking roads count at least 150 map cm
  wide: adoption widens narrower segments towards that floor, and MapKit
  validation keeps placements off every corridor, tunnels included. A candidate without
  a free spot is skipped and counted
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
    sidewalks; per segment, and over MapKit's joint faces where two segments
    meet: the mouths either side of the vertex, set back the larger half width (at
    most 40% of the segment) and as wide as their segments, joined on each side where the two curb lines
    meet, with MapKit's fillet on the inside of a bend, or by a straight edge
    where they would meet behind a mouth, as at a width step) + 2 map cm,
    buildings + 10 cm, water, barriers, junction mouths and other
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
- City streetlights (`Furniture.streetlights`, MapKit `builtin:city_streetlight_*`,
  last of all, so earlier placement IDs never move; generated, not surveyed; OSM
  `street_lamp` nodes are not read): vehicle ground roads whose OSM class is
  trunk, primary, secondary or tertiary or one of their links. Roads without a class
  qualify when they have junction stop lines. Motorways, residential streets,
  alleys, service roads, bridges and tunnels get none. Rows walk chains of records
  through two-arm nodes of the same arrangement (one-way records only in their
  travel sense), so spacing and side continue across record splits. A chain end
  keeps the junction mouth + 60 map cm clear (+2.5 m before a painted crosswalk),
  or 135 map cm at a free end. Stations are centred on the chain:
  - Two-way roads of 6+ lanes get opposite pairs every 10 map m.
  - Two-way roads of 4–5 lanes and one-way roads of 3+ lanes are staggered on both
    sides, 10 map m per side and half a spacing apart.
  - Other roads and links get one side every 11.7 map m. One-way roads use the
    driver's side; two-way roads use the side with more free stations (a fixed
    seed breaks ties).
  - Each pole is a solid 12 cm box. It stands like a signal, 38 map cm beyond the
    road and its sidewalk at the segment's width (30 cm clearance plus the pole).
    Its local +x points over the road. The arm id is the shortest reach (75, 135,
    195, 255, 315 or 375 map cm) that puts the head centre at least 25 map cm
    over the carriageway, so heads sit 25–85 map cm over the outer lane; the
    longest arm serves sidewalks up to 312 map cm (both 20261105c cards stay
    under 300). A wider sidewalk is skipped (`skipped_streetlights_reach`).
  - On the median side of a one-way road facing an opposite one-way carriageway
    within 6 map m, a median narrower than twice the wider of the two
    carriageways' sidewalks + 80 map cm (a centred pole clears both roads'
    sidewalk + 30 cm by its half and 4 cm) gets nothing (`median`). Where both
    heads reach their carriageway, a twin
    (`builtin:city_streetlight_twin_75` or `_twin_135`) stands at the median
    centre. Wider medians get a single lamp at each edge, facing its own road.
  - A station tries itself, then nudges of 27 map cm and the midpoints between
    street trees and median beds within 1.35 map m, nearest first, so arms pass
    between crowns.
  - The pole keeps clear of every road corridor with its sidewalk + 30 map cm
    (per segment, with MapKit's joint faces where segments meet), junction
    mouths, buildings + 10 cm, water, narrow painted walking ribbons (non-grass
    surface areas whose mean width, 2 × area / perimeter, is under 120 map cm:
    a solid pole would stand in a drivable footway) and placed pieces (+4 cm,
    so twins fit the gaps between median beds).
  - The display envelope (the arm + 20 map cm, 25 behind the pole, 8 to each
    side) keeps clear of buildings + 10 cm (`building`), bridge and elevated decks
    + 1.2 map m (`deck`) and street-tree and median-pine crowns (`crown`). Its
    part within 25 map cm of the pole keeps clear of barriers + 10 cm (`barrier`).
  - Poles also keep clear of signal and guide-sign poles by 3 map m (`signal`),
    bus shelters, subway entrances and station signs by 1 map m (`stop`), sign
    posts by 50 cm (`sign`), and other lamps by 1.5 map m and their envelopes
    (`lamp`). Other failures count as `blocked`; a station whose offsets fail
    for several reasons counts the first specific one.
  - A station is skipped when an earlier head facing the same way lies within
    0.6 × the spacing (`covered`; for example, a partner road's twin).
  - The layer budget is 8,000 streetlights within MAX_PLACEMENTS. When the
    stations exceed it, the spacing widens in 5% steps rather than cutting rows
    short (`skipped_streetlights_spacing`). Stations still over MAX_PLACEMENTS or
    the 8,000 budget count `skipped_streetlights_limit`.
  - Counts: `streetlights_opposite`, `_staggered`, `_one_side`, `_twin`. The
    summary reports them and their skips on a line of their own.
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
required. An invalid source area (self-intersecting ring and similar) is excluded the
same way with its validity reason; it is never repaired. An excluded source leaves
with every feature built from it (a wall that is also the outer way of an excluded
multipolygon is not imported either).

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
