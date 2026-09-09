extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
var failures: Array[String] = []
var checks := 0
func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "OSM worker terminates: " + ui.status_label.text)
func fixture(python: String, path: String, height: String = "12") -> void:
	var output: Array = []
	check(OS.execute(python, PackedStringArray(["-B", ProjectSettings.globalize_path("res://tests/osm_fixture.py"), path, height]), output, true) == 0, "synthetic PBF writer: " + str(output))
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = 9
	ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512
	ui.import_origin_y.value = 512
	check(ui.import_coordinate_mode.selected == 1 and ui.import_coordinate_mode.disabled, "OSM uses explicit WGS84 origins")
	check(ui.import_license.text == LAYER.OSM_LICENSE and not ui.import_license.editable, "OSM attribution retained")
	if DisplayServer.get_name() != "headless":
		root.size = Vector2i(1024,720)
		ui._import_geojson()
		await process_frame
		check(ui.import_dialog.size.x <= root.size.x and ui.import_dialog.size.y <= root.size.y, "OSM form fits minimum window")
		check(ui.import_origin_y.is_visible_in_tree() and ui.import_source_format.is_visible_in_tree(), "format/origins visible")
		ui.import_dialog.hide()
	var path := ProjectSettings.globalize_path("user://synthetic source.osm.pbf")
	fixture(ui.import_python.text,path)
	var original := FileAccess.get_sha256(path)
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null, "PBF review candidate: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	check(ui.store.document == before, "staging does not mutate map")
	check(ui.pending_import.value.source.sha256 == original and ui.pending_import.value.adapter == "osm-extract-v1", "PBF identity and captured bytes")
	check(ui.import_summary.text.contains("OpenStreetMap") and ui.import_summary.text.contains("ignored_ways=1") and ui.import_summary.text.contains("estimates"), "source/omissions/estimates reviewed")
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	for field in ["license","adapter","origin"]:
		var bad := raw.duplicate(true)
		if field == "license": bad.source.license = "MIT"
		elif field == "adapter": bad.adapter = "geojson-v2"
		else: bad.coordinates.origin = [10,55]
		check(LAYER.new().load_value(bad,raw.layer_id,ui.import_coordinates_request) != "", "forged OSM " + field + " rejected")
	if DisplayServer.get_name() != "headless":
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture) == OK, "capture OSM review")
	ui._discard_import()
	check(ui.store.document == before and ui.pending_import == null, "discard preserves document")
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 1 and ui.store.document.roads.size() == 1 and ui.store.document.zones.size() == 1, "native adoption of PBF building/road/forest")
	check(ui.store.document.attributions[0].license == LAYER.OSM_LICENSE, "ODbL notice in document")
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 1, "one-shot adoption")
	var base := ProjectSettings.globalize_path("user://osm-project")
	check(ui.store.save_project(base) == "", "save OSM project")
	check(ui.store.autosave() == "", "OSM recovery snapshot")
	var reopened := STORE.new()
	check(reopened.open_project(base) == "", "reopen OSM project")
	check(reopened.document.attributions == ui.store.document.attributions, "provenance roundtrip")
	check(reopened.recover(ui.store.recovery_path()) == "", "recover OSM project")
	var output := ProjectSettings.globalize_path("user://osm-project.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(base,output)).ok, "package OSM document")
	var before_package := FileAccess.get_sha256(output)
	check(JSON.parse_string(ui.store.bridge.open_package(output)).ok, "open OSM package")
	check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)).ok, "native shared geometry generation")
	var updated_path := ProjectSettings.globalize_path("user://updated.osm.pbf")
	fixture(ui.import_python.text,updated_path,"23")
	ui._start_import(updated_path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null and ui.pending_import.value.layer_id != raw.layer_id and ui.pending_import.value.source.sha256 != original, "updated source gets fresh layer/hash")
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 2, "updated source retains old geometry")
	check(ui.store.undo() == "" and ui.store.document.buildings.size() == 1, "undo updated OSM layer")
	check(ui.store.redo() == "" and ui.store.document.buildings.size() == 2, "redo updated OSM layer")
	check(FileAccess.get_sha256(output) == before_package and FileAccess.get_sha256(path) == original, "source and existing package unchanged")
	before = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before, "OSM cancellation preserves accepted content")
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.store.undo() == "", "document change while review pending")
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 1, "stale review cannot adopt")
	ui.import_origin_lon.value = -90
	before = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before, "out-of-profile PBF rejected atomically")
	ui.import_source_format.select(0)
	ui.import_source_format.item_selected.emit(0)
	check(ui.import_license.editable and not ui.import_coordinate_mode.disabled, "return to independent GeoJSON settings")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_import_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)
