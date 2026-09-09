extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const LAYER := preload("res://scripts/import_layer.gd")
const EDIT := preload("res://scripts/workbench_edit.gd")
var ui: Control
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message + ": " + ui.status_label.text)
		quit(1)
		assert(value, message)
func wait_work() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await create_timer(0.002).timeout
	check(not ui.busy, "owned import/preview terminates")
func run() -> void:
	root.size = Vector2i(1024,720)
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
	var path := ProjectSettings.globalize_path("user://multipart.overture.json")
	var stdout: Array = []
	check(OS.execute(ui.import_python.text, PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/overture_fixture.py"),"--multipart",path]), stdout, true) == 0, "synthetic Overture multipart snapshot")
	var original := FileAccess.get_sha256(path)
	var initial: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import == null and ui.store.document == initial and ui.status_label.text.contains("recipe 5"), "courtyard refuses legacy recipe atomically with guidance")
	check(ui.store.apply_command("Explicit courtyard recipe",[{"field":"recipe_version","before":1,"after":5}]) == "", "explicit version choice")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import != null, "native-valid courtyard review")
	check(ui.pending_import.value.patches.size() == 3 and ui.pending_import.value.patches[0].after.holes.size() == 1, "three complete parts retain courtyard and island")
	check(ui.import_summary.text.contains("recipe 5") and ui.import_summary.text.contains("synthetic fixture"), "review exposes recipe and attribution")
	var candidate: Dictionary = ui.pending_import.value.duplicate(true)
	check(candidate.coordinates.overture.feature_sources[0].building_ids.size() == 3, "source identity maps every complete part")
	for mode in ["missing", "duplicate", "unknown", "count"]:
		var bad: Dictionary = candidate.duplicate(true)
		var feature: Dictionary = bad.coordinates.overture.feature_sources[0]
		if mode == "missing": feature.building_ids.pop_back()
		elif mode == "duplicate": feature.building_ids[1] = feature.building_ids[0]
		elif mode == "unknown": feature.building_ids[1] += "-forged"
		else: feature.footprint_count = 2
		check(LAYER.new().load_value(bad,bad.layer_id) != "", "forged mapping rejected: " + mode)
	ui._discard_import()
	check(ui.store.document.buildings.is_empty(), "discard preserves map")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 3, "adopt complete footprint")
	var b: Dictionary = ui.store.document.buildings[0].duplicate(true)
	var center := Vector2.ZERO
	for p: Array in b.holes[0]: center += Vector2(p[0],p[1]) / b.holes[0].size()
	center = Vector2(b.holes[0][0][0]+100,b.holes[0][0][1]+100)
	check(ui.canvas._hit(center) == "", "courtyard beside island is empty selection space")
	var moved := EDIT.translated("buildings",b,Vector2(100,200))
	check(moved.holes[0][0][0] == b.holes[0][0][0] + 100 and moved.holes[0][0][1] == b.holes[0][0][1] + 200, "movement translates hole with outer")
	check(ui.store.apply_command("Move courtyard",[EDIT.patch("buildings",b,moved)]) == "", "move complete geometry")
	check(ui.store.undo() == "" and ui.store.document.buildings[0] == b, "undo complete geometry")
	check(ui.store.undo() == "" and ui.store.document.buildings.is_empty(), "undo whole import")
	check(ui.store.redo() == "" and ui.store.document.buildings[0] == b, "redo preserves holes and notice")
	var forged: Dictionary = candidate.duplicate(true)
	forged.patches[0].after.holes[0][0] = forged.patches[0].after.footprint[0]
	var layer := LAYER.new()
	check(layer.load_value(forged,forged.layer_id) == "", "malformed geometry reaches native validation")
	var empty := STORE.new()
	empty.document.recipe_version = 5
	check(layer.validate_for(empty) != "", "invalid candidate never adopts")
	var bad_source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	bad_source.features[0].geometry.coordinates[2][0][1].append(4)
	var bad_path := ProjectSettings.globalize_path("user://invalid-part.overture.json")
	var bad_file := FileAccess.open(bad_path,FileAccess.WRITE)
	bad_file.store_string(JSON.stringify(bad_source))
	bad_file.close()
	var retained: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(bad_path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	check(ui.pending_import == null and ui.store.document == retained, "invalid final part rejects whole source")
	var project := ProjectSettings.globalize_path("user://overture-geometry-project")
	check(ui.store.save_project(project) == "" and ui.store.autosave() == "", "save and recoverable history")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "" and reopened.document.buildings == ui.store.document.buildings and reopened.document.attributions == ui.store.document.attributions, "project roundtrip")
	check(reopened.recover(ui.store.recovery_path()) == "" and reopened.document.buildings == ui.store.document.buildings, "recovery roundtrip")
	var package := ProjectSettings.globalize_path("user://overture-geometry.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok, "package export")
	var package_hash := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok, "native package reopen")
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok and not generated.data.chunk.building_prisms.is_empty(), "native solid roof generation")
	for prism: Dictionary in generated.data.chunk.building_prisms:
		var points := PackedVector2Array()
		for p: Array in prism.footprint: points.append(Vector2(p[0],p[1]))
		check(not Geometry2D.is_point_in_polygon(center,points), "roof/prism does not fill courtyard")
	ui.preview_x.value = 1
	ui.preview_y.value = 1
	ui._preview()
	await wait_work()
	check(ui.preview_cache.has(Vector2i(1,1)), "shared renderer attached courtyard preview")
	var old: Node = ui.preview_cache[Vector2i(1,1)].root
	ui._preview()
	ui._cancel_operation()
	await wait_work()
	check(ui.preview_cache[Vector2i(1,1)].root == old, "cancel preserves accepted preview")
	if DisplayServer.get_name() != "headless":
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture) == OK, "rendered courtyard capture")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	ui._cancel_operation()
	await wait_work()
	check(ui.pending_import == null and ui.store.document.buildings[0] == b, "cancel preserves accepted courtyard")
	ui._start_import(path,LAYER.OVERTURE_LICENSE)
	await wait_work()
	# Duplicate source overlaps existing recipe-5 solids and must fail as a whole.
	check(ui.pending_import == null and ui.store.document.buildings.size() == 3, "overlapping reimport rejects without replacement")
	check(FileAccess.get_sha256(path) == original and FileAccess.get_sha256(package) == package_hash, "source and published package remain byte-exact")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("overture_geometry_validator: PASS (", checks, " checks)")
	quit(0)
