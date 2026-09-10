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
	check(not ui.busy, "chain worker finishes: " + ui.status_label.text)

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
	var path := ProjectSettings.globalize_path("user://chain-original.pbf")
	var output: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_fixture.py"),path,"12","chains"]),output,true) == 0,"synthetic chained PBF: " + str(output))
	var source_hash := FileAccess.get_sha256(path)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import == null and ui.status_label.text.contains("recipe 2"),"legacy recipe cannot silently omit connected surface validation: " + ui.status_label.text)
	check(ui.store.apply_command("Choose connected road recipe",[{"field":"recipe_version","before":1,"after":2}]) == "","explicit recipe 2 selection")
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"native chained review: " + ui.status_label.text)
	if ui.pending_import != null:
		var raw: Dictionary = ui.pending_import.value.duplicate(true)
		check(ui.store.document == before,"review preserves accepted map")
		check(ui.import_summary.text.contains("two distinct explicit ground connections") and ui.import_summary.text.contains("maxheight:physical"),"continuation profile/clearance reviewed")
		check(raw.coordinates.osm_connections.joins.size() == 4,"four original source continuations retained")
		var limited := preload("res://scripts/document_store.gd").new()
		limited.document = before.duplicate(true)
		limited.document.cell_size_cm = 1000
		var bounded := LAYER.new()
		check(bounded.load_value(raw,ui.import_identity,ui.import_coordinates_request) == "" and bounded.validate_for(limited).contains("16 cells"),"native validation cells bounded before generation")
		for kind in ["null", "profile", "duplicate", "ref", "ways", "mapping", "kind", "clearance"]:
			var bad: Dictionary = raw.duplicate(true)
			match kind:
				"null": bad.coordinates.osm_connections = null
				"profile": bad.coordinates.osm_connections.profile = "inferred"
				"duplicate": bad.coordinates.osm_connections.joins.append(bad.coordinates.osm_connections.joins[0].duplicate(true))
				"ref": bad.coordinates.osm_connections.joins[0].ref = "999"
				"ways": bad.coordinates.osm_connections.joins[0].source_ways = ["2", "2"]
				"mapping": bad.coordinates.osm_connections.joins[0].retained[0].feature = 999
				"kind": bad.coordinates.osm_connections.joins[0].kind = "tunnel"
				"clearance":
					for p: Dictionary in bad.patches:
						if p.field == "roads" and p.after.kind == "tunnel":
							p.after.clearance_cm = 400
							break
			check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request) != "","forged continuation rejected: " + kind)
		# Existing native guards are still authoritative even for legacy metadata.
		for kind in ["clearance", "mouth", "terrain"]:
			var bad: Dictionary = raw.duplicate(true)
			bad.coordinates.erase("osm_connections")
			var roads: Array = []
			for p: Dictionary in bad.patches:
				if p.field == "roads": roads.append(p.after)
			if kind == "clearance": roads[7].clearance_cm = 400
			elif kind == "mouth":
				var target: Array = roads[1].points[0].duplicate()
				var previous: Array = roads[2].points[-1].duplicate()
				# Fold the middle deck back onto the incoming mouth.
				for road: Dictionary in roads:
					for point: Array in road.points:
						if point == previous: point[0] = target[0]
				for p: Dictionary in bad.patches:
					if p.field == "nodes" and p.id == roads[2].to: p.after.position[0] = target[0]
			else:
				var node_id: String = roads[0].to
				for road: Dictionary in roads:
					if road.from == node_id: road.points[0][1] = 100
					if road.to == node_id: road.points[-1][1] = 100
				for p: Dictionary in bad.patches:
					if p.field == "nodes" and p.id == node_id: p.after.position[1] = 100
			var candidate := LAYER.new()
			var error := candidate.load_value(bad,ui.import_identity,ui.import_coordinates_request)
			check(error == "", "native invalid fixture passes metadata: " + kind + " " + error)
			if error == "":
				var native_error := candidate.validate_for(ui.store)
				check(native_error.contains("E_GEOMETRY"),"native rejects joined " + kind + ": " + native_error)
			check(ui.store.document == before,"failed native candidate preserves map: " + kind)
		ui._adopt_import()
		check(ui.store.document.roads.size() == 10,"atomic chained adoption: " + ui.status_label.text)
		var adopted: Dictionary = ui.store.document.duplicate(true)
		check(ui.store.undo() == "" and ui.store.document.roads.is_empty() and ui.store.document.nodes.is_empty() and ui.store.document.recipe_version == 2,"whole chained graph Undo")
		check(ui.store.redo() == "" and ui.store.document == adopted,"exact chained Redo")
		await verify_package(ui,"full-chains",raw)
		var package_hash := FileAccess.get_sha256(ProjectSettings.globalize_path("user://full-chains.memap"))
		adopted = ui.store.document.duplicate(true)
		ui._start_import(path,LAYER.OSM_LICENSE)
		ui._cancel_operation()
		await wait_import(ui)
		check(ui.pending_import == null and ui.store.document == adopted,"cancel preserves connected graph")
		ui._start_import(path,LAYER.OSM_LICENSE)
		await wait_import(ui)
		check(ui.pending_import != null,"fresh chain retry stages")
		check(ui.store.undo() == "","change document during chain review")
		ui._adopt_import()
		check(ui.store.document.roads.is_empty(),"stale chain review cannot overwrite Undo")
		await verify_crop(ui,path)
		check(FileAccess.get_sha256(ProjectSettings.globalize_path("user://full-chains.memap")) == package_hash,"previous full package preserved through cancel/stale/crop")
	check(FileAccess.get_sha256(path) == source_hash,"original chain PBF preserved")
	check(DirAccess.get_directories_at("user://authoring-candidates").is_empty(),"disposable native candidates cleaned on success and failure")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_connections_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)

func verify_package(ui: Control, name: String, raw: Dictionary) -> void:
	var base := ProjectSettings.globalize_path("user://" + name)
	check(ui.store.save_project(base) == "","save chain project " + name)
	var package := base + ".memap"
	check(JSON.parse_string(ui.store.bridge.export_project(base,package)).ok,"export chain package " + name)
	var digest := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok,"reopen chain package " + name)
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"native chain generation " + name + ": " + str(generated.get("error","")))
	if generated.ok:
		for join: Dictionary in raw.coordinates.osm_connections.joins:
			if join.retained.is_empty(): continue
			var id: String = "import-" + raw.layer_id + "-osm-node-" + join.ref
			var at: Array = []
			for node: Dictionary in ui.store.document.nodes:
				if node.id == id: at = node.position
			var floor_seen := false
			var ceiling_seen := false
			for triangle: Dictionary in generated.data.chunk.triangles:
				for point: Array in triangle.vertices:
					if absi(int(point[0])-int(at[0])) > 1: continue
					if absi(int(point[2])-int(at[2])) > 201: continue
					floor_seen = floor_seen or (triangle.spawnable and point[1] == at[1])
					ceiling_seen = ceiling_seen or (not triangle.spawnable and point[1] == at[1]+450)
			check(floor_seen,"floor reaches source join " + join.ref + " " + name)
			if join.kind == "tunnel": check(ceiling_seen,"physical ceiling continuous at " + join.ref + " " + name)
		check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)) == generated,"deterministic chain generation " + name)
	check(FileAccess.get_sha256(package) == digest,"prior chain package retained " + name)

func verify_crop(ui: Control, path: String) -> void:
	ui.osm_panel.enabled.button_pressed = true
	ui.osm_panel.streaming.button_pressed = true
	var bbox := [9.00075,54.9999,9.0015,55.001]
	for i in range(4): ui.osm_panel.fields[i].value = bbox[i]
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"streaming shared-node crop review: " + ui.status_label.text)
	if ui.pending_import == null: return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.coordinates.osm_stream.selected.ways == 10 and raw.coordinates.osm_stream.structure_closure.structures == 6,"all source chains/ground approaches collected before crop")
	check(raw.coordinates.osm_crop.policy == "geometry-intersection-v4" and raw.coordinates.osm_crop.vertical.partial_structure_ways == 0,"complete ways with lost continuation use v4 section metadata")
	for kind in ["missing", "downgrade", "sections", "duplicate-sections", "role", "closure", "count", "mapping", "source-way"]:
		var bad: Dictionary = raw.duplicate(true)
		match kind:
			"missing": bad.coordinates.erase("osm_connections")
			"downgrade": bad.coordinates.osm_crop.policy = "geometry-intersection-v3"
			"sections": bad.coordinates.osm_crop.vertical.connection_sections[0] = "999"
			"duplicate-sections": bad.coordinates.osm_crop.vertical.connection_sections[0] = bad.coordinates.osm_crop.vertical.connection_sections[1]
			"role": bad.coordinates.osm_crop.vertical.structures[0].endpoints[0].role = "source-node"
			"closure": bad.coordinates.osm_stream.structure_closure = null
			"count": bad.coordinates.osm_stream.structure_closure.visits = 200001
			"mapping": bad.coordinates.osm_connections.joins[0].retained = []
			"source-way": bad.coordinates.osm_crop.vertical.structures[0].source_way = "999"
		check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request) != "","forged cropped chain rejected: " + kind)
	check(ui.store.document == before,"cropped review preserves map")
	ui._adopt_import()
	check(ui.store.document.roads.size() == 2,"adopt exact middle bridge/tunnel only: " + ui.status_label.text)
	await verify_package(ui,"cropped-chains",raw)
	var adopted: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui.osm_panel.fields[0].value += 0.000001
	ui.osm_panel.fields[0].value -= 0.000001
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"restored selection rejects late chain crop")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"cropped chain Undo")
	check(ui.store.redo() == "" and ui.store.document.roads.size() == 2,"cropped chain Redo")
