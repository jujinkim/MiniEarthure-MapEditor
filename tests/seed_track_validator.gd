extends SceneTree
const EDITOR:=preload("res://scripts/editor_main.gd")
var failures:Array[String]=[]
func _initialize()->void:run.call_deferred()
func check(ok:bool,label:String)->void:
	if not ok:failures.append(label);push_error(label)
func settle(screen:Control)->void:
	var end:=Time.get_ticks_msec()+10000
	while screen.store.track_edit_busy and Time.get_ticks_msec()<end:await process_frame
	check(not screen.store.track_edit_busy,"template edit completes")
func run()->void:
	var screen:=EDITOR.new();root.add_child(screen);await process_frame
	var bench:Node=screen.track_workbench
	for id in ["double_jump","air_ring_chain","grind_shortcut","jump_shortcut_5"]:
		screen.store.new_track();bench.refresh()
		var before:Dictionary=screen.store.document.duplicate(true)
		check(bench.append_template(id),"template palette command "+id)
		await settle(screen)
		var after:Dictionary=screen.store.document.duplicate(true)
		check(after.assembled_track.get("geometry_issues",[]).is_empty(),"template geometry "+id)
		check(after.assembled_track.authoring.instances.size()>1,"template expanded to editable roads "+id)
		check(screen.store.undo()=="","template Undo accepted "+id)
		await settle(screen)
		check(screen.store.document==before,"one Undo restores entire template "+id)
		check(screen.store.redo()=="","template Redo accepted "+id)
		await settle(screen)
		check(screen.store.document==after,"one Redo restores template geometry and interactions "+id)
	var saved:=screen.store.document.duplicate(true)
	var project:=ProjectSettings.globalize_path("user://jump-source")
	check(screen.store.save_project(project)=="","save jump source")
	screen.store.new_track()
	check(screen.store.open_project(project)=="" and screen.store.document==saved,"reopen preserves explicit jump definitions and geometry")
	screen._open_track_generator()
	var native:RefCounted=ClassDB.instantiate("MapKitBridge")
	var defaults:Dictionary=JSON.parse_string(native.track_seed_defaults(42)).data
	var source:Dictionary=JSON.parse_string(native.track_template_source("double_jump")).data
	var result:Dictionary=JSON.parse_string(native.compile_track_source(JSON.stringify(source)))
	result.data.seed_defaults=defaults
	screen.track_epoch=screen.store.command_epoch;screen.track_request=42
	screen.track_job.completed.emit(42,result)
	check(screen.environment_preview.weather==defaults.weather and screen.environment_preview.seconds==float(defaults.time_minutes)*60,"adoption resets preview to shared seed defaults")
	var document:Dictionary=screen.store.document.duplicate(true)
	screen.preview_time.select(4);screen.preview_time.item_selected.emit(4)
	screen.preview_weather.select(2);screen.preview_weather.item_selected.emit(2)
	check(screen.store.document==document,"preview edits never modify package time or serialize weather")
	screen._open_track_generator();screen._cancel_track_generation()
	check(screen.environment_preview.weather=="rain" and screen.environment_preview.seconds==21*3600,"generator return and cancel retain preview overrides")
	screen.track_epoch=screen.store.command_epoch;screen.track_request=43
	screen.track_job.completed.emit(42,result)
	check(screen.environment_preview.weather=="rain","late result preserves preview")
	screen.track_job.completed.emit(43,{"ok":false,"error":{"code":"E_TRACK_DURATION","message":"controlled failure"}})
	check(screen.environment_preview.weather=="rain" and screen.store.document==document,"failed result preserves map and preview")
	screen.track_epoch=screen.store.command_epoch;screen.track_request=44
	screen.track_job.completed.emit(44,result)
	check(screen.environment_preview.weather==defaults.weather,"new adopted result resets preview overrides")
	screen.queue_free();await process_frame;await process_frame
	print("seed_track_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
