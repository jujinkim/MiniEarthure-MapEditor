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
	var positioned: bool = meta.has("connection_profile")
	if positioned and meta.connection_profile != "explicit-position-v1": return "Invalid connection position profile."
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
		if entry.get("road_class") not in ["motorway","trunk","primary","secondary","tertiary","residential","living_street","service","unclassified"]: return "Invalid road physical profile."
		var scoped: bool = entry.has("road_spans")
		if not scoped and (not guard._count(entry.get("width_cm"),100000) or entry.width_cm < 1 or entry.get("surface") not in ["asphalt","gravel","dirt"]): return "Invalid legacy physical profile."
		var refs: Variant = entry.get("connectors")
		var road_ids: Variant = entry.get("road_ids")
		if refs is not Array or refs.size() < 2 or refs.size() > 8192 or road_ids is not Array or road_ids.size() != refs.size()-1: return "Incomplete segment mapping."
		var previous_at := -1.0
		if positioned and (not scoped or entry.get("source_fractions") is not Array or entry.source_fractions.size() < 2 or entry.source_fractions.size() > 8192): return "Missing connection source fractions."
		var previous_vertex := -1
		var previous_resolved := -1.0
		var unique := {}
		for ref in refs:
			if ref is not Dictionary or not guard._text(ref.get("connector_id")) or not connector_nodes.has(ref.connector_id) or unique.has(ref.connector_id) or not guard._finite(ref.get("at"),0,1) or ref.at <= previous_at: return "Invalid segment connector ordering."
			if positioned:
				if not guard._finite(ref.get("resolved_at"),0,1) or ref.resolved_at <= previous_resolved or abs(ref.resolved_at-ref.at) > 0.0000001 or not guard._finite(ref.get("displacement_m"),0,0.001): return "Invalid connector position mapping."
				if not ref.has("vertex"): return "Missing connector source index."
				if ref.vertex != null and (not guard._count(ref.vertex,entry.source_fractions.size()-1) or entry.source_fractions[int(ref.vertex)] != ref.resolved_at): return "Invalid connector source index."
				if ref.vertex == null and (ref.resolved_at <= 0 or ref.resolved_at >= 1 or entry.source_fractions.has(ref.resolved_at)): return "Invalid interior connector position."
				previous_resolved = ref.resolved_at
			elif not guard._count(ref.get("vertex"),8191) or ref.vertex <= previous_vertex: return "Invalid segment connector vertex."
			unique[ref.connector_id] = true
			used[ref.connector_id] = true
			previous_at = ref.at
			if ref.vertex != null: previous_vertex = int(ref.vertex)
		if refs[0].vertex != 0 or refs[0].at > 0.0000001 or refs[-1].at < 0.9999999: return "Missing segment endpoint connectors."
		if positioned:
			if refs[-1].vertex != entry.source_fractions.size()-1 or refs[0].resolved_at != 0 or refs[-1].resolved_at != 1: return "Missing positioned endpoints."
			source_points += entry.source_fractions.size()
		else: source_points += int(refs[-1].vertex)+1
		if scoped:
			var error := validate_spans(entry, guard, positioned)
			if error != "": return error
		for i in range(road_ids.size()):
			var rid: Variant = road_ids[i]
			if not guard._text(rid) or expected_roads.has(rid) or expected_roads.size() >= 2048: return "Invalid/duplicate split-road mapping."
			if scoped:
				var span: Dictionary = entry.road_spans[i]
				expected_roads[rid] = {"from":connector_nodes[refs[i].connector_id], "to":connector_nodes[refs[i+1].connector_id], "widths":span.widths_cm, "surfaces":span.surfaces, "geometry":span.points_cm, "points":span.points_cm.size()}
			else:
				expected_roads[rid] = {"from":connector_nodes[refs[i].connector_id], "to":connector_nodes[refs[i+1].connector_id], "width":entry.width_cm, "surface":entry.surface, "points":refs[i+1].vertex-refs[i].vertex+1}
			output_points += int(expected_roads[rid].points)
	if output_points > 16384 or source_points > 8192 or meta.get("source_position_count") != source_points or raw.get("point_count") != output_points: return "Transportation point budget/count mismatch."
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
			if expected.has("geometry"):
				if record.points != expected.geometry or record.widths_cm != expected.widths or record.surfaces != expected.surfaces: return "Road span mapping changed."
			else:
				for width in record.widths_cm:
					if width != expected.width: return "Road width mapping changed."
				for surface in record.surfaces:
					if surface != expected.surface: return "Road surface mapping changed."
		else: return "Transportation may only add nodes and roads."
	return ""

## New span provenance is optional only for previously authored uniform layers.
static func validate_spans(entry: Dictionary, guard: Script, positioned: bool = false) -> String:
	var spans: Variant = entry.road_spans
	var physical: Variant = entry.get("physical_rules")
	var source: Variant = entry.get("source_fractions")
	if spans is not Array or spans.size() != entry.road_ids.size() or physical is not Dictionary: return "Incomplete physical spans."
	if source is not Array or source.size() < 2 or source.size() != entry.connectors[-1].vertex+1 or source.size() > 8192: return "Invalid source fractions."
	var last := -1.0
	for at in source:
		if not guard._finite(at,0,1) or at <= last: return "Invalid source fraction order."
		last = at
	if source[0] != 0 or source[-1] != 1: return "Incomplete source fractions."
	for ref in entry.connectors:
		if not positioned and abs(source[int(ref.vertex)]-ref.at) > 0.0000001: return "Connector fraction mapping changed."
	var boundaries := {}
	for key in ["width_rules", "road_surface"]:
		var rules: Variant = physical.get(key)
		if rules is not Array or rules.is_empty() or rules.size() > 1024: return "Invalid physical rules."
		last = 0
		for rule in rules:
			if rule is not Array or rule.size() != 3 or not guard._finite(rule[0],0,1) or not guard._finite(rule[1],0,1) or rule[0] != last or rule[1] <= rule[0]: return "Physical rule gap/overlap."
			if key == "width_rules":
				if rule[2] != null and not guard._finite(rule[2],0.2,100): return "Invalid physical width."
			elif rule[2] not in [null,"unknown","paved","gravel","dirt"]: return "Invalid physical surface."
			if rule[2] == null and (rules.size() != 1 or rule[0] != 0 or rule[1] != 1): return "Scoped null physical rule."
			boundaries[rule[0]] = true
			boundaries[rule[1]] = true
			last = rule[1]
		if last != 1: return "Incomplete physical coverage."
	var seen := {}
	var count := 0
	for i in range(spans.size()):
		var span: Variant = spans[i]
		if span is not Dictionary or span.get("road_id") != entry.road_ids[i]: return "Invalid span identity."
		var fractions: Variant = span.get("fractions")
		if fractions is not Array or fractions.size() < 2 or fractions.size() > 16384: return "Invalid span fractions."
		count += fractions.size()
		if count > 16384: return "Span point budget exceeded."
		var start: Variant = entry.connectors[i].resolved_at if positioned else source[int(entry.connectors[i].vertex)]
		var end: Variant = entry.connectors[i+1].resolved_at if positioned else source[int(entry.connectors[i+1].vertex)]
		if fractions[0] != start or fractions[-1] != end: return "Span connector range changed."
		if span.get("points_cm") is not Array or span.points_cm.size() != fractions.size() or span.get("widths_cm") is not Array or span.widths_cm.size() != fractions.size()-1 or span.get("surfaces") is not Array or span.surfaces.size() != fractions.size()-1: return "Invalid span arrays."
		last = -1
		var indices := {"width_rules":0, "road_surface":0}
		for j in range(fractions.size()):
			var at: Variant = fractions[j]
			if not guard._finite(at,0,1) or at <= last: return "Invalid span order."
			seen[at] = true
			last = at
			if j == fractions.size()-1: continue
			for key in indices:
				var rules: Array = physical[key]
				while indices[key] < rules.size()-1 and at >= rules[indices[key]][1]: indices[key] += 1
				var rule: Array = rules[indices[key]]
				if at >= rule[1] or not guard._finite(fractions[j+1],0,1) or fractions[j+1] <= at or fractions[j+1] > rule[1]: return "Unsplit physical boundary."
				if key == "width_rules":
					var width: float = 8.0 if rule[2] == null else float(rule[2])
					var scaled := width * 100.0
					var rounded: float = floor(scaled)
					if scaled-rounded > 0.5 or (scaled-rounded == 0.5 and int(rounded) % 2 == 1): rounded += 1
					if span.widths_cm[j] != rounded: return "Span width mapping changed."
				else:
					var surface: String = "asphalt" if rule[2] in [null,"unknown","paved"] else rule[2]
					if span.surfaces[j] != surface: return "Span surface mapping changed."
	for at in source + boundaries.keys():
		if not seen.has(at): return "Missing source/physical boundary."
	return ""
