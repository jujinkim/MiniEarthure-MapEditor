extends SceneTree
const DEM := preload("res://scripts/dem_import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func state() -> String: return JSON.stringify([ui.store.document,ui.store.undo_stack,ui.store.redo_stack,ui.store.history_bytes,ui.store.dirty])
func wait_job() -> void:
	var deadline := Time.get_ticks_msec()+20000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"DEM child completed; status="+ui.validation_label.text)
func fixture(path: String, bias: int = 0) -> void:
	var output: Array = []
	var python := OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	check(OS.execute(python,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/dem_fixture.py"),path,str(bias)]),output,true)==0,"create synthetic COG: "+str(output))
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	check(ui.store.apply_command("single-cell synthetic map",[{"field":"bounds","before":ui.store.document.bounds.duplicate(true),"after":{"min":[0,0],"max":[51200,51200]}}])=="","single-cell fixture bounds")
	var project := ProjectSettings.globalize_path("user://dem-project")
	check(ui.store.save_project(project)=="","save isolated DEM project")
	var source := ProjectSettings.globalize_path("user://original-synthetic.tif")
	fixture(source)
	var source_sha := FileAccess.get_sha256(source)
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var panel: ConfirmationDialog = ui.dem_panel
	panel.source.text = source
	panel.fields.Longitude.value = 9.5
	panel.fields.Latitude.value = 55.5
	panel.open()
	await process_frame
	check(panel.visible and panel.size.x<=root.size.x and panel.size.y<=root.size.y,"DEM form fits 1024x720: "+str(panel.size))
	if DisplayServer.get_name() != "headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH") != "":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")+".form.png")==OK,"capture DEM form")
	var before := state()
	panel.prepare()
	await wait_job()
	check(not panel.plan.is_empty() and not panel.get_ok_button().disabled,"local source size/projection review: "+ui.validation_label.text)
	if panel.plan.is_empty():
		ui.queue_free();await process_frame;quit(1);return
	check(panel.plan.source.sha256 == source_sha and panel.summary.text.contains("EGM2008") and panel.summary.text.contains("source accuracy"),"review source identity, vertical reference and accuracy")
	check(state()==before,"review leaves document and history unchanged")
	panel.get_ok_button().pressed.emit()
	await wait_job()
	check(panel.candidate != null and panel.review.visible,"native validates sampled DEM for explicit review: "+ui.validation_label.text)
	if panel.candidate == null:
		ui.queue_free();await process_frame;quit(1);return
	var receipt: Dictionary = panel.candidate.value.dem.receipt.duplicate(true)
	var first_id: String = panel.candidate.value.layer_id
	var first_destination: String = panel.destination
	var first_png := first_destination+".png"
	var raster: Dictionary = panel.candidate.value.dem.sampling.duplicate(true)
	var result := {"review":receipt,"raster":raster,"png_path":first_png,"png_sha256":FileAccess.get_sha256(first_png),"png_bytes":FileAccess.get_file_as_bytes(first_png).size()}
	var reviewed: Dictionary = panel.plan.duplicate(true)
	check(state()==before and FileAccess.get_sha256(first_destination)==source_sha,"capture and native staging preserve original document/source")
	check(panel.review_text.text.contains("explicit bilinear") and panel.review_text.text.contains("DSM") and panel.review.size.y<=root.size.y,"sampling review and minimum window")
	if DisplayServer.get_name() != "headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH") != "":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH"))==OK,"capture DEM review")
	panel.review.canceled.emit()
	check(panel.candidate==null and state()==before and FileAccess.file_exists(first_destination),"discard preserves completed COG and project")
	# Reuse immutable capture for boundary checks; no repeated acquisition required.
	var layer := DEM.new()
	for malformed in [null, [], "invalid"]:
		var malformed_review: Dictionary = reviewed.duplicate(true)
		malformed_review.options.coordinates = malformed
		check(layer.stage_dem(ui.canvas.author.terrain,result,malformed_review,first_destination)!="" and state()==before,"malformed DEM frame rejects without script error")
	var bad := result.duplicate(true)
	bad.review.vertical_crs = "ellipsoidal"
	check(layer.stage_dem(ui.canvas.author.terrain,bad,reviewed,first_destination)!="" and state()==before,"forged vertical/source contract rejected")
	bad=result.duplicate(true);bad.png_sha256="0".repeat(64)
	check(layer.stage_dem(ui.canvas.author.terrain,bad,reviewed,first_destination)!="","changed derived PNG rejected")
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,first_destination)=="","restage immutable candidate")
	check(layer.value.layer_id != first_id,"fresh DEM layer identity")
	check(layer.adopt(ui.canvas.author.terrain)=="" and ui.store.document.heightmaps.size()==1,"adopt one active terrain cell")
	check(layer.adopt(ui.canvas.author.terrain)!="","one-shot adoption")
	var first: Dictionary = ui.store.document.heightmaps[0].duplicate(true)
	check(ui.store.document.attributions[0].notice.contains(source_sha),"original COG hash survives native attribution")
	check(ui.store.undo()=="" and ui.store.document.heightmaps.is_empty(),"atomic geometry/notice undo")
	check(ui.store.redo()=="" and ui.store.document.heightmaps[0]==first,"redo restores file and descriptor")
	check(ui.store.save_project(project)=="","save imported terrain")
	var output := ProjectSettings.globalize_path("user://retained.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,output)).ok,"package DEM with shared native geometry")
	var package_sha := FileAccess.get_sha256(output)
	fixture(source,2)
	panel.prepare();await wait_job();panel.acquire();await wait_job()
	check(panel.candidate != null,"changed source stages new layer")
	if panel.candidate != null:
		check(panel.candidate.value.previous==first,"review previous active terrain")
		panel.review.confirmed.emit()
	check(ui.store.document.attributions.size()==2 and ui.store.document.heightmaps.size()==1,"UI explicit reimport keeps both notices and one active tile")
	check(ui.store.undo()=="" and ui.store.document.heightmaps[0]==first,"reimport Undo selects original")
	check(ui.store.redo()=="" and FileAccess.get_sha256(output)==package_sha and FileAccess.get_sha256(first_destination)==source_sha,"redo preserves original package/capture")
	check(ui.store.save_project(project)=="" and ui.store.autosave()=="","save and recovery DEM metadata")
	var reopened := STORE.new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==ui.store.document.attributions,"reopen exact provenance")
	check(reopened.recover(ui.store.recovery_path())=="","recover imported DEM")
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,first_destination)=="","stage before stale generation")
	ui.store.undo();ui.store.redo()
	before=state()
	check(layer.adopt(ui.canvas.author.terrain).contains("Stale") and state()==before,"undo/redo generation makes pending DEM stale")
	panel.prepare()
	var cancelled: RefCounted = ui.import_job
	panel.invalidate()
	await wait_job()
	check(cancelled.cancelled and state()==before and panel.plan.is_empty(),"cancel kills owned child; no stale plan/adoption")
	panel.prepare();await wait_job()
	check(not panel.plan.is_empty(),"fresh retry after cancellation")
	panel.acquire()
	var old: RefCounted = ui.import_job
	panel.fields.Longitude.value=9.6
	await wait_job()
	check(old.cancelled and panel.candidate==null and state()==before,"changed coordinates cancel old acquisition and preserve map")
	# Changed source after review is a hard rejection, never a new implicit snapshot.
	panel.fields.Longitude.value=9.5
	panel.prepare();await wait_job()
	fixture(source,3)
	panel.acquire();await wait_job()
	check(panel.candidate==null and state()==before,"changed source since review rejects without mutation")
	panel.prepare()
	var timed: RefCounted = ui.import_job
	timed.poll(timed.deadline_ms)
	await wait_job()
	check(timed.cancelled and state()==before,"deadline cancels DEM child")
	panel.prepare()
	var owned: RefCounted = ui.import_job
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.cancelled and owned.pid==-1,"owner close reaps DEM helper")
	print("dem_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)
