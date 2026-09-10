extends RefCounted
## Bounded source-tree provenance for reuse of the existing GeoJSON leaf adapters.
static func tree_error(value: Variant, depth: int, state: Array, count: int, boundary: Script) -> String:
	state[1] += 1
	if depth > 16 or state[1] > 40000: return "GeometryCollection tree budget exceeded."
	if value is Array:
		state[2] += 1
		if value.is_empty() or value.size() > 40000: return "Invalid empty/oversized GeometryCollection."
		for child in value:
			var error := tree_error(child, depth+1, state, count, boundary)
			if error != "": return error
	elif not boundary._count(value, count-1) or value != state[0]:
		return "GeometryCollection leaves must retain source order without gaps."
	else:
		state[0] += 1
	return ""

static func validate(raw: Dictionary, boundary: Script) -> String:
	var meta: Variant = raw.coordinates.get("geojson_collections")
	var records := {}
	for patch: Dictionary in raw.patches:
		if patch.id.contains("-collection"): records[patch.id] = patch
	if meta == null: return "Missing GeometryCollection provenance." if not records.is_empty() else ""
	if raw.adapter != "geojson-v2" or meta is not Dictionary or meta.size() != 3 or meta.get("profile") != "feature-leaves-v1" or meta.get("sources") is not Array or meta.sources.is_empty() or meta.sources.size() > 20000 or meta.get("leaves") is not Array or meta.leaves.size() != raw.feature_count: return "Invalid GeometryCollection profile."
	if records.size() != raw.patches.size(): return "Incomplete GeometryCollection record namespace."
	var state := [0,0,0]
	for index in range(meta.sources.size()):
		var source: Variant = meta.sources[index]
		if source is not Dictionary or source.size() != 2 or not boundary._count(source.get("feature"), 19999) or source.feature != index or not source.has("tree"): return "Invalid GeometryCollection source feature."
		var error := tree_error(source.tree, 0, state, raw.feature_count, boundary)
		if error != "": return error
	if state[0] != raw.feature_count or state[2] == 0: return "Missing GeometryCollection source leaves."
	var points := 0
	for index in range(meta.leaves.size()):
		var leaf: Variant = meta.leaves[index]
		if leaf is not Dictionary or leaf.size() != 4 or not boundary._count(leaf.get("feature"), 19999) or leaf.feature != index or leaf.get("geometry") not in ["LineString", "MultiLineString", "Polygon", "MultiPolygon"] or leaf.get("record_ids") is not Array or leaf.record_ids.is_empty() or leaf.record_ids.size() > 60000 or not boundary._count(leaf.get("point_count"), 200000) or leaf.point_count < 2: return "Invalid GeometryCollection leaf mapping."
		points += int(leaf.point_count)
		if points > raw.point_count: return "GeometryCollection point budget exceeded."
		var road: bool = leaf.geometry in ["LineString", "MultiLineString"]
		var multiple: bool = leaf.geometry in ["MultiLineString", "MultiPolygon"]
		if road and leaf.record_ids.size() % 3 != 0: return "Incomplete GeometryCollection road records."
		var parts: int = leaf.record_ids.size()/3 if road else leaf.record_ids.size()
		if not multiple and parts != 1: return "Unexpected GeometryCollection leaf parts."
		var area_field := ""
		var actual_points := 0
		for part in range(parts):
			var base := "import-%s-%d-collection" % [raw.layer_id,index]
			if multiple: base += "-part-%d" % part
			for offset in range(3 if road else 1):
				var id: String = base + (["-from","-to",""][offset] if road else "")
				if leaf.record_ids[part*(3 if road else 1)+offset] != id or not records.has(id): return "GeometryCollection record identity/order changed."
				var patch: Dictionary = records[id]
				if road:
					if patch.field != ("nodes" if offset < 2 else "roads"): return "GeometryCollection road record kind changed."
					if offset == 2 and (patch.after.get("kind") != "ground" or patch.after.get("clearance_cm") != null or patch.after.get("from") != base+"-from" or patch.after.get("to") != base+"-to"): return "GeometryCollection roads must remain independent ground geometry."
					if offset == 2:
						if patch.after.get("points") is not Array: return "Invalid GeometryCollection road points."
						actual_points += patch.after.points.size()
				else:
					if patch.field not in ["buildings", "zones"] or (area_field != "" and area_field != patch.field): return "GeometryCollection area record kind changed."
					area_field = patch.field
					var outer: Variant = patch.after.get("footprint" if patch.field == "buildings" else "polygon")
					var holes: Variant = patch.after.get("holes" if patch.field == "buildings" else "exclusions", [])
					if outer is not Array or holes is not Array: return "Invalid GeometryCollection polygon points."
					actual_points += outer.size()
					for hole in holes:
						if hole is not Array: return "Invalid GeometryCollection polygon hole."
						actual_points += hole.size()
				records.erase(id)
		if actual_points != leaf.point_count: return "GeometryCollection source point count changed."
	if points != raw.point_count or not records.is_empty(): return "Incomplete GeometryCollection output mapping."
	return ""
