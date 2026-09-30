extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const EDITOR := preload("res://scripts/editor_main.gd")
var failures: Array[String]=[]
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failures.append(label); push_error(label)
func run() -> void:
	var store:=STORE.new()
	store.new_track()
	check(store.document.assembled_track.authoring is Dictionary and not store.document.free_roam,"new track draft")
	var source: Dictionary=JSON.parse_string(store.bridge.track_shortcut_source()).data
	check(store.edit_track(source)=="","compile composed branch")
	var before:=store._signature(store.document)
	var changed:=source.duplicate(true)
	changed.instances[0].position_cm[0]+=137
	check(store.edit_track(changed)=="","free movement saves disconnected draft")
	check(not store.document.assembled_track.issues.is_empty(),"draft reports disconnected ports")
	var after:=store._signature(store.document)
	check(store.undo()=="" and store._signature(store.document)==before,"source and derived geometry undo")
	check(store.redo()=="" and store._signature(store.document)==after,"source and derived geometry redo")
	check(store.edit_track(source,store.command_epoch-1)!="" and store._signature(store.document)==after,"stale edit rejected without mutation")
	check(store.autosave()=="","draft recovery")
	var recovered:=STORE.new()
	check(recovered.recover(store.recovery_path())=="" and recovered._signature(recovered.document)==after,"draft restored")
	var path:=ProjectSettings.globalize_path("user://track-draft")
	var save_error: String=store.save_project(path)
	check(save_error=="","disconnected project saves: "+save_error)
	var reopened:=STORE.new()
	check(reopened.open_project(path)=="" and reopened.document.assembled_track==store.document.assembled_track,"draft project reopens")
	var native: RefCounted=ClassDB.instantiate("MapKitBridge")
	var exported: Dictionary=JSON.parse_string(native.export_project(path,ProjectSettings.globalize_path("user://draft.memap")))
	check(not exported.ok and exported.error.code=="E_TRACK_DRAFT","draft execution export refused")
	var geometry: Dictionary=store.document.assembled_track.duplicate(true)
	check(store.set_free_roam(true)=="" and store.document.assembled_track==geometry,"free roam keeps track geometry")
	check(store.undo()=="" and not store.document.free_roam,"policy undo")
	var screen:=EDITOR.new()
	root.add_child(screen)
	await process_frame
	check(screen.track_workbench.active and screen.preview_dock.visible and screen.canvas.visible,"track workspace has 3D and auxiliary plan")
	check(screen.track_workbench.palette.visible,"manual piece palette")
	var bench: Node=screen.track_workbench
	bench.add_piece("straight")
	bench.add_piece("gentle45")
	check(bench.source.instances.size()==2 and bench.source.connections.size()==1,"palette placement and port snap commands")
	bench.duplicate_piece()
	check(bench.source.instances.size()==3,"duplicate command")
	bench.delete_piece()
	check(bench.source.instances.size()==2,"delete command")
	bench.selected=1
	bench._properties()
	bench.controls[0].value=3.0
	bench.controls[2].value=22.0
	bench.apply_properties()
	check(bench.source.instances[1].position_cm.map(func(v): return int(v))==[300,0,2200],"numeric free placement: "+str(bench.source.instances[1].position_cm))
	bench.selected=0
	bench._properties()
	bench.connect_curve()
	check(bench.source.instances.size()==3 and bench.source.instances.back().preset=="free_curve" and bench.source.connections.size()==2,"free cubic replaces disconnected direct edge")
	bench.selected=0
	bench._properties()
	bench.add_action("jump_panel")
	check(bench.source.actions.size()==1 and bench.source.actions[0].landing==null,"continuous road jump has no forced landing road")
	check(screen.store.undo()=="" and bench.source.actions.is_empty(),"controller command undo")
	screen._open_track_generator()
	var current: String=screen.store._signature(screen.store.document)
	screen.track_epoch=screen.store.command_epoch
	screen.track_job.completed.emit(1,{"ok":false,"error":{"code":"E_TRACK_DURATION","message":"Requested 60 s; closest 70 s; outside tolerance"}})
	check(screen.store._signature(screen.store.document)==current,"failed generation retains current map")
	screen.track_epoch=screen.store.command_epoch-1
	screen.track_job.completed.emit(2,{"ok":true,"data":{"document":store.document}})
	check(screen.store._signature(screen.store.document)==current,"late generation cannot replace edited map")
	screen.queue_free()
	await process_frame
	print("track_workbench_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
