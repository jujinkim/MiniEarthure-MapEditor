extends Control
signal selection_changed(ids: Array)
signal status(text: String)
const AUTHOR := preload("./authoring_tools.gd")
var author := AUTHOR.new()
var brush_cursor := Vector2.ZERO
var terrain_textures := {}
const EDIT := preload("./workbench_edit.gd")
var store: RefCounted
var tool := "Select":
	set(value):
		if value != tool:
			cancel_interaction()
		tool = value
var selected: Array[String] = []
var draft: Array[Vector2] = []
var snap_cm := 100.0
var snap_enabled := true
var layer_state: Dictionary = {}
var drag_start := Vector2.ZERO
var dragging := false
var drag_offset := Vector2.ZERO
var marquee := false
var marquee_end := Vector2.ZERO
var marquee_additive := false
var zoom := 1.0
var pan := Vector2.ZERO

func _ready() -> void:
	author.configure(store, self)
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	clip_contents = true

func _scale() -> float:
	var bounds: Dictionary = store.document.bounds
	return maxf(0.00001, minf((size.x - 80.0) / float(bounds.max[0] - bounds.min[0]), (size.y - 80.0) / float(bounds.max[1] - bounds.min[1])) * zoom)

func screen(p: Array) -> Vector2:
	var bounds: Dictionary = store.document.bounds
	return Vector2(40, size.y - 40) + Vector2(float(p[0]) - bounds.min[0], -(float(p[1]) - bounds.min[1])) * _scale() + pan

func raw_world(p: Vector2) -> Vector2:
	var bounds: Dictionary = store.document.bounds
	var v := (p - Vector2(40, size.y - 40) - pan) / _scale()
	return Vector2(v.x + bounds.min[0], -v.y + bounds.min[1])

func world(p: Vector2) -> Vector2:
	var v := raw_world(p)
	var step := snap_cm if snap_enabled else 1.0
	return Vector2(snappedf(v.x, step), snappedf(v.y, step))

func layer_keys(entry: Dictionary) -> Array[String]:
	var result: Array[String] = [entry.field]
	var id: String = str(entry.record.id)
	if id.begins_with("import-"):
		var pieces := id.split("-")
		if pieces.size() >= 3:
			result.append("import/" + pieces[1])
	return result

func available(entry: Dictionary, editing: bool = false) -> bool:
	for layer in layer_keys(entry):
		var state: Dictionary = layer_state.get(layer, {})
		if not state.get("visible", true) or (editing and state.get("locked", false)):
			return false
	return true

func opacity(entry: Dictionary) -> float:
	var value := 1.0
	for layer in layer_keys(entry):
		value *= float(layer_state.get(layer, {}).get("opacity", 1.0))
	return value

func normalize_selection() -> void:
	var keys: Array[String] = []
	for entry in EDIT.entries(store.document):
		if (entry.key in selected or str(entry.record.id) in selected) and available(entry, true):
			keys.append(entry.key)
	selected.assign(keys)

func set_selection(ids: Array) -> void:
	selected.assign(ids)
	normalize_selection()
	selection_changed.emit(selected)
	queue_redraw()

func select_all() -> void:
	var keys: Array[String] = []
	for entry in EDIT.entries(store.document):
		if available(entry, true): keys.append(entry.key)
	set_selection(keys)

func set_layer_state(key: String, value: Dictionary) -> void:
	cancel_interaction()
	layer_state[key] = value.duplicate(true)
	set_selection(selected)

func fit_map() -> void:
	zoom = 1.0
	pan = Vector2.ZERO
	queue_redraw()

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("101216"))
	if store == null or store.document.is_empty(): return
	var doc: Dictionary = store.document
	var bounds: Dictionary = doc.bounds
	var cell := int(doc.cell_size_cm)
	for x in range(int(bounds.min[0]), int(bounds.max[0]) + 1, cell):
		draw_line(screen([x, bounds.min[1]]), screen([x, bounds.max[1]]), Color("34373c"))
	for y in range(int(bounds.min[1]), int(bounds.max[1]) + 1, cell):
		draw_line(screen([bounds.min[0], y]), screen([bounds.max[0], y]), Color("34373c"))
	var visible_tiles := {}
	for tile: Dictionary in doc.heightmaps:
		if not available({"field":"heightmaps", "record":{"id":"terrain"}}): continue
		var start := screen([bounds.min[0] + tile.cell.x * cell, bounds.min[1] + tile.cell.y * cell])
		var end := screen([bounds.min[0] + (tile.cell.x + 1) * cell, bounds.min[1] + (tile.cell.y + 1) * cell])
		var area := Rect2(start, end - start).abs()
		if not area.intersects(Rect2(Vector2.ZERO, size)) or visible_tiles.size() >= 16: continue
		var key: String = store.project_path + ":" + str(tile.path) + ":" + str(tile.offset_cm) + ":" + str(tile.step_cm) + ":" + str(doc.terrain_base_cm)
		var texture: Texture2D = terrain_textures.get(key)
		if texture == null:
			var source := AUTHOR.FILES.read(store.project_path.path_join(tile.path), AUTHOR.TERRAIN.PNG.MAX_BYTES)
			if not source.has("error"):
				var side := int(doc.cell_size_cm) / int(tile.spacing_cm) + 1
				var decoded := AUTHOR.TERRAIN.PNG.decode(source.bytes, side, int(tile.offset_cm), int(tile.step_cm))
				if not decoded.has("error"):
					var thumbnail := Image.create(33, 33, false, Image.FORMAT_RGB8)
					for y in range(33):
						for x in range(33):
							var h := int(decoded.heights[mini(side-1, (32-y)*(side-1)/32)*side + mini(side-1, x*(side-1)/32)])
							var elevation := clampf(float(h - doc.terrain_base_cm) / 2000.0, -1, 1)
							thumbnail.set_pixel(x, y, Color(0.16, 0.23, 0.15).lerp(Color(0.75,0.68,0.40) if elevation >= 0 else Color(0.10,0.20,0.38), absf(elevation)))
					texture = ImageTexture.create_from_image(thumbnail)
		if texture != null:
			draw_texture_rect(texture, area, false, Color(1,1,1,0.8 * opacity({"field":"heightmaps", "record":{"id":"terrain"}})))
			visible_tiles[key] = texture
		draw_string(ThemeDB.fallback_font, Vector2(start.x + 4, end.y + 18), "PNG16 %d,%d · offset %.2fm" % [tile.cell.x, tile.cell.y, tile.offset_cm / 100.0], HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("a4c88c"))
	terrain_textures = visible_tiles
	if tool == "Terrain":
		var center := screen([brush_cursor.x, brush_cursor.y])
		draw_arc(center, float(author.options.radius_cm) * _scale(), 0, TAU, 48, Color("ffe14c"), 2)
		for point in author.terrain.stroke: draw_circle(screen([point.x, point.y]), 3, Color("ffe14c"))
	var transformed := {}
	if dragging and drag_offset != Vector2.ZERO:
		for item: Dictionary in EDIT.plan(doc, selected, "move", drag_offset).patches:
			transformed[EDIT.key(item.field, item.id)] = item.after
	for entry in EDIT.entries(doc):
		if not available(entry): continue
		var record: Dictionary = transformed.get(entry.key, entry.record)
		var points := PackedVector2Array()
		for p in EDIT.points(entry.field, record): points.append(screen([p.x, p.y]))
		var chosen: bool = entry.key in selected
		var color := Color("ffe14c") if chosen else Color("e1e3e6")
		color.a = opacity(entry)
		if not available(entry, true): color = Color(0.5, 0.52, 0.55, color.a)
		if entry.field in ["zones", "buildings"]:
			if points.size() < 3: continue
			if record.get("holes", []).is_empty():
				draw_colored_polygon(points, Color(color, color.a * (0.28 if chosen else 0.12)))
			points.append(points[0])
			draw_polyline(points, color, 2.5 if chosen else 1.5, true)
			for polygon: Array in (record.get("entrances", record.get("exclusions", [])) + record.get("holes", [])):
				var outline := PackedVector2Array()
				for p: Array in polygon: outline.append(screen(p))
				if outline.size() > 2:
					outline.append(outline[0])
					draw_polyline(outline, Color(color, color.a * 0.6), 1.0, true)
		elif entry.field in ["roads", "repetitions"]:
			for i in range(points.size() - 1):
				var width := maxf(3.0, float(record.widths_cm[i]) * _scale()) if entry.field == "roads" else 2.0
				if chosen: draw_line(points[i], points[i + 1], Color("ffe14c"), width + 5.0, true)
				draw_line(points[i], points[i + 1], color if not chosen else Color("4e4825"), width, true)
		else:
			draw_circle(points[0], 5.0 if entry.field == "nodes" else 8.0, Color(color, color.a * 0.35))
			draw_arc(points[0], 5.0 if entry.field == "nodes" else 8.0, 0, TAU, 20, color, 2.0, true)
		if chosen:
			for p in points: draw_rect(Rect2(p - Vector2(3, 3), Vector2(6, 6)), Color("ffe14c"))
	for p in draft: draw_circle(screen([p.x, p.y]), 5.0, Color("ffe14c"))
	if draft.size() > 1:
		var line := PackedVector2Array()
		for p in draft: line.append(screen([p.x, p.y]))
		draw_polyline(line, Color("ffe14c"), 2.0)
	if marquee:
		var start := screen([drag_start.x, drag_start.y])
		var end := screen([marquee_end.x, marquee_end.y])
		var rect := Rect2(start, end - start).abs()
		draw_rect(rect, Color(1, 0.88, 0.3, 0.12))
		draw_rect(rect, Color("ffe14c"), false, 1.5)

func _hit(p: Vector2) -> String:
	var objects := EDIT.entries(store.document)
	objects.reverse()
	for entry in objects:
		if not available(entry, true): continue
		var points := EDIT.points(entry.field, entry.record)
		if entry.field in ["buildings", "zones"]:
			if Geometry2D.is_point_in_polygon(p, PackedVector2Array(points)):
				var courtyard := false
				for ring: Array in entry.record.get("holes", []):
					var hole := PackedVector2Array()
					for point: Array in ring: hole.append(Vector2(point[0], point[1]))
					if Geometry2D.is_point_in_polygon(p, hole): courtyard = true
				if not courtyard: return entry.key
		elif points.size() == 1:
			if p.distance_to(points[0]) <= 9.0 / _scale(): return entry.key
		else:
			for i in range(points.size() - 1):
				var tolerance := maxf(float(entry.record.widths_cm[i]) / 2.0, 8.0 / _scale()) if entry.field == "roads" else 8.0 / _scale()
				if p.distance_to(Geometry2D.get_closest_point_to_segment(p, points[i], points[i + 1])) <= tolerance: return entry.key
	return ""

func _select_at(p: Vector2, additive: bool) -> void:
	var hit := _hit(p)
	if additive:
		if hit in selected: selected.erase(hit)
		elif hit != "": selected.append(hit)
	elif hit not in selected:
		selected.clear()
		if hit != "": selected.append(hit)
	set_selection(selected)

func _snap_vertex(p: Vector2) -> Vector2:
	if not snap_enabled: return p.round()
	var best := p
	var distance := 9.0 / _scale()
	for entry in EDIT.entries(store.document):
		if not available(entry, true): continue
		for vertex in EDIT.points(entry.field, entry.record):
			if p.distance_to(vertex) < distance:
				distance = p.distance_to(vertex)
				best = vertex
	return best

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and event.pressed:
			var anchor := raw_world(event.position)
			zoom = clampf(zoom * (1.15 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.15), 0.25, 32.0)
			pan += event.position - screen([anchor.x, anchor.y])
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			if tool == "Select": cancel_interaction()
			else: finish_shape()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				grab_focus()
				var p := world(event.position)
				if tool == "Terrain":
					var options: Dictionary = author.options.duplicate(true)
					options.spacing_cm = options.grid_cm
					_report(author.terrain.begin(p, options))
				elif tool == "Select":
					var hit := _hit(raw_world(event.position))
					_select_at(raw_world(event.position), event.shift_pressed)
					drag_start = p
					if hit == "":
						marquee = true
						marquee_additive = event.shift_pressed
						marquee_end = p
					elif hit in selected and not event.shift_pressed:
						var failure: String = store.begin_gesture("Move selection")
						dragging = failure == ""
						if failure != "": status.emit(failure)
				else:
					draft.append(_snap_vertex(p))
					if tool == "Place": finish_shape()
					elif event.double_click: finish_shape()
			else:
				if author.terrain.active:
					_report(author.terrain.finish())
				elif marquee:
					var rect := Rect2(drag_start, marquee_end - drag_start).abs()
					var keys: Array = selected.duplicate() if marquee_additive else []
					for entry in EDIT.entries(store.document):
						if not available(entry, true): continue
						var contained := true
						for p in EDIT.points(entry.field, entry.record):
							if not rect.has_point(p): contained = false
						if contained: keys.append(entry.key)
					set_selection(keys)
				elif dragging and drag_offset != Vector2.ZERO:
					_move_selection(drag_offset, false)
				cancel_interaction(false)
		accept_event()
		queue_redraw()
	elif event is InputEventMouseMotion:
		if event.button_mask & MOUSE_BUTTON_MASK_MIDDLE:
			pan += event.relative
		elif author.terrain.active:
			var failure := author.terrain.sample(world(event.position))
			if failure != "":
				author.terrain.cancel()
				status.emit(failure)
		elif dragging:
			drag_offset = world(event.position) - drag_start
		elif marquee:
			marquee_end = world(event.position)
		var p := world(event.position)
		brush_cursor = p
		status.emit("x %.2f m  ·  y %.2f m  ·  %d selected%s" % [p.x / 100.0, p.y / 100.0, selected.size(), "  ·  move %.2f / %.2f m" % [drag_offset.x / 100.0, drag_offset.y / 100.0] if dragging else ""])
		queue_redraw()

func finish_shape() -> void:
	if tool == "Terrain": return
	if draft.size() > 1 and draft[-1] == draft[-2]: draft.pop_back()
	var failure := author.draw(tool, draft)
	_report(failure)
	# Invalid drafts remain editable/cancellable, preserving the user's input.
	if failure == "": draft.clear()
	queue_redraw()

func duplicate_selection() -> void:
	cancel_interaction()
	normalize_selection()
	var bounds := Rect2()
	var first := true
	for entry in EDIT.entries(store.document):
		if entry.key not in selected: continue
		var points := EDIT.points(entry.field, entry.record)
		for polygon: Array in entry.record.get("entrances", entry.record.get("exclusions", [])):
			for p: Array in polygon: points.append(Vector2(p[0], p[1]))
		var radius := 500.0
		if entry.field == "roads":
			for width in entry.record.widths_cm: radius = maxf(radius, float(width) / 2.0)
		for p in points:
			if first:
				bounds = Rect2(p, Vector2.ZERO)
				first = false
			bounds = bounds.expand(p - Vector2.ONE * radius).expand(p + Vector2.ONE * radius)
	if first: return
	var step := snap_cm if snap_enabled else 1.0
	var offset := Vector2(ceilf((bounds.size.x + 500.0) / step) * step, ceilf((bounds.size.y + 500.0) / step) * step)
	# Four bounded candidates, each passing the existing native all-or-none gate.
	for delta in [Vector2(0, offset.y), Vector2(offset.x, 0), Vector2(0, -offset.y), Vector2(-offset.x, 0)]:
		if _execute("duplicate", delta) == "": return

func delete_selection() -> void:
	cancel_interaction()
	_execute("delete")

func _move_selection(delta: Vector2, duplicate: bool) -> void:
	_execute("duplicate" if duplicate else "move", delta.round())

func _execute(operation: String, delta: Vector2 = Vector2.ZERO) -> String:
	normalize_selection()
	var plan := EDIT.plan(store.document, selected, operation, delta)
	if plan.has("error"):
		_report(plan.error)
		return plan.error
	for entry in EDIT.entries(store.document):
		if entry.key in plan.affected and not available(entry, true):
			var reason: String = "Edit affects a hidden or locked layer: " + entry.key + ". Unlock/show it first."
			_report(reason)
			return reason
	if plan.patches.is_empty(): return "No editable selection."
	var failure := ""
	if dragging and operation == "move":
		failure = store.stage_patches(plan.patches)
		if failure == "": failure = store.commit_gesture()
	else:
		failure = store.apply_command(operation.capitalize() + " selection", plan.patches)
	if failure == "": set_selection(plan.selection)
	_report(failure)
	return failure

func cancel_interaction(clear_draft: bool = true) -> void:
	author.terrain.cancel()
	dragging = false
	marquee = false
	drag_offset = Vector2.ZERO
	if store != null: store.cancel_gesture()
	if clear_draft: draft.clear()
	queue_redraw()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT: cancel_interaction()

func _report(failure: String) -> void:
	status.emit(failure if failure != "" else "Edit applied. Undo: Ctrl/Cmd+Z")
