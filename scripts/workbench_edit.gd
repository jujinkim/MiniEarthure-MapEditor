extends RefCounted
## Vector edit planning only. MapKit validation and DocumentStore publish atomically.
const FIELDS := ["zones", "buildings", "roads", "repetitions", "placements", "nodes"]

static func key(field: String, id: String) -> String:
	return field + "/" + id

static func entries(document: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for field: String in FIELDS:
		for record: Dictionary in document.get(field, []):
			result.append({"field": field, "record": record, "key": key(field, str(record.id))})
	return result

static func points(field: String, record: Dictionary) -> Array[Vector2]:
	var result: Array[Vector2] = []
	if field in ["buildings", "zones"]:
		for p: Array in record.get("footprint", record.get("polygon", [])):
			result.append(Vector2(p[0], p[1]))
	elif field in ["roads", "repetitions"]:
		for p: Array in record.points:
			result.append(Vector2(p[0], p[2]))
	else:
		result.append(Vector2(record.position[0], record.position[2]))
	return result

static func translated(field: String, record: Dictionary, delta: Vector2) -> Dictionary:
	var after := record.duplicate(true)
	if field in ["buildings", "zones"]:
		var polygons: Array = [after.get("footprint", after.get("polygon", []))]
		polygons.append_array(after.get("entrances", after.get("exclusions", [])))
		polygons.append_array(after.get("holes", []))
		for polygon: Array in polygons:
			for p: Array in polygon:
				p[0] += int(delta.x)
				p[1] += int(delta.y)
	else:
		var vertices: Array = after.points if field in ["roads", "repetitions"] else [after.position]
		for p: Array in vertices:
			p[0] += int(delta.x)
			p[2] += int(delta.y)
	return after

static func patch(field: String, before: Variant, after: Variant) -> Dictionary:
	return {"field": field, "id": str((after if after != null else before).id), "before": before, "after": after}

static func fresh_id(field: String) -> String:
	# Never append to an already maximum-length producer ID.
	return field + "-" + Crypto.new().generate_random_bytes(12).hex_encode()

static func plan(document: Dictionary, selection: Array, operation: String, delta: Vector2 = Vector2.ZERO) -> Dictionary:
	var patches: Array = []
	var next_selection: Array[String] = []
	var chosen := {}
	var moved_nodes := {}
	for entry in entries(document):
		if entry.key in selection:
			chosen[entry.key] = true
			if entry.field == "nodes":
				moved_nodes[str(entry.record.id)] = true
			elif entry.field == "roads":
				moved_nodes[str(entry.record.from)] = true
				moved_nodes[str(entry.record.to)] = true
	if chosen.is_empty():
		return {"patches": [], "selection": [], "affected": []}
	var node_copies := {}
	if operation == "duplicate":
		for node: Dictionary in document.nodes:
			if moved_nodes.has(str(node.id)):
				var after := translated("nodes", node, delta)
				after.id = fresh_id("node")
				node_copies[str(node.id)] = after.id
				patches.append(patch("nodes", null, after))
	for entry in entries(document):
		var field: String = entry.field
		var before: Dictionary = entry.record
		var selected: bool = chosen.has(entry.key)
		if operation == "delete":
			if field == "nodes" and moved_nodes.has(str(before.id)):
				var referenced := false
				for road: Dictionary in document.roads:
					if not chosen.has(key("roads", str(road.id))) and str(before.id) in [str(road.from), str(road.to)]:
						referenced = true
				if referenced and selected:
					return {"error": "Node is used by an unselected road. Select its roads to delete together."}
				if not referenced:
					patches.append(patch(field, before, null))
			elif selected:
				patches.append(patch(field, before, null))
			continue
		if operation == "duplicate":
			if not selected:
				continue
			if field == "nodes":
				next_selection.append(key(field, node_copies[str(before.id)]))
				continue
			var after := translated(field, before, delta)
			after.id = fresh_id(field)
			if field == "roads":
				after.from = node_copies[str(before.from)]
				after.to = node_copies[str(before.to)]
			patches.append(patch(field, null, after))
			next_selection.append(key(field, str(after.id)))
			continue
		var after := before.duplicate(true)
		if field == "nodes" and moved_nodes.has(str(before.id)):
			after = translated(field, before, delta)
		elif selected:
			after = translated(field, before, delta)
		elif field == "roads":
			# Moving a shared endpoint updates every incident road, exactly once.
			for endpoint in [["from", 0], ["to", after.points.size() - 1]]:
				if moved_nodes.has(str(before[endpoint[0]])):
					after.points[endpoint[1]][0] += int(delta.x)
					after.points[endpoint[1]][2] += int(delta.y)
		if after != before:
			patches.append(patch(field, before, after))
	var affected: Array[String] = []
	for item: Dictionary in patches:
		if item.before != null:
			affected.append(key(item.field, str(item.id)))
	return {"patches": patches, "selection": next_selection if operation == "duplicate" else ([] if operation == "delete" else selection.duplicate()), "affected": affected}
