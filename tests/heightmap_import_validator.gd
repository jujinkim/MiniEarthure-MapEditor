extends SceneTree
const LAYER := preload("res://scripts/heightmap_import_layer.gd")
const PNG := preload("res://scripts/terrain_png.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const STORE := preload("res://scripts/document_store.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func state() -> String:
	return JSON.stringify([ui.store.document,ui.store.undo_stack,ui.store.redo_stack,ui.store.history_bytes,ui.store.dirty])
func write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var terrain: RefCounted = ui.canvas.author.terrain
	var project := ProjectSettings.globalize_path("user://raster-project")
	check(ui.store.save_project(project) == "", "save isolated project")
	var heights := PackedInt64Array()
	heights.resize(17 * 17)
	heights.fill(0)
	heights[8 * 17 + 8] = 100
	var encoded := PNG.encode(heights,17)
	var source := ProjectSettings.globalize_path("user://synthetic.png")
	write(source,encoded.bytes)
	var attribution := {"source":"Synthetic terrain","license":"MIT","notice":"original fixture"}
	var layer := LAYER.new()
	var before := state()
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,500,attribution) == "", "stage valid cell")
	check(state() == before and not FileAccess.file_exists(project.path_join(layer.value.heightmap.path)), "staging does not publish payload/document/history")
	var id: String = layer.value.layer_id
	check(layer.summary().contains("500") and layer.summary().contains("rows +local y"), "review accuracy and orientation")
	layer.discard()
	check(layer.adopt(terrain) != "" and state() == before, "discard prevents adoption")
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,500,attribution) == "" and layer.value.layer_id != id, "fresh source identity")
	# Captured bytes are stable even if the input changes during review.
	write(source,PackedByteArray([1,2,3]))
	check(layer.adopt(terrain) == "", "adopt captured source snapshot")
	check(FILES.read(source).bytes == PackedByteArray([1,2,3]), "adoption never rewrites source")
	check(ui.store.document.heightmaps.size() == 1 and ui.store.document.attributions.size() == 1, "one active tile and source notice")
	var first: Dictionary = ui.store.document.heightmaps[0].duplicate(true)
	check(FILES.read(project.path_join(first.path)).bytes == encoded.bytes, "captured file installed exactly")
	check(layer.adopt(terrain) != "", "candidate consumed once")
	check(ui.store.undo() == "" and ui.store.document.heightmaps.is_empty(), "atomic undo raster and attribution")
	check(ui.store.redo() == "" and ui.store.document.heightmaps.size() == 1, "redo restores captured bytes")
	check(ui.store.save_project(project) == "", "save first import")
	var output := ProjectSettings.globalize_path("user://original.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,output)).ok, "package imported raster")
	var package_hash := FileAccess.get_sha256(output)
	heights[8 * 17 + 8] = 200
	var updated := PNG.encode(heights,17)
	write(source,updated.bytes)
	before = state()
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,0,attribution) == "" and state() == before, "reimport requires fresh review")
	check(layer.value.previous == first and layer.value.heightmap.source_accuracy_cm == null, "review retains previous tile and unknown accuracy")
	check(layer.adopt(terrain) == "", "activate updated cell")
	check(ui.store.document.heightmaps.size() == 1 and ui.store.document.attributions.size() == 2, "reimport retains both source notices with one active cell")
	check(ui.store.undo() == "" and ui.store.document.heightmaps[0] == first, "undo reactivates old file")
	check(ui.store.redo() == "", "redo reimport")
	check(FileAccess.get_sha256(output) == package_hash and FILES.read(project.path_join(first.path)).bytes == encoded.bytes, "original package and old payload preserved")
	check(ui.store.save_project(project) == "" and ui.store.autosave() == "", "persist imported layer")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "" and reopened.document.attributions == ui.store.document.attributions, "metadata reopen")
	check(reopened.recover(ui.store.recovery_path()) == "", "recovery references retained")
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,0,attribution) == "", "stage before document change")
	check(ui.store.undo() == "" and ui.store.redo() == "", "document changes then returns to same content")
	before = state()
	check(layer.adopt(terrain).contains("Stale") and state() == before, "changed generation stays stale even after undo/redo")
	# An adjacent non-flat edge must fail before payload publication.
	heights.fill(100)
	write(source,PNG.encode(heights,17).bytes)
	check(layer.stage(terrain,source,Vector2i(1,0),3200,100,1,0,attribution).contains("E_SEAM") and state() == before, "mismatched seam rejected atomically")
	write(source,updated.bytes)
	check(layer.stage(terrain,source,Vector2i(-1,0),3200,0,1,0,attribution) != "" and state() == before, "out-of-map cell rejected")
	check(layer.stage(terrain,source,Vector2i.ZERO,3000,0,1,0,attribution) != "", "invalid grid rejected")
	write(source,PackedByteArray([1,2,3]))
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,0,attribution) != "" and state() == before, "invalid PNG preserves state")
	write(source,encoded.bytes)
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,0,attribution) == "", "stage different bytes before external previous-payload mutation")
	var current_path: String = project.path_join(ui.store.document.heightmaps[0].path)
	write(current_path,PackedByteArray([9]))
	check(layer.adopt(terrain) != "" and state() == before, "external file conflict preserves document/history")
	write(current_path,updated.bytes)
	layer.discard()
	write(source,updated.bytes)
	check(layer.stage(terrain,source,Vector2i.ZERO,3200,0,1,0,attribution) == "", "stage before locking")
	ui.canvas.set_layer_state("heightmaps", {"locked":true})
	check(layer.adopt(terrain).contains("unlock") and state() == before, "lock at adoption preserves state")
	ui.canvas.set_layer_state("heightmaps", {})
	layer.discard()
	# Exercise the actual authoring review and cancel/adopt controls.
	ui.author_panel.open()
	ui.author_panel._stage_heightmap(source,Vector2i.ZERO,3200,0,1,500,attribution)
	await process_frame
	check(ui.author_panel.heightmap_review.visible and ui.author_panel.heightmap_summary.text.contains("SHA-256"), "review UI shows source identity")
	check(ui.author_panel.heightmap_review.size.x <= root.size.x and ui.author_panel.heightmap_review.size.y <= root.size.y, "review fits minimum window")
	if DisplayServer.get_name() != "headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH") != "":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")) == OK, "capture review")
	ui.author_panel.heightmap_review.canceled.emit()
	check(ui.author_panel.heightmap_candidate == null and state() == before, "UI discard preserves state")
	ui.author_panel._stage_heightmap(source,Vector2i.ZERO,3200,0,1,500,attribution)
	ui.author_panel.heightmap_review.confirmed.emit()
	check(ui.author_panel.heightmap_candidate == null and ui.store.document.attributions.size() == 3, "UI adopts one new layer")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("heightmap_import_validator: ", "PASS" if failures.is_empty() else failures, "; checks=",checks)
	quit(0 if failures.is_empty() else 1)
