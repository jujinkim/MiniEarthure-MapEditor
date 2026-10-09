extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const EDITOR := preload("res://scripts/editor_main.gd")
var failures: Array[String]=[]
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failures.append(label); push_error(label)
func settle(screen: Control) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while screen.store.track_edit_busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not screen.store.track_edit_busy, "bounded track command completion")

func run() -> void:
	var store:=STORE.new()
	store.new_track()
	check(store.document.assembled_track.authoring is Dictionary and not store.document.free_roam,"new track draft")
	var source: Dictionary=JSON.parse_string(store.bridge.track_shortcut_source()).data
	var compiled: String=store.edit_track(source)
	check(compiled=="","compile composed branch: "+compiled)
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
	check(not exported.ok and exported.error.code in ["E_TRACK_DRAFT","E_TRACK_GEOMETRY"],"draft execution export refused: "+str(exported))
	var geometry: Dictionary=store.document.assembled_track.duplicate(true)
	var policy: String=store.set_free_roam(true)
	check(policy=="" and store.document.assembled_track==geometry,"free roam keeps track geometry: "+policy)
	check(store.undo()=="" and not store.document.free_roam,"policy undo")
	var screen:=EDITOR.new()
	root.add_child(screen)
	await process_frame
	check(screen.track_workbench.active and screen.preview_dock.visible and screen.canvas.visible,"track workspace has 3D and auxiliary plan")
	check(screen.track_workbench.palette.visible,"manual piece palette")
	var bench: Node=screen.track_workbench
	bench.add_piece("straight")
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit(), "preview then place straight")
	await settle(screen)
	bench.add_piece("gentle45")
	check(bench.placement.preview_at(bench.PREVIEW.point(screen.store.document.assembled_track.pieces[0].path.back().position_cm)) and bench.placement.commit(), "preview then snap gentle45")
	await settle(screen)
	check(bench.source.instances.size()==2 and bench.source.connections.size()==1,"palette placement and port snap commands")
	bench.duplicate_piece()
	await settle(screen)
	check(bench.source.instances.size()==3,"duplicate command")
	bench.delete_piece()
	await settle(screen)
	check(bench.source.instances.size()==2,"delete command")
	bench.selected=1
	bench._properties()
	bench.controls[0].value=3.0
	bench.controls[2].value=22.0
	bench.apply_properties()
	await settle(screen)
	check(bench.source.instances[1].position_cm.map(func(v): return int(v))==[300,0,2200],"numeric free placement: "+str(bench.source.instances[1].position_cm))
	bench.selected=0
	bench._properties()
	bench.connect_curve()
	await settle(screen)
	check(bench.source.instances.size()==3 and bench.source.instances.back().preset=="free_curve" and bench.source.connections.size()==2,"free cubic replaces disconnected direct edge")
	bench.selected=0
	bench._properties()
	bench.add_action("jump_panel")
	check(bench.placement.preview_attachment(0, 0) and bench.placement.commit(), "attach panel at road sample")
	await settle(screen)
	check(bench.source.actions.size()==1 and bench.source.actions[0].landing==null,"continuous road jump has no forced landing road")
	check(bench.source.actions[0].panel_width_percent==50 and bench.source.actions[0].panel_alignment=="center","new panel defaults")
	check(bench.set_panel_layout(0,25,"right"),"edit existing attachment width/alignment")
	await settle(screen)
	check(bench.source.actions[0].panel_width_percent==25 and bench.source.actions[0].panel_alignment=="right","edited panel source")
	var edited: Dictionary = screen.store.document.duplicate(true)
	check(screen.store.undo()=="" and bench.source.actions[0].panel_width_percent==50,"panel layout undo")
	check(screen.store.redo()=="","panel layout redo accepted")
	await settle(screen)
	check(screen.store.document==edited,"panel layout redo includes geometry")
	var panel_path:=ProjectSettings.globalize_path("user://panel-layout")
	var panel_error: String=screen.store.save_project(panel_path)
	check(panel_error=="","panel source save: " + panel_error)
	var panel_store:=STORE.new()
	var reopen_error: String=panel_store.open_project(panel_path)
	check(reopen_error=="", "panel project reopens: " + reopen_error)
	var saved_actions: Array=panel_store.document.assembled_track.authoring.actions
	check(saved_actions.size()==1 and int(saved_actions[0].panel_width_percent)==25 and saved_actions[0].panel_alignment=="right", "panel layout reopens: " + str(saved_actions))
	check(panel_store.document.gimmicks==JSON.parse_string(JSON.stringify(edited.gimmicks)), "reopened panel geometry matches saved output")
	bench.add_action("acceleration_panel")
	bench.placement.panel_width_percent=75;bench.placement.panel_alignment="left"
	check(bench.placement.preview_attachment(0,2),"partial panel preview")
	var preview_serial: int=bench.placement.serial
	bench.placement.cancel()
	check(not bench.placement.commit(preview_serial) and screen.store.document==edited,"cancel preview preserves source")
	check(screen.store.undo()=="","undo layout before removing attachment")
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
