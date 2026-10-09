extends SceneTree
const FILES := preload("res://scripts/authoring_files.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures.append(message)
		push_error(message)
func state() -> String:
	return JSON.stringify([ui.store.document,ui.store.undo_stack,ui.store.redo_stack,ui.store.history_bytes,ui.store.dirty])
func run() -> void:
	root.size = Vector2i(1440,900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	ui.store.new_track(true)
	ui.set_tool_workspace("landscape")
	await process_frame
	var author: RefCounted = ui.canvas.author
	check(ui.store.save_project(ProjectSettings.globalize_path("user://safety")) == "", "save safety fixture")
	check(author.set_theme("default") == "", "explicit recipe")
	var options: Dictionary = author.options.duplicate(true)
	options.radius_cm = 1600
	var before := state()
	ui.canvas.set_layer_state("heightmaps", {"locked":true})
	check(author.terrain.begin(Vector2(51200,51200),options).contains("unlock") and state() == before, "terrain layer lock blocks brush")
	ui.canvas.set_layer_state("heightmaps", {})
	options.radius_cm = 199
	check(author.terrain.begin(Vector2(25600,25600),options).contains("E_BRUSH") and state() == before,"radius below existing grid rejected")
	options.radius_cm = 1600
	check(author.terrain.begin(Vector2(25600,25600),options) == "", "begin stale gesture")
	ui.store.command_epoch += 1
	before = state()
	check(author.terrain.finish().contains("stale") and state() == before and not ui.store.has_gesture(), "stale stroke cannot publish")
	check(ui.store.apply_command("invalid cell", [{"field":"heightmaps","id":"bad","before":null,"after":{"cell":"invalid"}}]) != "", "malformed composite record identity fails safely")
	check(ui.store.record_id("heightmaps", {"cell":{"x":0,"y":1}}) == ui.store.record_id("heightmaps", {"cell":{"y":1.0,"x":0.0}}), "cell identity stable across order/numeric JSON conversion")
	check(author.terrain.begin(Vector2(25600,25600),options) == "" and author.terrain.step(Vector2(25600,25600),1)=="", "begin raster command")
	author.terrain.last_usec=Time.get_ticks_usec()
	check(author.terrain.finish() == "" and ui.store.save_project(ui.store.project_path)=="", "explicitly save raster stroke")
	var record: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ui.store.project_path.path_join("document.json"))).heightmaps[0]
	var path: String = ui.store.project_path.path_join(record.path)
	var original: PackedByteArray = FILES.read(path).bytes
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(original + PackedByteArray([0]));file.close()
	check(ui.store.undo()=="" and ui.store.dirty,"memory Undo needs no PNG writes or reads")
	before = state()
	check(ui.store.save_project(ui.store.project_path).contains("E_CONFLICT") and state() == before,"external payload conflict blocks publication and retains memory")
	file = FileAccess.open(path,FileAccess.WRITE);file.store_buffer(original);file.close()
	check(ui.store.redo()=="" and not ui.store.dirty,"redo restores saved memory baseline")
	var oversized := PackedByteArray()
	oversized.resize(ui.store.HISTORY_BYTES)
	var new_path := "editor/" + FILES.digest(oversized) + ".png"
	var after := record.duplicate(true)
	after.path = new_path
	before = state()
	var failure := FILES.apply(ui.store,"oversized binary",[{"field":"heightmaps","id":ui.store.record_id("heightmaps",record),"before":null,"after":after}],{new_path:oversized})
	check(failure.contains("undo budget") and state() == before, "binary/text shared history limit before publication")
	check(not FileAccess.file_exists(ui.store.project_path.path_join(new_path)), "oversized input never installed")
	check(FILES.write_new(path, PackedByteArray([1,2,3])).contains("conflict"), "immutable install never overwrites differing bytes")
	# Mixed ground/bridge connection must match actual terrain, not just graph XYZ.
	ui._new()
	ui.new_free_roam.button_pressed = true
	ui.new_map_dialog.hide()
	ui.new_map_dialog.confirmed.emit()
	if ui.unsaved_dialog.visible:
		ui.unsaved_dialog.hide()
		ui._continue_document_action()
	check(author.set_theme("default") == "", "road safety recipe")
	author.options.start_cm = 500
	author.options.end_cm = 500
	ui.canvas.tool = "Road"
	ui.canvas.draft.assign([Vector2(10000,20000),Vector2(30000,20000)])
	ui.canvas.finish_shape()
	check(ui.store.document.roads.size() == 1,"ground reference heights allowed")
	author.options.kind = "bridge"
	ui.canvas.draft.assign([Vector2(30000,20000),Vector2(50000,20000)])
	before = state()
	ui.canvas.finish_shape()
	check(state() == before and ui.canvas.draft.size() == 2 and ui.status_label.text.contains("E_GEOMETRY"), "invalid terrain/structure junction shown immediately and draft retained")
	ui.canvas.cancel_interaction()
	ui.canvas.set_layer_state("nodes", {"locked":true})
	before = state()
	ui.canvas.draft.assign([Vector2(10000,50000),Vector2(30000,50000)])
	ui.canvas.finish_shape()
	check(state() == before and ui.status_label.text.contains("unlock"), "locked endpoint layer blocks new graph creation")
	ui.canvas.set_layer_state("nodes", {})
	ui._new()
	ui.new_free_roam.button_pressed = true
	ui.new_map_dialog.hide()
	ui.new_map_dialog.confirmed.emit()
	if ui.unsaved_dialog.visible:
		ui.unsaved_dialog.hide()
		ui._continue_document_action()
	check(author.set_theme("default") == "", "terrain portal recipe")
	author.options.start_cm = 0
	author.options.end_cm = 0
	author.options.kind = "ground"
	ui.canvas.tool = "Road"
	ui.canvas.draft.assign([Vector2(10000,20000),Vector2(30000,20000)])
	ui.canvas.finish_shape()
	author.options.kind = "bridge"
	ui.canvas.draft.assign([Vector2(30000,20000),Vector2(50000,20000)])
	ui.canvas.finish_shape()
	check(ui.store.document.roads.size() == 2, "terrain-level portal accepted")
	check(ui.store.save_project(ProjectSettings.globalize_path("user://portal-safety")) == "", "save portal source")
	before = state()
	check(author.terrain.begin(Vector2(30000,20000), options) == "", "begin portal terrain edit")
	check(author.terrain.step(Vector2(30000,20000),1)=="","raise portal terrain in memory")
	author.terrain.last_usec=Time.get_ticks_usec()
	var errors: Array[String]=[]
	ui.store.track_edit_finished.connect(func(message: String): if message!="":errors.append(message))
	failure = author.terrain.finish()
	var deadline:=Time.get_ticks_msec()+15000
	while ui.store.water_job!=null and Time.get_ticks_msec()<deadline: await process_frame
	check(not errors.is_empty() and errors[0].contains("E_GEOMETRY") and state()==before,"invalid portal terrain rolls back before command publication")
	# Source replacement also cancels the active brush; its old release is inert.
	ui.canvas.set_layer_state("nodes",{})
	ui.canvas.cancel_interaction()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("authoring_safety_validator: ", "PASS" if failures.is_empty() else failures, "; checks=",checks)
	quit(0 if failures.is_empty() else 1)
