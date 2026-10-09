extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const TERRAIN := preload("res://scripts/terrain_tools.gd")
const FILES := preload("res://scripts/document_files.gd")
const WORK := preload("res://scripts/package_work.gd")
var checks := 0
var failures: Array[String] = []
class CompletedWater extends RefCounted:
	var result: Array = []
	func is_alive() -> bool: return false
	func finish() -> Dictionary: return {"ok":true,"data":result}
class CountingFiles extends FILES:
	var writes := 0
	var fail := false
	var delegate := preload("res://scripts/document_files.gd").new()
	func digest(path: String) -> String: return delegate.digest(path)
	func read_json(path: String) -> Dictionary: return delegate.read_json(path)
	func write(path: String,text: String,expected: String) -> String:
		writes += 1
		return "Injected save failure" if fail else delegate.write(path,text,expected)
func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)
func _initialize() -> void: run.call_deferred()
func height(store: RefCounted, p := Vector2(3200,3200)) -> int:
	var result: Dictionary = JSON.parse_string(store.working_snapshot().height(p))
	check(result.ok,"height query")
	return int(result.data.height) if result.ok else -999999
func settle(store: RefCounted) -> void:
	var deadline := Time.get_ticks_msec()+10000
	while (store.water_job != null or not store.file_request.is_empty()) and Time.get_ticks_msec()<deadline:
		store.poll_water(); store.poll_file_operation(); await process_frame
	check(store.water_job == null and store.file_request.is_empty(),"workers settle")
func run() -> void:
	var store := STORE.new();store.new_document()
	var file_results: Array[Dictionary] = []
	store.file_operation_finished.connect(func(result: Dictionary): file_results.append(result))
	store.document.bounds.max = [6400,6400];store.document.cell_size_cm = 3200
	var writer := CountingFiles.new();store.files = writer
	var terrain := TERRAIN.new();terrain.store = store
	var before_files := DirAccess.get_directories_at("user://")
	var opts := {"mode":"raise","radius_cm":1600,"rate_cm_s":200}
	check(terrain.begin(Vector2(3200,3200),opts)=="","unsaved brush begins")
	var times: Array[float] = []
	for i in 60:
		var began := Time.get_ticks_usec()
		check(terrain.step(Vector2(3200,3200),1.0/60)=="","timed brush step")
		times.append((Time.get_ticks_usec()-began)/1000.0)
	terrain.last_usec = Time.get_ticks_usec()
	check(terrain.finish()=="" and store.undo_stack.size()==1,"release creates one memory command")
	check(height(store)>=200 and height(store)<=201,"time based height")
	check(writer.writes==0 and DirAccess.get_directories_at("user://")==before_files,"brush and finish perform zero map writes")
	var raised := height(store)
	check(store.undo()=="" and height(store)==0,"sparse height undo")
	check(store.redo()=="" and height(store)==raised,"sparse height redo")
	var job := WORK.new();job.working = store.working_snapshot().fork()
	var preview: Dictionary = job.run(store.document,"","preview",Vector2i.ZERO,{},false)
	check(preview.ok,"unsaved preview: "+str(preview.get("error",{})))
	check(writer.writes==0 and DirAccess.get_directories_at("user://")==before_files,"preview and history perform zero map writes")
	var path := ProjectSettings.globalize_path("user://memory-project")
	check(store.start_file_operation("save",path)=="","first explicit save starts")
	await settle(store)
	check(not store.dirty and writer.writes==1 and store.undo_stack.size()==1,"save baseline preserves undo")
	var reopened := STORE.new();check(reopened.open_project(path)=="" and height(reopened)==raised,"save and reopen memory heights")
	check(store.start_file_operation("save",path)=="","repeat save starts")
	await settle(store)
	check(writer.writes==1,"unchanged save skips writes")
	check(terrain.begin(Vector2(3200,3200),opts)=="" and terrain.step(Vector2(3200,3200),0.5)=="","second edit")
	terrain.last_usec = Time.get_ticks_usec();check(terrain.finish()=="" and store.dirty,"second edit dirty")
	check(store.undo()=="" and not store.dirty and height(store)==raised,"undo reaches saved arrays and clears dirty")
	check(store.redo()=="" and store.dirty,"redo leaves saved baseline")
	var edits := height(store);var history := store.undo_stack.size()
	writer.fail = true
	check(store.start_file_operation("save",path)=="","failure starts")
	await settle(store)
	check(store.dirty and height(store)==edits and store.undo_stack.size()==history,"failed save retains dirty, memory and history")
	writer.fail = false
	check(store.start_file_operation("save",path)=="","cancel starts")
	store.cancel_file_operation();await settle(store)
	check(store.dirty and height(store)==edits,"cancelled save retains edits")
	var external := FileAccess.open(path.path_join("document.json"),FileAccess.WRITE);external.store_string("{}\n");external.close()
	check(store.save_project(path).contains("changed on disk") and store.dirty,"external conflict retains edits")
	var copy := path+"-copy";check(store.save_project(copy)=="","Save As resolves conflict")
	var snapshot: RefCounted = store.working_snapshot().fork()
	check(terrain.begin(Vector2(1000,1000),opts)=="" and terrain.step(Vector2(1000,1000),0.25)=="","save during brush begins")
	check(store.start_file_operation("save",copy)=="","save finishes brush instead of cancelling")
	await settle(store);check(not terrain.active and not store.dirty,"active brush included in saved baseline: "+str(file_results.back().get("error","")))
	# Water fill / terrain refresh are detached and memory-only.
	var water_store := STORE.new();water_store.new_document();water_store.document.bounds.max=[6400,6400];water_store.document.cell_size_cm=3200
	water_store.track_edit_finished.connect(func(message: String): if message != "": print("WATER ERROR: ",message))
	check(water_store.start_water(Vector2(1000,1000))=="","flat fill starts")
	await settle(water_store);check(water_store.document.get("water_bodies",[]).is_empty() and water_store.undo_stack.is_empty(),"flat fill is no-op")
	var lower := TERRAIN.new();lower.store=water_store
	check(lower.begin(Vector2(3200,3200),{"mode":"lower","radius_cm":1600})=="" and lower.step(Vector2(3200,3200),2)=="","basin sculpt")
	lower.last_usec=Time.get_ticks_usec();check(lower.finish()=="","basin finishes")
	check(water_store.start_water(Vector2(4000,3200))=="","sloping fill starts")
	await settle(water_store);check(not water_store.document.get("water_bodies",[]).is_empty(),"connected basin filled")
	var water_before: Array=water_store.document.get("water_bodies",[]).duplicate(true)
	var basin_height := height(water_store)
	check(lower.begin(Vector2(3200,3200),opts)=="" and lower.step(Vector2(3200,3200),4)=="","cancel fixture sculpts")
	lower.last_usec=Time.get_ticks_usec();check(lower.finish()=="","cancel fixture starts water refresh")
	# Even a worker that finished before Cancel cannot publish its result later.
	while water_store.water_job.is_alive(): await process_frame
	water_store.cancel_water();await settle(water_store)
	check(height(water_store)==basin_height and water_store.document.water_bodies==water_before and water_store.undo_stack.size()==2,"cancel rolls back terrain and shore without a command")
	for stale_field in ["id","session","revision"]:
		water_store.water_pending={"id":water_store.water_request,"session":water_store.session_id,"revision":water_store.command_epoch,"delta":PackedInt32Array()}
		water_store.water_pending[stale_field]-=1
		water_store.water_job=CompletedWater.new()
		water_store.poll_water()
		check(water_store.document.water_bodies==water_before and water_store.undo_stack.size()==2,"late water result rejected by "+stale_field)
	check(lower.begin(Vector2(3200,3200),opts)=="" and lower.step(Vector2(3200,3200),4)=="","island sculpt")
	lower.last_usec=Time.get_ticks_usec();check(lower.finish()=="","terrain water command async")
	await settle(water_store)
	check(water_store.undo_stack.size()==3,"terrain and water refresh share one undo step")
	check(water_store.undo()=="" and water_store.document.get("water_bodies",[])==water_before,"undo restores complete shore")
	check(water_store.start_water(Vector2(3400,3200),true)=="","remove water starts")
	await settle(water_store);check(water_store.document.get("water_bodies",[]).is_empty(),"remove entire connected water")
	# New default track documents accept terrain without a directory or format conversion.
	var track_store := STORE.new();track_store.new_track()
	var track_brush := TERRAIN.new();track_brush.store=track_store
	var origin := Vector2(track_store.document.bounds.min[0]+1600,track_store.document.bounds.min[1]+1600)
	check(track_brush.begin(origin,opts)=="" and track_brush.step(origin,0.5)=="","unsaved default map accepts terrain")
	track_brush.last_usec=Time.get_ticks_usec();check(track_brush.finish()=="","default map stroke finishes")
	await settle(track_store)
	check(track_store.undo_stack.size()==1 and track_store.document.assembled_track.authoring.terrain_integration,"terrain uses integrated current v1 document")
	check(track_store.undo()=="" and track_store.redo()=="","first terrain integration is one reversible command")
	track_store.shutdown_track_edit()
	# Publishing new PNG identities must not rewrite earlier import commands.
	var imported := STORE.new();imported.new_document();imported.document.bounds.max=[3200,3200];imported.document.cell_size_cm=3200
	var import_path := ProjectSettings.globalize_path("user://import-and-sculpt")
	check(imported.save_project(import_path)=="","save import fixture")
	var samples := PackedInt64Array();samples.resize(17*17);samples.fill(0);samples[8*17+8]=100
	var source := ProjectSettings.globalize_path("user://history-source.png")
	var source_file := FileAccess.open(source,FileAccess.WRITE);source_file.store_buffer(preload("res://scripts/terrain_png.gd").encode(samples,17).bytes);source_file.close()
	var import_brush := TERRAIN.new();import_brush.store=imported
	check(import_brush.import_png(source,Vector2i.ZERO,200,0,1,0,{"source":"Synthetic history","license":"MIT","notice":"fixture"})=="","import original heightmap")
	check(import_brush.begin(Vector2(1600,1600),opts)=="" and import_brush.step(Vector2(1600,1600),1)=="","sculpt imported source")
	import_brush.last_usec=Time.get_ticks_usec();check(import_brush.finish()=="","finish imported stroke")
	var imported_height := height(imported,Vector2(1600,1600))
	check(imported.save_project(import_path)=="","save sculpted source")
	check(imported.undo()=="" and height(imported,Vector2(1600,1600))==100,"undo stroke after imported PNG publication")
	var import_undo: String = imported.undo()
	check(import_undo=="" and imported.document.heightmaps.is_empty(),"undo import after Save: "+import_undo)
	check(imported.redo()=="" and height(imported,Vector2(1600,1600))==100,"redo original import")
	check(imported.redo()=="" and height(imported,Vector2(1600,1600))==imported_height and not imported.dirty,"redo sculpt reaches saved baseline")
	check(imported.save_project(import_path+"-copy")=="","unchanged Save As keeps source and published identities")
	var import_reopened := STORE.new()
	check(import_reopened.open_project(import_path+"-copy")=="" and height(import_reopened,Vector2(1600,1600))==imported_height,"Save As reopens exact sculpted heights")
	check(imported.undo()=="" and imported.undo()=="" and imported.redo()=="" and imported.redo()=="" and not imported.dirty,"Save As retains complete imported terrain history")
	import_reopened.shutdown_track_edit()
	imported.shutdown_track_edit()
	# Build real UI once to check command wiring, startup and dirty highlighting.
	var ui: Node = load("res://main.tscn").instantiate();root.add_child(ui);await process_frame
	check(ui.commands.keys_for("file.save").has(KEY_MASK_CTRL|KEY_S) and ui.commands.keys_for("file.save").has(KEY_MASK_META|KEY_S),"Ctrl+S and Cmd+S share Save")
	check(not ui.has_method("_autosave") and not store.has_method("autosave"),"no timer/transition autosave API")
	ui._request_document_action("new")
	check(ui.unsaved_dialog.visible and ui.recovery_continue_button.text.contains("Continue"),"three way unsaved prompt")
	ui.unsaved_dialog.hide();ui.pending_document_action.clear()
	ui.store.new_track(true)
	var save_button: Button
	for item: Dictionary in ui.commands.buttons:
		if item.id == "file.save": save_button = item.control.get_ref(); break
	check(save_button != null and save_button.modulate != Color.WHITE,"dirty content highlights Save")
	ui._start_save(ProjectSettings.globalize_path("user://shortcut-project"))
	await settle(ui.store)
	check(save_button.modulate == Color.WHITE,"successful Save clears highlight")
	for use_meta in [false,true]:
		check(ui.store.apply_command("Shortcut fixture",[{"field":"seed","before":ui.store.document.seed,"after":ui.store.document.seed+1}])=="","shortcut dirty fixture")
		var event := InputEventKey.new();event.keycode=KEY_S;event.pressed=true
		event.meta_pressed=use_meta;event.ctrl_pressed=not use_meta
		check(ui.commands.handle_key(event),"platform shortcut dispatches Save")
		await settle(ui.store)
		check(not ui.store.dirty and save_button.modulate == Color.WHITE,"shortcut publishes same saved baseline")
	# Simulating the old timer interval cannot write a recovery file.
	var recovery_files := DirAccess.get_files_at("user://recovery") if DirAccess.dir_exists_absolute("user://recovery") else PackedStringArray()
	ui._process(16.0)
	check((DirAccess.get_files_at("user://recovery") if DirAccess.dir_exists_absolute("user://recovery") else PackedStringArray())==recovery_files,"elapsed autosave interval creates no map data")
	ui.queue_free();await process_frame
	times.sort();print("memory brush step p95_ms=",times[int(times.size()*0.95)],"; updates_hz=",1000.0/(times.reduce(func(a,b):return a+b,0.0)/times.size()))
	store.shutdown_track_edit();water_store.shutdown_track_edit();reopened.shutdown_track_edit()
	print("terrain_native_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)
