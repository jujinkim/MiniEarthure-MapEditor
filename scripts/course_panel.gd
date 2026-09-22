extends RefCounted
## Public authoring only. Evidence is opaque and never created by an editor action.
var panel: Control
var courses: OptionButton
var points: ItemList
var name_input: LineEdit
var shape: OptionButton
var mode: OptionButton
var start: OptionButton
var height: SpinBox
var radius: SpinBox
var heading: SpinBox
var draft: Array[Dictionary] = []
var original: Dictionary = {}
var picker: FileDialog
var _placing := false
var _replace := -1
var level: OptionButton
var _undo: Array = []
var _redo: Array = []
var _preview: Node3D
var _last_edit: Dictionary = {}
var _restoring := false
var _loaded_heading := 0.0

func setup(owner: Control) -> void:
	panel = owner
	var box: VBoxContainer = panel.page("Courses")
	panel.hint(box, "Unverified courses can be saved and exported. Complete a player validation drive in the game, then import its course and evidence here.")
	courses = panel.choice(box, "Map courses", ["New course"], "New course")
	for course: Dictionary in panel.editor.store.document.get("courses", []): courses.add_item(course.definition.display_name)
	courses.item_selected.connect(_select)
	name_input = panel.text(box, "Name", "My course")
	mode = panel.choice(box, "Finish", ["circuit", "sprint"], "circuit")
	start = panel.choice(box, "Start", ["ground", "air"], "ground")
	heading = panel.number(box, "Start direction (degrees in map X/Z)", 0, -180, 180)
	height = panel.number(box, "Height (m)", 0, -100000, 100000, 0.1)
	level = panel.choice(box,"Placement height",["ground","manual"],"ground")
	radius = panel.number(box, "Radius (m)", 12, 1, 1000, 0.1)
	shape = panel.choice(box, "Checkpoint shape", ["sphere", "hemisphere"], "sphere")
	points = ItemList.new()
	points.custom_minimum_size.y = 120
	box.add_child(points)
	points.item_selected.connect(func(i: int):
		height.value = draft[i].position_cm[1] / 100.0
		radius.value = draft[i].radius_cm / 100.0
		shape.select(0 if draft[i].shape == "sphere" else 1))
	panel.button(box, "Add checkpoint · click map", func(): _place(-1))
	panel.button(box, "Move selected · click map", func():
		if not points.get_selected_items().is_empty(): _place(points.get_selected_items()[0]))
	panel.button(box, "Apply height / radius / shape", _attributes)
	panel.button(box, "Delete checkpoint", _delete)
	panel.button(box, "Move earlier", _move.bind(-1))
	panel.button(box, "Move later", _move.bind(1))
	panel.button(box, "Undo draft", _undo_draft)
	panel.button(box, "Redo draft", _redo_draft)
	panel.button(box, "Save course to map", _save)
	panel.button(box, "Import completed course…", func(): picker.popup_centered_ratio(0.75))
	panel.hint(box, "Map Undo/Redo includes saved course edits. Preview circles show checkpoint radius; height is stored in 3D. Circuit finish shares checkpoint 1; hosting chooses 1–10 laps.")
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	picker.filters = PackedStringArray(["*.mecourse ; Course v1"])
	panel.add_child(picker)
	picker.file_selected.connect(import_course)
	panel.editor.canvas.course_point_selected.connect(_point)
	name_input.text_changed.connect(func(_value: String): _metadata_changed())
	mode.item_selected.connect(func(_index: int): _metadata_changed())
	start.item_selected.connect(func(_index: int): _metadata_changed())
	heading.value_changed.connect(func(_value: float): _metadata_changed())
	_refresh()

func _select(index: int) -> void:
	_undo.clear()
	_redo.clear()
	original = {} if index == 0 else panel.editor.store.document.courses[index-1].duplicate(true)
	draft.clear()
	_restoring = true
	name_input.text = "My course"
	mode.select(0)
	start.select(0)
	heading.value = 0
	if not original.is_empty():
		var d: Dictionary = original.definition
		draft.assign(d.checkpoints.duplicate(true))
		name_input.text = d.display_name
		mode.select(0 if d.mode == "circuit" else 1)
		start.select(0 if d.start_mode == "ground" else 1)
		heading.value = rad_to_deg(atan2(d.start_direction[1],d.start_direction[0]))
	_loaded_heading = heading.value
	_restoring = false
	_refresh()

func _place(index: int) -> void:
	_placing = true
	_replace = index
	panel.editor.canvas.tool = "Course"
	panel.report("Click the map; the selected height allows rooftop, bridge and airborne placement.")

func _point(point: Vector2) -> void:
	if not _placing or not panel.visible or panel.editor.busy: return
	var elevation := roundi(height.value*100)
	if level.selected == 0:
		var ground := _ground(point)
		if ground.has("error"):
			panel.report(ground.error)
			return
		elevation = ground.height
	_remember()
	var cp := {"position_cm":[roundi(point.x),elevation,roundi(point.y)],"radius_cm":roundi(radius.value*100),"shape":shape.get_item_text(shape.selected),"placement_mode":"free","surface_id":"terrain"}
	if _replace < 0:
		if draft.size() >= 64: return
		draft.append(cp)
	else: draft[_replace] = cp
	_placing = false
	panel.editor.canvas.tool = "Select"
	_refresh()

func _attributes() -> void:
	if points.get_selected_items().is_empty(): return
	_remember()
	var cp := draft[points.get_selected_items()[0]]
	cp.position_cm[1] = roundi(height.value*100)
	cp.radius_cm = roundi(radius.value*100)
	cp.shape = shape.get_item_text(shape.selected)
	_refresh()

func _delete() -> void:
	if points.get_selected_items().is_empty(): return
	_remember()
	draft.remove_at(points.get_selected_items()[0])
	_refresh()

func _move(delta: int) -> void:
	if points.get_selected_items().is_empty(): return
	var i := points.get_selected_items()[0]
	if i+delta < 0 or i+delta >= draft.size(): return
	_remember()
	var cp := draft[i]
	draft[i] = draft[i+delta]
	draft[i+delta] = cp
	_refresh()
	points.select(i+delta)

func _refresh() -> void:
	points.clear()
	for i in draft.size(): points.add_item("%d · %s · height %.1f m · radius %.1f m" % [i+1,draft[i].shape,draft[i].position_cm[1]/100.0,draft[i].radius_cm/100.0])
	panel.editor.canvas.course_points = draft.duplicate(true)
	panel.editor.canvas.queue_redraw()
	if is_instance_valid(_preview): _preview.queue_free()
	_preview = preload("res://addons/mapkit/godot/course_renderer.gd").create(draft)
	panel.editor.viewport.add_child(_preview)
	_last_edit = _snapshot()

func _save() -> void:
	var store: RefCounted = panel.editor.store
	var b: Dictionary = store.document.bounds
	var angle := deg_to_rad(heading.value)
	var direction: Array = original.definition.start_direction.duplicate() if not original.is_empty() and heading.value == _loaded_heading else [roundi(cos(angle)*1000000),roundi(sin(angle)*1000000)]
	var body := {"map_id":store.document.map_id,"display_name":name_input.text,"world_content_hash":original.get("definition",{}).get("world_content_hash","0".repeat(64)),
		"mode":mode.get_item_text(mode.selected),"start_mode":start.get_item_text(start.selected),"start_direction":direction,"checkpoints":draft}
	var result: Dictionary = JSON.parse_string(store.bridge.seal_course(JSON.stringify(body),PackedInt64Array([b.min[0],b.min[1],b.max[0],b.max[1]])))
	if not result.ok:
		panel.report(store.reason(result))
		return
	var course: Dictionary = result.data.document
	if original.has("validation"): course.validation = original.validation.duplicate(true)
	_adopt(course)

func _adopt(course: Dictionary) -> void:
	var patches: Array = []
	if not original.is_empty() and original.course_id != course.course_id: patches.append({"field":"courses","id":original.course_id,"before":original,"after":null})
	var previous: Variant = panel.editor.store._get_value(panel.editor.store.document,"courses",course.course_id)
	patches.append({"field":"courses","id":course.course_id,"before":previous,"after":course})
	var failure: String = panel.editor.store.apply_command("Edit course",patches)
	if failure == "":
		original = course.duplicate(true)
		courses.clear()
		courses.add_item("New course")
		for entry: Dictionary in panel.editor.store.document.get("courses",[]):
			courses.add_item(entry.definition.display_name)
			if entry.course_id == course.course_id: courses.select(courses.item_count-1)
		_select(courses.selected)
	panel.report(failure)

func import_course(path: String) -> void:
	var file := FileAccess.open(path,FileAccess.READ)
	if file == null or file.get_length() > 15000:
		panel.report("Course exceeds the 15 KB authoring limit or is unavailable.")
		return
	file.close()
	var read := preload("./document_files.gd").new().read_json(path)
	if read.has("error"):
		panel.report(read.error)
		return
	if not read.value is Dictionary:
		panel.report("Course object required.")
		return
	var course: Dictionary = read.value
	if course.get("definition",{}).get("map_id") != panel.editor.store.document.map_id:
		panel.report("Course map ID differs from this project.")
		return
	var document: Dictionary = panel.editor.store.document.duplicate(true)
	document.courses = [course]
	var typed: Dictionary = panel.editor.store._validate(document)
	if not typed.ok:
		panel.report(panel.editor.store.reason(typed))
		return
	if course.has("validation"):
		var reference: Dictionary = course.validation
		if not preload("./project_snapshot.gd").safe_relative(str(reference.get("path",""))) or reference.get("bytes",0) > 32*1024*1024:
			panel.report("Invalid bounded validation reference.")
			return
		var source := path.get_base_dir().path_join(reference.path)
		if not FileAccess.file_exists(source): source = path.get_base_dir().get_base_dir().path_join(reference.path)
		var payload := preload("./authoring_files.gd").read(source,32*1024*1024)
		if payload.has("error") or payload.bytes.size() != reference.bytes or preload("./authoring_files.gd").digest(payload.bytes) != reference.sha256:
			panel.report("Missing or damaged completion evidence; original project preserved.")
			return
		if panel.editor.store.project_path == "":
			panel.report("Save the project before importing evidence.")
			return
		var failure := preload("./project_snapshot.gd").install_payload(panel.editor.store.project_path.path_join(reference.path),payload.bytes,reference.sha256)
		if failure != "":
			panel.report(failure)
			return
	original = {}
	_adopt(course)

func teardown() -> void:
	if panel != null and is_instance_valid(panel.editor.canvas):
		if panel.editor.canvas.course_point_selected.is_connected(_point): panel.editor.canvas.course_point_selected.disconnect(_point)
		panel.editor.canvas.course_points = []
		panel.editor.canvas.queue_redraw()
	if is_instance_valid(picker): picker.queue_free()
	if is_instance_valid(_preview): _preview.queue_free()

func _remember() -> void:
	_undo.append(_snapshot())
	if _undo.size() > 64: _undo.pop_front()
	_redo.clear()

func _undo_draft() -> void:
	if _undo.is_empty(): return
	_redo.append(_snapshot())
	_restore_edit(_undo.pop_back())
	_refresh()

func _redo_draft() -> void:
	if _redo.is_empty(): return
	_undo.append(_snapshot())
	_restore_edit(_redo.pop_back())
	_refresh()

func _snapshot() -> Dictionary:
	return {"points":draft.duplicate(true),"name":name_input.text,"mode":mode.selected,"start":start.selected,"heading":heading.value}

func _restore_edit(value: Dictionary) -> void:
	_restoring = true
	draft.assign(value.points)
	name_input.text = value.name
	mode.select(value.mode)
	start.select(value.start)
	heading.value = value.heading
	_restoring = false
	_placing = false
	panel.editor.canvas.tool = "Select"

func _metadata_changed() -> void:
	if _restoring or _last_edit.is_empty(): return
	if _snapshot() == _last_edit: return
	_undo.append(_last_edit.duplicate(true))
	if _undo.size() > 64: _undo.pop_front()
	_redo.clear()
	_refresh()

func _ground(point: Vector2) -> Dictionary:
	var store: RefCounted = panel.editor.store
	var doc: Dictionary = store.document
	var cell_size := int(doc.cell_size_cm)
	var local := point-Vector2(doc.bounds.min[0],doc.bounds.min[1])
	var cell := Vector2i(floori(local.x/cell_size),floori(local.y/cell_size))
	var terrain := preload("./terrain_tools.gd").new()
	terrain.store = store
	var tile := terrain.descriptor(cell)
	if tile.is_empty(): return {"height":int(doc.terrain_base_cm)}
	var spacing := int(tile.spacing_cm)
	var side := cell_size/spacing+1
	var loaded := terrain._load(cell,side)
	if loaded.has("error"): return loaded
	var p := (local-Vector2(cell)*cell_size)/spacing
	var x := clampi(floori(p.x),0,side-2)
	var y := clampi(floori(p.y),0,side-2)
	var values: PackedInt64Array = loaded.heights
	return {"height":roundi(lerpf(lerpf(values[y*side+x],values[y*side+x+1],p.x-x),lerpf(values[(y+1)*side+x],values[(y+1)*side+x+1],p.x-x),p.y-y))}
