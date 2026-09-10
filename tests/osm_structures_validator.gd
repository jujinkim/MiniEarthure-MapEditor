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
	await check_ground_crop(ui,path)
	check(FileAccess.get_sha256(path) == source_hash and FileAccess.get_sha256(package) == package_hash,"ground crop preserves original PBF and prior package")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_structures_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)

func check_ground_crop(ui: Control, path: String) -> void:
	var before: Dictionary = ui.store.document.duplicate(true)
	ui.osm_panel.enabled.button_pressed = true
	var bbox := [9.0001,54.9999,9.0021,55.001]
	for i in range(4): ui.osm_panel.fields[i].value = bbox[i]
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"clipped ground approaches native review: " + ui.status_label.text)
	if ui.pending_import == null: return
	check(ui.store.document == before,"ground crop review preserves accepted document")
	check(ui.import_summary.text.contains("ground still follows map terrain"),"ground crop reviews reference heights and terrain behavior")
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.coordinates.osm_crop.vertical.clipped_ground_features == 4 and raw.coordinates.osm_crop.vertical.retained_structure_features == 2,"vertical crop counts reviewed")
	for kind in ["missing", "profile", "count", "retained", "downgrade"]:
		var bad: Dictionary = raw.duplicate(true)
		match kind:
			"missing": bad.coordinates.osm_crop.erase("vertical")
			"profile": bad.coordinates.osm_crop.vertical.profile = "guessed"
			"count": bad.coordinates.osm_crop.vertical.clipped_ground_features = 100
			"retained": bad.coordinates.osm_crop.vertical.retained_structure_features = 0
			"downgrade": bad.coordinates.osm_crop.policy = "geometry-intersection-v1"
		check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request) != "","forged vertical crop rejected: " + kind)
	# A crop shorter than one quantized centimetre must fail native review atomically.
	var collapsed: Dictionary = raw.duplicate(true)
	for patch: Dictionary in collapsed.patches:
		if patch.field == "roads":
			patch.after.points[1] = patch.after.points[0].duplicate()
			break
	var invalid := LAYER.new()
	check(invalid.load_value(collapsed,ui.import_identity,ui.import_coordinates_request) == "" and invalid.validate_for(ui.store) != "","native rejects collapsed crop segment")
	check(ui.store.document == before,"collapsed crop rejection preserves document")
	ui._adopt_import()
	check(ui.store.document.roads.size() == 6,"clipped approaches atomically adopted")
	if ui.store.document.roads.size() != 6: return
	var roads: Array = ui.store.document.roads
	check(roads[0].from.contains("crop-") and roads[0].to == roads[1].from and roads[1].to == roads[2].from,"synthetic outer boundary preserves original bridge joins")
	check(roads[3].to == roads[4].from and roads[4].to == roads[5].from and roads[4].clearance_cm == 450,"tunnel connections and clearance survive approach crop")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	var base := ProjectSettings.globalize_path("user://ground-crop-project")
	check(ui.store.save_project(base) == "","save cropped structure source")
	check(JSON.parse_string(ui.store.bridge.export_project(base,base+".memap")).ok,"build cropped structure package")
	check(JSON.parse_string(ui.store.bridge.open_package(base+".memap")).ok,"open cropped structure package")
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"generate cropped structure geometry: " + str(generated.get("error","")))
	if generated.ok:
		var deck := false
		var roof := false
		for triangle: Dictionary in generated.data.chunk.triangles:
			for point: Array in triangle.vertices:
				deck = deck or point[1] == 600
				roof = roof or point[1] == -150
		check(deck and roof,"cropped package retains elevated deck and physical tunnel roof")
	# Save updates provenance, so freeze the accepted state after that operation.
	adopted = ui.store.document.duplicate(true)
	ui.osm_panel.fields[0].value = 9.0005
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"partial bridge/tunnel crop rejected without changing map")
	ui.osm_panel.fields[0].value = bbox[0]
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"ground crop cancellation preserves map")
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui.osm_panel.fields[0].value += 0.000001
	ui.osm_panel.fields[0].value -= 0.000001
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"changed-restored bbox rejects late ground crop")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"ground crop one-command Undo")
	check(ui.store.redo() == "" and ui.store.document.roads.size() == 6,"ground crop Redo")
	check(ui.store.undo() == "","remove crop before independent streaming retry")
	ui.osm_panel.streaming.button_pressed = true
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"streaming ground crop retry: " + ui.status_label.text)
	if ui.pending_import != null:
		check(ui.pending_import.value.coordinates.osm_crop.vertical.clipped_ground_features == 4,"streaming preserves ground crop profile")
		ui._adopt_import()
		check(ui.store.document.roads.size() == roads.size(),"streaming crop native adoption")
		if ui.store.document.roads.size() == roads.size():
			for i in range(roads.size()): check(ui.store.document.roads[i].points == roads[i].points,"whole/streaming crop geometry parity %d" % i)
