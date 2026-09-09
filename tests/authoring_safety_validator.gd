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
	await process_frame
	var author: RefCounted = ui.canvas.author
	check(ui.store.save_project(ProjectSettings.globalize_path("user://safety")) == "", "save safety fixture")
	check(author.recipe(4,"default") == "", "explicit recipe")
	var options: Dictionary = author.options.duplicate(true)
	options.spacing_cm = 200
	options.radius_cm = 102400
	var before := state()
	ui.canvas.set_layer_state("heightmaps", {"locked":true})
	check(author.terrain.begin(Vector2(51200,51200),options).contains("unlock") and state() == before, "terrain layer lock blocks brush")
	ui.canvas.set_layer_state("heightmaps", {})
	check(author.terrain.begin(Vector2(51200,51200),options) == "", "begin bounded planning")
	for i in range(40): author.terrain.sample(Vector2(51200 + i * 10,51200))
	var planning_failure: String = author.terrain.finish()
	check(planning_failure.contains("budget") and state() == before, "oversized grid plan preserves document/history")
	options.spacing_cm = 3200
	options.radius_cm = 6400
	check(author.terrain.begin(Vector2(25600,25600),options) == "", "begin stale gesture")
	ui.store.document.seed += 1
	before = state()
	check(author.terrain.finish().contains("stale") and state() == before and not ui.store.has_gesture(), "stale stroke cannot publish")
	check(ui.store.apply_command("invalid cell", [{"field":"heightmaps","id":"bad","before":null,"after":{"cell":"invalid"}}]) != "", "malformed composite record identity fails safely")
	check(ui.store.record_id("heightmaps", {"cell":{"x":0,"y":1}}) == ui.store.record_id("heightmaps", {"cell":{"y":1.0,"x":0.0}}), "cell identity stable across order/numeric JSON conversion")
	check(author.terrain.begin(Vector2(25600,25600),options) == "", "begin raster command")
	check(author.terrain.finish() == "", "valid raster stroke")
	var record: Dictionary = ui.store.document.heightmaps[0]
	var path: String = ui.store.project_path.path_join(record.path)
	var original: PackedByteArray = FILES.read(path).bytes
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(original + PackedByteArray([0]))
	file.close()
	before = state()
	check(ui.store.undo().contains("changed") and state() == before, "external payload changes block undo without mutation")
	file = FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(original)
	file.close()
	check(ui.store.undo() == "" and ui.store.redo() == "", "unchanged immutable bytes permit history travel")
	var oversized := PackedByteArray()
	oversized.resize(ui.store.HISTORY_BYTES)
	var new_path := "editor/" + FILES.digest(oversized) + ".png"
	var after := record.duplicate(true)
	after.path = new_path
	before = state()
	var failure := FILES.apply(ui.store,"oversized binary",[{"field":"heightmaps","id":ui.store.record_id("heightmaps",record),"before":record,"after":after}],{new_path:oversized})
	check(failure.contains("undo budget") and state() == before, "binary/text shared history limit before publication")
	check(not FileAccess.file_exists(ui.store.project_path.path_join(new_path)), "oversized input never installed")
	check(FILES.write_new(path, PackedByteArray([1,2,3])).contains("conflict"), "immutable install never overwrites differing bytes")
	# Mixed ground/bridge connection must match actual terrain, not just graph XYZ.
	ui._new()
	check(author.recipe(2,"default") == "", "road safety recipe")
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
	check(author.recipe(2,"default") == "", "terrain portal recipe")
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
	failure = author.terrain.finish()
	check(failure.contains("E_GEOMETRY") and state() == before, "terrain edit cannot break existing ground/structure junction: " + failure)
	# Source replacement also cancels the active brush; its old release is inert.
	ui.canvas.set_layer_state("nodes",{})
	ui.canvas.cancel_interaction()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("authoring_safety_validator: ", "PASS" if failures.is_empty() else failures, "; checks=",checks)
	quit(0 if failures.is_empty() else 1)
