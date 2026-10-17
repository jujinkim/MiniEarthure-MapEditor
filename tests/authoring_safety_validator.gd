extends SceneTree
const FILES := preload("res://scripts/authoring_files.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func raster_source(name: String, height: int) -> String:
	var side := 2
	var samples := PackedInt64Array();samples.resize(side*side);samples.fill(height)
	var path := ProjectSettings.globalize_path("user://%s.png" % name)
	var file := FileAccess.open(path,FileAccess.WRITE);file.store_buffer(preload("res://scripts/terrain_png.gd").encode(samples,side).bytes);file.close()
	return path

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
	var cell_size := int(ui.store.document.cell_size_cm)
	var cell := Vector2i(25600/cell_size, 25600/cell_size)
	var raster := raster_source("safety-flat", 0)
	var attribution := {"source":"Synthetic safety","license":"MIT","notice":"fixture"}
	var before := state()
	ui.canvas.set_layer_state("heightmaps", {"locked":true})
	check(author.terrain.import_png(raster,cell,cell_size,0,1,0,attribution).contains("unlock") and state() == before, "terrain layer lock blocks import")
	ui.canvas.set_layer_state("heightmaps", {})
	check(ui.store.apply_command("invalid cell", [{"field":"heightmaps","id":"bad","before":null,"after":{"cell":"invalid"}}]) != "", "malformed composite record identity fails safely")
	check(ui.store.record_id("heightmaps", {"cell":{"x":0,"y":1}}) == ui.store.record_id("heightmaps", {"cell":{"y":1.0,"x":0.0}}), "cell identity stable across order/numeric JSON conversion")
	check(author.terrain.import_png(raster,cell,cell_size,0,1,0,attribution) == "" and ui.store.save_project(ui.store.project_path)=="", "explicitly save imported raster")
	var record: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ui.store.project_path.path_join("document.json"))).heightmaps[0]
	var path: String = ui.store.project_path.path_join(record.path)
	var original: PackedByteArray = FILES.read(path).bytes
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(original + PackedByteArray([0]));file.close()
	check(ui.store.apply_command("dirty fixture",[{"field":"seed","before":ui.store.document.seed,"after":ui.store.document.seed+1}])=="" and ui.store.dirty,"memory edit needs no PNG writes")
	before = state()
	check(ui.store.save_project(ui.store.project_path).contains("E_CONFLICT") and state() == before,"external payload conflict blocks publication and retains memory")
	file = FileAccess.open(path,FileAccess.WRITE);file.store_buffer(original);file.close()
	check(ui.store.undo()=="" and not ui.store.dirty,"undo restores saved memory baseline")
	var oversized := PackedByteArray()
	oversized.resize(ui.store.HISTORY_BYTES)
	var new_path := "editor/" + FILES.digest(oversized) + ".png"
	var after := record.duplicate(true)
	after.path = new_path
	before = state()
	var failure := FILES.apply(ui.store,"oversized binary",[{"field":"heightmaps","id":ui.store.record_id("heightmaps",record),"before":ui.store.document.heightmaps[0],"after":after}],{new_path:oversized})
	check(failure.contains("undo budget") and state() == before, "binary/text shared history limit before publication")
	check(not FileAccess.file_exists(ui.store.project_path.path_join(new_path)), "oversized input never installed")
	check(FILES.write_new(path, PackedByteArray([1,2,3])).contains("conflict"), "immutable install never overwrites differing bytes")
	# Mixed ground/bridge connection must match actual terrain, not just graph XYZ.
	ui.store.new_track(true)
	ui._document_changed()
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
	ui.store.new_track(true)
	ui._document_changed()
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
	ui.canvas.set_layer_state("nodes",{})
	ui.canvas.cancel_interaction()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("authoring_safety_validator: ", "PASS" if failures.is_empty() else failures, "; checks=",checks)
	quit(0 if failures.is_empty() else 1)
