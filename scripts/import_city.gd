extends RefCounted
const I18N := preload("./locale_text.gd")
const LIMITS := preload("./limit_warnings.gd")
const UNITS := preload("./import_units.gd")

## A source-metre value of `cm` whole map centimetres at 1:denominator.
static func _map_cm(value: Variant, cm: int, denominator: int) -> bool:
	return (value is int or value is float) and absf(float(value) - cm * denominator / 100.0) < 1e-9

## Validate worker claims and complete source/record coverage before adoption.
static func validate(raw: Dictionary, requested: Dictionary, boundary: Script, notes: Array = []) -> String:
	var meta: Variant = raw.coordinates.get("osm_city")
	if meta == null: return "Missing requested city optimization." if requested.get("osm_city", false) else ""
	if raw.adapter != "osm-extract-v1" or not raw.coordinates.has("osm_stream") or meta is not Dictionary or meta.get("profile") != "scale-aware-city-v1" or not UNITS.valid_denominator(meta.get("scale_denominator")): return "Invalid city optimization profile."
	if not requested.is_empty() and requested.get("osm_city") != true: return "Unrequested city optimization."
	var denominator := int(meta.scale_denominator)
	if not requested.is_empty() and requested.get("osm_scale", UNITS.OSM_DENOMINATOR) != denominator: return "City map scale does not match the request."
	if not _map_cm(meta.get("grid_m"),1,denominator) or not boundary._count(meta.get("gap_m"),64) or int(meta.gap_m) not in [0,2,4,8,16,32,64]: return "Invalid city approximation settings."
	if not boundary._finite(meta.get("line_tolerance_m"),0,4) or not boundary._finite(meta.get("polygon_tolerance_m"),0,8) or not is_equal_approx(float(meta.line_tolerance_m),minf(4.0,float(meta.gap_m)/4.0)) or not is_equal_approx(float(meta.polygon_tolerance_m),minf(8.0,float(meta.gap_m)/4.0)): return "Invalid city approximation settings."
	var count_text := {"before":{"features":"City source features", "positions":"City source positions", "roads":"City source roads", "buildings":"City source buildings", "areas":"City source areas", "barriers":"City source barriers"},
		"after":{"features":"City output features", "positions":"City output positions", "roads":"City output roads", "buildings":"City output buildings", "areas":"City output areas", "barriers":"City output barriers"}}
	for key in ["before", "after"]:
		var counts: Variant = meta.get(key)
		if counts is not Dictionary: return "Missing city geometry counts."
		# Barriers are optional: layers without barriers keep their counts.
		if not counts.has("barriers"): counts = counts.merged({"barriers": 0})
		for field in ["features", "positions", "roads", "buildings", "areas", "barriers"]:
			if not boundary._soft(notes, "city_%s_%s" % [key, field], counts.get(field), (2000000 if field == "positions" else 250000) if key == "before" else (800000 if field == "positions" else 100000), count_text[key][field]): return "Invalid city geometry counts."
		if counts.features != counts.roads+counts.buildings+counts.areas+counts.barriers: return "City geometry category mismatch."
	if meta.after.features != raw.get("feature_count") or meta.after.positions < raw.get("point_count", 0) or not boundary._count(meta.get("protected_buildings"), meta.after.buildings): return "City output count mismatch."
	if not boundary._soft(notes, "city_unmerged_groups", meta.get("unmerged_numeric_groups"), 250000, "Unmerged city groups"): return "Invalid city retained group count."
	if not boundary._count(meta.get("painted_pedestrian_ways"),meta.before.roads): return "Invalid city ground paint count."
	if not boundary._count(meta.get("level_structures"),meta.before.roads): return "Invalid city ground-level structure count."
	if not boundary._count(meta.get("layered_buildings"),meta.before.buildings): return "Invalid city layered building count."
	if not boundary._count(meta.get("estimated_structure_roads"),meta.after.roads) or int(meta.estimated_structure_roads) != raw.coordinates.get("osm_estimated_structures",[]).size(): return "Invalid city estimated structure count."
	if meta.get("vegetation_spacing_m") != 32 or meta.get("vegetation_density_per_mille") != 750: return "Invalid city vegetation estimates."
	if not boundary._count(meta.get("widened_roads"),meta.before.roads) or not _map_cm(meta.get("minimum_road_width_m"),20,denominator) or meta.get("surface_mappings") is not Array: return "Invalid city road approximations."
	LIMITS.over(notes, "city_surface_mappings", meta.surface_mappings.size(), 512, "City road surface mappings")
	var mapped := {}
	var mapped_count := 0
	for entry: Variant in meta.surface_mappings:
		if entry is not Dictionary or not boundary._text(entry.get("source")) or entry.get("target") not in ["asphalt","concrete","dirt","gravel","grass"] or not boundary._count(entry.get("features"),meta.before.roads) or mapped.has(entry.source): return "Invalid city surface mapping."
		mapped[entry.source] = true
		mapped_count += int(entry.features)
	if mapped_count > meta.before.roads: return "City surface mapping count exceeded."
	if meta.get("estimated_road_widths") is not Dictionary or not _map_cm(meta.get("road_clearance_m"),10,denominator) or not _map_cm(meta.get("building_clearance_m"),2,denominator) or not _map_cm(meta.get("polygon_partition_gap_m"),4,denominator) or meta.get("trimmed_building_sources") is not Array or meta.get("overlap_adjusted_sources") is not Array: return "Invalid city road approximations."
	var estimated_width_count := 0
	for kind: Variant in meta.estimated_road_widths:
		if not boundary._text(kind) or not boundary._count(meta.estimated_road_widths[kind],meta.before.roads): return "Invalid city road approximations."
		estimated_width_count += int(meta.estimated_road_widths[kind])
	if estimated_width_count > meta.before.roads: return "Invalid city road approximations."
	if meta.get("source_ids") is not Array or meta.source_ids.is_empty() or meta.source_ids.size() > meta.before.features or meta.get("groups") is not Array or meta.groups.size() != meta.after.features: return "Invalid city source mapping."
	var pattern := RegEx.new()
	pattern.compile("^(way|relation)/[1-9][0-9]{0,19}$")
	var sources := {}
	var excluded := {}
	for entry in raw.coordinates.get("osm_review", {}).get("excluded", []): excluded[entry.source_id] = true
	for source: Variant in meta.source_ids:
		if source is not String or pattern.search(source) == null or sources.has(source) or excluded.has(source): return "Invalid/duplicate/excluded city source."
		sources[source] = false
	for list: Array in [meta.trimmed_building_sources,meta.overlap_adjusted_sources]:
		var trimmed := {}
		for source: Variant in list:
			if source is not String or not sources.has(source) or trimmed.has(source): return "Invalid city road approximations."
			trimmed[source] = true
	if raw.get("patches") is not Array: return "Invalid city output records."
	var barrier_count := 0
	var water_count := 0
	for patch: Variant in raw.patches:
		if patch is Dictionary and patch.get("field") == "zones":
			if patch.get("after") is not Dictionary or patch.after.get("spacing_cm") != 3200 or patch.after.get("density_per_mille") != 750: return "Invalid city vegetation estimates."
		if patch is Dictionary and patch.get("field") == "barriers":
			var barrier: Variant = patch.get("after")
			if barrier is not Dictionary or barrier.get("kind") not in ["hedge", "fence", "wall"] or barrier.get("line") is not Array or barrier.line.size() < 2 or not boundary._count(barrier.get("height_cm"), 1000 * denominator) or not boundary._count(barrier.get("thickness_cm"), 100 * denominator): return "Invalid city barrier."
			barrier_count += 1
		if patch is Dictionary and patch.get("field") == "water_bodies":
			var body: Variant = patch.get("after")
			if body is not Dictionary or body.get("polygon") is not Array or body.polygon.size() < 3 or body.get("islands") is not Array or not body.islands.is_empty() or body.get("flow_cm_s") is not Array or body.flow_cm_s.size() != 2 or body.flow_cm_s.any(func(v: Variant) -> bool: return v != 0) or not (body.get("surface_cm") is int or body.get("surface_cm") is float) or not (body.get("bottom_cm") is int or body.get("bottom_cm") is float) or float(body.bottom_cm) >= float(body.surface_cm): return "Invalid city water."
			water_count += 1
		if patch is Dictionary and patch.get("field") == "buildings":
			var parts: Variant = patch.get("after", {}).get("parts", []) if patch.get("after") is Dictionary else null
			if parts is not Array or parts.size() > 255: return "Invalid city building parts."
			for part: Variant in parts:
				if part is not Dictionary or part.get("footprint") is not Array or part.footprint.size() < 3: return "Invalid city building parts."
	if barrier_count != int(meta.after.get("barriers", 0)): return "City barrier count mismatch."
	var crop: Variant = raw.coordinates.get("osm_play_area", [])
	if crop is not Array or crop.size() > 16: return "Invalid city play area."
	for ring: Variant in crop:
		if ring is not Array or ring.size() < 3 or ring.size() > 512: return "Invalid city play area."
		for point: Variant in ring:
			if point is not Array or point.size() != 2 or not boundary._finite(point[0], -100000000, 100000000) or not boundary._finite(point[1], -100000000, 100000000) or point[0] != floor(point[0]) or point[1] != floor(point[1]): return "Invalid city play area."
	var water: Variant = meta.get("water", {})
	if water is not Dictionary or water_count != int(water.get("pieces", 0)) or water.get("dropped_sources", []) is not Array: return "City water count mismatch."
	for source: Variant in water.get("dropped_sources", []):
		if source is not String or pattern.search(source) == null or sources.has(source) or excluded.has(source): return "Invalid dropped city water sources."
	# Dropped barrier sources (bridge guard rails, below one map centimetre) are
	# disclosed, never also imported, and come from the cropped barrier sources.
	var dropped: Variant = meta.get("barriers", {}).get("dropped_sources", []) if meta.get("barriers", {}) is Dictionary else null
	if dropped is not Array or dropped.size() > int(meta.before.get("barriers", 0)): return "Invalid dropped city barrier sources."
	var dropped_ids := {}
	for source: Variant in dropped:
		if source is not String or pattern.search(source) == null or sources.has(source) or excluded.has(source) or dropped_ids.has(source): return "Invalid dropped city barrier sources."
		dropped_ids[source] = true
	var skipped: Variant = meta.get("skipped", {})
	if skipped is not Dictionary: return "Invalid skipped city inputs."
	for key: Variant in skipped:
		if key not in ["barrier_ways", "city_areas"] or not boundary._soft(notes, "city_skipped_" + key, skipped[key], 250000, "Skipped city inputs"): return "Invalid skipped city inputs."
	if int(skipped.get("barrier_ways", 0)) + int(skipped.get("city_areas", 0)) > int(raw.coordinates.osm_stream.selected.ways) + int(raw.coordinates.osm_stream.selected.relations): return "Invalid skipped city inputs."
	var record_count: int = raw.patches.size()
	var next_record := 0
	var references := 0
	for group: Variant in meta.groups:
		if group is not Dictionary or group.get("sources") is not Array or group.sources.is_empty() or group.get("records") is not Array or group.records.size() != 2 or group.get("name", "") is not String or str(group.get("name", "")).length() > 512 or group.get("estimated_height",false) is not bool: return "Invalid city aggregation mapping."
		if group.has("names"):
			if group.names is not Array or group.names.size() > group.sources.size(): return "Invalid city aggregation mapping."
			for name: Variant in group.names:
				if not boundary._text(name): return "Invalid city aggregation mapping."
		references += group.sources.size()
		var local_sources := {}
		for index: Variant in group.sources:
			if not boundary._count(index,meta.source_ids.size()-1) or local_sources.has(int(index)): return "Unknown/duplicate city aggregation source."
			local_sources[int(index)] = true
			sources[meta.source_ids[int(index)]] = true
		if not boundary._count(group.records[0],record_count) or not boundary._count(group.records[1],record_count) or group.records[0] != next_record: return "Noncontiguous city output mapping."
		next_record += int(group.records[1])
		if next_record > record_count: return "City output mapping exceeds records."
	if false in sources.values() or next_record != record_count: return "Incomplete city source/output coverage."
	LIMITS.over(notes, "city_mapping_references", references, 2000000, "City source mapping references")
	if paint_total(raw.patches, denominator) > PAINT_SEGMENTS: return "City road markings exceed the paint segment bound."
	return ""

## MapKit (road_paint.rs, road_style.rs) refuses more than 128 paint segments
## of a marked road plus its two-arm neighbours per cell, at display time.
## Checked for whole records (any cell size) on the adopted 1:D vertices.
const PAINT_SEGMENTS := 128
const PAINT_ROAD_FLOOR_CM := 150.0

static func _map_point(point: Array, denominator: int) -> Vector2:
	return Vector2(roundi(float(point[0]) / denominator), roundi(float(point[2]) / denominator))

static func _map_width(width: Variant, denominator: int) -> float:
	return maxf(roundi(float(width) / denominator), PAINT_ROAD_FLOOR_CM)

## Points of MapKit's fillet at p (road_plan.rs fillet), without rounding dedupe.
static func _arc(a: Vector2, p: Vector2, b: Vector2, width: float) -> int:
	var la := a.distance_to(p)
	var lb := p.distance_to(b)
	if la < 2.0 or lb < 2.0: return 1
	var u := (p - a) / la
	var v := (b - p) / lb
	var turn := absf(atan2(u.x * v.y - u.y * v.x, u.dot(v)))
	if turn < 0.001: return 1
	var radius := width / 2.0 + clampf(width * 0.15, 20.0, 100.0)
	var tangent := tan(turn / 2.0)
	var r := minf(minf(radius * tangent, 0.45 * la), 0.45 * lb) / tangent
	var step := minf(PI / 18.0, 2.0 * acos(clampf(1.0 - 1.0 / maxf(r, 1.0), -1.0, 1.0)))
	return int(ceil(ceil(turn / step) / 2.0)) * 2 + 1

## Paint path segments of one marked road: a point per free end, a fillet arc
## per interior vertex and half of the join arc at each two-arm end, whose
## neighbour vertex and width are `joins[end]` ([] when the end is free).
static func paint_segments(road: Dictionary, denominator: int, joins: Array) -> int:
	var points: Array = road.points
	var xy: Array = points.map(func(point: Array) -> Vector2: return _map_point(point, denominator))
	var w: Array = road.widths_cm.map(func(width: Variant) -> float: return _map_width(width, denominator))
	var total := 0
	for n in range(1, xy.size() - 1): total += _arc(xy[n - 1], xy[n], xy[n + 1], maxf(w[n - 1], w[n]))
	for end in 2:
		var join: Array = joins[end]
		if join.is_empty():
			total += 1
			continue
		var arc := _arc(join[0], xy[0], xy[1], maxf(join[1], w[0])) if end == 0 else _arc(xy[-2], xy[-1], join[0], maxf(w[-1], join[1]))
		var half := int((arc - 1) / 2.0)
		total += arc - half if end == 0 else half + 1
	return total - 1

## The largest paint total of a marked road plus its marked two-arm neighbours.
static func paint_total(patches: Array, denominator: int) -> int:
	var ends := {}
	var marked: Array = []
	for patch: Variant in patches:
		if patch is not Dictionary or patch.get("field") != "roads" or patch.get("after") is not Dictionary: continue
		var road: Dictionary = patch.after
		if road.get("points") is not Array or road.get("widths_cm") is not Array or road.points.size() < 2 or road.widths_cm.size() != road.points.size() - 1:
			if road.get("markings") != null: return PAINT_SEGMENTS + 1
			continue
		ends.get_or_add(str(road.get("from")), []).append([road, 0])
		ends.get_or_add(str(road.get("to")), []).append([road, 1])
		if road.get("markings") != null: marked.append(road)
	var neighbours := {}
	var estimates := {}
	for road: Dictionary in marked:
		var joins: Array = []
		var others: Array = []
		for end in 2:
			var list: Array = ends[str(road["from" if end == 0 else "to"])]
			var join: Array = []
			if list.size() == 2:
				for arm: Array in list:
					if is_same(arm[0], road) and arm[1] == end: continue
					var other: Dictionary = arm[0]
					var at: int = 1 if arm[1] == 0 else other.points.size() - 2
					join = [_map_point(other.points[at], denominator), _map_width(other.widths_cm[0 if arm[1] == 0 else -1], denominator)]
					others.append(other.id)
			joins.append(join)
		estimates[road.id] = paint_segments(road, denominator, joins)
		neighbours[road.id] = others
	var worst := 0
	for road: Dictionary in marked:
		var total: int = estimates[road.id]
		for id: Variant in neighbours[road.id]: total += int(estimates.get(id, 0))
		worst = maxi(worst, total)
	return worst

static func summary(meta: Dictionary) -> String:
	var denominator := float(meta.scale_denominator)
	var result := I18N.t("Automatic city optimization · 1:%d\nFeatures: %d → %d · positions: %d → %d\nRoads: %d → %d · buildings: %d → %d · areas: %d → %d\nSimplification level: %.2f source m (%.2f map m). Every building keeps its own footprint; landmark/tall buildings, road corridors and courtyards remain protected.\nBuilding heights without source tags are estimates; exact source mappings are retained.\nRoad surfaces are game-material approximations: %s. Roads widened to the 20 cm map minimum: %d.\n") % [int(denominator),meta.before.features,meta.after.features,meta.before.positions,meta.after.positions,meta.before.roads,meta.after.roads,meta.before.buildings,meta.after.buildings,meta.before.areas,meta.after.areas,float(meta.gap_m),float(meta.gap_m)/denominator,JSON.stringify(meta.surface_mappings),meta.widened_roads]
	result += I18N.t("Paths, footways, cycleways and steps painted as drivable ground, not roads: %d ways.\n") % meta.painted_pedestrian_ways
	result += I18N.t("Bridges, tunnels and layered ways without source heights that cross no other road, or only painted paths when no height can be estimated, are drawn at ground level: %d ways (estimate).\n") % meta.level_structures
	result += I18N.t("Buildings above other features (positive layer, not roof canopies) stand on the ground: %d sources (estimate).\n") % meta.layered_buildings
	result += I18N.t("Overpasses and underpasses without source heights use estimated 6 m levels and ramps up to 8%%: %d structure roads (not surveyed).\n") % meta.estimated_structure_roads
	var rules: Dictionary = meta.get("road_rules", {})
	if not rules.is_empty():
		var sidewalks := 0
		for key: String in rules:
			if key.begins_with("sidewalk_cm_") and key != "sidewalk_cm_0": sidewalks += int(rules[key])
		result += I18N.t("City road rules: %d dual carriageways merged into two-way roads (%d one-way ways, %d median links); %d widths from lane counts; %d service ways and %d tracks painted as drivable ground; %d roads with sidewalks; %d roads with lane markings and %d junction crosswalks (estimates).\n") % [int(rules.get("dual_merged_pairs", 0)), int(rules.get("dual_merged_ways", 0)), int(rules.get("dual_absorbed_links", 0)), int(rules.get("lane_widths", 0)), int(rules.get("painted_service", 0)), int(rules.get("painted_track", 0)), sidewalks, int(rules.get("marked", 0)), int(rules.get("crosswalks", 0))]
	var records: Dictionary = meta.get("building_records", {})
	var barriers: Dictionary = meta.get("barriers", {})
	var paint: Dictionary = meta.get("ground_paint", {})
	if not records.is_empty() or not barriers.is_empty():
		result += I18N.t("City sites: %d building records with %d solids (nearby buildings of one site and category share a record as separate parts).\n") % [int(records.get("records", 0)), int(records.get("solids", 0))]
		result += I18N.t("Barriers: %d pieces from %d explicit OSM barrier ways and %d pieces of %d inferred site perimeters, opened at paths, painted driveways and gates; heights are estimates.\n") % [int(barriers.get("explicit_records", 0)), int(barriers.get("explicit_ways", 0)), int(barriers.get("inferred_records", 0)), int(barriers.get("inferred_sites", 0))]
		result += I18N.t("Ground paint: %d pieces (pedestrian %d, grass %d, asphalt %d, concrete %d, dirt %d, gravel %d) over concrete unpainted ground.\n") % [int(paint.get("pieces", 0)), int(paint.get("pedestrian", 0)), int(paint.get("grass", 0)), int(paint.get("asphalt", 0)), int(paint.get("concrete", 0)), int(paint.get("dirt", 0)), int(paint.get("gravel", 0))]
		var water: Dictionary = meta.get("water", {})
		result += I18N.t("Water: %d pieces from %d water areas and %d waterways (ribbons at their width), cut by roads and walking ways; surface level and depth are estimates; %d waterways wholly under roads are not imported.\n") % [int(water.get("pieces", 0)), int(water.get("areas", 0)), int(water.get("waterways", 0)), water.get("dropped_sources", []).size()]
		var skipped: Dictionary = meta.get("skipped", {})
		result += I18N.t("Not imported: %d barrier sources dropped (guard rails on bridges, wholly within gates or crossings, shorter than one map centimetre), %d barrier ways off the ground or with unsupported tags, %d city-only areas that cannot be imported.\n") % [barriers.get("dropped_sources", []).size(), int(skipped.get("barrier_ways", 0)), int(skipped.get("city_areas", 0))]
	result += I18N.t("Complex polygons are partitioned with a %.2f source m separation (%.2f map m); source IDs and courtyards remain recorded.\n") % [meta.polygon_partition_gap_m,meta.polygon_partition_gap_m/denominator]
	result += I18N.t("Forest/orchard trees are illustrative estimates: %.0f source m spacing (%.0f map m), %d%% density. All source area boundaries remain represented; individual tree locations are not surveyed.\n") % [meta.vegetation_spacing_m,meta.vegetation_spacing_m/denominator,meta.vegetation_density_per_mille/10]
	return result + I18N.t("Estimated road widths by class: %s. Building sources cut for road clearance: %d; adjusted for overlapping buildings: %d.\nNames and source IDs of enclosed buildings are retained in their containing volume. Geometry changes are approximations; originals stay unchanged.\n") % [JSON.stringify(meta.estimated_road_widths),meta.trimmed_building_sources.size(),meta.overlap_adjusted_sources.size()]
