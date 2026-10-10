extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
const LAYER := preload("res://scripts/import_layer.gd")
var failed := false
func check(ok: bool,message: String) -> void:
	if not ok: failed=true; push_error(message)
func _initialize() -> void: run.call_deferred()
func finish(ui: Control) -> void:
	var until := Time.get_ticks_msec()+15000
	while ui.busy and Time.get_ticks_msec()<until: await process_frame
	check(not ui.busy,"review worker terminates: "+ui.status_label.text)
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.store.new_track(true)
	ui.import_python.text=OS.get_environment("MINIEARTHURE_PYTHON")
	var path:=ProjectSettings.globalize_path("user://review.pbf")
	var output: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_review_fixture.py"),path]),output,true)==0,"synthetic source: "+str(output))
	var hash:=FileAccess.get_sha256(path)
	var before: Dictionary=ui.store.document.duplicate(true)
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_origin_x.value=512
	ui.import_origin_y.value=512
	ui.osm_panel.enabled.button_pressed=true
	ui.osm_panel.streaming.button_pressed=true
	var b: Array=[8.9999,54.9999,9.006,55.006]
	for i in range(4): ui.osm_panel.fields[i].value=b[i]
	ui._start_import(path,LAYER.OSM_LICENSE)
	await finish(ui)
	check(ui.pending_import==null and ui.store.document==before,"unsupported bridge defaults to whole-import rejection")
	ui.osm_panel.exclusions.button_pressed=true
	ui._start_import(path,LAYER.OSM_LICENSE)
	await finish(ui)
	check(ui.pending_import!=null,"explicit exclusion candidate: "+ui.status_label.text)
	if ui.pending_import==null: ui.queue_free(); await process_frame; quit(1); return
	var value: Dictionary=ui.pending_import.value.duplicate(true)
	check(value.coordinates.osm_review.excluded[0].source_id=="way/2","exact unsupported bridge source ID is reviewed")
	check(ui.import_exclusions.visible and ui.import_review.get_ok_button().disabled,"adoption requires explicit review checkbox")
	ui._adopt_import()
	check(ui.store.document==before and ui.pending_import!=null,"unchecked review cannot adopt")
	var forged: Dictionary=value.duplicate(true)
	forged.coordinates.osm_review.excluded.append(forged.coordinates.osm_review.excluded[0].duplicate(true))
	check(LAYER.new().load_value(forged,ui.import_identity,ui.import_coordinates_request)!="","duplicate exclusion rejected")
	ui.import_exclusions.button_pressed=true
	ui._adopt_import()
	await finish(ui)
	check(ui.store.document.buildings.size()==1 and ui.store.document.roads.is_empty(),"review adopts complete supported candidate without guessed bridge")
	check(ui.store.undo()=="" and ui.store.document.buildings==before.buildings and ui.store.document.zones==before.zones and ui.store.document.attributions==before.attributions and ui.store.document.free_roam==before.free_roam,"one-command Undo restores all reviewed records and metadata")
	check(ui.store.redo()=="" and ui.store.document.buildings.size()==1,"Redo restores reviewed layer")
	check(FileAccess.get_sha256(path)==hash,"source preserved")
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("osm_review_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
