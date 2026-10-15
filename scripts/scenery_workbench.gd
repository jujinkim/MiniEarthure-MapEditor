extends Node
const I18N := preload("./locale_text.gd")
const EDIT := preload("./workbench_edit.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var editor: Control
var tool := ""
var turns := 0
var selected := {}
var candidate := {}
var binding := {}
var moving := false
var origin := Vector3.ZERO
var start := {}
var ghost: MeshInstance3D
var last_screen: Variant = null

func build(owner: Control) -> void:
	editor = owner
	editor.store.changed.connect(func(): cancel(); selected = {})

func activate(kind: String) -> void:
	editor._cancel_editing()
	editor.canvas.tool = "Select"
	tool = kind
	binding = token()
	editor._status(I18N.t("Click to place scenery · Escape cancels"))

func token() -> Dictionary:
	return {"epoch":editor.store.command_epoch,"session":editor.store.session_id}

func current() -> bool:
	return binding == token() and not editor.store.editing_locked() and not editor.store.draft_pending()

func cancel() -> void:
	tool = ""
	moving = false
	candidate = {}
	last_screen = null
	if is_instance_valid(ghost): ghost.queue_free()
	ghost = null

func current_height() -> float:
	if candidate.is_empty(): return editor.spatial.height
	return float(candidate.get("base_cm",candidate.get("position",[0,0,0])[1]))/100

func adjust_height(delta: float) -> bool:
	if not current() or (tool == "" and not moving) or candidate.is_empty(): return false
	if candidate.has("base_cm"): candidate.base_cm += roundi(delta*100)
	else: candidate.position[1] += roundi(delta*100)
	show_candidate()
	return true

func point(screen: Vector2) -> Variant:
	if editor.spatial.manual or moving:
		return editor.track_workbench._plane_point(screen,current_height() if moving else editor.spatial.height)
	var hit: Dictionary = editor.spatial.surface(screen)
	if hit.has("point"): return hit.point
	return editor.track_workbench._plane_point(screen,editor.spatial.height)

func update(screen: Vector2) -> bool:
	last_screen = screen
	var p: Variant = point(screen)
	if not p is Vector3: return false
	if moving:
		candidate = EDIT.translated(selected.field,start,Vector2(roundi((p.x-origin.x)*100),roundi(-(p.z-origin.z)*100)))
		if editor.spatial.manual:
			if candidate.has("base_cm"): candidate.base_cm = roundi(editor.spatial.height*100)
			else: candidate.position[1] = roundi(editor.spatial.height*100)
	elif tool == "building":
		var x := roundi(p.x*100); var z := roundi(-p.z*100)
		candidate = {"id":"building-"+Crypto.new().generate_random_bytes(6).hex_encode(),"footprint":[[x-300,z-200],[x+300,z-200],[x+300,z+200],[x-300,z+200]],"base_cm":roundi(p.y*100),"height_cm":400,"usage":"residential","material":"brick","roof":"flat"}
	elif tool != "":
		candidate = {"id":"scenery-"+Crypto.new().generate_random_bytes(6).hex_encode(),"asset_id":tool,"position":[roundi(p.x*100),roundi(p.y*100),roundi(-p.z*100)],"quarter_turns":turns,"yaw_offset_mdeg":0}
	else: return false
	show_candidate()
	return true

func show_candidate() -> void:
	if candidate.is_empty(): return
	if not is_instance_valid(ghost):
		ghost = MeshInstance3D.new()
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.albedo_color = Color(0.2,0.7,1,0.35)
		ghost.material_override = material
		editor.preview_world.add_child(ghost)
	var box := BoxMesh.new()
	box.size = Vector3(1.2,2,1.2)
	if candidate.has("footprint"):
		var low := Vector2(INF,INF); var high := Vector2(-INF,-INF)
		for p: Array in candidate.footprint: low = low.min(Vector2(p[0],p[1])); high = high.max(Vector2(p[0],p[1]))
		box.size = Vector3((high.x-low.x)/100,float(candidate.height_cm)/100,(high.y-low.y)/100)
		ghost.position = Vector3((low.x+high.x)/200,float(candidate.base_cm)/100+box.size.y/2,-(low.y+high.y)/200)
	else:
		if candidate.asset_id == "builtin:fence": box.size = Vector3(4,1,0.15)
		ghost.position = PREVIEW.point(candidate.position)+Vector3.UP*box.size.y/2
		ghost.rotation.y = int(candidate.quarter_turns)*PI/2
	ghost.mesh = box

func commit() -> bool:
	if not current() or candidate.is_empty(): return false
	var field: String = selected.field if moving else "buildings" if tool == "building" else "placements"
	if not editor.canvas.available({"field":field,"record":candidate},true): return false
	var before: Variant = start if moving else null
	if before == candidate: cancel(); return false
	var keep_tool := tool
	var failure: String = editor.canvas.author.apply("Place or move scenery",[EDIT.patch(field,before,candidate)])
	if failure != "": editor._status(I18N.diagnostic(failure)); return false
	if keep_tool != "": activate(keep_tool)
	return true

func rotate_selected() -> void:
	if tool != "":
		turns = (turns+1)%4
		if last_screen != null: update(last_screen)
	elif not selected.is_empty():
		var record: Dictionary = selected.record.duplicate(true)
		if selected.field == "placements": record.quarter_turns = (int(record.quarter_turns)+1)%4
		elif selected.field == "buildings":
			var center := Vector2.ZERO
			for p: Array in record.footprint: center += Vector2(p[0],p[1])
			center /= record.footprint.size()
			var rings: Array = [record.footprint]; rings.append_array(record.get("holes",[])); rings.append_array(record.get("entrances",[]))
			for ring: Array in rings:
				for p: Array in ring:
					var delta := Vector2(p[0],p[1])-center
					p[0] = roundi(center.x-delta.y); p[1] = roundi(center.y+delta.x)
		var failure: String = editor.canvas.author.apply("Rotate scenery",[EDIT.patch(selected.field,selected.record,record)])
		if failure != "": editor._status(I18N.diagnostic(failure))

func pick(screen: Vector2) -> Dictionary:
	var roads: RefCounted = editor.track_workbench.road_tools
	if roads.environment_epoch != editor.store.command_epoch or roads.environment_session != editor.store.session_id: return {}
	var records := {}
	for field in ["placements","buildings"]:
		for record: Dictionary in editor.store.document.get(field,[]):
			var entry := {"field":field,"record":record,"key":EDIT.key(field,record.id)}
			if editor.canvas.available(entry,true): records[record.id] = entry
	var camera: Camera3D = editor.preview_camera.camera
	var ray_origin := camera.project_ray_origin(screen)
	var ray := camera.project_ray_normal(screen)
	var best := {"distance":INF,"id":""}
	for t: Dictionary in roads.triangles:
		if not records.has(t.object_id): continue
		var vertices: Array = t.vertices.map(func(p): return PREVIEW.point(p))
		pick_triangles(vertices,Transform3D.IDENTITY,t.object_id,ray_origin,ray,best)
	# Rendered asset instances retain exact source IDs and production mesh transforms.
	for cell: Dictionary in roads.rendered.values():
		for group: Dictionary in cell.job.instances.values():
			for i in group.ids.size():
				if not records.has(group.ids[i]): continue
				for part: Dictionary in group.groups:
					pick_triangles(Array(part.multi.mesh.get_faces()),part.node.global_transform*part.multi.get_instance_transform(i),group.ids[i],ray_origin,ray,best)
		pick_nodes(cell.job.root,"",records,ray_origin,ray,best)
	return records.get(best.id,{})

func pick_nodes(node: Node, id: String, records: Dictionary, ray_origin: Vector3, ray: Vector3, best: Dictionary) -> void:
	id = node.get_meta("mapkit_object_id",id)
	if node is MeshInstance3D and node.mesh != null and records.has(id): pick_triangles(Array(node.mesh.get_faces()),node.global_transform,id,ray_origin,ray,best)
	for child in node.get_children(): pick_nodes(child,id,records,ray_origin,ray,best)

func pick_triangles(vertices: Array, transform: Transform3D, id: String, ray_origin: Vector3, ray: Vector3, best: Dictionary) -> void:
	for i in range(0,vertices.size(),3):
		var hit: Variant = editor.track_workbench.placement._surface_triangle(ray_origin,ray,transform*vertices[i],transform*vertices[i+1],transform*vertices[i+2])
		if hit is Vector3 and ray_origin.distance_to(hit) < best.distance: best.distance = ray_origin.distance_to(hit); best.id = id

func input(event: InputEvent) -> bool:
	if editor.tool_workspace != "landscape" or editor.busy or editor.store.editing_locked() or editor._popup_open(editor) or editor.canvas.tool != "Select": return false
	if event is InputEventMouseMotion and (moving or tool != ""):
		if event.button_mask & (MOUSE_BUTTON_MASK_RIGHT|MOUSE_BUTTON_MASK_MIDDLE): return false
		update(event.position)
		return true
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if moving and not event.pressed: commit(); cancel(); return true
		if not event.pressed: return false
		if tool != "":
			if update(event.position): commit()
			return true
		selected = pick(event.position)
		editor.canvas.selected = [] if selected.is_empty() else [selected.key]
		editor._selection(editor.canvas.selected)
		if not selected.is_empty():
			binding = token(); start = selected.record.duplicate(true); candidate = start.duplicate(true)
			var p: Variant = editor.track_workbench._plane_point(event.position,current_height())
			if p is Vector3: moving = true; origin = p
		return true
	return false
