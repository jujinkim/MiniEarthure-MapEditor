extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const VERTICAL := preload("res://scripts/import_vertical.gd")
const STORE := preload("res://scripts/document_store.gd")
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
	check(not ui.busy,"vertical worker finished: "+ui.status_label.text)
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	check(ui.store.apply_command("Choose connected road recipe",[{"field":"recipe_version","before":1,"after":2}]) == "","explicit recipe 2 selection")
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var directory := ProjectSettings.globalize_path("user://")
	var output: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/vertical_fixture.py"),directory]),output,true)==0,"synthetic local height/DEM fixtures: "+str(output))
	var grid_path := directory.path_join("correction.json")
	var source := directory.path_join("source.osm.pbf")
	var original_grid := FileAccess.get_file_as_string(grid_path)
	var hashes := {}
	for name in ["correction.json","source.osm","source.osm.pbf","terrain.tif"]: hashes[name] = FileAccess.get_sha256(directory.path_join(name))
	var project := directory.path_join("vertical-project")
	check(ui.store.save_project(project)=="","save isolated project")
	# Sample an actual synthetic EGM2008 DEM: 102m at datum, zero=102 -> flat local 0.
	var dem: ConfirmationDialog = ui.dem_panel
	dem.fields.Longitude.value=9.5
	dem.fields.Latitude.value=55.5
	dem.fields["Local origin x (m)"].value=512
	dem.fields["Local origin y (m)"].value=512
	dem.fields["Cell x"].value=1
	dem.fields["Cell y"].value=1
	dem.fields["EGM2008 at local zero (m)"].value=102
	dem.source.text=directory.path_join("terrain.tif")
	dem.prepare(); await wait_job()
	check(not dem.plan.is_empty(),"DEM plan: "+ui.status_label.text)
	if dem.plan.is_empty(): await finish(); return
	dem.acquire(); await wait_job()
	check(dem.candidate != null,"DEM native candidate: "+ui.status_label.text)
	if dem.candidate == null: await finish(); return
	dem.adopt()
	check(ui.store.document.heightmaps.size()==1,"actual terrain adopted")
	var before := state()
	ui.import_source_format.select(1);ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value=9.5;ui.import_origin_lat.value=55.5
	ui.import_origin_x.value=512;ui.import_origin_y.value=512
	# Legacy EGM96 and different zeros cannot silently mix with active DEM.
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import == null and ui.status_label.text.contains("Vertical frame conflicts") and state()==before,"EGM96 / EGM2008 mismatch rejected atomically; status="+ui.status_label.text+" preserved="+str(state()==before))
	var panel: RefCounted = ui.vertical_panel
	panel.target.select(1);panel.target.item_selected.emit(1)
	panel.zero.value=102
	panel.path.text=grid_path
	panel.open();await process_frame
	check(panel.dialog.visible and panel.dialog.size.x <= root.size.x and panel.dialog.size.y <= root.size.y,"height dialog fits minimum window: "+str(panel.dialog.size)+" root="+str(root.size))
	if DisplayServer.get_name() != "headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH") != "":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")+".vertical.png")==OK,"capture height reference form")
	panel.dialog.hide()
	panel.path.text=directory.path_join("missing.json")
	ui._start_import(source,LAYER.OSM_LICENSE)
	check(not ui.busy and ui.pending_import == null and state()==before,"missing grid rejects before starting worker")
	panel.path.text=grid_path
	panel.zero.value=101
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import == null and ui.status_label.text.contains("Vertical frame conflicts") and state()==before,"different local zero rejected")
	panel.zero.value=102
	ui._start_import(source,LAYER.OSM_LICENSE)
	# Snapshot ownership: changes to the external file after capture cannot change this request.
	var file := FileAccess.open(grid_path,FileAccess.WRITE);file.store_string("changed externally");file.close()
	await wait_job()
	check(ui.pending_import != null,"converted native review: "+ui.status_label.text)
	if ui.pending_import == null: await finish(); return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.coordinates.vertical.grid_source.json == original_grid and state()==before,"exact captured grid survives external file change without adoption")
	check(VERTICAL.validate(raw,{})=="","stored vertical provenance can be read without a live request")
	var null_metadata := raw.duplicate(true)
	null_metadata.coordinates.vertical = null
	check(LAYER.new().load_value(null_metadata,ui.import_identity)!="","null vertical metadata rejected without a live request")
	file=FileAccess.open(grid_path,FileAccess.WRITE);file.store_string(original_grid);file.close()
	check(ui.import_summary.text.contains("EGM2008") and ui.import_summary.text.contains("102") and ui.import_summary.text.contains("CC0 synthetic fixture") and ui.import_summary.text.contains("not independently verified") and ui.import_summary.text.contains(hashes["correction.json"]),"datum/zero/hash/license/accuracy are reviewed")
	for kind in ["missing","datum","zero","hash","bytes","grid","method","order","counts","range"]:
		var bad := raw.duplicate(true)
		match kind:
			"missing": bad.coordinates.erase("vertical")
			"datum": bad.coordinates.vertical.target_crs=VERTICAL.CRS.EGM96
			"zero": bad.coordinates.vertical.vertical_zero_m=101
			"hash": bad.coordinates.vertical.grid_source.sha256="0".repeat(64)
			"bytes": bad.coordinates.vertical.grid_source.bytes=1
			"grid": bad.coordinates.vertical.grid_source.json="{}"
			"method": bad.coordinates.vertical.method="guess"
			"order": bad.coordinates.vertical.order="after crop"
			"counts": bad.coordinates.vertical.explicit_points=1
			"range": bad.coordinates.vertical.delta_range_m=[4,2]
		check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request)!="","forged vertical metadata rejected: "+kind)
	ui._adopt_import()
	await wait_job()
	check(ui.store.document.roads.size()==6,"atomic converted graph adoption")
	if ui.store.document.roads.size()!=6: await finish(); return
	check(ui.store.document.roads[1].points[2][1]==600 and ui.store.document.roads[4].points[2][1]==-600 and ui.store.document.roads[4].clearance_cm==450,"H96+delta-zero and unchanged physical clearance")
	check(ui.store.document.attributions.back().notice.contains(hashes["correction.json"]),"correction provenance retained")
	var adopted: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.roads.is_empty() and ui.store.document.heightmaps.size()==1,"one Undo keeps terrain and removes vector layer")
	check(ui.store.redo()=="" and ui.store.document==adopted,"Redo restores exact graph/provenance")
	check(ui.store.save_project(project)=="","save aligned project")
	var package := directory.path_join("aligned.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok,"build aligned DEM/structure package")
	var package_hash := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok,"reopen aligned package")
	var generated: Dictionary=JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"native terrain/apron/deck/tunnel generation: "+str(generated.get("error")))
	if generated.ok:
		var heights := {}
		for triangle: Dictionary in generated.data.chunk.triangles:
			for point: Array in triangle.vertices: heights[int(point[1])]=true
		check(heights.has(600) and heights.has(-600) and heights.has(-150),"actual converted deck, floor and ceiling")
	var reopened := STORE.new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==adopted.attributions,"project reopen preserves exact correction bytes")
	# Conflicting frame rejected in either import direction and after loading legacy OSM notices.
	var fake_doc := adopted.duplicate(true)
	fake_doc.heightmaps=[]
	check(VERTICAL.frame_error(fake_doc,{"target_crs":VERTICAL.CRS.EGM2008,"vertical_zero_m":101},dem.options().coordinates).contains("Vertical frame conflicts"),"DEM direction checks active OSM")
	var legacy: Dictionary=JSON.parse_string(fake_doc.attributions.back().notice)
	legacy.coordinates.erase("vertical")
	fake_doc.attributions.back().notice=JSON.stringify(legacy)
	check(VERTICAL.frame_error(fake_doc,{"target_crs":VERTICAL.CRS.EGM2008,"vertical_zero_m":102},dem.options().coordinates).contains("Vertical frame conflicts"),"legacy explicit OSM is EGM96 zero")
	fake_doc.nodes=[]
	check(VERTICAL.frame_error(fake_doc,{"target_crs":VERTICAL.CRS.EGM2008,"vertical_zero_m":102},dem.options().coordinates)=="","inactive historical notices do not lock frame")
	# Same PNG bytes do not imply the same active heightmap (offset, spacing, cell).
	fake_doc=adopted.duplicate(true)
	fake_doc.nodes=[]
	fake_doc.heightmaps[0].offset_cm+=1
	check(VERTICAL.frame_error(fake_doc,{"target_crs":VERTICAL.CRS.EGM96,"vertical_zero_m":0},dem.options().coordinates)=="","inactive DEM descriptor with a reused PNG does not lock frame")
	fake_doc=adopted.duplicate(true)
	var changed_origin: Dictionary=dem.options().coordinates.duplicate(true)
	changed_origin.origin[0]+=0.000001
	check(VERTICAL.frame_error(fake_doc,{"target_crs":VERTICAL.CRS.EGM2008,"vertical_zero_m":102},changed_origin).contains("Projection origin conflicts"),"horizontal origin mismatch rejects height alignment")
	before=state()
	dem.fields["EGM2008 at local zero (m)"].value=101
	dem.prepare();await wait_job();dem.acquire();await wait_job()
	check(dem.candidate==null and ui.status_label.text.contains("Vertical frame conflicts") and state()==before,"actual conflicting DEM import preserves roads and terrain")
	dem.fields["EGM2008 at local zero (m)"].value=102
	ui._start_import(source,LAYER.OSM_LICENSE)
	var owned: RefCounted=ui.import_job
	panel.zero.value=101;panel.zero.value=102
	await wait_job()
	check(owned.cancelled and ui.pending_import==null and state()==before,"restored selection still invalidates old generation and cancels child")
	ui._start_import(source,LAYER.OSM_LICENSE);ui._cancel_operation();await wait_job()
	check(ui.pending_import==null and state()==before,"cancel preserves graph and DEM")
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import!=null,"fresh retry")
	panel.zero.value=101;panel.zero.value=102
	ui._adopt_import()
	await wait_job()
	check(ui.pending_import==null and state()==before,"changed review selection cannot adopt after restoration")
	# Streaming also uses the same captured correction and target-height crop.
	ui.osm_panel.enabled.button_pressed=true
	ui.osm_panel.streaming.button_pressed=true
	var bbox := [9.5007,55.5,9.5017,55.502]
	for i in range(4):ui.osm_panel.fields[i].value=bbox[i]
	ui._start_import(source,LAYER.OSM_LICENSE);await wait_job()
	check(ui.pending_import!=null and state()==before,"streaming converted partial structures native review: "+ui.status_label.text)
	if ui.pending_import!=null:
		check(ui.pending_import.value.coordinates.osm_crop.policy=="geometry-intersection-v3" and ui.pending_import.value.coordinates.vertical.grid_source.json==original_grid,"streaming crop retains source correction")
	ui._discard_import()
	for name: String in hashes:check(FileAccess.get_sha256(directory.path_join(name))==hashes[name],"original preserved: "+name)
	check(FileAccess.get_sha256(package)==package_hash,"prior package preserved through rejection/cancel/retry")
	await finish()

func finish() -> void:
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("vertical_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
