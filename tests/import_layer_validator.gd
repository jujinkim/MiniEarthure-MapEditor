extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
var failures: Array[String] = []
func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "import joins within deadline: " + ui.status_label.text)
func click_adopt(ui: Control) -> void:
	await process_frame
	var button: Button = ui.import_review.get_ok_button()
	for down in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = button.get_global_rect().get_center() + Vector2(ui.import_review.position)
		event.global_position = event.position
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = down
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
		root.push_input(event)
		await process_frame
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var base := ProjectSettings.globalize_path("user://import-boundary")
	DirAccess.make_dir_recursive_absolute(base)
	var path := base.path_join("source with spaces.geojson")
	var content := JSON.stringify({"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[30,10],[30,30],[10,30],[10,10]]]}}]})
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(content)
	file.close()
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_worker("import", path, "MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.store.document == before, "unadopted import cannot mutate: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		quit(1)
		return
	var value: Dictionary = ui.pending_import.value.duplicate(true)
	var id: String = value.layer_id
	check(ui.import_review.visible and ui.import_summary.text.contains("height_m"), "review displays missing/estimated values")
	for mutation in ["version", "identity", "replace", "field", "record", "duplicate", "metadata"]:
		var bad := value.duplicate(true)
		match mutation:
			"version": bad.import_version = 99
			"identity": bad.layer_id = "b".repeat(32)
			"replace": bad.patches[0].before = bad.patches[0].after
			"field": bad.patches[0].field = "bounds"
			"record": bad.patches[0].after.id = "existing"
			"duplicate": bad.patches.append(bad.patches[0].duplicate(true))
			"metadata": bad.source.license = ""
		check(LAYER.new().load_value(bad, id) != "", "reject boundary " + mutation)
	ui._discard_import()
	check(ui.store.document == before, "discard preserves document")
	ui._start_worker("import", path, "MIT")
	await wait_import(ui)
	await click_adopt(ui)
	check(ui.store.document.buildings.size() == 1 and ui.store.undo_stack.size() == 1, "single atomic adoption")
	if ui.store.document.buildings.is_empty():
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	var first: Dictionary = ui.store.document.buildings[0].duplicate(true)
	check(ui.store.save_project(base.path_join("project")) == "", "save adopted import")
	check(ui.store.autosave() == "", "recoverable import attribution")
	var saved := FileAccess.get_sha256(base.path_join("project/document.json"))
	ui._start_worker("import", path, "MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.pending_import.value.layer_id != id, "repeat imports receive fresh identity")
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 2 and ui.store.document.attributions.size() == 2, "repeat creates second layer")
	check(ui.store.document.buildings.has(first), "old layer unchanged")
	check(ui.store.undo() == "" and ui.store.document.buildings == [first], "undo only new layer")
	check(ui.store.redo() == "" and ui.store.document.buildings.size() == 2, "redo second layer")
	check(FileAccess.get_sha256(base.path_join("project/document.json")) == saved, "adoption does not rewrite saved file")
	ui._start_worker("import", path, "MIT")
	await wait_import(ui)
	ui.store.new_document()
	ui._adopt_import()
	check(ui.store.document.buildings.is_empty() and ui.pending_import == null, "document replacement invalidates review")
	ui._start_worker("import", path, "MIT")
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document.buildings.is_empty(), "late cancelled result not published")
	check(FileAccess.get_file_as_string(path) == content, "original source preserved")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("import_layer_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
