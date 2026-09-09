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
	var deadline := Time.get_ticks_msec()+30000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"DEM mosaic child completed; "+ui.validation_label.text)
func run() -> void:
	root.size=Vector2i(1024,720)
	ui=load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	check(ui.store.apply_command("four-cell synthetic map",[{"field":"bounds","before":ui.store.document.bounds.duplicate(true),"after":{"min":[0,0],"max":[102400,102400]}}])=="","fixture bounds")
	var project := ProjectSettings.globalize_path("user://mosaic-project")
	check(ui.store.save_project(project)=="","save isolated mosaic project")
	var folder := ProjectSettings.globalize_path("user://synthetic-cogs")
	var output: Array=[]
	var python := OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	check(OS.execute(python,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/dem_fixture.py"),folder,"mosaic"]),output,true)==0,"create synthetic mosaic: "+str(output))
	ui.import_python.text=python
	var panel: ConfirmationDialog=ui.dem_panel
	panel.mosaic.button_pressed=true
	panel.source.text=folder
	panel.fields.Longitude.value=9.997
	panel.fields.Latitude.value=54.997
	panel.fields["Cell columns"].value=2
	panel.fields["Cell rows"].value=2
	panel.open()
	await process_frame
	check(panel.size.x<=1024 and panel.size.y<=720,"mosaic form fits 1024x720: "+str(panel.size))
	if DisplayServer.get_name()!="headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH")!="":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")+".mosaic.form.png")==OK,"capture mosaic form")
	var before := state()
	panel.prepare();await wait_job()
	check(not panel.plan.is_empty(),"four-source review: "+ui.validation_label.text)
	if panel.plan.is_empty(): ui.queue_free();await process_frame;quit(1);return
	check(panel.plan.sources.size()==4 and panel.plan.cells.size()==4,"review includes every source/cell")
	check(state()==before,"source review non-mutating")
	panel.acquire();await wait_job()
	check(panel.candidate!=null,"whole-mosaic native staging: "+ui.validation_label.text)
	if panel.candidate==null: ui.queue_free();await process_frame;quit(1);return
	var receipt: Dictionary=panel.candidate.value.dem.receipt.duplicate(true)
	var sampling: Dictionary=panel.candidate.value.dem.sampling.duplicate(true)
	var reviewed: Dictionary=panel.plan.duplicate(true)
	var destination: String=panel.destination
	var result := {"review":receipt,"raster":sampling,"outputs":[]}
	for index in range(4):
		var path := destination+".cell-%d.png" % index
		result.outputs.append({"cell":reviewed.cells[index],"png_path":path,"png_sha256":FileAccess.get_sha256(path),"png_bytes":FileAccess.get_file_as_bytes(path).size()})
	check(state()==before,"capture/staging leaves document and history unchanged")
	check(panel.review.visible and panel.review_text.text.contains("atomically"),"explicit complete-mosaic review")
	if DisplayServer.get_name()!="headless" and OS.get_environment("MAPEDITOR_CAPTURE_PATH")!="":
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH")+".mosaic.png")==OK,"capture mosaic review")
	panel.discard()
	var layer := DEM.new()
	var bad := result.duplicate(true)
	bad.outputs.pop_back()
	check(layer.stage_dem(ui.canvas.author.terrain,bad,reviewed,destination)!="" and state()==before,"partial output cannot adopt")
	bad=result.duplicate(true);bad.outputs[3].cell=bad.outputs[0].cell
	check(layer.stage_dem(ui.canvas.author.terrain,bad,reviewed,destination)!="" and state()==before,"duplicate cell cannot adopt")
	bad=result.duplicate(true);bad.outputs[3].png_sha256="0".repeat(64)
	check(layer.stage_dem(ui.canvas.author.terrain,bad,reviewed,destination)!="" and state()==before,"last-cell hash failure preserves every cell")
	check(ui.store.apply_command("outside flat neighbor",[{"field":"bounds","before":ui.store.document.bounds.duplicate(true),"after":{"min":[0,0],"max":[153600,102400]}}])=="","extend fixture to outside neighbor")
	before=state()
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,destination).contains("E_SEAM") and state()==before,"outside seam failure rejects all cells without repair")
	check(ui.store.undo()=="","restore fixture bounds")
	before=state()
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,destination)=="","restage complete mosaic")
	check(layer.adopt(ui.canvas.author.terrain)=="" and ui.store.document.heightmaps.size()==4 and ui.store.document.attributions.size()==1,"all four cells and one provenance command adopted")
	check(layer.adopt(ui.canvas.author.terrain)!="","mosaic one-shot adoption")
	var first: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.heightmaps.is_empty() and ui.store.document.attributions.is_empty(),"single Undo removes entire mosaic")
	check(ui.store.redo()=="" and ui.store.document==first,"single Redo restores entire mosaic")
	check(ui.store.save_project(project)=="","save mosaic")
	var package := ProjectSettings.globalize_path("user://mosaic.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok,"native mosaic export")
	var sha := FileAccess.get_sha256(package)
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,destination)=="","same-source reimport stage")
	check(layer.value.previous.size()==4 and layer.adopt(ui.canvas.author.terrain)=="" and ui.store.document.attributions.size()==2,"new source layer retains previous four descriptors")
	check(ui.store.undo()=="" and ui.store.document==first,"reimport Undo restores all old references")
	check(FileAccess.get_sha256(package)==sha,"existing package preserved")
	check(layer.stage_dem(ui.canvas.author.terrain,result,reviewed,destination)=="","stage before generation change")
	ui.store.redo();ui.store.undo();before=state()
	check(layer.adopt(ui.canvas.author.terrain).contains("Stale") and state()==before,"undo/redo invalidates pending mosaic")
	check(ui.store.save_project(project)=="" and ui.store.autosave()=="","persist mosaic and recovery")
	var reopened := STORE.new()
	check(reopened.open_project(project)=="" and reopened.document==ui.store.document,"reopen all cells/provenance")
	check(reopened.recover(ui.store.recovery_path())=="","recover mosaic")
	panel.prepare()
	var cancelled: RefCounted=ui.import_job
	panel.fields["Cell columns"].value=1
	panel.fields["Cell columns"].value=2
	await wait_job()
	check(cancelled.cancelled and panel.plan.is_empty() and panel.candidate==null and state()==before,"changed-then-restored selection rejects late result")
	panel.prepare();await wait_job()
	panel.acquire()
	var timed: RefCounted=ui.import_job
	timed.poll(timed.deadline_ms)
	await wait_job()
	check(timed.cancelled and panel.candidate==null and state()==before,"deadline preserves complete document")
	panel.prepare()
	var owned: RefCounted=ui.import_job
	ui.store.dirty=false
	ui.queue_free();await process_frame
	check(owned.cancelled and owned.pid==-1,"close reaps mosaic child")
	print("dem_mosaic_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)
