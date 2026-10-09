extends RefCounted
## Same brush session as the 2D canvas; the cursor follows memory terrain.
var editor: Control
var ring: MeshInstance3D
var mesh := ImmediateMesh.new()
var material := StandardMaterial3D.new()

func input(event: InputEvent) -> bool:
	if editor.tool_workspace != "landscape" or editor.canvas.tool not in ["Terrain","Water","Remove water"]:
		if is_instance_valid(ring): ring.hide()
		return false
	if editor.store.editing_locked() or editor.busy or editor._popup_open(editor): return false
	if event is not InputEventMouseMotion and event is not InputEventMouseButton: return false
	if event is InputEventMouseButton and event.button_index != MOUSE_BUTTON_LEFT: return false
	if event is InputEventMouseMotion and event.button_mask & (MOUSE_BUTTON_MASK_MIDDLE | MOUSE_BUTTON_MASK_RIGHT): return false
	var brush: RefCounted = editor.canvas.author.terrain
	if event is InputEventMouseButton and not event.pressed and brush.active:
		var finished: String = brush.finish()
		if finished != "": editor._status(finished)
		return true
	var camera: Camera3D = editor.preview_camera.camera
	var hit: Dictionary = JSON.parse_string(editor.store.working_snapshot().raycast(camera.project_ray_origin(event.position),camera.project_ray_normal(event.position)))
	if not hit.ok or hit.data.is_empty(): return false
	var point := Vector2(hit.data.point[0],hit.data.point[2])
	editor.canvas.brush_cursor = point
	_cursor(point)
	var failure := ""
	if event is InputEventMouseButton:
		if event.pressed:
			if editor.canvas.tool == "Terrain": failure = brush.begin(point, editor.canvas.author.options)
			elif editor.canvas.available({"field":"water_bodies","record":{"id":"water"}},true): failure = editor.store.start_water(point,editor.canvas.tool == "Remove water")
		elif brush.active: failure = brush.finish()
	elif brush.active: failure = brush.sample(point)
	if failure != "": editor._status(failure)
	editor.canvas.queue_redraw()
	return true

func _cursor(point: Vector2) -> void:
	if not is_instance_valid(ring):
		ring = MeshInstance3D.new()
		ring.name = "TerrainBrush"
		ring.mesh = mesh
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.albedo_color = Color("ffb657")
		material.no_depth_test = true
		ring.material_override = material
		editor.preview_world.add_child(ring)
	mesh.clear_surfaces()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	var radius: float = editor.canvas.author.options.radius_cm if editor.canvas.tool == "Terrain" else 100.0
	for i in 48:
		for j in [i,i+1]:
			var p := point + Vector2.from_angle(float(j)*TAU/48)*radius
			var height: Dictionary = JSON.parse_string(editor.store.working_snapshot().height(p))
			if not height.ok:
				mesh.surface_end()
				ring.hide()
				return
			mesh.surface_add_vertex(Vector3(p.x/100, float(height.data.height)/100 + 0.04, -p.y/100))
	mesh.surface_end()
	ring.show()
