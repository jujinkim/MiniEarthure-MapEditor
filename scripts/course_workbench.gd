extends Node
## Course review and direct manipulation share the document's existing command owner.
const I18N := preload("./locale_text.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
const RENDER := preload("res://addons/mapkit/godot/course_renderer.gd")
var editor: Control
var panel: VBoxContainer
var preview: Node3D
var proposal := {}
var binding := {}
var gates: Array = []
var selected := -1
var moving := false
var move_before := {}
var placing := false
var manual_course := false
var original := {}
var circuit := false
var course_name := "My course"
var closure := {}
var closure_view: Node3D
var road_picking := false
var road_seconds := 60
var road_proposal := {}
var start_direction: Array = []

func build(owner: Control) -> void:
	editor = owner
	panel = VBoxContainer.new()
	panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	editor.left_dock.add_child(panel)
	panel.hide()
	editor.store.changed.connect(changed)
	editor.store.draft_changed.connect(func(_context: Dictionary): changed())

func token() -> Dictionary:
	return {"session":editor.store.session_id,"epoch":editor.store.command_epoch,"revision":editor.store.draft_revision}

func current() -> bool:
	return binding == token() and not editor.store.editing_locked() and not editor.busy

func open() -> void:
	panel.show()
	if gates.is_empty() and proposal.is_empty(): load_current()
	show_gates()
	refresh()

func changed() -> void:
	if binding.get("session",-1) != editor.store.session_id:
		manual_course = false; original = {}; course_name = I18N.t("My course"); circuit = false; start_direction = []; road_proposal = {}
	proposal = {}
	road_picking = false
	closure = {}
	moving = false
	placing = false
	move_before = {}
	if is_instance_valid(closure_view): closure_view.queue_free()
	if editor.tool_group == "course": load_current(); refresh()
	else:
		gates = []
		if is_instance_valid(preview): preview.queue_free()

func load_current() -> void:
	binding = token()
	gates = []
	selected = -1
	var source: Dictionary = editor.store.track_source()
	if not manual_course and not source.instances.is_empty():
		circuit = source.settings.circuit
		for cp: Dictionary in source.checkpoints:
			var index := -1
			for i in source.instances.size():
				if source.instances[i].id == cp.piece: index = i; break
			if index < 0: continue
			var result: Dictionary = JSON.parse_string(editor.store.bridge.track_checkpoint(JSON.stringify(editor.store.track_pieces()[index].path[int(cp.sample)])))
			if result.ok:
				var gate: Dictionary = result.data
				gate.surface_id = "assembled-road-%d" % index
				gates.append(gate)
	else:
		manual_course = true
		if not original.is_empty():
			for course: Dictionary in editor.store.document.get("courses",[]):
				if course.course_id == original.course_id: original = course.duplicate(true); gates = original.definition.checkpoints.duplicate(true)
		elif not editor.store.document.get("courses",[]).is_empty():
			original = editor.store.document.get("courses",[])[0].duplicate(true)
			gates = original.definition.checkpoints.duplicate(true)
		if not original.is_empty(): circuit = original.definition.mode == "circuit"; course_name = original.definition.display_name
	show_gates()

func refresh() -> void:
	for child in panel.get_children(): panel.remove_child(child); child.queue_free()
	editor._label(panel,I18N.t("Course"))
	var name_input := LineEdit.new()
	name_input.text = course_name
	name_input.placeholder_text = I18N.t("Course name")
	name_input.text_changed.connect(func(value: String): course_name = value)
	panel.add_child(name_input)
	var mode := CheckButton.new()
	mode.text = I18N.t("Circuit")
	mode.button_pressed = circuit
	mode.toggled.connect(func(value: bool):
		circuit = value
		if not manual_course:
			var source: Dictionary = editor.store.track_source()
			source.settings.circuit = value
			editor.track_workbench._commit(source))
	panel.add_child(mode)
	editor._button(panel,"Suggest basic course",suggest)
	editor._button(panel,"Preview circuit connection",preview_closure)
	editor._button(panel,"New course on surfaces",func():
		editor._cancel_editing()
		manual_course = true; original = {}; gates = []; proposal = {}; road_proposal = {}; start_direction = []; binding = token(); refresh(); show_gates())
	if not editor.store.document.get("roads",[]).is_empty():
		var seconds := SpinBox.new()
		seconds.min_value = 20; seconds.max_value = 300; seconds.step = 10; seconds.value = road_seconds
		seconds.suffix = "s"; seconds.tooltip_text = I18N.t("Road course duration at the reference speed")
		seconds.value_changed.connect(func(value: float): road_seconds = int(value))
		panel.add_child(seconds)
		editor._button(panel,"Suggest course on roads",func():
			editor._cancel_editing()
			road_picking = true; binding = token()
			editor._status(I18N.t("Click a road to start; the course follows the camera direction.")))
		for diagnostic: Dictionary in road_proposal.get("diagnostics",[]):
			var button: Button = editor._button(panel,I18N.diagnostic(diagnostic.message),func():
				if diagnostic.position_cm != null: editor.preview_camera.frame(PREVIEW.point(diagnostic.position_cm),32))
			button.custom_minimum_size.x = 220
	if not editor.store.document.get("courses",[]).is_empty():
		var picker := OptionButton.new()
		picker.add_item(I18N.t("Open existing course"))
		for course: Dictionary in editor.store.document.get("courses",[]): picker.add_item(course.definition.display_name)
		picker.item_selected.connect(func(index: int):
			if index == 0: return
			manual_course = true; original = editor.store.document.get("courses",[])[index-1].duplicate(true)
			proposal = {}; load_current(); refresh())
		panel.add_child(picker)
	if manual_course: editor._button(panel,"Add checkpoint in 3D",func(): placing = true; editor._status(I18N.t("Click a surface to place a checkpoint.")))
	var list := ItemList.new()
	list.custom_minimum_size.y = 100
	panel.add_child(list)
	for i in gates.size(): list.add_item(I18N.t("Start") if i == 0 else I18N.t("Finish") if i == gates.size()-1 and not circuit else I18N.t("Checkpoint %d") % (i+1))
	list.item_selected.connect(func(index: int): selected = index; editor.preview_camera.frame(PREVIEW.point(gates[index].position_cm),32))
	editor._label(panel,I18N.t("Select and drag checkpoints in 3D. Escape cancels."))
	if selected >= 0:
		editor._button(panel,"Delete checkpoint",delete_checkpoint)
	if not proposal.is_empty():
		editor._label(panel,I18N.t("Review the preview. Apply explicitly replaces the track checkpoints."))
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size.y = 90
		panel.add_child(scroll)
		var messages := VBoxContainer.new()
		scroll.add_child(messages)
		for diagnostic: Dictionary in proposal.diagnostics:
			var button: Button = editor._button(messages,I18N.diagnostic(diagnostic.message),func():
				if diagnostic.position_cm != null: editor.preview_camera.frame(PREVIEW.point(diagnostic.position_cm),32)
				editor.track_workbench.open_advanced())
			button.custom_minimum_size.x = 220
		var apply: Button = editor._button(panel,"Apply course proposal",apply_proposal)
		apply.disabled = not proposal.applicable
	elif manual_course: editor._button(panel,"Save course to map",save_manual)
	if not closure.is_empty():
		editor._label(panel,I18N.t("Connection ready") if closure.ok else I18N.diagnostic(closure.error))
		var apply: Button = editor._button(panel,"Apply circuit connection",apply_closure)
		apply.disabled = not closure.ok
	editor._button(panel,"Test Drive",editor._test_drive)
	editor._button(panel,"Advanced tools…",func(): editor.open_advanced())

func delete_checkpoint() -> void:
	if not current() or selected < 0 or selected >= gates.size(): return
	if not manual_course and proposal.is_empty():
		var source: Dictionary = editor.store.track_source()
		source.checkpoints.remove_at(selected)
		editor.track_workbench._commit(source)
		return
	gates.remove_at(selected)
	if not proposal.is_empty(): proposal.checkpoints.remove_at(selected)
	selected = -1
	refresh()
	show_gates()

func suggest() -> void:
	editor._cancel_editing()
	manual_course = false
	original = {}
	binding = token()
	var result: Dictionary = JSON.parse_string(editor.store.bridge.suggest_track_course(JSON.stringify(editor.store.track_source())))
	if not result.ok: editor._status(I18N.error(result.error)); return
	proposal = result.data
	gates = proposal.gates.duplicate(true)
	circuit = editor.store.track_source().settings.circuit
	show_gates()
	refresh()

func apply_proposal() -> bool:
	if not current() or proposal.is_empty() or not proposal.applicable: return false
	var source: Dictionary = editor.store.track_source()
	source.checkpoints = proposal.checkpoints.duplicate(true)
	if source.checkpoints.size() < 2 or source.checkpoints.size() > 64: return false
	var checked: Dictionary = JSON.parse_string(editor.store.bridge.compile_track_source(JSON.stringify(source)))
	if not checked.ok or not checked.data.document.assembled_track.issues.is_empty():
		editor._status(I18N.t("Checkpoint must follow the shared route order.")); return false
	return editor.track_workbench._commit(source)

func show_gates() -> void:
	if is_instance_valid(preview): preview.queue_free()
	preview = RENDER.create(gates)
	editor.preview_world.add_child(preview)

func allowed(gate: Dictionary, index: int) -> bool:
	var result: Dictionary = JSON.parse_string(editor.store.bridge.checkpoint_edit_allowed(JSON.stringify(gates),JSON.stringify(gate),index))
	if not result.get("ok",false) or not result.data:
		editor._status(I18N.t("Checkpoint overlaps an existing checkpoint; change rejected."))
		return false
	return true

func input(event: InputEvent) -> bool:
	if editor.tool_group != "course" or not current() or editor._popup_open(editor): return false
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed:
			if moving: confirm_move(); return true
			return false
		if road_picking:
			road_picking = false
			var hit: Dictionary = editor.spatial.surface(event.position,true)
			if hit.is_empty() or str(hit.get("road","")) == "": editor._status(I18N.t("Choose a start on a drivable road")); return true
			suggest_road(hit.point,-editor.preview_camera.camera.global_basis.z)
			return true
		if placing:
			var hit: Dictionary = editor.spatial.surface(event.position)
			if hit.is_empty() or gates.size() >= 64: return true
			var p: Vector3 = hit.point
			var gate := {"position_cm":[roundi(p.x*100),roundi((editor.spatial.height if editor.spatial.manual else p.y)*100),roundi(-p.z*100)],"radius_cm":230,"shape":"sphere","placement_mode":"road_snap","surface_id":hit.surface}
			if allowed(gate,-1): gates.append(gate); placing = false; show_gates(); refresh()
			return true
		var camera: Camera3D = editor.preview_camera.camera
		var nearest := 18.0
		selected = -1
		for i in gates.size():
			var p := PREVIEW.point(gates[i].position_cm)
			if camera.is_position_behind(p): continue
			var distance := camera.unproject_position(p).distance_to(event.position)
			if distance < nearest: nearest = distance; selected = i
		if selected >= 0:
			moving = true
			move_before = {"gates":gates.duplicate(true),"proposal":proposal.duplicate(true)}
		return true
	if event is InputEventMouseMotion and moving:
		if event.button_mask & (MOUSE_BUTTON_MASK_RIGHT|MOUSE_BUTTON_MASK_MIDDLE): cancel(); return false
		var hit: Dictionary = editor.spatial.surface(event.position,not manual_course)
		if hit.is_empty(): return true
		var gate: Dictionary = gates[selected].duplicate(true)
		var reference := {}
		if not manual_course:
			if not hit.has("piece"): return true
			reference = {"piece":editor.store.track_source().instances[hit.piece].id,"sample":hit.sample}
			var result: Dictionary = JSON.parse_string(editor.store.bridge.track_checkpoint(JSON.stringify(editor.store.track_pieces()[hit.piece].path[hit.sample])))
			if not result.ok: return true
			gate = result.data
		else: gate.position_cm = [roundi(hit.point.x*100),roundi(hit.point.y*100),roundi(-hit.point.z*100)]
		gate.surface_id = hit.surface
		if allowed(gate,selected):
			gates[selected] = gate
			if not proposal.is_empty(): proposal.checkpoints[selected] = reference
			else: move_before.reference = reference
			show_gates()
		return true
	return false

func confirm_move() -> bool:
	if not moving or not current(): return false
	moving = false
	if gates == move_before.gates: move_before = {}; return false
	if not manual_course and proposal.is_empty():
		var source: Dictionary = editor.store.track_source()
		source.checkpoints[selected] = move_before.reference
		# Reuse compiler diagnostics for common-route and ordering constraints.
		var checked: Dictionary = JSON.parse_string(editor.store.bridge.compile_track_source(JSON.stringify(source)))
		if not checked.ok or not checked.data.document.assembled_track.issues.is_empty(): cancel(); editor._status(I18N.t("Checkpoint must follow the shared route order.")); return false
		editor.track_workbench._commit(source)
	elif not proposal.is_empty():
		# User-modified proposals keep their explicit Apply boundary.
		var source: Dictionary = editor.store.track_source()
		source.checkpoints = proposal.checkpoints.duplicate(true)
		var checked: Dictionary = JSON.parse_string(editor.store.bridge.compile_track_source(JSON.stringify(source)))
		if not checked.ok or not checked.data.document.assembled_track.issues.is_empty(): cancel(); return false
	move_before = {}
	refresh()
	return true

func cancel() -> void:
	if not move_before.is_empty(): gates = move_before.gates; proposal = move_before.proposal; show_gates()
	move_before = {}
	moving = false
	placing = false
	road_picking = false

func save_manual() -> bool:
	if not current(): return false
	var bounds: Dictionary = editor.store.document.bounds
	var direction: Array = original.get("definition",{}).get("start_direction",start_direction if not start_direction.is_empty() else [0,1000000])
	var body := {"map_id":editor.store.document.map_id,"display_name":course_name,"world_content_hash":original.get("definition",{}).get("world_content_hash","0".repeat(64)),"mode":"circuit" if circuit else "sprint","start_mode":"ground","start_direction":direction,"checkpoints":gates}
	var result: Dictionary = JSON.parse_string(editor.store.bridge.seal_course(JSON.stringify(body),PackedInt64Array([bounds.min[0],bounds.min[1],bounds.max[0],bounds.max[1]])))
	if not result.ok: editor._status(I18N.error(result.error)); return false
	var course: Dictionary = result.data.document
	if original.has("validation"): course.validation = original.validation.duplicate(true)
	var patches: Array = []
	if not original.is_empty(): patches.append({"field":"courses","id":original.course_id,"before":original,"after":null})
	patches.append({"field":"courses","id":course.course_id,"before":null,"after":course})
	var failure: String = editor.store.apply_command("Edit course",patches)
	if failure != "": editor._status(I18N.diagnostic(failure)); return false
	original = course
	return true

func preview_closure() -> void:
	editor._cancel_editing()
	binding = token()
	var next: Dictionary = editor.store.track_source()
	if next.paths.is_empty() or next.paths[0].pieces.size() < 2: editor._status(I18N.t("Place at least two connected pieces first.")); return
	var route: Array = next.paths[0].pieces
	var from := -1
	var to := -1
	for i in next.instances.size():
		if next.instances[i].id == route.back(): from = i
		if next.instances[i].id == route[0]: to = i
	if from < 0 or to < 0: return
	var a: Dictionary = editor.store.track_pieces()[from].path.back()
	var b: Dictionary = editor.store.track_pieces()[to].path[0]
	if PREVIEW.point(a.position_cm).distance_to(PREVIEW.point(b.position_cm)) > 0.02:
		var reach := maxf(400,PREVIEW.point(a.position_cm).distance_to(PREVIEW.point(b.position_cm))*50)
		var p1: Array = []; var p2: Array = []
		for j in 3:
			p1.append(roundi(a.position_cm[j]+a.forward[j]*reach/1000000))
			p2.append(roundi(b.position_cm[j]-b.forward[j]*reach/1000000))
		var id := "close-"+Crypto.new().generate_random_bytes(4).hex_encode()
		next.instances.append({"id":id,"preset":"free_curve","position_cm":[0,0,0],"rotation_mdeg":[0,0,0],"width_cm":400,"entry_width_cm":int(a.lateral_cm)*2,"exit_width_cm":int(b.lateral_cm)*2,"control_points":[a.position_cm,p1,p2,b.position_cm]})
		next.connections.append({"from":route.back(),"to":id})
		route.append(id)
	next.connections.append({"from":route.back(),"to":route[0]})
	next.settings.circuit = true
	var result: Dictionary = JSON.parse_string(editor.store.bridge.compile_track_source(JSON.stringify(next)))
	var issues: Array = result.data.document.assembled_track.issues if result.ok else [I18N.error(result.error)]
	closure = {"ok":result.ok and issues.is_empty(),"source":next,"error":" / ".join(issues)}
	if is_instance_valid(closure_view): closure_view.queue_free()
	closure_view = Node3D.new()
	editor.preview_world.add_child(closure_view)
	var line := MeshInstance3D.new()
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	var positions: Array = []
	if result.ok and next.instances.size() > editor.store.track_source().instances.size():
		for sample: Dictionary in result.data.document.assembled_track.pieces.back().path: positions.append(PREVIEW.point(sample.position_cm))
	else: positions = [PREVIEW.point(a.position_cm),PREVIEW.point(b.position_cm)+Vector3.UP]
	for i in range(1,positions.size()): mesh.surface_add_vertex(positions[i-1]); mesh.surface_add_vertex(positions[i])
	mesh.surface_end(); line.mesh = mesh
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.no_depth_test = true
	material.albedo_color = Color("65c7ed") if closure.ok else Color("ff384e")
	line.material_override = material; closure_view.add_child(line)
	refresh()

func apply_closure() -> bool:
	if not current() or closure.is_empty() or not closure.ok: return false
	return editor.track_workbench._commit(closure.source)

func adjust_height(delta: float) -> bool:
	if not moving or not manual_course or selected < 0: return false
	var gate: Dictionary = gates[selected].duplicate(true)
	gate.position_cm[1] += roundi(delta*100)
	if allowed(gate,selected): gates[selected] = gate; show_gates()
	return true

## Road proposals become an unsaved manual course; Save course to map seals it in one Undo step.
func suggest_road(point: Vector3, forward: Vector3) -> bool:
	if not current(): return false
	var request := {"start_cm":[roundi(point.x*100),roundi(-point.z*100)],"heading":[roundi(forward.x*1000),roundi(-forward.z*1000)],"mode":"circuit" if circuit else "sprint","duration_seconds":road_seconds}
	var result: Dictionary = JSON.parse_string(editor.store.bridge.suggest_road_course(JSON.stringify(editor.store.document),JSON.stringify(request)))
	if not result.ok: editor._status(I18N.error(result.error)); return false
	road_proposal = result.data
	manual_course = true; original = {}; proposal = {}; selected = -1
	if road_proposal.applicable:
		gates = road_proposal.gates.duplicate(true)
		start_direction = [int(road_proposal.start_direction[0]),int(road_proposal.start_direction[1])]
		editor._status(I18N.t("Review the road course, then save it to the map."))
	show_gates()
	refresh()
	return road_proposal.applicable
