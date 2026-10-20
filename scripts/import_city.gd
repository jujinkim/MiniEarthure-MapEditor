extends RefCounted
const I18N := preload("./locale_text.gd")
## Validate worker claims and complete source/record coverage before adoption.
static func validate(raw: Dictionary, requested: Dictionary, boundary: Script) -> String:
	var meta: Variant = raw.coordinates.get("osm_city")
	if meta == null: return "Missing requested city optimization." if requested.get("osm_city", false) else ""
	if raw.adapter != "osm-extract-v1" or not raw.coordinates.has("osm_stream") or meta is not Dictionary or meta.get("profile") != "scale-aware-city-v1" or meta.get("scale_denominator") != 8: return "Invalid city optimization profile."
	if not requested.is_empty() and requested.get("osm_city") != true: return "Unrequested city optimization."
	if not boundary._finite(meta.get("grid_m"),0.079999999,0.080000001) or not boundary._count(meta.get("gap_m"),64) or int(meta.gap_m) not in [0,2,4,8,16,32,64]: return "Invalid city approximation settings."
	if not boundary._finite(meta.get("line_tolerance_m"),0,4) or not boundary._finite(meta.get("polygon_tolerance_m"),0,8) or not is_equal_approx(float(meta.line_tolerance_m),minf(4.0,float(meta.gap_m)/4.0)) or not is_equal_approx(float(meta.polygon_tolerance_m),minf(8.0,float(meta.gap_m)/4.0)): return "Invalid city approximation settings."
	for key in ["before", "after"]:
		var counts: Variant = meta.get(key)
		if counts is not Dictionary: return "Missing city geometry counts."
		for field in ["features", "positions", "roads", "buildings", "areas"]:
			if not boundary._count(counts.get(field), (2000000 if field == "positions" else 250000) if key == "before" else (800000 if field == "positions" else 100000)): return "City geometry count budget exceeded."
		if counts.features != counts.roads+counts.buildings+counts.areas: return "City geometry category mismatch."
	if meta.after.features != raw.get("feature_count") or meta.after.positions < raw.get("point_count", 0) or not boundary._count(meta.get("protected_buildings"), meta.after.buildings): return "City output count mismatch."
	if not boundary._count(meta.get("unmerged_numeric_groups"),250000): return "Invalid city retained group count."
	if not boundary._count(meta.get("painted_pedestrian_ways"),meta.before.roads): return "Invalid city ground paint count."
	if not boundary._count(meta.get("level_structures"),meta.before.roads): return "Invalid city ground-level structure count."
	if not boundary._count(meta.get("layered_buildings"),meta.before.buildings): return "Invalid city layered building count."
	if not boundary._count(meta.get("estimated_structure_roads"),meta.after.roads) or int(meta.estimated_structure_roads) != raw.coordinates.get("osm_estimated_structures",[]).size(): return "Invalid city estimated structure count."
	if meta.get("vegetation_spacing_m") != 32 or meta.get("vegetation_density_per_mille") != 750: return "Invalid city vegetation estimates."
	if not boundary._count(meta.get("widened_roads"),meta.before.roads) or meta.get("minimum_road_width_m") != 1.6 or meta.get("surface_mappings") is not Array or meta.surface_mappings.size() > 512: return "Invalid city road approximations."
	var mapped := {}
	var mapped_count := 0
	for entry: Variant in meta.surface_mappings:
		if entry is not Dictionary or not boundary._text(entry.get("source")) or entry.get("target") not in ["asphalt","concrete","dirt","gravel","grass"] or not boundary._count(entry.get("features"),meta.before.roads) or mapped.has(entry.source): return "Invalid city surface mapping."
		mapped[entry.source] = true
		mapped_count += int(entry.features)
	if mapped_count > meta.before.roads: return "City surface mapping count exceeded."
	if meta.get("estimated_road_widths") is not Dictionary or meta.get("road_clearance_m") != 0.8 or meta.get("building_clearance_m") != 0.16 or meta.get("polygon_partition_gap_m") != 0.32 or meta.get("trimmed_building_sources") is not Array or meta.get("overlap_adjusted_sources") is not Array: return "Invalid city road approximations."
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
	for patch: Variant in raw.patches:
		if patch is Dictionary and patch.get("field") == "zones":
			if patch.get("after") is not Dictionary or patch.after.get("spacing_cm") != 3200 or patch.after.get("density_per_mille") != 750: return "Invalid city vegetation estimates."
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
		if references > 2000000: return "City mapping reference budget exceeded."
		var local_sources := {}
		for index: Variant in group.sources:
			if not boundary._count(index,meta.source_ids.size()-1) or local_sources.has(int(index)): return "Unknown/duplicate city aggregation source."
			local_sources[int(index)] = true
			sources[meta.source_ids[int(index)]] = true
		if not boundary._count(group.records[0],record_count) or not boundary._count(group.records[1],record_count) or group.records[0] != next_record: return "Noncontiguous city output mapping."
		next_record += int(group.records[1])
		if next_record > record_count: return "City output mapping exceeds records."
	if false in sources.values() or next_record != record_count: return "Incomplete city source/output coverage."
	return ""

static func summary(meta: Dictionary) -> String:
	var result := I18N.t("Automatic city optimization · 1:8\nFeatures: %d → %d · positions: %d → %d\nRoads: %d → %d · buildings: %d → %d · areas: %d → %d\nGap filling: ≤ %.2f source m (%.2f map m). Named/tall buildings, road corridors and courtyards remain protected.\nMerged building heights are estimates; exact source mappings are retained.\nRoad surfaces are game-material approximations: %s. Roads widened to the 20 cm map minimum: %d.\n") % [meta.before.features,meta.after.features,meta.before.positions,meta.after.positions,meta.before.roads,meta.after.roads,meta.before.buildings,meta.after.buildings,meta.before.areas,meta.after.areas,float(meta.gap_m),float(meta.gap_m)/8.0,JSON.stringify(meta.surface_mappings),meta.widened_roads]
	result += I18N.t("Paths, footways, cycleways and steps painted as drivable ground, not roads: %d ways.\n") % meta.painted_pedestrian_ways
	result += I18N.t("Bridges, tunnels and layered ways without source heights that cross no other road, or only painted paths when no height can be estimated, are drawn at ground level: %d ways (estimate).\n") % meta.level_structures
	result += I18N.t("Buildings above other features (positive layer, not roof canopies) stand on the ground: %d sources (estimate).\n") % meta.layered_buildings
	result += I18N.t("Overpasses and underpasses without source heights use estimated 6 m levels and ramps up to 8%%: %d structure roads (not surveyed).\n") % meta.estimated_structure_roads
	result += I18N.t("Complex polygons are partitioned with a %.2f source m separation (%.2f map m); source IDs and courtyards remain recorded.\n") % [meta.polygon_partition_gap_m,meta.polygon_partition_gap_m/8.0]
	result += I18N.t("Forest/orchard trees are illustrative estimates: %.0f source m spacing (%.0f map m), %d%% density. All source area boundaries remain represented; individual tree locations are not surveyed.\n") % [meta.vegetation_spacing_m,meta.vegetation_spacing_m/8.0,meta.vegetation_density_per_mille/10]
	return result + I18N.t("Estimated road widths by class: %s. Building sources cut for road clearance: %d; adjusted for overlapping buildings: %d.\nNames and source IDs of enclosed buildings are retained in their containing volume. Geometry changes are approximations; originals stay unchanged.\n") % [JSON.stringify(meta.estimated_road_widths),meta.trimmed_building_sources.size(),meta.overlap_adjusted_sources.size()]
