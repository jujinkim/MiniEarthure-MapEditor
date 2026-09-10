extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const HEIGHTS := preload("res://scripts/import_height_supplement.gd")
const NATIVE := preload("res://scripts/import_native_job.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func state() -> String: return JSON.stringify([ui.store.document,ui.store.undo_stack,ui.store.redo_stack,ui.store.history_bytes,ui.store.dirty])
func wait_job() -> void:
	var deadline := Time.get_ticks_msec()+20000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"height worker finished: "+ui.status_label.text)
func write(path: String, text: String) -> void:
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_string(text);file.close()
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate();root.add_child(ui)
	await process_frame
	check(ui.store.apply_command("Recipe 2",[{"field":"recipe_version","before":1,"after":2}]) == "","explicit structural recipe")
	ui.import_python.text=OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1);ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value=9.5;ui.import_origin_lat.value=55.5
	ui.import_origin_x.value=512;ui.import_origin_y.value=512
	var directory := ProjectSettings.globalize_path("user://")
	var output: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_heights_fixture.py"),directory]),output,true)==0,"synthetic missing node fixture: "+str(output))
	if not failures.is_empty(): await finish(); return
	var source := directory.path_join("source.pbf")
	var height_path := directory.path_join("heights.json")
	var heights := FileAccess.get_file_as_string(height_path)
	var hashes := {}
	for name in ["source.pbf","source.osm","heights.json","incomplete.json","correction.json"]:hashes[name]=FileAccess.get_sha256(directory.path_join(name))
	var project := directory.path_join("height-project")
	check(ui.store.save_project(project)=="","save isolated project")
	var prior := directory.path_join("prior.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,prior)).ok and JSON.parse_string(ui.store.bridge.open_package(prior)).ok,"prior package loaded")
	var prior_hash := FileAccess.get_sha256(prior)
	var bridge_before: String=ui.store.bridge.document_json()
	var before := state()
	var panel: RefCounted=ui.vertical_panel
	panel.target.select(1);panel.target.item_selected.emit(1);panel.zero.value=102
	panel.path.text=directory.path_join("correction.json")
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import==null and state()==before,"missing heights still reject without explicit supplement")
	panel.supplement_path.text=directory.path_join("missing.json")
	ui._start_import(source,LAYER.OSM_LICENSE)
	check(not ui.busy and ui.pending_import==null and state()==before,"missing supplemental file rejects before worker")
	panel.supplement_path.text=directory.path_join("incomplete.json")
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import==null and state()==before,"incomplete source/approach profile rejects atomically")
	panel.supplement_path.text=height_path
	panel.open();await process_frame
	check(panel.dialog.visible and panel.dialog.size.x<=root.size.x and panel.dialog.size.y<=root.size.y,"height form fits minimum window: "+str(panel.dialog.size))
	if DisplayServer.get_name()!="headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH")!="":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")+".heights.png")==OK,"capture supplemental selection")
	panel.dialog.hide()
	check(HEIGHTS.source_error("malformed")!="","malformed JSON returns an error without engine diagnostics")
	check(HEIGHTS.source_error(heights)=="","strict source accepts quoted braces in provenance")
	check(not HEIGHTS.unique_keys('{"source":1,"so\\u0075rce":2}'),"escaped duplicate keys rejected")
	check(HEIGHTS.source_error(heights.replace('"format":','"format":"duplicate", "format":'))!="","duplicate source keys rejected")
	var parsed: Dictionary=JSON.parse_string(heights)
	for kind in ["datum","height","numeric-id","duplicate-id","id-range","empty","extra"]:
		var bad: Dictionary=parsed.duplicate(true)
		match kind:
			"datum":bad.vertical_crs="EPSG:3855 / EGM2008 metres"
			"height":bad.nodes[0].height_m=true
			"numeric-id":bad.nodes[0].node_id=1
			"duplicate-id":bad.nodes.append(bad.nodes[0])
			"id-range":bad.nodes[0].node_id="9223372036854775808"
			"empty":bad.nodes=[]
			"extra":bad.extra="unsupported"
		check(HEIGHTS.source_error(JSON.stringify(bad))!="","invalid supplement selection: "+kind)
	check(HEIGHTS.source_error(" ".repeat(HEIGHTS.MAX_BYTES+1))!="","source byte cap")
	ui._start_import(source,LAYER.OSM_LICENSE)
	write(height_path,"changed externally after capture")
	await wait_job()
	check(ui.pending_import!=null,"supplemented native review: "+ui.status_label.text)
	if ui.pending_import==null:write(height_path,heights);await finish();return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(state()==before and ui.store.bridge.document_json()==bridge_before,"review preserves document/history/loaded bridge")
	check(raw.coordinates.osm_height_supplement.source.json==heights and raw.coordinates.osm_height_supplement.applied_nodes==7,"immutable supplement snapshot and complete application count")
	check(ui.import_summary.text.contains("Local height supplement") and ui.import_summary.text.contains("CC0 synthetic fixture") and ui.import_summary.text.contains("not independently verified") and ui.import_summary.text.contains(hashes["heights.json"]),"supplement source/license/accuracy/hash reviewed")
	check(LAYER.new().load_value(raw,ui.import_identity)=="","stored supplemental provenance reads without current request")
	for kind in ["missing","null","hash","bytes","osm-hash","count","profile","order","changed-request","unrequested"]:
		var bad: Dictionary=raw.duplicate(true)
		var requested: Dictionary=ui.import_coordinates_request.duplicate(true)
		match kind:
			"missing":bad.coordinates.erase("osm_height_supplement")
			"null":bad.coordinates.osm_height_supplement=null
			"hash":bad.coordinates.osm_height_supplement.source.sha256="0".repeat(64)
			"bytes":bad.coordinates.osm_height_supplement.source.bytes=1
			"osm-hash":bad.source.sha256="0".repeat(64)
			"count":bad.coordinates.osm_height_supplement.applied_nodes=1
			"profile":bad.coordinates.osm_height_supplement.profile="inferred"
			"order":bad.coordinates.osm_height_supplement.order="after crop"
			"changed-request":requested.height_supplement="{}"
			"unrequested":requested.erase("height_supplement")
		check(LAYER.new().load_value(bad,ui.import_identity,requested)!="","forged supplemental provenance: "+kind)
	ui._adopt_import();await wait_job()
	check(ui.store.document.roads.size()==6,"atomic supplemental graph adoption using captured bytes")
	write(height_path,heights)
	if ui.store.document.roads.size()!=6:await finish();return
	check(ui.store.document.roads[1].points[2][1]==600 and ui.store.document.roads[4].points[2][1]==-600 and ui.store.document.roads[4].clearance_cm==450,"missing and original heights use H96+delta-zero; physical clearance preserved")
	var adopted: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.document.attributions.back().notice.contains(hashes["heights.json"]),"exact supplemental provenance saved in attribution")
	check(ui.store.undo()=="" and ui.store.document.roads.is_empty(),"single Undo removes supplemental layer")
	check(ui.store.redo()=="" and ui.store.document==adopted,"Redo restores exact supplemental graph")
	check(ui.store.save_project(project)=="","save supplemental project")
	var pack := directory.path_join("supplemented.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,pack)).ok and JSON.parse_string(ui.store.bridge.open_package(pack)).ok,"export/reopen supplemented package")
	var generated: Dictionary=JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"actual supplemented native terrain/deck/tunnel: "+str(generated.get("error")))
	if generated.ok:
		var found := {}
		for triangle: Dictionary in generated.data.chunk.triangles:
			for point: Array in triangle.vertices:found[int(point[1])]=true
		check(found.has(600) and found.has(-600) and found.has(-150),"generated deck/floor/ceiling elevations")
	var reopened := preload("res://scripts/document_store.gd").new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==adopted.attributions,"reopen keeps exact supplement source bytes")
	before=state();bridge_before=ui.store.bridge.document_json()
	ui._start_import(source,LAYER.OSM_LICENSE)
	var old: RefCounted=ui.import_job
	panel.supplement_path.text="";panel.changed();panel.supplement_path.text=height_path;panel.changed()
	await wait_job()
	check(old.cancelled and ui.pending_import==null and state()==before,"restored supplement selection cancels Python worker and invalidates generation")
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import!=null,"retry supplemental review")
	panel.supplement_path.text="";panel.changed();panel.supplement_path.text=height_path;panel.changed()
	ui._adopt_import();await wait_job()
	check(ui.pending_import==null and state()==before,"restored selection cannot adopt old review")
	ui._start_import(source,LAYER.OSM_LICENSE)
	var deadline := Time.get_ticks_msec()+20000
	while ui.busy and not ui.import_job is NATIVE and Time.get_ticks_msec()<deadline:await process_frame
	check(ui.busy and ui.import_job is NATIVE,"supplement reaches asynchronous native validation")
	if ui.busy and ui.import_job is NATIVE:
		old=ui.import_job
		panel.supplement_path.text="";panel.changed();panel.supplement_path.text=height_path;panel.changed()
		await wait_job()
		check(old.cancelled and old.exited and not DirAccess.dir_exists_absolute(old.directory) and ui.pending_import==null and state()==before,"native cancellation retires owned work and preserves accepted map")
	# Partial stream retains complete original supplement even when source nodes crop out.
	ui.osm_panel.enabled.button_pressed=true;ui.osm_panel.streaming.button_pressed=true
	var bbox := [9.5007,55.5,9.5017,55.502]
	for i in range(4):ui.osm_panel.fields[i].value=bbox[i]
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import!=null and state()==before,"stream crop with full original supplemental heights: "+ui.status_label.text)
	if ui.pending_import!=null:
		check(ui.pending_import.value.coordinates.osm_crop.policy=="geometry-intersection-v3" and ui.pending_import.value.coordinates.osm_height_supplement.source.json==heights,"crop keeps original supplement snapshot")
	ui._discard_import()
	check(ui.store.bridge.document_json()==bridge_before,"rejected/cancelled/review candidates preserve loaded bridge")
	for name: String in hashes:check(FileAccess.get_sha256(directory.path_join(name))==hashes[name],"original preserved: "+name)
	check(FileAccess.get_sha256(prior)==prior_hash,"prior package bytes preserved")
	await finish()
func finish() -> void:
	ui.store.dirty=false;ui.queue_free();await process_frame
	print("osm_heights_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
