extends RefCounted
## Recheck complete source-to-node/road mapping before native candidate validation.
static func validate(raw: Dictionary, guard: Script) -> String:
	var meta: Variant = raw.coordinates.get("overture_transportation")
	if raw.source.license != guard.OVERTURE_TRANSPORTATION_LICENSE or raw.coordinates.mode != "wgs84-utm": return "Transportation requires WGS84 and attribution."
	if meta is not Dictionary or meta.get("provider") != "Overture" or meta.get("theme") != "transportation" or meta.get("type") != "segment" or meta.get("profile") != "ground-graph-v1" or meta.get("license") != guard.OVERTURE_TRANSPORTATION_LICENSE: return "Invalid transportation profile."
	if not guard._text(meta.get("release")) or not guard._finite(meta.get("ground_m"), -9000, 9000): return "Invalid transportation release/plane."
	var pattern := RegEx.new()
	pattern.compile("^20[0-9]{2}-[0-9]{2}-[0-9]{2}\\.[0-9]+$")
	if pattern.search(meta.release) == null: return "Invalid transportation release."
	var bbox: Variant = meta.get("bbox")
	if bbox is not Array or bbox.size() != 4: return "Invalid transportation bbox."
	for i in range(4):
		if not guard._finite(bbox[i], -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84): return "Invalid transportation bbox."
	if bbox[0] >= bbox[2] or bbox[1] >= bbox[3] or bbox[2]-bbox[0] > 0.02 or bbox[3]-bbox[1] > 0.02: return "Invalid transportation area size."
	var segments: Variant = meta.get("segment_sources")
	var connectors: Variant = meta.get("connector_sources")
	if segments is not Array or segments.is_empty() or connectors is not Array or connectors.is_empty() or segments.size()+connectors.size() > 1024 or segments.size()+connectors.size() != raw.get("feature_count"): return "Invalid transportation source counts."
	var source_ids := {}
	var connector_nodes := {}
	var expected_nodes := {}
	var expected_roads := {}
	for entry in connectors + segments:
		if entry is not Dictionary or not guard._text(entry.get("id")) or source_ids.has(entry.id) or not guard._count(entry.get("version"), 2147483647) or entry.version < 1: return "Invalid/duplicate transportation identity."
		source_ids[entry.id] = true
		if entry.get("sources") is not Array or entry.sources.is_empty() or entry.sources.size() > 128: return "Missing transportation sources."
		for source in entry.sources:
			if source is not Dictionary or not guard._text(source.get("dataset")): return "Invalid transportation attribution."
	for entry in connectors:
		if not guard._text(entry.get("node_id")) or expected_nodes.has(entry.node_id) or entry.get("position_cm") is not Array or entry.position_cm.size() != 3: return "Invalid connector node mapping."
		for coordinate in entry.position_cm:
			if not guard._finite(coordinate,-10000000,10000000) or coordinate != floor(coordinate): return "Invalid connector coordinate."
		if abs(entry.position_cm[1] - meta.ground_m*100) > 0.500001: return "Connector plane changed."
		connector_nodes[entry.id] = entry.node_id
		expected_nodes[entry.node_id] = entry.position_cm
	var used := {}
	var source_points: int = connectors.size()
	var output_points: int = connectors.size()
	for entry in segments:
		if entry.get("road_class") not in ["motorway","trunk","primary","secondary","tertiary","residential","living_street","service","unclassified"] or not guard._count(entry.get("width_cm"),100000) or entry.width_cm < 1 or entry.get("surface") not in ["asphalt","gravel","dirt"]: return "Invalid road physical profile."
		var refs: Variant = entry.get("connectors")
		var road_ids: Variant = entry.get("road_ids")
		if refs is not Array or refs.size() < 2 or refs.size() > 8192 or road_ids is not Array or road_ids.size() != refs.size()-1: return "Incomplete segment mapping."
		var previous_at := -1.0
		var previous_vertex := -1
		var unique := {}
		for ref in refs:
			if ref is not Dictionary or not guard._text(ref.get("connector_id")) or not connector_nodes.has(ref.connector_id) or unique.has(ref.connector_id) or not guard._finite(ref.get("at"),0,1) or ref.at <= previous_at or not guard._count(ref.get("vertex"),8191) or ref.vertex <= previous_vertex: return "Invalid segment connector ordering."
			unique[ref.connector_id] = true
			used[ref.connector_id] = true
			previous_at = ref.at
			previous_vertex = int(ref.vertex)
		if refs[0].vertex != 0 or refs[0].at > 0.0000001 or refs[-1].at < 0.9999999: return "Missing segment endpoint connectors."
		source_points += int(refs[-1].vertex)+1
		for i in range(road_ids.size()):
			var rid: Variant = road_ids[i]
			if not guard._text(rid) or expected_roads.has(rid) or expected_roads.size() >= 2048: return "Invalid/duplicate split-road mapping."
			expected_roads[rid] = {"from":connector_nodes[refs[i].connector_id], "to":connector_nodes[refs[i+1].connector_id], "width":entry.width_cm, "surface":entry.surface, "points":refs[i+1].vertex-refs[i].vertex+1}
			output_points += int(expected_roads[rid].points)
	if source_points > 8192 or meta.get("source_position_count") != source_points or raw.get("point_count") != output_points: return "Transportation point budget/count mismatch."
	if used.size() != connectors.size(): return "Unreferenced connector mapping."
	if raw.patches.size() != expected_nodes.size()+expected_roads.size(): return "Incomplete transportation patches."
	for patch in raw.patches:
		var record: Dictionary = patch.after
		if patch.field == "nodes":
			if not expected_nodes.has(patch.id) or record.get("position") != expected_nodes[patch.id] or record.get("level") != 0: return "Connector geometry changed."
		elif patch.field == "roads":
			if not expected_roads.has(patch.id): return "Unmapped transportation road."
			var expected: Dictionary = expected_roads[patch.id]
			if record.get("from") != expected.from or record.get("to") != expected.to or record.get("kind") != "ground" or record.get("clearance_cm") != null or record.get("sidewalk_cm") != null: return "Transportation connectivity/profile changed."
			if record.get("points") is not Array or record.points.size() != expected.points or record.points[0] != expected_nodes[expected.from] or record.points[-1] != expected_nodes[expected.to]: return "Transportation endpoint geometry changed."
			for point in record.points:
				if point is not Array or point.size() != 3 or point[1] != expected_nodes[expected.from][1]: return "Transportation road plane changed."
			if record.get("widths_cm") is not Array or record.widths_cm.size() != record.points.size()-1 or record.get("surfaces") is not Array or record.surfaces.size() != record.points.size()-1: return "Invalid road physical arrays."
			for width in record.widths_cm:
				if width != expected.width: return "Road width mapping changed."
			for surface in record.surfaces:
				if surface != expected.surface: return "Road surface mapping changed."
		else: return "Transportation may only add nodes and roads."
	return ""
