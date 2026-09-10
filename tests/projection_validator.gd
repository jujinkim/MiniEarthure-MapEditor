extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
var failures: Array[String] = []
func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "projection worker terminates: " + ui.status_label.text)
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	if ui.import_python.text == "": ui.import_python.text = "python3"
	ui.import_coordinate_mode.select(1)
	ui.import_origin_lon.value = 9
	ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512
	ui.import_origin_y.value = 512
	ui.import_accuracy.text = "synthetic 1 m"
	ui.import_license.text = "MIT"
	if DisplayServer.get_name() != "headless":
		root.size = Vector2i(1024,720)
		ui.import_coordinate_mode.item_selected.emit(1)
		ui._import_geojson()
		await process_frame
		await process_frame
		check(ui.import_dialog.size.x <= root.size.x and ui.import_dialog.size.y <= root.size.y, "geographic form fits minimum window")
		check(not ui.import_dialog.get_ok_button().disabled, "valid license enables source selection")
		var help: Label = ui.import_license.get_parent().get_child(0)
		check(help.get_global_rect().end.y <= ui.import_license.get_global_rect().position.y, "help and license input do not overlap")
		check(ui.import_origin_y.is_visible_in_tree() and ui.import_python.is_visible_in_tree(), "origin/Python controls visible")
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture) == OK, "capture geographic form")
		ui.import_dialog.hide()

	var path := ProjectSettings.globalize_path("user://geographic source.geojson")
	var geo := {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"height_m":12},"geometry":{"type":"Polygon","coordinates":[[[9,55],[9.0002,55],[9.0002,55.0002],[9,55.0002],[9,55]]]}}]}
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify(geo))
	file.close()
	var original := FileAccess.get_sha256(path)
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null, "projection candidate: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(ui.import_summary.text.contains("EPSG:32632") and ui.import_summary.text.contains("synthetic 1 m"), "review projection/provenance")
	for change in ["origin","crs"]:
		var bad := raw.duplicate(true)
		if change == "origin": bad.coordinates.origin = [10,55]
		else: bad.coordinates.target_crs = "EPSG:32633"
		check(LAYER.new().load_value(bad,raw.layer_id,ui.import_coordinates_request) != "", "wrong projection request rejected")
	ui._adopt_import()
	await wait_import(ui)
	var footprint: Array = ui.store.document.buildings[0].footprint
	check(JSON.stringify(footprint) == JSON.stringify(JSON.parse_string('[[51200,51200],[52479,51200],[52479,53426],[51200,53426]]')), "axis/centimetre fixture")
	var base := ProjectSettings.globalize_path("user://project")
	check(ui.store.save_project(base) == "", "save projection")
	check(ui.store.autosave() == "", "retain projection recovery")
	var recovery: String = ui.store.recovery_path()
	var reopened := STORE.new()
	check(reopened.open_project(base) == "", "reopen projection")
	check(reopened.document.attributions == ui.store.document.attributions, "projection attribution roundtrip")
	check(reopened.recover(recovery) == "", "recover projection metadata")
	var output := ProjectSettings.globalize_path("user://project.memap")
	var packaged: Dictionary = JSON.parse_string(ui.store.bridge.export_project(base,output))
	check(packaged.ok, "package projected document")
	var before_package := FileAccess.get_sha256(output)
	check(JSON.parse_string(ui.store.bridge.open_package(output)).ok, "open projected package")
	var chunk: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(chunk.ok, "shared native generation for projected geometry")
	# Updating original data has no automatic effect; new candidate is separate.
	geo.features[0].properties.height_m = 23
	file = FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify(geo))
	file.close()
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.pending_import.value.source.sha256 != original, "updated source produces new candidate")
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.buildings.size() == 2, "updated source adds separate layer")
	var heights: Array = []
	for building: Dictionary in ui.store.document.buildings: heights.append(int(building.height_cm))
	heights.sort()
	check(heights == [1200,2300], "old content is not automatically replaced")
	check(FileAccess.get_sha256(output) == before_package, "existing package preserved")
	check(ui.store.undo() == "" and ui.store.document.buildings.size() == 1, "undo updated layer")
	check(ui.store.redo() == "" and ui.store.document.buildings.size() == 2, "redo updated layer")
	# Out-of-area and late cancellation preserve accepted content and history.
	var before: Dictionary = ui.store.document.duplicate(true)
	ui.import_origin_lon.value = -90
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before, "out-of-strip rejects whole input")
	ui.import_origin_lon.value = 9
	ui._start_import(path,"MIT")
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before, "cancelled projection retains live map")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("projection_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
