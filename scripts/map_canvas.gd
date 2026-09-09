extends Control
signal selection_changed(ids: Array)
signal status(text: String)
var store: RefCounted
var tool := "Select":
	set(value):
		if value != tool:
			cancel_interaction()
		tool = value
var selected: Array[String] = []
var draft: Array[Vector2] = []
var snap_cm := 100.0
var drag_start := Vector2.ZERO
var dragging := false
var drag_offset := Vector2.ZERO
var zoom := 1.0
var pan := Vector2.ZERO

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	clip_contents = true

func _scale() -> float:
	var bounds: Dictionary = store.document.bounds
	return minf((size.x - 80.0) / float(bounds.max[0] - bounds.min[0]), (size.y - 80.0) / float(bounds.max[1] - bounds.min[1])) * zoom

func screen(p: Array) -> Vector2:
	var bounds: Dictionary = store.document.bounds
	return Vector2(40, size.y - 40) + Vector2(float(p[0]) - bounds.min[0], -(float(p[1]) - bounds.min[1])) * _scale() + pan

func world(p: Vector2) -> Vector2:
	var bounds: Dictionary = store.document.bounds
	var v := (p - Vector2(40, size.y - 40) - pan) / _scale()
	return Vector2(snappedf(v.x + bounds.min[0], snap_cm), snappedf(-v.y + bounds.min[1], snap_cm))

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("11151a"))
	if store == null or store.document.is_empty():
		return
	var doc: Dictionary = store.document
	var bounds: Dictionary = doc.bounds
	var cell := int(doc.cell_size_cm)
	for x in range(int(bounds.min[0]), int(bounds.max[0]) + 1, cell):
		draw_line(screen([x, bounds.min[1]]), screen([x, bounds.max[1]]), Color("343a42"))
	for y in range(int(bounds.min[1]), int(bounds.max[1]) + 1, cell):
		draw_line(screen([bounds.min[0], y]), screen([bounds.max[0], y]), Color("343a42"))
	for field in ["zones", "buildings"]:
		for record: Dictionary in doc[field]:
			var points := PackedVector2Array()
			for p: Array in record.get("footprint", record.get("polygon", [])):
				var delta := drag_offset if str(record.id) in selected else Vector2.ZERO
				points.append(screen([p[0] + delta.x, p[1] + delta.y]))
			var color := Color("53684d") if field == "zones" else Color("a0a9b2")
			if str(record.id) in selected:
				color = Color("f4da49")
			if points.size() >= 3:
				draw_colored_polygon(points, Color(color, 0.35))
				points.append(points[0])
				draw_polyline(points, color, 2.0, true)
	for road: Dictionary in doc.roads:
		var points := PackedVector2Array()
		for p: Array in road.points:
			points.append(screen([p[0], p[2]]))
		draw_polyline(points, Color("ffe14c") if str(road.id) in selected else Color("dce1e6"), maxf(3.0, float(road.widths_cm[0]) * _scale()), true)
	for p in draft:
		draw_circle(screen([p.x, p.y]), 5.0, Color("ffe14c"))
	if draft.size() > 1:
		var line := PackedVector2Array()
		for p in draft:
			line.append(screen([p.x, p.y]))
		draw_polyline(line, Color("ffe14c"), 2.0)

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and event.pressed:
			zoom = clampf(zoom * (1.15 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.15), 0.5, 12.0)
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			finish_shape()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				var p := world(event.position)
				status.emit("x %.2f m  ·  y %.2f m" % [p.x / 100.0, p.y / 100.0])
				if tool == "Select":
					_select_at(p, event.shift_pressed)
					drag_start = p
					var failure: String = store.begin_gesture("Move selection")
					dragging = failure == ""
					if failure != "":
						status.emit(failure)
				else:
					draft.append(p)
					if event.double_click:
						finish_shape()
			else:
				if dragging and drag_offset != Vector2.ZERO:
					_move_selection(drag_offset, false)
				cancel_interaction(false)
		queue_redraw()
	elif event is InputEventMouseMotion:
		if event.button_mask & MOUSE_BUTTON_MASK_MIDDLE:
			pan += event.relative
		elif dragging:
			drag_offset = world(event.position) - drag_start
		queue_redraw()

func _select_at(p: Vector2, additive: bool) -> void:
	if not additive:
		selected.clear()
	for field in ["buildings", "zones"]:
		for record: Dictionary in store.document[field]:
			var points := PackedVector2Array()
			for q: Array in record.get("footprint", record.get("polygon", [])):
				points.append(Vector2(q[0], q[1]))
			if Geometry2D.is_point_in_polygon(p, points):
				if str(record.id) not in selected:
					selected.append(str(record.id))
				selection_changed.emit(selected)
				return
	for road: Dictionary in store.document.roads:
		for i in range(road.points.size() - 1):
			var a: Array = road.points[i]
			var b: Array = road.points[i + 1]
			if p.distance_to(Geometry2D.get_closest_point_to_segment(p, Vector2(a[0], a[2]), Vector2(b[0], b[2]))) < maxf(road.widths_cm[i] / 2.0, 8.0 / _scale()):
				selected.append(str(road.id))
				selection_changed.emit(selected)
				return
	selection_changed.emit(selected)

func finish_shape() -> void:
	if draft.size() > 1 and draft[-1] == draft[-2]:
		draft.pop_back()
	var id := tool.to_lower() + "-" + Crypto.new().generate_random_bytes(6).hex_encode()
	if tool == "Road" and draft.size() >= 2:
		var points: Array = []
		for p in draft:
			points.append([int(p.x), 20, int(p.y)])
		var nodes: Array = []
		var patches: Array = []
		for index in [0, points.size() - 1]:
			var node_id := ""
			for existing: Dictionary in store.document.nodes:
				if JSON.parse_string(JSON.stringify(existing.position)) == JSON.parse_string(JSON.stringify(points[index])) and int(existing.level) == 0:
					node_id = str(existing.id)
					break
			if node_id == "":
				node_id = id + "-node-" + str(index)
				patches.append({"field": "nodes", "id": node_id, "before": null, "after": {"id": node_id, "position": points[index], "level": 0}})
			nodes.append(node_id)
		var widths: Array = []
		var surfaces: Array = []
		for _i in range(points.size() - 1):
			widths.append(800)
			surfaces.append("asphalt")
		patches.append({"field": "roads", "id": id, "before": null, "after": {"id": id, "from": nodes[0], "to": nodes[1], "points": points, "widths_cm": widths, "surfaces": surfaces, "kind": "ground", "clearance_cm": null, "sidewalk_cm": null}})
		_report(store.apply_command("Draw road", patches))
	elif tool in ["Building", "Forest", "Orchard"] and draft.size() >= 3:
		var polygon: Array = []
		for p in draft:
			polygon.append([int(p.x), int(p.y)])
		var record := {"id": id}
		var field := "zones"
		if tool == "Building":
			field = "buildings"
			record.merge({"footprint": polygon, "base_cm": 0, "height_cm": 1200, "usage": "residential", "material": "concrete", "roof": "flat"})
		else:
			record.merge({"polygon": polygon, "kind": tool.to_lower(), "spacing_cm": 800, "density_per_mille": 750, "exclusions": []})
		_report(store.apply_command("Draw " + tool, [{"field": field, "id": id, "before": null, "after": record}]))
	else:
		status.emit("Road: 2+ points. Polygon: 3+. Right-click finishes.")
	draft.clear()
	queue_redraw()

func duplicate_selection() -> void:
	_move_selection(Vector2(500, 500), true)

func _move_selection(delta: Vector2, duplicate: bool) -> void:
	var patches: Array = []
	for field in ["buildings", "zones"]:
		for record: Dictionary in store.document[field]:
			if str(record.id) not in selected:
				continue
			var after := record.duplicate(true)
			if duplicate:
				after.id = str(record.id) + "-" + Crypto.new().generate_random_bytes(4).hex_encode()
			var key := "footprint" if field == "buildings" else "polygon"
			for point: Array in after[key]:
				point[0] += int(delta.x)
				point[1] += int(delta.y)
			if field == "zones":
				for polygon: Array in after.exclusions:
					for point: Array in polygon:
						point[0] += int(delta.x)
						point[1] += int(delta.y)
			patches.append({"field": field, "id": after.id, "before": null if duplicate else record, "after": after})
	if not patches.is_empty():
		if dragging and not duplicate:
			var failure: String = store.stage_patches(patches)
			if failure == "":
				failure = store.commit_gesture()
			_report(failure)
		else:
			_report(store.apply_command("Duplicate" if duplicate else "Move selection", patches))

func cancel_interaction(clear_draft: bool = true) -> void:
	dragging = false
	drag_offset = Vector2.ZERO
	if store != null:
		store.cancel_gesture()
	if clear_draft:
		draft.clear()
	queue_redraw()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		cancel_interaction()

func _report(failure: String) -> void:
	status.emit(failure if failure != "" else "Edit applied. Undo: Ctrl+Z")
