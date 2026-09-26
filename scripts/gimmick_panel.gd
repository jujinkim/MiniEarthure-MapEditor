extends RefCounted
## Focused authoring for the current declarative structure contract.
const GEOMETRY := preload("res://addons/mapkit/godot/gimmick_geometry.gd")
var panel: Control
var picker: OptionButton
var template: OptionButton
var controls := {}
var before: Dictionary = {}
var preview: Node3D
var records: Array = []
var templates: Dictionary
var picking_surface := false

func setup(owner: Control) -> void:
	panel = owner
	var box: VBoxContainer = panel.page("Driving structures")
	panel.hint(box, "Motion uses a separate preview clock. Swept and landing bounds are validated when saving. Large jumps and moving obstacles need a bypass.")
	records = panel.editor.store.document.get("gimmicks", []).duplicate(true)
	picker = panel.choice(box, "Object", ["New structure"], "New structure")
	for record: Dictionary in records: picker.add_item(record.id)
	templates = JSON.parse_string(FileAccess.get_file_as_string("res://addons/mapkit/godot/driving_templates.json"))
	template = panel.choice(box, "Template", templates.keys(), templates.keys()[0])
	for axis in ["X", "Y", "Z"]:
		controls[axis] = panel.number(box, "Position " + axis + " (m)", 32 if axis != "Y" else 0, -10000, 10000, 0.01)
	controls.pitch = panel.number(box, "Pitch (degrees)", 0, -360, 360, 0.1)
	controls.roll = panel.number(box, "Roll (degrees)", 0, -360, 360, 0.1)
	controls.yaw = panel.number(box, "Yaw (degrees)", 0, -360, 360, 1)
	controls.strength = panel.number(box, "Target speed strength (%)", 100, 1, 100, 1)
	controls.height = panel.number(box, "Jump apex in still air (m)", 3, 0.1, 10, 0.1)
	controls.radius = panel.number(box, "Track radius (m)", 2.5, 1.5, 6, 0.1)
	controls.width = panel.number(box, "Loop width (m)", 2.2, 1.4, 6, 0.1)
	controls.length = panel.number(box, "Cylinder length (m)", 16, 6, 32, 0.1)
	panel.button(box, "Place panel on surface (click preview)", func():
		picking_surface = true
		panel.report("Click a road or the inner face of a static track. Yaw sets the travel direction."))
	controls.period = panel.number(box, "Period (seconds)", 5, 0.25, 120, 0.25)
	controls.phase = panel.number(box, "Initial phase (seconds)", 0, 0, 119.75, 0.25)
	for axis in ["X", "Y", "Z"]: controls["delta"+axis] = panel.number(box, "Travel " + axis + " (m)", 0, -32, 32, 0.1)
	for axis in ["X", "Y", "Z"]: controls["impulse"+axis] = panel.number(box, "Pad impulse " + axis + " (m/s)", 0, -50, 50, 0.1)
	controls.landing = panel.number(box, "Extra landing margin (m)", 20, 0, 64, 1)
	controls.time = panel.number(box, "Preview time (seconds)", 0, 0, 120, 0.05)
	controls.time.value_changed.connect(func(_v): show_preview())
	picker.item_selected.connect(select_record)
	template.item_selected.connect(func(_i):
		if before.is_empty(): load_controls(templates[template.get_item_text(template.selected)]))
	panel.button(box, "Preview motion and full bounds", show_preview)
	panel.button(box, "Save structure", save_record)
	panel.button(box, "Remove selected structure", remove_record)
	load_controls(templates[template.get_item_text(template.selected)])

func select_record(index: int) -> void:
	before = {} if index == 0 else records[index - 1].duplicate(true)
	load_controls(templates[template.get_item_text(template.selected)] if before.is_empty() else before)

func load_controls(g: Dictionary) -> void:
	for i in 3:
		var axis: String = ["X","Y","Z"][i]
		controls[axis].value = g.position[i] / 100.0
		controls["delta"+axis].value = g.motion.delta_cm[i] / 100.0
		controls["impulse"+axis].value = g.motion.impulse_cmps[i] / 100.0
	controls.yaw.value = g.rotation_mdeg[1] / 1000.0
	controls.pitch.value = g.rotation_mdeg[0] / 1000.0
	controls.roll.value = g.rotation_mdeg[2] / 1000.0
	controls.strength.value = g.get("effect",{}).get("strength_percent",100)
	controls.height.value = g.get("effect",{}).get("jump_height_cm",300)/100.0
	var track: Dictionary = g.get("track",{})
	controls.radius.value = track.get("radius_cm",250)/100.0
	controls.width.value = track.get("width_cm",220)/100.0
	controls.length.value = track.get("length_cm",1600)/100.0
	controls.period.value = g.motion.period_ms / 1000.0
	controls.phase.value = g.motion.phase_ms / 1000.0

func draft() -> Dictionary:
	var g: Dictionary = (templates[template.get_item_text(template.selected)] if before.is_empty() else before).duplicate(true)
	if before.is_empty(): g.id = "structure-" + Crypto.new().generate_random_bytes(6).hex_encode()
	for i in 3:
		var axis: String = ["X","Y","Z"][i]
		g.position[i] = roundi(controls[axis].value * 100)
		g.motion.delta_cm[i] = roundi(controls["delta"+axis].value * 100)
		g.motion.impulse_cmps[i] = roundi(controls["impulse"+axis].value * 100)
	g.rotation_mdeg = [roundi(controls.pitch.value*1000),roundi(controls.yaw.value*1000),roundi(controls.roll.value*1000)]
	if g.has("effect"):
		g.effect.strength_percent = roundi(controls.strength.value)
		g.effect.jump_height_cm = roundi(controls.height.value*100)
	if g.has("track"):
		g.track.radius_cm = roundi(controls.radius.value*100)
		g.track.width_cm = roundi(controls.width.value*100)
		g.track.length_cm = roundi(controls.length.value*100)
	g.motion.period_ms = roundi(controls.period.value * 1000)
	g.motion.phase_ms = roundi(controls.phase.value * 1000)
	var radius := 0
	for part: Dictionary in g.parts:
		for v: Array in part.vertices: radius = maxi(radius, ceili(absf(v[0])*g.scale_per_mille[0]/1000.0 + absf(v[1])*g.scale_per_mille[1]/1000.0 + absf(v[2])*g.scale_per_mille[2]/1000.0))
	if g.has("track"):
		radius = 4*int(g.track.radius_cm) + (2*int(g.track.width_cm) if g.track.kind == "loop" else int(g.track.length_cm)/2) + 40
	var margin := roundi(controls.landing.value * 100) if g.motion.kind in ["boost","launch","target_speed","jump_height","air_ring"] else 0
	for i in 3:
		g.safety_min_cm[i] = g.position[i] - radius + mini(0,int(g.motion.delta_cm[i])) - margin
		g.safety_max_cm[i] = g.position[i] + radius + maxi(0,int(g.motion.delta_cm[i])) + margin
	return g

func show_preview() -> void:
	if is_instance_valid(preview): preview.queue_free()
	var g := draft()
	for cached: Dictionary in panel.editor.preview_cache.values():
		for node: Node in cached.root.get_children():
			if node.has_meta("gimmick_id"): node.visible = node.get_meta("gimmick_id") != g.id
	preview = Node3D.new()
	var mesh := GEOMETRY.visual(g)
	mesh.transform = GEOMETRY.pose(g, roundi(controls.time.value * 1000))
	preview.add_child(mesh)
	var bounds := MeshInstance3D.new()
	var cube := BoxMesh.new()
	cube.size = (GEOMETRY.point(g.safety_max_cm) - GEOMETRY.point(g.safety_min_cm)).abs()
	bounds.mesh = cube
	bounds.position = (GEOMETRY.point(g.safety_max_cm) + GEOMETRY.point(g.safety_min_cm)) * 0.5
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(0.2,0.8,1,0.12)
	bounds.material_override = material
	preview.add_child(bounds)
	panel.editor.viewport.add_child(preview)

func save_record() -> void:
	var g := draft()
	var error: String = panel.editor.store.apply_command("Edit driving structure",[{"field":"gimmicks","id":g.id,"before":null if before.is_empty() else before,"after":g}])
	if error.is_empty():
		if before.is_empty():
			records.append(g.duplicate(true))
			picker.add_item(g.id)
			picker.select(records.size())
		else: records[picker.selected - 1] = g.duplicate(true)
		before = g.duplicate(true)
	panel.report(error if not error.is_empty() else "Structure saved.")

func remove_record() -> void:
	if before.is_empty(): return
	panel.report(panel.editor.store.apply_command("Remove driving structure",[{"field":"gimmicks","id":before.id,"before":before,"after":null}]))

func teardown() -> void:
	for cached: Dictionary in panel.editor.preview_cache.values():
		for node: Node in cached.root.get_children():
			if node.has_meta("gimmick_id"): node.visible = true
	if is_instance_valid(preview): preview.queue_free()

static func surface_pose(position: Vector3, normal: Vector3, direction: Vector3) -> Transform3D:
	var forward := direction.slide(normal).normalized()
	if forward.length_squared() < 0.01: forward = Vector3.RIGHT.slide(normal).normalized()
	return Transform3D(Basis(forward.cross(normal).normalized(),normal.normalized(),-forward),position)

func surface_input(event: InputEvent) -> bool:
	if not picking_surface or not event is InputEventMouseButton or event.button_index != MOUSE_BUTTON_LEFT or not event.pressed: return false
	var g := draft()
	if g.motion.kind not in ["boost","launch","target_speed","jump_height"]:
		panel.report("Surface placement is available for static panels.")
		picking_surface = false
		return true
	var camera: Camera3D = panel.editor.preview_camera.camera
	var origin := camera.project_ray_origin(event.position)
	var direction := camera.project_ray_normal(event.position)
	var best := {"distance":INF}
	for cached: Dictionary in panel.editor.preview_cache.values():
		_pick_meshes(cached.root,origin,direction,best,false)
	if not best.has("position"):
		panel.report("No eligible surface at this point.")
		return true
	var transform := surface_pose(best.position,best.normal,-GEOMETRY.pose(g,0).basis.z)
	var angles := transform.basis.get_euler()
	controls.X.value = transform.origin.x
	controls.Y.value = transform.origin.y
	controls.Z.value = -transform.origin.z
	controls.pitch.value = -rad_to_deg(angles.x)
	controls.yaw.value = -rad_to_deg(angles.y)
	controls.roll.value = rad_to_deg(angles.z)
	picking_surface = false
	show_preview()
	return true

func _pick_meshes(node: Node, origin: Vector3, ray: Vector3, best: Dictionary, special: bool) -> void:
	if node.has_meta("gimmick_id"):
		var id: String = node.get_meta("gimmick_id")
		for record: Dictionary in panel.editor.store.document.get("gimmicks",[]):
			if record.id == id:
				if record.motion.kind != "static" or not record.has("track"): return
				special = true
	if node is MeshInstance3D and node.mesh != null:
		if special and not bool(node.get_meta("curved_driving_surface",false)): return
		var faces: PackedVector3Array = node.mesh.get_faces()
		for i in range(0,faces.size(),3):
			var a: Vector3 = node.global_transform*faces[i]
			var b: Vector3 = node.global_transform*faces[i+1]
			var c: Vector3 = node.global_transform*faces[i+2]
			var normal := (c-a).cross(b-a).normalized()
			if (not special and normal.y < 0.2) or normal.dot(ray) >= 0.0: continue
			var hit: Variant = Geometry3D.ray_intersects_triangle(origin,ray,a,b,c)
			if hit is Vector3 and origin.distance_to(hit) < float(best.distance):
				best.distance = origin.distance_to(hit)
				best.position = hit
				best.normal = normal
	for child: Node in node.get_children(): _pick_meshes(child,origin,ray,best,special)
