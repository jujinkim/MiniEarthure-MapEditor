extends RefCounted
const EDIT := preload("./workbench_edit.gd")
const FILES := preload("./authoring_files.gd")
const TERRAIN := preload("./terrain_tools.gd")
var store: RefCounted
var canvas: Control
var terrain := TERRAIN.new()
var options := {
	"start_cm": 20, "end_cm": 20, "start_level": 0, "end_level": 0,
	"kind": "ground", "width_cm": 800, "surface": "asphalt", "clearance_cm": 400, "sidewalk_cm": 0,
	"height_cm": 1200, "base_cm": 0, "usage": "residential", "material": "concrete", "roof": "flat",
	"spacing_cm": 800, "density_per_mille": 750, "asset_id": "builtin:tree", "quarter_turns": 0,
	"mode": "raise", "radius_cm": 6400, "amount_cm": 100, "target_cm": 0, "grid_cm": 3200,
}

func configure(source: RefCounted, view: Control) -> void:
	store = source
	canvas = view
	terrain.store = source
	terrain.canvas = view

func recipe(version: int, theme: String) -> String:
	canvas.cancel_interaction()
	return store.apply_command("Choose recipe and theme", [{"field": "recipe_version", "before": store.document.recipe_version, "after": version}, {"field": "theme", "before": store.document.theme, "after": theme}])

func _insert(field: String, record: Dictionary) -> Dictionary:
	return {"field": field, "id": store.record_id(field, record), "before": null, "after": record}

func _points(draft: Array[Vector2]) -> Array:
	var distance := 0.0
	for i in range(1, draft.size()): distance += draft[i].distance_to(draft[i - 1])
	var traveled := 0.0
	var result: Array = []
	for i in range(draft.size()):
		if i > 0: traveled += draft[i].distance_to(draft[i - 1])
		result.append([roundi(draft[i].x), roundi(lerpf(options.start_cm, options.end_cm, traveled / distance if distance > 0 else 0)), roundi(draft[i].y)])
	return result

func draw(tool: String, draft: Array[Vector2]) -> String:
	var fields := {"Road": "roads", "Building": "buildings", "Forest": "zones", "Orchard": "zones", "Place": "placements", "Repeat": "repetitions", "Entrance": "buildings", "Exclusion": "zones"}
	var field: String = fields.get(tool, "")
	if field == "": return "Choose an authoring tool."
	if not canvas.available({"field": field, "record": {"id": "draft"}}, true): return "Show and unlock the target layer."
	var count := 1 if tool == "Place" else (2 if tool in ["Road", "Repeat"] else 3)
	if draft.size() < count: return "Add at least %d points; right-click finishes." % count
	var id := tool.to_lower() + "-" + Crypto.new().generate_random_bytes(6).hex_encode()
	var patches: Array = []
	var polygon: Array = []
	for point in draft: polygon.append([roundi(point.x), roundi(point.y)])
	var record := {"id": id}
	if tool == "Road":
		var points := _points(draft)
		var nodes: Array = []
		for end in [0, points.size() - 1]:
			var level := int(options.start_level if end == 0 else options.end_level)
			var node_id := id + "-node-" + str(end)
			var found := false
			for node: Dictionary in store.document.nodes:
				if store._json_copy(node.position) == store._json_copy(points[end]) and int(node.level) == level:
					if not canvas.available({"field": "nodes", "record": node}, true): return "Connected endpoint is hidden or locked."
					node_id = node.id
					found = true
					break
			if not found and not canvas.available({"field":"nodes", "record":{"id":node_id}}, true): return "Show and unlock graph nodes before drawing a new endpoint."
			if not found: patches.append(_insert("nodes", {"id": node_id, "position": points[end], "level": level}))
			nodes.append(node_id)
		var widths: Array = []
		var surfaces: Array = []
		for _i in range(points.size() - 1):
			widths.append(int(options.width_cm))
			surfaces.append(str(options.surface))
		record.merge({"from": nodes[0], "to": nodes[1], "points": points, "widths_cm": widths, "surfaces": surfaces, "kind": options.kind, "clearance_cm": int(options.clearance_cm) if options.kind in ["tunnel", "underpass"] else null, "sidewalk_cm": int(options.sidewalk_cm) if int(options.sidewalk_cm) > 0 else null})
	elif tool == "Building": record.merge({"footprint": polygon, "base_cm": int(options.base_cm), "height_cm": int(options.height_cm), "usage": options.usage, "material": options.material, "roof": options.roof})
	elif tool in ["Forest", "Orchard"]: record.merge({"polygon": polygon, "kind": tool.to_lower(), "spacing_cm": int(options.spacing_cm), "density_per_mille": int(options.density_per_mille), "exclusions": []})
	elif tool == "Place": record.merge({"asset_id": options.asset_id, "position": [polygon[0][0], int(options.base_cm), polygon[0][1]], "quarter_turns": int(options.quarter_turns)})
	elif tool == "Repeat": record.merge({"asset_id": options.asset_id, "points": _points(draft), "spacing_cm": int(options.spacing_cm)})
	else:
		if canvas.selected.size() != 1: return "Select exactly one building for an entrance or one zone for an exclusion."
		var selected := {}
		for entry in EDIT.entries(store.document):
			if entry.key == canvas.selected[0]: selected = entry
		if selected.is_empty() or selected.field != field or not canvas.available(selected, true): return "Select an editable " + field + " object."
		record = selected.record.duplicate(true)
		var key := "entrances" if tool == "Entrance" else "exclusions"
		var rings: Array = record.get(key, []).duplicate(true)
		rings.append(polygon)
		record[key] = rings
		patches.append(EDIT.patch(field, selected.record, record))
	if tool not in ["Entrance", "Exclusion"]: patches.append(_insert(field, record))
	return apply("Draw " + tool, patches, tool == "Road")

func apply(label: String, patches: Array, check_roads: bool = false) -> String:
	var candidate: Dictionary = store.document.duplicate(true)
	var failure: String = store._apply(candidate, patches, false)
	if failure != "": return failure
	var validation: Dictionary = store._validate(candidate)
	if not validation.ok: return store.reason(validation)
	candidate = validation.data.document
	for patch: Dictionary in patches:
		if patch.before != null and patch.field in EDIT.FIELDS and not canvas.available({"field": patch.field, "record": patch.before}, true): return "Edit affects a hidden or locked object."
	var cells: Array = []
	if check_roads:
		var size := int(candidate.cell_size_cm)
		var road_patches: Array = patches.duplicate()
		for patch: Dictionary in patches:
			if patch.field in ["bounds", "terrain_base_cm"]:
				for road: Dictionary in candidate.roads: road_patches.append({"field":"roads","after":road})
				break
		for patch: Dictionary in road_patches:
			if patch.field != "roads" or patch.after == null: continue
			for point: Array in patch.after.points:
				var x := int(point[0]) - int(candidate.bounds.min[0])
				var y := int(point[2]) - int(candidate.bounds.min[1])
				for cx in [maxi(0, (x - 1) / size), mini(x / size, ceili(float(candidate.bounds.max[0] - candidate.bounds.min[0]) / size) - 1)]:
					for cy in [maxi(0, (y - 1) / size), mini(y / size, ceili(float(candidate.bounds.max[1] - candidate.bounds.min[1]) / size) - 1)]:
						var cell := Vector2i(cx, cy)
						if cell not in cells: cells.append(cell)
		if cells.size() > 16: return "Road junction check exceeds 16 cells; author shorter connected roads."
	if check_roads or not candidate.heightmaps.is_empty() or not candidate.assets.is_empty():
		failure = FILES.validate(store, candidate, {}, cells)
		if failure != "": return failure
	return store.apply_command(label, patches)

func edit_road(before: Dictionary, points: Array, widths: Array, surfaces: Array, kind: String, clearance: Variant, sidewalk: Variant, levels: Array) -> String:
	if points.size() < 2 or levels.size() != 2: return "Road requires two endpoints and endpoint levels."
	for point in points:
		if point is not Array or point.size() != 3: return "Each road point is [x,height,y] in integer centimetres."
	var after := before.duplicate(true)
	after.merge({"points": points, "widths_cm": widths, "surfaces": surfaces, "kind": kind, "clearance_cm": clearance, "sidewalk_cm": sidewalk}, true)
	var patches: Array = [EDIT.patch("roads", before, after)]
	var changed_nodes := {}
	for end in [0, 1]:
		var node_id: String = before.from if end == 0 else before.to
		var original: Dictionary = store._get_value(store.document, "nodes", node_id)
		var node := original.duplicate(true)
		node.position = points[0 if end == 0 else -1]
		node.level = levels[end]
		changed_nodes[node_id] = node
		if node != original: patches.append(EDIT.patch("nodes", original, node))
	for road: Dictionary in store.document.roads:
		if road.id == before.id: continue
		var update := road.duplicate(true)
		if changed_nodes.has(road.from): update.points[0] = changed_nodes[road.from].position
		if changed_nodes.has(road.to): update.points[-1] = changed_nodes[road.to].position
		if update != road: patches.append(EDIT.patch("roads", road, update))
	return apply("Edit road structure and graph", patches, true)

func asset(record: Dictionary, source_path: String = "", validate_only: bool = false, context: Dictionary = {}) -> String:
	var before: Variant = store._get_value(store.document, "assets", str(record.id))
	var blobs := {}
	if source_path != "":
		var source := FILES.read(source_path, store.HISTORY_BYTES)
		if source.has("error"): return source.error
		var extension := source_path.get_extension().to_lower()
		if extension not in ["glb", "png", "webp"]: return "Choose a static GLB, PNG or WebP."
		if context.get("expected_source", "") != "" and FILES.digest(source.bytes) != context.expected_source: return "Asset source changed while preparing candidate."
		record.path = "editor/" + FILES.digest(source.bytes) + "." + extension
		blobs[record.path] = source.bytes
		if context.has("register_output"):
			var failure: String = context.register_output.call(record.path)
			if failure != "": return failure
	elif before != null: record.path = before.path
	else: return "Choose an asset source file."
	if context.has("blob_paths"): context.blob_paths.append_array(blobs.keys())
	return FILES.apply(store, "Author asset and proxy", [{"field": "assets", "id": str(record.id), "before": before, "after": record}], blobs, [], validate_only, context)
