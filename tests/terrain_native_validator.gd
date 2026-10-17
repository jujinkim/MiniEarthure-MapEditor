extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const TERRAIN := preload("res://scripts/terrain_tools.gd")
const FILES := preload("res://scripts/document_files.gd")
const WORK := preload("res://scripts/package_work.gd")
var checks := 0
var failures: Array[String] = []
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
	while not store.file_request.is_empty() and Time.get_ticks_msec()<deadline:
		store.poll_file_operation(); await process_frame
	check(store.file_request.is_empty(),"workers settle")
func edit(store: RefCounted) -> String:
	return store.apply_command("Memory fixture",[{"field":"seed","before":store.document.seed,"after":store.document.seed+1}])
func run() -> void:
	var store := STORE.new();store.new_document()
	var file_results: Array[Dictionary] = []
	store.file_operation_finished.connect(func(result: Dictionary): file_results.append(result))
	store.document.bounds.max = [6400,6400];store.document.cell_size_cm = 3200
	var writer := CountingFiles.new();store.files = writer
	var before_files := DirAccess.get_directories_at("user://")
	var seed := int(store.document.seed)
	check(edit(store)=="" and store.undo_stack.size()==1 and store.dirty,"edit creates one memory command")
	check(writer.writes==0 and DirAccess.get_directories_at("user://")==before_files,"edit performs zero map writes")
	var edited := int(store.document.seed)
	check(store.undo()=="" and int(store.document.seed)==seed,"memory undo")
	check(store.redo()=="" and int(store.document.seed)==edited,"memory redo")
	var job := WORK.new();job.working = store.working_snapshot().fork()
	var preview: Dictionary = job.run(store.document,"","preview",Vector2i.ZERO,{},false)
	check(preview.ok,"unsaved preview: "+str(preview.get("error",{})))
	check(writer.writes==0 and DirAccess.get_directories_at("user://")==before_files,"preview and history perform zero map writes")
	var path := ProjectSettings.globalize_path("user://memory-project")
	check(store.start_file_operation("save",path)=="","first explicit save starts")
	await settle(store)
	check(not store.dirty and writer.writes==1 and store.undo_stack.size()==1,"save baseline preserves undo")
	var reopened := STORE.new();check(reopened.open_project(path)=="" and int(reopened.document.seed)==edited,"save and reopen memory edit")
	check(store.start_file_operation("save",path)=="","repeat save starts")
	await settle(store)
	check(writer.writes==1,"unchanged save skips writes")
	check(edit(store)=="" and store.dirty,"second edit dirty")
	check(store.undo()=="" and not store.dirty and int(store.document.seed)==edited,"undo reaches saved baseline and clears dirty")
	check(store.redo()=="" and store.dirty,"redo leaves saved baseline")
	var edits := int(store.document.seed);var history := store.undo_stack.size()
	writer.fail = true
	check(store.start_file_operation("save",path)=="","failure starts")
	await settle(store)
	check(store.dirty and int(store.document.seed)==edits and store.undo_stack.size()==history,"failed save retains dirty, memory and history")
	writer.fail = false
	check(store.start_file_operation("save",path)=="","cancel starts")
	store.cancel_file_operation();await settle(store)
	check(store.dirty and int(store.document.seed)==edits,"cancelled save retains edits")
	var external := FileAccess.open(path.path_join("document.json"),FileAccess.WRITE);external.store_string("{}\n");external.close()
	check(store.save_project(path).contains("changed on disk") and store.dirty,"external conflict retains edits")
	var copy := path+"-copy";check(store.save_project(copy)=="","Save As resolves conflict")
	# Publishing new PNG identities must not rewrite earlier import commands.
	var imported := STORE.new();imported.new_document();imported.document.bounds.max=[3200,3200];imported.document.cell_size_cm=3200
	var import_path := ProjectSettings.globalize_path("user://import-history")
	check(imported.save_project(import_path)=="","save import fixture")
	var samples := PackedInt64Array();samples.resize(17*17);samples.fill(0);samples[8*17+8]=100
	var source := ProjectSettings.globalize_path("user://history-source.png")
	var source_file := FileAccess.open(source,FileAccess.WRITE);source_file.store_buffer(preload("res://scripts/terrain_png.gd").encode(samples,17).bytes);source_file.close()
	var importer := TERRAIN.new();importer.store=imported
	check(importer.import_png(source,Vector2i.ZERO,200,0,1,0,{"source":"Synthetic history","license":"MIT","notice":"fixture"})=="","import original heightmap")
	check(imported.save_project(import_path)=="" and height(imported,Vector2(1600,1600))==100,"save imported source")
	var import_undo: String = imported.undo()
	check(import_undo=="" and imported.document.heightmaps.is_empty(),"undo import after Save: "+import_undo)
	check(imported.redo()=="" and height(imported,Vector2(1600,1600))==100 and not imported.dirty,"redo import reaches saved baseline")
	check(imported.save_project(import_path+"-copy")=="","unchanged Save As keeps source and published identities")
	var import_reopened := STORE.new()
	check(import_reopened.open_project(import_path+"-copy")=="" and height(import_reopened,Vector2(1600,1600))==100,"Save As reopens exact imported heights")
	check(imported.undo()=="" and imported.redo()=="" and not imported.dirty,"Save As retains imported terrain history")
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
	store.shutdown_track_edit();reopened.shutdown_track_edit()
	print("terrain_native_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)
