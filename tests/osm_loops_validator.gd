extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
const JOB := preload("res://scripts/import_native_job.gd")
class CancelGeneration extends JOB:
	var reached := false
	var expire := false
	func _event(line: PackedByteArray) -> void:
		super._event(line)
		if phase == 4 and not reached:
			reached = true
			if expire: deadline_ms = 0
			else: cancel()
var failures: Array[String] = []
var checks := 0
func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+15000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"loop worker terminates: " + ui.status_label.text)
func capture(name: String) -> void:
	var folder := OS.get_environment("MAPEDITOR_LOOPS_CAPTURE_DIR")
	if DisplayServer.get_name() == "headless" or folder == "": return
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(folder.path_join(name+".png")) == OK,"capture " + name)
func pointer(button: Button) -> void:
	await process_frame
	for down in [true,false]:
		var event := InputEventMouseButton.new()
		event.position = button.get_global_rect().get_center()+Vector2(button.get_window().position)
		event.global_position = event.position
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = down
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
		root.push_input(event)
		await process_frame
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	root.size = Vector2i(1024,720)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = 9
	ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512
	ui.import_origin_y.value = 512
	var path := ProjectSettings.globalize_path("user://loop-original.pbf")
	var out: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_loops_fixture.py"),path]),out,true) == 0,"synthetic loop PBF: " + str(out))
	var source_hash := FileAccess.get_sha256(path)
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import == null and ui.status_label.text.contains("recipe 2"),"recipe 1 cannot silently skip native junctions: " + ui.status_label.text)
	check(ui.store.apply_command("Choose connected recipe",[{"field":"recipe_version","before":1,"after":2}]) == "","explicit recipe 2")
	var base := ProjectSettings.globalize_path("user://baseline")
	check(ui.store.save_project(base) == "","save baseline")
	check(JSON.parse_string(ui.store.bridge.export_project(base,base+".memap")).ok,"export baseline")
	check(JSON.parse_string(ui.store.bridge.open_package(base+".memap")).ok,"load baseline bridge")
	var baseline_chunk: String = ui.store.bridge.generate_chunk(1,1)
	var package_hash := FileAccess.get_sha256(base+".memap")
	var before: Dictionary = ui.store.document.duplicate(true)
	var undo_count: int = ui.store.undo_stack.size()
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"native loop/approach review: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.feature_count == 8 and raw.coordinates.osm_ground_loops.retained.size() == 7,"loop and incident approach mapping")
	check(raw.coordinates.vertical.explicit_points == 0,"estimated heights are not explicit vertical data")
	check(ui.import_summary.text.contains("No source height datum was applied") and not ui.import_summary.text.contains("EPSG:5773"),"review does not present estimated ground as converted EGM96 heights")
	check(ui.store.document == before and ui.store.undo_stack.size() == undo_count and ui.store.bridge.generate_chunk(1,1) == baseline_chunk,"review preserves map/history/loaded bridge")
	check(ui.import_summary.text.contains("osm_ground_loops") and ui.import_summary.text.contains("No routing/access/oneway") and ui.import_summary.text.contains(source_hash),"review explains source connectivity and omitted routing")
	for expire in [false,true]:
		var job := CancelGeneration.new()
		job.expire = expire
		check(job.start_validation(ui.store,ui.pending_import,false,"loop-test",path,Crypto.new().generate_random_bytes(16).hex_encode()) == "","start owned native loop cancellation")
		var deadline := Time.get_ticks_msec()+15000
		while not job.done and Time.get_ticks_msec()<deadline:
			job.poll()
			await process_frame
		check(job.reached and job.done and job.exited and job.structural and not job.result.ok,"loop generation admission/cancel/deadline reaps child")
		check(not DirAccess.dir_exists_absolute(job.directory) and ui.store.document == before,"cancel/deadline preserves map and retires scratch")
		if not job.done: job.shutdown()
	await capture("review")
	ui._open_import_details()
	for key in ["coordinates","osm_ground_loops","sources",0,"refs"]:
		var index: int = ui.import_details.page_keys.find(key)
		check(index >= 0,"exact loop detail exists " + str(key))
		if index >= 0: ui.import_details.descend(index)
	check(ui.import_details.current == ["1","2","3","4","1"],"exact original loop order accessible")
	await capture("details")
	await pointer(ui.import_details.get_ok_button())
	for kind in ["missing","profile","source-order","source-repeat","closed","unrelated","range","gap","ref","height","count","road","endpoint","node","type","mapping"]:
		var bad := raw.duplicate(true)
		var meta: Dictionary = bad.coordinates.osm_ground_loops
		var first: Dictionary = meta.retained[0]
		match kind:
			"missing": bad.coordinates.erase("osm_ground_loops")
			"profile": meta.profile = "positions"
			"source-order": meta.sources.reverse()
			"source-repeat": meta.sources[0].refs[1] = "1"
			"closed": meta.sources[0].closed = false
			"unrelated": meta.sources[1].refs = ["998","999"]
			"range": first.source_range = [0,2]
			"gap": meta.retained.remove_at(0)
			"ref": first.refs[0] = "999"
			"height":
				for p: Dictionary in bad.patches:
					if p.field == "roads" and p.id == first.road_id: p.after.points[0][1] += 1
			"count": first.refs.append("3")
			"road": first.road_id = "missing"
			"endpoint":
				for p: Dictionary in bad.patches:
					if p.field == "roads" and p.id == first.road_id: p.after.from = p.after.to
			"node": bad.patches[0].after.position[0] += 1
			"type": first.source_range[0] = true
			"mapping": meta.retained.reverse()
		check(LAYER.new().load_value(bad,raw.layer_id) != "","forged loop rejected " + kind)
	await pointer(ui.import_review.get_ok_button())
	await wait_import(ui)
	check(ui.store.document.roads.size() == 8 and ui.store.undo_stack.size() == undo_count+1,"single atomic loop graph adoption: " + ui.status_label.text)
	check(ui.store.bridge.generate_chunk(1,1) == baseline_chunk,"adoption preserves loaded bridge")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before),"one Undo removes loop and approaches")
	check(ui.store.redo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(adopted),"one Redo restores graph and source metadata")
	check(FileAccess.get_sha256(path) == source_hash,"review/adoption/history preserve original PBF")
	check(ui.store.save_project(ProjectSettings.globalize_path("user://adopted")) == "","save loop graph")
	check(ui.store.autosave() == "","autosave loop graph")
	var reopened := STORE.new()
	check(reopened.open_project(ui.store.project_path) == "" and reopened.document == ui.store.document,"reopen exact geometry/provenance")
	check(reopened.recover(ui.store.recovery_path()) == "" and reopened.document == ui.store.document,"recover exact geometry/provenance")
	var derived := ProjectSettings.globalize_path("user://adopted.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(ui.store.project_path,derived)).ok,"export loop package")
	check(JSON.parse_string(reopened.bridge.open_package(derived)).ok,"open loop package")
	verify_surface(reopened,raw)
	# No datum is invented for estimated loops in later explicit-height imports.
	check(preload("res://scripts/import_vertical.gd").frame_error(ui.store.document,{"target_crs":"EPSG:3855 / EGM2008 metres","vertical_zero_m":100},{}) == "","estimated loop creates no false vertical lock")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"remove loop before repeated candidate checks")
	before = ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before,"cancelled loop publishes nothing")
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null and ui.pending_import.value.layer_id != raw.layer_id,"fresh loop namespace")
	ui.import_origin_x.value += 1
	ui.import_origin_x.value -= 1
	ui._adopt_import()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before,"changed/restored selection rejects stale loop")
	# Crop streams the complete ring and all original incident approaches first.
	ui.osm_panel.enabled.button_pressed = true
	ui.osm_panel.streaming.button_pressed = true
	for i in range(4): ui.osm_panel.fields[i].value = [9,55,9+100.0/64000,55+100.0/111000][i]
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import != null,"streamed loop crop native review: " + ui.status_label.text)
	if ui.pending_import != null:
		var cropped: Dictionary = ui.pending_import.value
		check(cropped.coordinates.osm_stream.structure_closure.loops == 1 and cropped.coordinates.osm_stream.structure_closure.ways == 3,"complete source loop incidence collected")
		check(cropped.coordinates.osm_crop.policy == "geometry-intersection-v1" and cropped.coordinates.osm_ground_loops.retained.size() == 4,"estimated ground crop source mappings")
		var bad := cropped.duplicate(true)
		bad.coordinates.osm_stream.structure_closure.structures = "bad"
		check(LAYER.new().load_value(bad,cropped.layer_id) != "","malformed closure counts fail without type error")
		ui._adopt_import()
		await wait_import(ui)
		check(ui.store.document.roads.size() == 4,"crop adopts connected original junction and independent cuts")
		check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before),"crop Undo is atomic")
	before = ui.store.document.duplicate(true)
	ui.osm_panel.enabled.button_pressed = false
	ui.osm_panel.streaming.button_pressed = false
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	var file := FileAccess.open(path,FileAccess.READ_WRITE)
	file.seek_end();file.store_8(0);file.close()
	ui._adopt_import()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before,"original source mutation rejects adoption")
	var collapsed := ProjectSettings.globalize_path("user://collapsed.pbf")
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_loops_fixture.py"),collapsed,"collapse"]),out,true) == 0,"synthetic quantization collapse")
	ui._start_import(collapsed,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == before,"native collapse rejects whole graph: " + ui.status_label.text)
	check(FileAccess.get_sha256(base+".memap") == package_hash and FileAccess.get_file_as_bytes(path).size() > 0,"baseline package/source retained")
	check(not DirAccess.dir_exists_absolute("user://authoring-candidates") or DirAccess.get_directories_at("user://authoring-candidates").is_empty(),"native loop scratch retired")
	await structural_loops(ui)
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("osm_loops_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)

func verify_surface(store: RefCounted, raw: Dictionary) -> void:
	var triangles: Array = []
	for x in [0,1]:
		for y in [0,1]:
			var generated: Dictionary = JSON.parse_string(store.bridge.generate_chunk(x,y))
			check(generated.ok,"actual loop cell generation %d/%d" % [x,y])
			if generated.ok: triangles.append_array(generated.data.chunk.triangles)
	for patch: Dictionary in raw.patches:
		if patch.field != "roads" or not patch.id.ends_with("-loop"): continue
		var p: Array = patch.after.points
		for end in [0,p.size()-1]:
			var next: int = 1 if end == 0 else end-1
			for fraction in [0.025,0.1,0.3,0.5]:
				var at := Vector2(p[end][0],p[end][2]).lerp(Vector2(p[next][0],p[next][2]),fraction)
				# Recipe 2 ground roads follow the actual flat terrain, not the
				# estimated source Y. Require an imported road surface, never grass.
				check(covers(triangles,at,0),"continuous loop/approach floor " + patch.id + " " + str(end) + " " + str(fraction))
func covers(triangles: Array, at: Vector2, height: float) -> bool:
	for t: Dictionary in triangles:
		if not t.spawnable or not t.object_id.ends_with("-loop"): continue
		var v: Array = t.vertices
		var a := Vector2(v[0][0],v[0][2]);var b := Vector2(v[1][0],v[1][2]);var c := Vector2(v[2][0],v[2][2])
		var area := (b-a).cross(c-a)
		if absf(area) < 0.1: continue
		var u := (b-at).cross(c-at)/area;var w := (c-at).cross(a-at)/area;var q := 1-u-w
		if minf(u,minf(w,q)) >= -0.00001 and absf(u*v[0][1]+w*v[1][1]+q*v[2][1]-height) <= 1: return true
	return false

func structural_loops(ui: Control) -> void:
	for mode: String in ["direct_bridge", "direct_tunnel", "closed_bridge", "closed_tunnel", "closed_join_bridge"]:
		var path := ProjectSettings.globalize_path("user://" + mode + ".pbf")
		var out: Array = []
		check(OS.execute(ui.import_python.text, PackedStringArray(["-B", ProjectSettings.globalize_path("res://tests/osm_loops_fixture.py"),path,mode]),out,true) == 0,"synthetic " + mode)
		var original := FileAccess.get_sha256(path)
		var before: Dictionary = ui.store.document.duplicate(true)
		ui._start_import(path,LAYER.OSM_LICENSE)
		await wait_import(ui)
		check(ui.pending_import != null,"native structural loop review " + mode + ": " + ui.status_label.text)
		if ui.pending_import == null: continue
		var raw: Dictionary = ui.pending_import.value.duplicate(true)
		check(raw.coordinates.osm_ground_loops.profile == "source-node-segments-v2","structural source-kind profile " + mode)
		if mode == "closed_bridge":
			var job := CancelGeneration.new()
			check(job.start_validation(ui.store,ui.pending_import,false,"structural-loop-test",path,Crypto.new().generate_random_bytes(16).hex_encode()) == "","start owned structural loop cancellation")
			var deadline := Time.get_ticks_msec()+15000
			while not job.done and Time.get_ticks_msec()<deadline:
				job.poll()
				await process_frame
			check(job.reached and job.done and job.exited and not job.result.ok,"structural loop generation cancellation reaps child")
			check(ui.store.document == before and not DirAccess.dir_exists_absolute(job.directory),"structural loop cancellation retains document and removes owned scratch")
			if not job.done: job.shutdown()
		for field: String in ["kind", "clearance_cm", "explicit_height"]:
			var bad := raw.duplicate(true)
			var meta: Dictionary = bad.coordinates.osm_ground_loops
			if field == "explicit_height":
				for source: Dictionary in meta.sources:
					if source.kind != "ground":
						for retained: Dictionary in meta.retained:
							if retained.source_way == source.way: retained.explicit_height = false
			else:
				for source: Dictionary in meta.sources:
					if source.kind != "ground": source[field] = "ground" if field == "kind" else 123
			check(LAYER.new().load_value(bad,raw.layer_id) != "","forged structural loop " + mode + ": " + field)
		ui._adopt_import()
		await wait_import(ui)
		check(ui.store.document.roads.size() == raw.feature_count,"atomic structural loop adoption " + mode + ": " + ui.status_label.text)
		if ui.store.document.roads.size() == raw.feature_count:
			var base := ProjectSettings.globalize_path("user://project-" + mode)
			check(ui.store.save_project(base) == "","save " + mode)
			check(JSON.parse_string(ui.store.bridge.export_project(base,base+".memap")).ok,"export " + mode)
			check(JSON.parse_string(ui.store.bridge.open_package(base+".memap")).ok,"open " + mode)
			var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
			check(generated.ok,"actual structural loop generation " + mode)
			var structural_floor := false
			var tunnel_ceiling := false
			if generated.ok:
				for triangle: Dictionary in generated.data.chunk.triangles:
					if not triangle.object_id.ends_with("-loop"): continue
					for point: Array in triangle.vertices:
						structural_floor = structural_floor or (triangle.spawnable and absf(point[1]) >= 500)
						tunnel_ceiling = tunnel_ceiling or (not triangle.spawnable and point[1] < 0)
			check(structural_floor,"native structural height retained " + mode)
			if mode.ends_with("tunnel"): check(tunnel_ceiling,"native loop tunnel ceiling " + mode)
			check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before),"atomic structural loop Undo " + mode)
			check(ui.store.redo() == "","structural loop Redo " + mode)
			check(ui.store.undo() == "","restore pre-loop document " + mode)
		check(FileAccess.get_sha256(path) == original,"structural loop original preserved " + mode)
		# Partial structural loops exercise crop-to-output IDs and retained ground
		# approach checks, with the full source validated before clipping.
		if mode.begins_with("closed"):
			ui.osm_panel.enabled.button_pressed = true
			ui.osm_panel.streaming.button_pressed = true
			for i in range(4): ui.osm_panel.fields[i].value = [9,55,9+100.0/64000,55+100.0/111000][i]
			ui._start_import(path,LAYER.OSM_LICENSE)
			await wait_import(ui)
			check(ui.pending_import != null,"native cropped structural loop " + mode + ": " + ui.status_label.text)
			if ui.pending_import != null:
				check(ui.pending_import.value.coordinates.osm_crop.policy == "geometry-intersection-v3","partial structural loop provenance " + mode)
				ui._adopt_import()
				await wait_import(ui)
				check(ui.store.document.roads.size() == 4,"partial structural loop atomic adoption " + mode + ": " + ui.status_label.text)
				check(ui.store.undo() == "","partial structural loop Undo " + mode)
			ui.osm_panel.enabled.button_pressed = false
			ui.osm_panel.streaming.button_pressed = false
