extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const CANVAS := preload("res://scripts/map_canvas.gd")
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	_run.call_deferred()

func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "import/adoption retires: " + ui.status_label.text)

func _run() -> void:
	check(ClassDB.class_exists("MapKitBridge"), "MapKitBridge must load without private game repositories")
	var store := STORE.new()
	store.new_document()
	var canvas := CANVAS.new()
	canvas.store = store
	root.add_child(canvas)
	canvas.tool = "Building"
	canvas.draft.assign([Vector2(1000, 1000), Vector2(3000, 1000), Vector2(3000, 3000), Vector2(1000, 3000)])
	canvas.finish_shape()
	check(store.document.buildings.size() == 1, "manual building command")
	var building: Dictionary = store.document.buildings[0].duplicate(true)
	store.undo()
	check(store.document.buildings.is_empty(), "undo building")
	store.redo()
	check(store.document.buildings == [building], "redo building")
	canvas.selected.assign([str(building.id)])
	canvas.duplicate_selection()
	check(store.document.buildings.size() == 2, "duplicate selection")
	store.undo()
	canvas.tool = "Road"
	canvas.draft.assign([Vector2(1000, 5000), Vector2(15000, 5000)])
	canvas.finish_shape()
	check(store.document.roads.size() == 1 and store.document.nodes.size() == 2, "road and graph command")
	canvas.draft.assign([Vector2(15000, 5000), Vector2(25000, 15000)])
	canvas.finish_shape()
	check(store.document.nodes.size() == 3, "snapped road endpoint reuses graph node")
	store.undo()
	check(store.document.roads.size() == 1 and store.document.nodes.size() == 2, "undo connected road keeps shared endpoint")
	var before: Dictionary = store.document.duplicate(true)
	var invalid := building.duplicate(true)
	invalid.height_cm = -1
	check(store.apply_command("bad", [{"field": "buildings", "id": building.id, "before": building, "after": invalid}]) != "", "reject invalid property")
	check(store.document == before, "failed command leaves document intact")
	var base := ProjectSettings.globalize_path("user://editor-contract")
	check(store.save_project(base) == "", "save project")
	check(store.autosave() == "", "autosave")
	var recovery := store.recovery_path()
	var reopened := STORE.new()
	check(reopened.open_project(base) == "", "reopen public project")
	check(reopened.document.buildings == store.document.buildings, "save/reopen geometry")
	check(reopened.recover(recovery) == "", "recover snapshot")
	var destination := base + "-" + Crypto.new().generate_random_bytes(4).hex_encode() + ".memap"
	var result: Dictionary = JSON.parse_string(store.bridge.export_project(base, destination))
	check(result.ok, "export editor project")
	check(JSON.parse_string(store.bridge.open_package(destination)).ok, "load exported package")
	var generated: Dictionary = JSON.parse_string(store.bridge.generate_chunk(0, 0))
	check(generated.ok, "generate through independent binding")
	if generated.ok:
		check(str(generated.data.generated_sha256).length() == 64, "generation hash")
	var scene: PackedScene = load("res://main.tscn")
	var ui := scene.instantiate()
	root.add_child(ui)
	await process_frame
	ui.store.document = store.document.duplicate(true)
	ui._document_changed()
	ui._preview()
	for _i in range(300):
		await process_frame
		if not ui.busy:
			break
	check(not ui.busy, "preview worker finishes")
	check(str(ui.status_label.text).begins_with("Preview ready"), "3D renderer attaches generated preview")
	var import_path := base + "/source.geojson"
	var source_file := FileAccess.open(import_path, FileAccess.WRITE)
	source_file.store_string(JSON.stringify({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"height_m": 8}, "geometry": {"type": "Polygon", "coordinates": [[[100, 100], [120, 100], [120, 120], [100, 120], [100, 100]]]}}]}))
	source_file.close()
	ui._start_worker("import", import_path, "MIT")
	await wait_import(ui)
	check(not ui.busy and ui.pending_import != null and ui.store.document.buildings.size() == 1, "child-process GeoJSON prepares without mutation")
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.buildings.size() == 2, "explicit import adoption")
	check(ui.store.document.attributions.size() == 1, "import retains source license")
	ui.store.undo()
	check(ui.store.document.buildings.size() == 1 and ui.store.document.attributions.is_empty(), "import is one undo command")
	ui.store.dirty = false
	ui.queue_free()
	canvas.queue_free()
	await process_frame
	print("editor_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
