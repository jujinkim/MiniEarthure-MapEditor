extends RefCounted
## Editor-only provenance for independent GeoJSON road parts. No graph inference.
static func validate(raw: Dictionary, boundary: Script) -> String:
	var meta: Variant = raw.coordinates.get("geojson_multilines")
	if raw.adapter != "geojson-v2":
		return "MultiLineString provenance requires GeoJSON." if meta != null else ""
	if meta == null:
		for patch: Dictionary in raw.patches:
			if patch.field == "roads" and patch.id.contains("-part-"): return "Missing MultiLineString provenance."
		return ""
	var roads := {}
	var nodes := {}
	var references := {}
	for patch: Dictionary in raw.patches:
		if patch.field == "nodes": nodes[patch.id] = patch.after
		if patch.field != "roads": continue
		for end: String in ["from", "to"]:
			var node: Variant = patch.after.get(end)
			references[node] = references.get(node, 0) + 1
		if patch.id.contains("-part-"): roads[patch.id] = patch.after
	if meta is not Dictionary or meta.size() != 2 or meta.get("profile") != "disconnected-parts-v1" or meta.get("features") is not Array or meta.features.is_empty() or meta.features.size() > raw.feature_count: return "Invalid MultiLineString profile."
	var previous := -1
	var total_points := 0
	for feature in meta.features:
		if feature is not Dictionary or feature.size() != 3 or not boundary._count(feature.get("feature"), raw.feature_count - 1) or feature.feature <= previous: return "Invalid MultiLineString source feature order."
		previous = int(feature.feature)
		if feature.get("road_ids") is not Array or feature.road_ids.is_empty() or feature.road_ids.size() > 20000 or feature.get("point_counts") is not Array or feature.point_counts.size() != feature.road_ids.size(): return "Invalid MultiLineString part mapping."
		for part in range(feature.road_ids.size()):
			var id := "import-%s-%d%s-part-%d" % [raw.layer_id, previous, "-collection" if raw.coordinates.has("geojson_collections") else "", part]
			var count: Variant = feature.point_counts[part]
			if feature.road_ids[part] != id or not roads.has(id) or not boundary._count(count, 200000) or count < 2: return "Invalid MultiLineString road mapping."
			var road: Dictionary = roads[id]
			if road.get("kind") != "ground" or road.get("clearance_cm") != null or road.get("points") is not Array or road.points.size() != count: return "Invalid MultiLineString ground part."
			for end: String in ["from", "to"]:
				var node_id := id + "-" + end
				if road.get(end) != node_id or not nodes.has(node_id) or references.get(node_id) != 1: return "MultiLineString endpoints must remain independent."
				if nodes[node_id].get("position") != road.points[0 if end == "from" else -1]: return "MultiLineString endpoint geometry changed."
			total_points += int(count)
			if total_points > raw.point_count: return "MultiLineString point count exceeds source."
			roads.erase(id)
	return "Unmapped MultiLineString road." if not roads.is_empty() else ""
