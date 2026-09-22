extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const SNAPSHOT := preload("res://scripts/project_snapshot.gd")
const PANEL := preload("res://scripts/course_panel.gd")
var failed := false
func check(value: bool, message: String) -> void:
	if not value:
		failed = true
		push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.course_panel
	check(panel._ground(Vector2(2000,3000)).height == ui.store.document.terrain_base_cm,"ground placement uses terrain height")
	panel.level.select(1)
	panel.height.value = 25
	panel._place(-1)
	panel._point(Vector2(2000,3000))
	panel.height.value = 40
	panel.shape.select(1)
	panel._place(-1)
	panel._point(Vector2(6000,3000))
	check(panel.draft.size()==2 and panel.draft[1].position_cm[1]==4000 and panel.draft[1].shape=="hemisphere","3D shape authoring")
	var hemisphere: MeshInstance3D = panel._preview.get_child(1)
	check(is_equal_approx(hemisphere.mesh.get_aabb().position.y,0.0) and is_equal_approx(hemisphere.mesh.get_aabb().end.y,12.0),"hemisphere preview has the actual 12 m upward radius")
	panel.points.select(1)
	panel._move(-1)
	check(panel.draft[0].shape=="hemisphere","checkpoint order changes")
	panel._undo_draft()
	check(panel.draft[0].shape=="sphere","draft undo")
	panel._redo_draft()
	check(panel.draft[0].shape=="hemisphere","draft redo")
	panel.start.select(1)
	panel.heading.value = 90
	panel._undo_draft()
	check(panel.heading.value==0,"draft undo includes start direction")
	panel._redo_draft()
	check(panel.heading.value==90 and panel.start.selected==1,"draft redo restores heading and start mode")
	panel._save()
	check(ui.store.document.get("courses",[]).size()==1,"save unverified public course")
	if ui.store.document.get("courses",[]).is_empty():
		ui.queue_free()
		quit(1)
		return
	var original: Dictionary = ui.store.document.courses[0].duplicate(true)
	check(not original.has("validation") and original.definition.start_mode=="air","editor never certifies")
	check(ui.store.undo()=="" and ui.store.document.get("courses",[]).is_empty(),"map undo removes course")
	check(ui.store.redo()=="" and ui.store.document.courses[0]==original,"map redo restores exact course")
	var project := ProjectSettings.globalize_path("user://course-project")
	check(ui.store.save_project(project)=="","project saves")
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(native.open_project(project)).ok,"native project reload")
	var listed: Dictionary = JSON.parse_string(native.courses_json())
	check(listed.ok and listed.data.courses.size()==1,"public bridge lists saved course")
	var opaque := "public opaque completion payload"
	var proof_hash := opaque.sha256_text()
	var imported := original.duplicate(true)
	imported.validation = {"sha256":proof_hash,"bytes":opaque.to_utf8_buffer().size(),"world_content_hash":original.definition.world_content_hash,"geometry_hash":"a".repeat(64),"path":"course-validation/%s.mevalidation" % proof_hash}
	var source := ProjectSettings.globalize_path("user://course-import")
	check(SNAPSHOT.install_payload(source.path_join(imported.validation.path),opaque.to_utf8_buffer(),proof_hash)=="","opaque evidence fixture installed")
	var file := FileAccess.open(source.path_join("course.mecourse"),FileAccess.WRITE)
	file.store_string(JSON.stringify(imported))
	file.close()
	panel.import_course(source.path_join("course.mecourse"))
	check(ui.store.document.courses.size()==1 and ui.store.document.courses[0].has("validation"),"import replaces same course with reference")
	check(FileAccess.get_sha256(project.path_join(imported.validation.path))==proof_hash,"evidence copied without private game dependency")
	check(ui.store.save_project(ProjectSettings.globalize_path("user://course-copy"))=="","Save As retains course and payload")
	check(FileAccess.get_sha256(ui.store.project_path.path_join(imported.validation.path))==proof_hash,"Save As payload intact")
	ui.queue_free()
	await process_frame
	print("course_authoring_validator: "+("FAIL" if failed else "PASS · public authoring and opaque evidence only"))
	quit(1 if failed else 0)
