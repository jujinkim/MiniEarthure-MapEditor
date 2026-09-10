extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
var ui: Control
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		push_error(message + ": " + ui.status_label.text)
		quit(1)
		assert(ok, message)
func wait_work() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "owned work terminates")
func run() -> void:
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(3)
	ui.import_source_format.item_selected.emit(3)
	ui.import_origin_lon.value = 9
	ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512
	ui.import_origin_y.value = 512
	var path := ProjectSettings.globalize_path("user://vertical.overture.json")
	var output: Array = []
	check(OS.execute(ui.import_python.text, PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/overture_fixture.py"),"--vertical",path]),output,true) == 0, "synthetic vertical source")
	var source_hash := FileAccess.get_sha256(path)
	var initial: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import == null and ui.store.document == initial and ui.status_label.text.contains("recipe 3"), "legacy recipe refuses vertical solids")
	check(ui.store.apply_command("Choose recipe",[{"field":"recipe_version","before":1,"after":5}]) == "", "explicit recipe selection")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import != null, "vertical native review")
	var candidate: Dictionary = ui.pending_import.value.duplicate(true)
	check(candidate.patches.size() == 2 and candidate.coordinates.overture.parent_sources.size() == 1, "parent retained only as source")
	check(ui.import_summary.text.contains("Common ground") and preload("res://tests/import_review_helpers.gd").source_readable(ui, "overture", "feature_sources"), "source and plane limitations reviewed")
	for mode in ["parent", "duplicate", "orphan", "dimension", "unknown"]:
		var bad: Dictionary = candidate.duplicate(true)
		if mode == "parent": bad.coordinates.overture.parent_sources.clear()
		elif mode == "duplicate": bad.coordinates.overture.parent_sources.append(bad.coordinates.overture.parent_sources[0].duplicate(true))
		elif mode == "orphan": bad.coordinates.overture.feature_sources[0].parent_id = "missing"
		elif mode == "dimension": bad.patches[1].after.base_cm = 0
		else: bad.coordinates.overture.parent_sources[0].part_ids.append("missing")
		check(LAYER.new().load_value(bad,bad.layer_id) != "", "forged family rejected: " + mode)
	ui._discard_import()
	check(ui.store.document.buildings.is_empty(), "discard preserves map")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	ui._adopt_import()
	await wait_work()
	check(ui.store.document.buildings.size() == 2, "atomic two-part adoption")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(adopted.buildings[0].base_cm == 200 and adopted.buildings[0].height_cm == 400 and adopted.buildings[1].base_cm == 1000 and adopted.buildings[1].height_cm == 300, "exact bottom/thickness and vertical gap")
	check(ui.store.undo() == "" and ui.store.document.buildings.is_empty(), "whole-family undo")
	check(ui.store.redo() == "" and ui.store.document == adopted, "whole-family redo")
	var project := ProjectSettings.globalize_path("user://vertical-project")
	check(ui.store.save_project(project) == "", "save source project")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "" and reopened.document == adopted, "source and solids roundtrip")
	var package := project + ".memap"
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok, "build native package")
	var package_hash := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok, "reopen package")
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok and not generated.data.chunk.building_prisms.is_empty(), "native generation contains parts only")
	var solid_ids := {}
	var lower_seen := false
	var upper_seen := false
	for prism: Dictionary in generated.data.chunk.building_prisms:
		solid_ids[prism.object_id] = true
		var lower: bool = prism.bottom_cm == 200
		var upper: bool = prism.bottom_cm == 1000
		for top in prism.top_cm:
			lower = lower and top == 600
			upper = upper and top == 1300
		check(lower or upper, "every triangular prism preserves part interval: " + JSON.stringify(prism))
		lower_seen = lower_seen or lower
		upper_seen = upper_seen or upper
	check(solid_ids.size() == 2 and lower_seen and upper_seen, "collision prisms preserve empty vertical gap: " + str(solid_ids))
	var bad_source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	bad_source.features[2].properties.min_height = 1
	var bad_path := ProjectSettings.globalize_path("user://overlap.overture.json")
	var file := FileAccess.open(bad_path,FileAccess.WRITE)
	file.store_string(JSON.stringify(bad_source))
	file.close()
	check(ui.store.undo() == "", "empty document for overlap proof")
	ui._start_import(bad_path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import == null and ui.store.document.buildings.is_empty(), "native overlap rejects entire family")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	ui._cancel_operation()
	await wait_work()
	check(ui.pending_import == null and ui.store.document.buildings.is_empty(), "cancel preserves current document")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import != null, "fresh retry")
	check(ui.store.redo() == "", "document revision changes during review")
	ui._adopt_import()
	await wait_work()
	check(ui.store.document.buildings.size() == 2, "stale review never duplicates family")
	check(FileAccess.get_sha256(path) == source_hash and FileAccess.get_sha256(package) == package_hash, "source/prior package retained")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("overture_vertical_validator: PASS (%d checks)" % checks)
	quit(0)
