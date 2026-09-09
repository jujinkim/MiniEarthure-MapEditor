extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
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
	check(not ui.busy, "structure worker terminates: " + ui.status_label.text)
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
	var path := ProjectSettings.globalize_path("user://structures.osm.pbf")
	var output: Array = []
	check(OS.execute(ui.import_python.text, PackedStringArray(["-B", ProjectSettings.globalize_path("res://tests/osm_fixture.py"),path,"12","structures"]),output,true) == 0,"synthetic structure PBF: " + str(output))
	var source_hash := FileAccess.get_sha256(path)
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"structure candidate: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	check(ui.store.document == before,"review preserves accepted document")
	check(ui.import_summary.text.contains("EGM96") and ui.import_summary.text.contains("maxheight:physical"),"vertical datum and physical clearance reviewed")
	ui._adopt_import()
	check(ui.store.document.roads.size() == 6,"native structure adoption: " + ui.status_label.text)
	if ui.store.document.roads.size() == 6:
		var roads: Array = ui.store.document.roads
		check(roads[1].kind == "bridge" and roads[4].kind == "tunnel", "structure kinds survive native adoption")
		check(roads[0].to == roads[1].from and roads[1].to == roads[2].from,"bridge approaches share graph endpoints")
		check(roads[3].to == roads[4].from and roads[4].to == roads[5].from,"tunnel approaches share graph endpoints")
		check(roads[1].points[1][1] == 600 and roads[4].points[1][1] == -600 and roads[4].clearance_cm == 450,"explicit grades and physical clearance survive")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"one-command undo removes whole structure graph")
	check(ui.store.redo() == "" and ui.store.document == adopted,"redo restores exact graph")
	var base := ProjectSettings.globalize_path("user://structures-project")
	check(ui.store.save_project(base) == "", "save structured source project")
	var package := base + ".memap"
	check(JSON.parse_string(ui.store.bridge.export_project(base,package)).ok,"build structure package")
	var package_hash := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok,"open structured package")
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"generate bridge/tunnel geometry: " + str(generated.get("error", "")))
	if generated.ok:
		var bridge_floor := false
		var tunnel_floor := false
		var tunnel_roof := false
		for triangle: Dictionary in generated.data.chunk.triangles:
			# Native triangle vertices must retain both vertical surfaces and roof.
			for point: Array in triangle.vertices:
				bridge_floor = bridge_floor or point[1] == 600
				tunnel_floor = tunnel_floor or point[1] == -600
				tunnel_roof = tunnel_roof or point[1] == -150
		check(bridge_floor and tunnel_floor and tunnel_roof,"generated elevated deck, depressed floor and physical ceiling")
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"cancellation preserves structure graph")
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"retry stages fresh structures")
	check(ui.store.undo() == "","change document during structure review")
	ui._adopt_import()
	check(ui.store.document.roads.is_empty(),"stale structure review cannot overwrite document")
	check(FileAccess.get_sha256(path) == source_hash and FileAccess.get_sha256(package) == package_hash,"source and prior package preserved")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_structures_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
