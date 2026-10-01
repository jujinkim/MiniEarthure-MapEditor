extends Node
## Uncommitted placement owns only view state. MapKit owns all frames and geometry.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
const STYLE := preload("./workbench_style.gd")
var bench: Node
var tool := ""
var kind := "piece"
var epoch := -1
var document_id := ""
var serial := 0
var candidate: Dictionary = {}
var height := 0.0
var yaw := 0.0
var width_cm := 400
var jump_height_cm := 200
var landing: Variant = null
var hint := "Move over the 3D view to preview · Click to place"
var ghost: Node3D
var guides: MeshInstance3D
var cache: Dictionary = {}
var geometry_builds := 0
var last_point: Variant = null
var last_screen: Variant = null
var yaw_control: SpinBox
var moving_index := -1
var move_origin: Variant = null
var move_item: Dictionary = {}
var moved := false
var hidden_nodes: Array[Node3D] = []
var ghost_key := ""
var pending_pointer: Variant = null
var pointer_updates := 0

func begin_move(index: int, point: Vector3) -> void:
	cancel()
	moving_index = index
	move_origin = point
	move_item = bench.source.instances[index].duplicate(true)
	tool = move_item.preset
	kind = "piece"
	height = float(move_item.position_cm[1]) * 0.01
	yaw = float(move_item.rotation_mdeg[1]) * 0.001
	epoch = bench.editor.store.command_epoch
	document_id = str(bench.editor.store.document.map_id)

func resume_tool(state: Dictionary) -> void:
	for field in ["tool", "kind", "height", "yaw", "width_cm", "landing", "jump_height_cm"]: set(field, state[field])
	epoch = bench.editor.store.command_epoch
	document_id = str(bench.editor.store.document.map_id)
	hint = "Placed · Move to preview the next piece · Click to place"
	bench.palette_tools.select_tool("track." + kind + "." + tool)

func _process(_delta: float) -> void:
	if pending_pointer == null: return
	var screen: Vector2 = pending_pointer
	pending_pointer = null
	if current(): update_pointer(screen)
	else: cancel()


func activate(type: String, preset: String) -> void:
	if not bench.active or bench.editor.store.track_edit_busy or bench.editor.busy: return
	bench.editor._cancel_editing()
	if not bench.editor.preview_dock.visible: bench.editor._set_view_mode("split")
	kind = type
	tool = preset
	epoch = bench.editor.store.command_epoch
	document_id = str(bench.editor.store.document.map_id)
	height = float(bench.source.instances[bench.selected].position_cm[1]) / 100.0 if bench.selected >= 0 else 0.0
	yaw = 0.0
	if kind == "piece":
		for entry: Dictionary in bench.catalogue.entries:
			if entry.id == tool: width_cm = 400 if entry.widths_cm.any(func(value): return int(value) == 400) else int(entry.widths_cm[0])
	else:
		jump_height_cm = roundi(bench.action_height.value * 100.0) if is_instance_valid(bench.action_height) else 200
		landing = null
		if is_instance_valid(bench.landing_target) and bench.landing_target.get_selected_id() >= 0:
			landing = {"piece":bench.source.instances[bench.landing_target.get_selected_id()].id, "sample":int(bench.landing_sample.value)}
	hint = "Move over the 3D view · Click to place · Rotate with the preview controls" if kind == "piece" else "Point at a road surface · Click to attach"
	bench.palette_tools.select_tool("track." + kind + "." + tool)
	bench._properties()
	bench.show_hint()
	bench.editor.commands.refresh_buttons()

func cancel() -> void:
	for node in hidden_nodes:
		if is_instance_valid(node): node.show()
	hidden_nodes.clear()
	moving_index = -1
	move_origin = null
	move_item = {}
	moved = false
	pending_pointer = null
	ghost_key = ""
	serial += 1
	tool = ""
	candidate.clear()
	last_point = null
	last_screen = null
	epoch = -1
	if is_instance_valid(ghost): ghost.queue_free()
	ghost = null
	if is_instance_valid(guides): guides.queue_free()
	guides = null

func invalidate_candidate() -> void:
	pending_pointer = null
	serial += 1
	candidate.clear()
	if is_instance_valid(ghost): ghost.hide()
	if is_instance_valid(guides): guides.hide()
	if tool != "":
		hint = "Move over the 3D view to refresh the preview"
		bench.show_hint()

func current() -> bool:
	return tool != "" and bench.active and epoch == bench.editor.store.command_epoch and document_id == str(bench.editor.store.document.map_id) and bench.editor.preview_dock.visible and not bench.editor._popup_open(bench.editor)

func build_controls(parent: Node) -> void:
	var heading := Label.new()
	heading.text = "PREVIEW · " + bench.piece_name(tool)
	heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(heading)
	if kind == "piece":
		var elevation: SpinBox = bench._spin(parent, "Height (m)", height)
		elevation.value_changed.connect(func(value: float): height = value; invalidate_candidate())
		yaw_control = bench._spin(parent, "Rotation (degrees)", yaw, -360, 360, 0.1)
		yaw_control.value_changed.connect(func(value: float): yaw = value; invalidate_candidate())
		var width := OptionButton.new()
		for entry: Dictionary in bench.catalogue.entries:
			if entry.id != tool: continue
			for w in entry.widths_cm:
				width.add_item("Preview width %dm" % (float(w) / 100.0), int(w))
				if int(w) == width_cm: width.select(width.item_count - 1)
		parent.add_child(width)
		width.item_selected.connect(func(_i: int): width_cm = width.get_selected_id(); invalidate_candidate())
		var row := HBoxContainer.new()
		parent.add_child(row)
		bench.editor.commands.button(row, "track.rotate_left")
		bench.editor.commands.button(row, "track.rotate_right")
	elif kind == "action":
		var jump: SpinBox = bench._spin(parent, "Jump height (m)", float(jump_height_cm) / 100.0, 0.5, 10.0, 0.1)
		jump.value_changed.connect(func(value: float): jump_height_cm = roundi(value * 100); invalidate_candidate())
		var target := OptionButton.new()
		target.add_item("Continuous road jump", -2)
		for i in bench.source.instances.size():
			target.add_item("Landing · " + bench.source.instances[i].id, i)
			if landing != null and landing.piece == bench.source.instances[i].id: target.select(target.item_count - 1)
		parent.add_child(target)
		var station: SpinBox = bench._spin(parent, "Landing sample", 0 if landing == null else landing.sample, 0, 1024, 1)
		var changed := func():
			landing = null if target.get_selected_id() < 0 else {"piece":bench.source.instances[target.get_selected_id()].id, "sample":int(station.value)}
			invalidate_candidate()
		target.item_selected.connect(func(_i: int): changed.call())
		station.value_changed.connect(func(_v: float): changed.call())

func rotate_by(degrees: float) -> void:
	if tool == "" or kind != "piece": return
	yaw = wrapf(yaw + degrees, -180.0, 180.0)
	if is_instance_valid(yaw_control): yaw_control.set_value_no_signal(yaw)
	invalidate_candidate()
	if last_point != null: preview_at(last_point)

func _instance(preset: String, w: int) -> Dictionary:
	return {"id":"preview", "preset":preset, "position_cm":[0, 0, 0], "rotation_mdeg":[0, 0, 0],
		"width_cm":w, "entry_width_cm":w, "exit_width_cm":w,
		"control_points":[[0, 0, 0], [0, 0, 600], [600, 0, 1200], [1200, 0, 1200]] if preset in ["free_curve", "flight_curve"] else []}

func solve_item(item: Dictionary, excluded := -1) -> Dictionary:
	var result: Dictionary = JSON.parse_string(bench.editor.store.bridge.track_instance(JSON.stringify(item)))
	if not result.ok: return {"error":result.error.message}
	var snap_index := -1
	var nearest := 3.0
	if bench.snap.button_pressed:
		for i in bench.source.instances.size():
			if i == excluded: continue
			var other: Dictionary = bench.editor.store.document.assembled_track.pieces[i]
			var distance := PREVIEW.point(result.data.path[0].position_cm).distance_to(PREVIEW.point(other.path.back().position_cm))
			if distance < nearest: nearest = distance; snap_index = i
	if snap_index >= 0:
		var snapped: Dictionary = JSON.parse_string(bench.editor.store.bridge.snap_track_instance(JSON.stringify(item), JSON.stringify(bench.source.instances[snap_index])))
		if not snapped.ok: return {"error":snapped.error.message}
		item = snapped.data
		result = JSON.parse_string(bench.editor.store.bridge.track_instance(JSON.stringify(item)))
		if not result.ok: return {"error":result.error.message}
	return {"item":item, "piece":result.data, "snap":snap_index}

func preview_at(point: Vector3) -> bool:
	if not current(): invalidate_candidate(); return false
	last_point = point
	pointer_updates += 1
	serial += 1
	var item: Dictionary
	if moving_index >= 0:
		var delta: Vector3 = point - move_origin
		if not moved and delta.length() <= 0.01: return false
		moved = true
		item = move_item.duplicate(true)
		item.position_cm[0] += roundi(delta.x * 100)
		item.position_cm[2] -= roundi(delta.z * 100)
	else:
		item = _instance(tool, width_cm)
		item.position_cm = [roundi(point.x * 100), roundi(height * 100), roundi(-point.z * 100)]
		item.rotation_mdeg[1] = roundi(yaw * 1000)
	var solved := solve_item(item, moving_index)
	if solved.has("error"): _failure(solved.error); return false
	candidate = {"serial":serial, "epoch":epoch, "document":document_id, "kind":kind, "tool":tool, "item":solved.item, "snap":solved.snap}
	if moving_index >= 0: _show_move(solved.piece)
	elif not _show_ghost(solved.item, -1, solved.piece): return false
	hint = ("Release to move" if moving_index >= 0 else "Click to place · Rotate with the preview controls") + (" · Snap to " + bench.source.instances[solved.snap].id if solved.snap >= 0 else " · No port snap")
	bench.show_hint()
	return true

func _show_move(piece: Dictionary) -> void:
	if not is_instance_valid(ghost):
		ghost = Node3D.new()
		bench.editor.preview_world.add_child(ghost)
		for node: MeshInstance3D in bench.view.get_meta("objects", {}).values():
			if node.get_meta("owner", -1) != moving_index: continue
			var copy := node.duplicate()
			ghost.add_child(copy)
			node.hide()
			hidden_nodes.append(node)
		_tint(ghost)
	var original: Dictionary = bench.editor.store.document.assembled_track.pieces[moving_index]
	ghost.transform = frame(piece.path[0]) * frame(original.path[0]).affine_inverse()
	ghost.show()
	_draw_guides(piece, -1)

func commit_move() -> bool:
	if not current() or not moved or candidate.is_empty() or candidate.epoch != epoch or candidate.serial != serial: return false
	# Returning to the same transform is a click/no-op, even near a port.
	if last_point != null and last_point.distance_to(move_origin) <= 0.01: return false
	if candidate.item == move_item: return false
	var next: Dictionary = bench.source.duplicate(true)
	next.instances[moving_index] = candidate.item.duplicate(true)
	if candidate.snap >= 0:
		var edge := {"from":next.instances[candidate.snap].id, "to":candidate.item.id}
		if not next.connections.has(edge): next.connections.append(edge)
	return bench._commit(next)

func preview_attachment(piece_index: int, sample: int) -> bool:
	if not current() or kind == "piece": return false
	serial += 1
	if piece_index < 0 or piece_index >= bench.source.instances.size():
		_failure("Point at a road surface to attach this tool.")
		return false
	var piece: Dictionary = bench.editor.store.document.assembled_track.pieces[piece_index]
	if sample < 0 or sample >= piece.path.size() or piece.path[sample].mode == "flight":
		_failure("This point has no supported road surface.")
		return false
	candidate = {"serial":serial, "epoch":epoch, "document":document_id, "kind":kind, "tool":tool,
		"target":piece_index, "sample":sample, "height_cm":jump_height_cm, "landing":landing.duplicate(true) if landing is Dictionary else null}
	if not _show_ghost(bench.source.instances[piece_index], sample): return false
	hint = "Click to attach · " + str(bench.source.instances[piece_index].id) + " / " + str(sample) + ""
	bench.show_hint()
	return true

func _failure(reason: String) -> void:
	invalidate_candidate()
	hint = reason
	bench.show_hint()

func commit(expected_serial := -1) -> bool:
	if not current() or candidate.is_empty(): return false
	if expected_serial >= 0 and expected_serial != serial: return false
	if candidate.serial != serial or candidate.epoch != epoch or candidate.document != document_id or candidate.tool != tool: return false
	var next: Dictionary = bench.source.duplicate(true)
	var next_selection: int = bench.selected
	if kind == "piece":
		var item: Dictionary = candidate.item.duplicate(true)
		item.id = "p-" + Crypto.new().generate_random_bytes(4).hex_encode()
		if candidate.snap >= 0: next.connections.append({"from":next.instances[candidate.snap].id, "to":item.id})
		if next.paths.is_empty(): next.paths = [{"id":"base", "pieces":[]}]
		next.paths[clampi(bench.route_index, 0, next.paths.size() - 1)].pieces.append(item.id)
		next.instances.append(item)
		next_selection = next.instances.size() - 1
	elif kind == "action":
		next.actions.append({"id":"a-" + Crypto.new().generate_random_bytes(4).hex_encode(), "kind":tool,
			"piece":next.instances[candidate.target].id, "sample":candidate.sample, "height_cm":candidate.height_cm, "landing":candidate.landing})
	else:
		var attachment:=_attachment(next.instances[candidate.target], candidate.sample)
		next.attachments.append(attachment)
		if tool=="grind_rail":
			var result: Dictionary=JSON.parse_string(bench.editor.store.bridge.track_attachment_lines(JSON.stringify(next.instances[candidate.target]),JSON.stringify(attachment)))
			if not result.ok:_failure(result.error.message);return false
			for line: Dictionary in result.data:
				line.id="grind-"+Crypto.new().generate_random_bytes(6).hex_encode()
				next.get_or_add("grind_lines",[]).append(line)
	var state := {"tool":tool, "kind":kind, "height":float(next.instances[next_selection].position_cm[1]) / 100.0 if kind == "piece" else height,
		"yaw":yaw, "width_cm":width_cm, "landing":landing, "jump_height_cm":jump_height_cm}
	if not bench._commit(next, next_selection, {"repeat":state}): return false
	# Admission consumes the candidate. Repeat placement resumes only after success.
	cancel()
	return true

func _attachment(item: Dictionary, sample: int) -> Dictionary:
	var result: Dictionary = JSON.parse_string(bench.editor.store.bridge.track_instance(JSON.stringify(item)))
	var station := 0.0
	for i in range(1, sample + 1): station += PREVIEW.point(result.data.path[i].position_cm).distance_to(PREVIEW.point(result.data.path[i - 1].position_cm)) * 100
	return {"kind":tool, "piece":item.id, "path":"main", "station_cm":roundi(station), "side":1}

static func frame(sample: Dictionary) -> Transform3D:
	var forward := PREVIEW.point(sample.forward).normalized()
	var normal := PREVIEW.point(sample.normal).normalized()
	return Transform3D(Basis(forward.cross(normal).normalized(), normal, -forward), PREVIEW.point(sample.position_cm))

func _show_ghost(item: Dictionary, sample := -1, compiled_piece: Dictionary = {}) -> bool:
	# Cache a single isolated piece using MapKit's production tessellator. Pointer
	# movement changes a rigid transform, never recompiles the document.
	var local := item.duplicate(true)
	local.id = "preview"
	local.position_cm = [0, 0, 0]
	local.rotation_mdeg = [0, 0, 0]
	var key := JSON.stringify([local, kind, tool if kind != "piece" else "", sample, jump_height_cm if kind == "action" else 0])
	if not cache.has(key):
		var source: Dictionary = bench.source.duplicate(true)
		for field in ["connections", "paths", "checkpoints", "actions", "attachments", "grind_lines", "structures"]: source[field] = []
		source.instances = [local]
		source.original_seed = null
		source.grounded_supports = false
		source.settings.circuit = false
		if kind == "action": source.actions = [{"id":"preview", "kind":tool, "piece":"preview", "sample":sample, "height_cm":jump_height_cm, "landing":null}]
		elif kind == "obstacle":
			source.attachments = [_attachment(local, sample)]
			if tool=="grind_rail":
				var lines: Dictionary=JSON.parse_string(bench.editor.store.bridge.track_attachment_lines(JSON.stringify(local),JSON.stringify(source.attachments[0])))
				if not lines.ok:_failure(lines.error.message);return false
				source.grind_lines=lines.data
		var compiled: Dictionary = JSON.parse_string(bench.editor.store.bridge.compile_track_source(JSON.stringify(source)))
		if not compiled.ok: _failure(compiled.error.message); return false
		var template := PREVIEW.create(compiled.data.document)
		_tint(template)
		if cache.size() >= 24:
			cache[cache.keys()[0]].node.free()
			cache.erase(cache.keys()[0])
		cache[key] = {"node":template, "entry":compiled.data.document.assembled_track.pieces[0].path[0]}
		geometry_builds += 1
	if ghost_key != key or not is_instance_valid(ghost):
		if is_instance_valid(ghost): ghost.queue_free()
		ghost = cache[key].node.duplicate()
		bench.editor.preview_world.add_child(ghost)
		ghost_key = key
	if compiled_piece.is_empty():
		var result: Dictionary = JSON.parse_string(bench.editor.store.bridge.track_instance(JSON.stringify(item)))
		if not result.ok: _failure(result.error.message); return false
		compiled_piece = result.data
	ghost.transform = frame(compiled_piece.path[0]) * frame(cache[key].entry).affine_inverse()
	ghost.show()
	_draw_guides(compiled_piece, sample)
	return true

func _tint(node: Node) -> void:
	if node is MeshInstance3D:
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.albedo_color = Color(0.34, 0.73, 1.0, 0.4)
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		node.material_override = material
	for child in node.get_children(): _tint(child)

func _draw_guides(piece: Dictionary, sample: int) -> void:
	if not is_instance_valid(guides):
		guides = MeshInstance3D.new()
		guides.mesh = ImmediateMesh.new()
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.vertex_color_use_as_albedo = true
		material.no_depth_test = true
		guides.material_override = material
		bench.editor.preview_world.add_child(guides)
	guides.show()
	var mesh: ImmediateMesh = guides.mesh
	mesh.clear_surfaces()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	# Flight curves deliberately have no solid surface; show the shared sampled
	# trajectory as an editor guide instead of inventing road geometry.
	mesh.surface_set_color(STYLE.BLUE)
	for i in range(1, piece.path.size()):
		if piece.path[i].mode == "flight" or piece.path[i - 1].mode == "flight":
			mesh.surface_add_vertex(PREVIEW.point(piece.path[i - 1].position_cm))
			mesh.surface_add_vertex(PREVIEW.point(piece.path[i].position_cm))
	var samples: Array = [piece.path[0], piece.path.back()] if sample < 0 else [piece.path[sample]]
	for i in samples.size():
		var pose := frame(samples[i])
		mesh.surface_set_color(STYLE.CORAL if i == 0 else STYLE.YELLOW)
		var start := pose.origin + pose.basis.y * 0.15
		var tip := start - pose.basis.z * 2
		for segment in [[start, tip], [tip, tip + pose.basis.z * 0.6 + pose.basis.x * 0.4], [tip, tip + pose.basis.z * 0.6 - pose.basis.x * 0.4]]:
			mesh.surface_add_vertex(segment[0]); mesh.surface_add_vertex(segment[1])
	if candidate.get("snap", -1) >= 0:
		var port: Dictionary = bench.editor.store.document.assembled_track.pieces[candidate.snap].path.back()
		var pose := frame(port)
		mesh.surface_set_color(STYLE.YELLOW)
		for points in [[Vector3(-1,0,0), Vector3(1,0,0)], [Vector3(0,-1,0), Vector3(0,1,0)]]:
			mesh.surface_add_vertex(pose * points[0]); mesh.surface_add_vertex(pose * points[1])
	mesh.surface_end()

static func _surface_triangle(origin: Vector3, ray: Vector3, a: Vector3, b: Vector3, c: Vector3) -> Variant:
	if (b - a).cross(c - a).length_squared() < 0.00000001: return null
	var hit: Variant = Plane(a, b, c).intersects_ray(origin, ray)
	if not hit is Vector3: return null
	# Include shared triangle edges; excluding an exact sample seam makes a
	# perfectly valid road-center pointer disappear between adjacent triangles.
	var weights := Geometry3D.get_triangle_barycentric_coords(hit, a, b, c)
	return hit if minf(weights.x, minf(weights.y, weights.z)) >= -0.00001 else null

func _surface_at(screen: Vector2) -> Dictionary:
	var camera: Camera3D = bench.editor.preview_camera.camera
	var origin := camera.project_ray_origin(screen)
	var ray := camera.project_ray_normal(screen)
	var best := {"distance":INF, "piece":-1, "sample":-1}
	var pieces: Array = bench.editor.store.document.get("assembled_track", {}).get("pieces", [])
	# Use the shared driving frames/widths. Each ribbon quad is selectable from
	# its driving side; flight samples never become attachment targets.
	for p in pieces.size():
		var path: Array = pieces[p].path
		for i in range(1, path.size()):
			if path[i - 1].mode == "flight" or path[i].mode == "flight": continue
			var a := frame(path[i - 1])
			var b := frame(path[i])
			if ray.dot(a.basis.y) >= 0: continue
			var w := float(path[i - 1].lateral_cm) * 0.01
			var v := float(path[i].lateral_cm) * 0.01
			var points := [a.origin - a.basis.x*w, a.origin + a.basis.x*w, b.origin + b.basis.x*v, b.origin - b.basis.x*v]
			for triangle in [[0, 1, 2], [0, 2, 3]]:
				var hit: Variant = _surface_triangle(origin, ray, points[triangle[0]], points[triangle[1]], points[triangle[2]])
				if hit is Vector3 and origin.distance_to(hit) < best.distance:
					best = {"distance":origin.distance_to(hit), "piece":p, "sample":i - 1 if hit.distance_to(a.origin) <= hit.distance_to(b.origin) else i}
	return best

func update_pointer(screen: Vector2) -> bool:
	last_screen = screen
	if kind == "piece":
		var point: Variant = bench._plane_point(screen, height)
		if point == null: _failure("Point at the placement plane."); return false
		return preview_at(point)
	var hit := _surface_at(screen)
	return preview_attachment(hit.piece, hit.sample)

func input(event: InputEvent) -> bool:
	if bench.editor.store.track_edit_busy: cancel(); return false
	if not current(): cancel(); return false
	if event is InputEventMouseMotion:
		if event.button_mask & (MOUSE_BUTTON_MASK_RIGHT | MOUSE_BUTTON_MASK_MIDDLE):
			if moving_index >= 0: cancel()
			else: invalidate_candidate()
			return false
		pending_pointer = event.position
		return true
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if moving_index >= 0:
				if not event.pressed:
					pending_pointer = null
					if update_pointer(event.position): commit_move()
					cancel()
				return true
			if event.pressed and not event.double_click:
				# Refresh at the click position, using only the current generation.
				if update_pointer(event.position): commit(serial)
			return true
		if event.button_index in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			if moving_index >= 0: cancel()
			else: invalidate_candidate()
	return false

func _exit_tree() -> void:
	cancel()
	for entry: Dictionary in cache.values(): entry.node.free()
	cache.clear()
