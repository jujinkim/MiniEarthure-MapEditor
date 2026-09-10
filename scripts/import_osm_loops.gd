extends RefCounted
## Original node identity and traversal survive deterministic split and bbox cuts.
static func source_ref(value: Variant) -> bool:
	if value is not String or value.length() < 1 or value.length() > 19 or value[0] == "0": return false
	for c in value:
		if c not in "0123456789": return false
	return true

static func validate(raw: Dictionary, boundary: Script) -> String:
	var meta: Variant = raw.coordinates.get("osm_ground_loops")
	var roads := {}
	var nodes := {}
	for patch: Dictionary in raw.patches:
		if patch.field == "roads" and patch.id.ends_with("-loop"): roads[patch.id] = patch.after
		if patch.field == "nodes": nodes[patch.id] = patch.after
	if meta == null: return "Missing OSM loop provenance." if not roads.is_empty() else ""
	if raw.adapter != "osm-extract-v1" or meta is not Dictionary or meta.size() != 3 or meta.get("profile") not in ["source-node-segments-v1", "source-node-segments-v2"] or meta.get("sources") is not Array or meta.sources.is_empty() or meta.sources.size() > 20000 or meta.get("retained") is not Array or meta.retained.size() != roads.size(): return "Invalid OSM loop profile."
	var structural: bool = meta.profile == "source-node-segments-v2"
	var structural_sources := 0
	var sources := {}
	var loop_nodes := {}
	var reference_count := 0
	var previous_way := ""
	for entry in meta.sources:
		if entry is not Dictionary or entry.size() != (5 if structural else 3) or not source_ref(entry.get("way")) or entry.get("closed") is not bool or entry.get("refs") is not Array or entry.refs.size() < (4 if entry.closed else 2): return "Invalid OSM loop source."
		if structural:
			if entry.get("kind") not in ["ground", "bridge", "tunnel"] or not entry.has("clearance_cm"): return "Invalid OSM loop source kind."
			if entry.kind == "tunnel":
				if not boundary._count(entry.clearance_cm, 5000) or entry.clearance_cm < 200: return "Invalid OSM loop tunnel clearance."
			elif entry.clearance_cm != null: return "Unexpected OSM loop clearance."
			structural_sources += int(entry.kind != "ground")
		if previous_way != "" and (entry.way.length() < previous_way.length() or (entry.way.length() == previous_way.length() and entry.way <= previous_way)): return "Invalid OSM loop source order."
		previous_way = entry.way
		reference_count += entry.refs.size()
		if reference_count > 200000: return "OSM loop source reference budget exceeded."
		var unique := {}
		for i in range(entry.refs.size()):
			var ref: Variant = entry.refs[i]
			if not source_ref(ref): return "Invalid OSM loop node reference."
			if entry.closed and i == entry.refs.size()-1:
				if ref != entry.refs[0]: return "OSM loop is not closed."
			elif unique.has(ref): return "Repeated OSM loop source node."
			unique[ref] = true
			if entry.closed: loop_nodes[ref] = true
		sources[entry.way] = entry
	if structural and structural_sources == 0: return "Missing OSM loop structural source."
	if loop_nodes.is_empty(): return "Missing closed OSM source way."
	for entry: Dictionary in meta.sources:
		var incident := false
		for ref: String in entry.refs:
			if loop_nodes.has(ref): incident = true
		if not incident: return "OSM loop approach lacks a shared original node."
	var crop: bool = raw.coordinates.has("osm_crop")
	var ranges := {}
	var last_feature := -1
	var total_points := 0
	var cuts := {}
	for entry in meta.retained:
		if entry is not Dictionary or entry.size() != 5 or entry.get("road_id") is not String or not roads.has(entry.road_id) or entry.get("source_way") is not String or not sources.has(entry.source_way) or entry.get("explicit_height") is not bool: return "Invalid retained OSM loop mapping."
		var prefix: String = "import-" + raw.layer_id + "-"
		var index: String = entry.road_id.trim_prefix(prefix).trim_suffix("-loop")
		if not index.is_valid_int() or str(int(index)) != index or int(index) <= last_feature or not boundary._count(int(index), raw.feature_count-1): return "Invalid OSM loop feature order."
		last_feature = int(index)
		var source: Dictionary = sources[entry.source_way]
		var span: Variant = entry.get("source_range")
		if span is not Array or span.size() != 2 or not boundary._finite(span[0],0,source.refs.size()-1) or not boundary._finite(span[1],0,source.refs.size()-1) or span[0] >= span[1]: return "Invalid OSM loop source range."
		if source.closed and ceilf(span[1])-floorf(span[0]) != 1: return "Closed OSM road must split at every original node."
		var previous: float = ranges.get(entry.source_way,0.0)
		if span[0] < previous or (not crop and span[0] != previous): return "Overlapping or missing OSM loop source range."
		ranges[entry.source_way] = span[1]
		var refs: Variant = entry.get("refs")
		var road: Dictionary = roads[entry.road_id]
		var count := int(ceilf(span[1])-floorf(span[0]))+1
		if refs is not Array or refs.size() != count or road.get("kind") != source.get("kind", "ground") or road.get("clearance_cm") != source.get("clearance_cm") or road.get("points") is not Array or road.points.size() != count: return "Invalid OSM loop geometry/profile."
		if road.kind != "ground" and not entry.explicit_height: return "OSM structural loop requires explicit heights."
		total_points += count
		if total_points > raw.point_count: return "OSM loop point budget exceeded."
		for i in range(count):
			var position: float = span[0] if i == 0 else span[1] if i == count-1 else floorf(span[0])+i
			if position == floorf(position):
				if refs[i] != source.refs[int(position)]: return "OSM loop original node changed."
			else:
				if not crop or refs[i] is not String or not refs[i].begins_with("crop-") or refs[i].length() > 80: return "Invalid OSM loop crop endpoint."
				if cuts.has(refs[i]): return "OSM loop crop endpoints must remain independent."
				cuts[refs[i]] = true
			if not entry.explicit_height and (road.points[i] is not Array or road.points[i].size() != 3 or road.points[i][1] != 20): return "OSM estimated loop elevation changed."
		for end: String in ["from","to"]:
			var node_id: String = prefix + "osm-node-" + str(refs[0 if end == "from" else -1])
			if road.get(end) != node_id or not nodes.has(node_id) or nodes[node_id].get("position") != road.points[0 if end == "from" else -1]: return "OSM loop endpoint identity or geometry changed."
		roads.erase(entry.road_id)
	if not crop:
		for way: String in sources:
			if ranges.get(way,0) != sources[way].refs.size()-1: return "Incomplete OSM loop source coverage."
	return ""
