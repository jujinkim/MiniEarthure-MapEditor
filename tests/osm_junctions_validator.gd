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
	check(not ui.busy, "junction worker finishes: " + ui.status_label.text)

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
	var path := ProjectSettings.globalize_path("user://junction-original.pbf")
	var output: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_fixture.py"),path,"12","junctions"]),output,true) == 0,"synthetic junction PBF: " + str(output))
	var source_hash := FileAccess.get_sha256(path)
	check(ui.store.apply_command("Choose structural recipe",[{"field":"recipe_version","before":1,"after":2}]) == "","explicit recipe 2")
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"native branch/mixed review: " + ui.status_label.text)
	if ui.pending_import != null:
		var raw: Dictionary = ui.pending_import.value.duplicate(true)
		check(ui.store.document == before,"junction review preserves accepted map")
		check(raw.coordinates.osm_connections.profile == "explicit-structural-junctions-v2","explicit source arm version")
		check(ui.import_summary.text.contains("portal boundaries") and ui.import_summary.text.contains("32 native arms"),"mixed cross-section estimate and source limitations reviewed")
		for kind in ["version", "missing-arm", "duplicate-arm", "direction", "source-way", "kind", "source-clearance", "retained-end", "retained-source", "retained-feature", "missing-retained", "road-kind", "road-clearance", "overflow"]:
			var bad: Dictionary = raw.duplicate(true)
			var join: Dictionary = bad.coordinates.osm_connections.joins[2]
			match kind:
				"version": bad.coordinates.osm_connections.profile = "same-kind-endpoints-v1"
				"missing-arm": join.source_arms.pop_back()
				"duplicate-arm": join.source_arms.append(join.source_arms[0].duplicate(true))
				"direction": join.source_arms[0].end = "near"
				"source-way": join.source_ways.append("999")
				"kind": join.kind = "tunnel"
				"source-clearance": join.source_arms[-1].clearance_cm = 451
				"retained-end": join.retained[0].end = "to"
				"retained-source": join.retained[0].source_way = join.retained[1].source_way
				"retained-feature": join.retained[0].feature = 999
				"missing-retained": join.retained.pop_back()
				"road-kind", "road-clearance":
					var id: String = "import-" + raw.layer_id + "-" + str(int(join.retained[-1].feature))
					for p: Dictionary in bad.patches:
						if p.field == "roads" and p.id == id:
							if kind == "road-kind": p.after.kind = "bridge"
							else: p.after.clearance_cm = 400
				"overflow":
					while join.source_arms.size() < 33: join.source_arms.append(join.source_arms[0].duplicate(true))
			check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request) != "","forged junction rejected: " + kind)
		var conflicting: Dictionary = raw.duplicate(true)
		var interior: Dictionary = conflicting.coordinates.osm_connections.joins[0]
		interior.source_arms[0].kind = "tunnel"
		interior.source_arms[0].clearance_cm = 450
		interior.kind = "mixed"
		check(LAYER.new().load_value(conflicting,ui.import_identity,ui.import_coordinates_request).contains("source-way"),"two sides of one original way cannot invent different cross-sections")
		for kind in ["mouth", "clearance"]:
			var bad: Dictionary = raw.duplicate(true)
			bad.coordinates.erase("osm_connections")
			var joined: Array = []
			for p: Dictionary in bad.patches:
				if p.field == "roads" and p.after.from.ends_with("osm-node-200"): joined.append(p.after)
			if kind == "mouth": joined[1].points[1] = joined[0].points[1].duplicate()
			else: joined[1].clearance_cm = 400
			var candidate := LAYER.new()
			check(candidate.load_value(bad,ui.import_identity,ui.import_coordinates_request) == "","native-invalid branch passes legacy metadata " + kind)
			var error := candidate.validate_for(ui.store)
			check(error.contains("E_GEOMETRY"),"native rejects mixed branch " + kind + ": " + error)
			check(ui.store.document == before,"native branch failure preserves accepted map")
		ui._adopt_import()
		await wait_import(ui)
		check(ui.store.document.roads.size() == 22,"atomic all junction roads: " + ui.status_label.text)
		var adopted: Dictionary = ui.store.document.duplicate(true)
		check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"junction graph Undo")
		check(ui.store.redo() == "" and ui.store.document == adopted,"junction graph Redo")
		verify_package(ui,"full-junctions",raw)
		var package_hash := FileAccess.get_sha256(ProjectSettings.globalize_path("user://full-junctions.memap"))
		adopted = ui.store.document.duplicate(true)
		ui._start_import(path,LAYER.OSM_LICENSE)
		ui._cancel_operation()
		await wait_import(ui)
		check(ui.pending_import == null and ui.store.document == adopted,"cancel preserves junctions")
		ui._start_import(path,LAYER.OSM_LICENSE)
		await wait_import(ui)
		check(ui.pending_import == null and ui.status_label.text.contains("E_BUDGET") and ui.store.document == adopted,"duplicate layered junctions exceed native subdivision budget without replacing accepted map: " + ui.status_label.text)
		check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)).ok,"budget failure preserves loaded accepted package")
		check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"remove accepted layer before fresh retry")
		ui._start_import(path,LAYER.OSM_LICENSE)
		await wait_import(ui)
		check(ui.pending_import != null,"fresh junction retry on empty map: " + ui.status_label.text)
		check(ui.store.undo() == "","edit while junction review pending")
		ui._adopt_import()
		await wait_import(ui)
		check(ui.store.document.roads.is_empty(),"stale junction cannot overwrite Undo")
		check(ui.store.redo() == "" and ui.store.document.recipe_version == 2,"restore selected recipe after stale review")
		for remaining in [1,2]: await verify_crop(ui,path,remaining)
		await verify_crop(ui,path,2,true)
		check(FileAccess.get_sha256(ProjectSettings.globalize_path("user://full-junctions.memap")) == package_hash,"previous junction package preserved")
	check(FileAccess.get_sha256(path) == source_hash,"original junction PBF preserved")
	check(DirAccess.get_directories_at("user://authoring-candidates").is_empty(),"junction native candidates disposed")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_junctions_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)

func xz(point: Array) -> Vector2: return Vector2(float(point[0]),float(point[2]))

func covers(triangles: Array, at: Vector2, height: float, spawnable: bool) -> bool:
	for triangle: Dictionary in triangles:
		if triangle.spawnable != spawnable: continue
		var v: Array = triangle.vertices
		var a := xz(v[0])
		var b := xz(v[1])
		var c := xz(v[2])
		var area := (b-a).cross(c-a)
		if absf(area) < 0.1: continue
		var u := (b-at).cross(c-at)/area
		var w := (c-at).cross(a-at)/area
		var t := 1.0-u-w
		if minf(u,minf(w,t)) < -0.00001: continue
		if absf(u*float(v[0][1])+w*float(v[1][1])+t*float(v[2][1])-height) <= 1.0: return true
	return false

func blocked(triangles: Array, start: Vector2, finish: Vector2) -> bool:
	for triangle: Dictionary in triangles:
		if triangle.spawnable: continue
		var v: Array = triangle.vertices
		var low := minf(float(v[0][1]),minf(float(v[1][1]),float(v[2][1])))
		var high := maxf(float(v[0][1]),maxf(float(v[1][1]),float(v[2][1])))
		if high-low < 200 or absf((xz(v[1])-xz(v[0])).cross(xz(v[2])-xz(v[0]))) > 0.1: continue
		for i in range(3):
			if xz(v[i]).distance_to(xz(v[(i+1)%3])) < 1: continue
			if Geometry2D.segment_intersects_segment(start,finish,xz(v[i]),xz(v[(i+1)%3])) != null: return true
	return false

func verify_package(ui: Control, name: String, raw: Dictionary) -> void:
	var base := ProjectSettings.globalize_path("user://" + name)
	check(ui.store.save_project(base) == "","save junction project " + name)
	check(JSON.parse_string(ui.store.bridge.export_project(base,base+".memap")).ok,"export junction package " + name)
	check(JSON.parse_string(ui.store.bridge.open_package(base+".memap")).ok,"reopen junction package " + name)
	var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"native junction generation " + name + ": " + str(generated.get("error","")))
	if not generated.ok: return
	var roads := {}
	for road: Dictionary in ui.store.document.roads: roads[road.id] = road
	for join: Dictionary in raw.coordinates.osm_connections.joins:
		for arm: Dictionary in join.retained:
			var road: Dictionary = roads["import-" + raw.layer_id + "-" + str(int(arm.feature))]
			var at: Array = road.points[0] if arm.end == "from" else road.points[-1]
			var next: Array = road.points[1] if arm.end == "from" else road.points[-2]
			# Sample both the apron and the body across each original mouth. Exact
			# source heights are level here, so falling/nearby ground cannot pass.
			for fraction in [0.025,0.075,0.15,0.25,0.5]:
				var sample := xz(at).lerp(xz(next),fraction)
				check(covers(generated.data.chunk.triangles,sample,float(at[1]),true),"continuous floor " + name + " " + join.ref + " " + str(arm.feature) + " " + str(fraction))
				if road.kind == "tunnel": check(covers(generated.data.chunk.triangles,sample,float(at[1])+450,false),"continuous tunnel-owned ceiling " + name + " " + join.ref + " " + str(fraction))
			check(not blocked(generated.data.chunk.triangles,xz(at).lerp(xz(next),0.01),xz(at).lerp(xz(next),0.5)),"no wall blocks structural mouth " + name + " " + join.ref)
	check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)) == generated,"deterministic junction generation " + name)

func verify_crop(ui: Control, path: String, remaining: int, mixed: bool = false) -> void:
	ui.osm_panel.enabled.button_pressed = true
	ui.osm_panel.streaming.button_pressed = true
	var bbox: Array = [9,55,9.0015,55.0015] if remaining == 1 else [9.0015,55,9.0025,55.0015]
	if mixed: bbox = [9.0065,55,9.0075,55.0015]
	var ref := "200" if mixed else "1"
	for i in range(4): ui.osm_panel.fields[i].value = bbox[i]
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"partial junction review " + str(remaining) + ": " + ui.status_label.text)
	if ui.pending_import == null: return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.coordinates.osm_stream.structure_closure.ways == (6 if mixed else 5),"whole branch closure")
	check(raw.coordinates.osm_crop.policy == "geometry-intersection-v4" and raw.coordinates.osm_connections.joins[0].retained.size() == remaining,"partial source junction truth " + str(remaining))
	for kind in ["section", "role", "mapping", "source-way"]:
		var bad: Dictionary = raw.duplicate(true)
		match kind:
			"section": bad.coordinates.osm_crop.vertical.connection_sections = []
			"role":
				for entry: Dictionary in bad.coordinates.osm_crop.vertical.structures:
					for end: Dictionary in entry.endpoints:
						if end.ref == ref: end.role = "source-node"
			"mapping": bad.coordinates.osm_connections.joins[0].retained.pop_back()
			"source-way": bad.coordinates.osm_crop.vertical.structures[0].source_way = "999"
		check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request) != "","forged partial branch rejected " + kind)
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.roads.size() == remaining*2,"only retained structural/ground arms adopted")
	verify_package(ui,"crop-"+str(remaining)+("-mixed" if mixed else ""),raw)
	var adopted: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui.osm_panel.fields[0].value += 0.000001
	ui.osm_panel.fields[0].value -= 0.000001
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"restored bbox rejects late branch response")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"crop junction Undo")
