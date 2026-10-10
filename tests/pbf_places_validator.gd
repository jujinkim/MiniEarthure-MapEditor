extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
const JOB := preload("res://scripts/pbf_places_job.gd")
var failed := false
func check(ok: bool, message: String) -> void:
	if not ok: failed=true; push_error(message)
func _initialize() -> void: run.call_deferred()
func finish(ui: Control) -> void:
	var until := Time.get_ticks_msec()+15000
	while ui.busy and Time.get_ticks_msec()<until: await process_frame
	check(not ui.busy,"place worker terminates")
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.import_python.text=OS.get_environment("MINIEARTHURE_PYTHON")
	var source := ProjectSettings.globalize_path("user://places.pbf")
	var output: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/pbf_places_fixture.py"),source]),output,true)==0,"synthetic PBF fixture: "+str(output))
	var before: Dictionary=ui.store.document.duplicate(true)
	var hash:=FileAccess.get_sha256(source)
	ui.osm_panel.source_path.text=source
	ui.osm_panel.place_query.text="가상시"
	ui.osm_panel.start_search()
	check(ui.busy and ui.import_job is JOB,"name search uses cancelable worker")
	var directory: String=ui.import_job.directory
	await finish(ui)
	check(ui.osm_panel.places.size()==1,"Korean search result: "+ui.osm_panel.place_status.text)
	check(ui.osm_panel.bbox()==[9.0,55.0,9.0002,55.0002],"exact outward rounded bbox")
	check(ui.import_origin_lon.value>9 and ui.import_origin_lat.value>55,"name search fills WGS84 origin")
	check(ui.osm_panel.area.places[0].name=="가상시","boundary map includes place name")
	check(ui.store.document==before and not DirAccess.dir_exists_absolute(directory),"search only changes import settings and cleans scratch")
	var job:=JOB.new()
	var value: Dictionary={"profile":"pbf-place-preview-v1","query":"가상시","source_name":"places.pbf","source_sha256":hash,"source_bytes":100,"places":ui.osm_panel.places.duplicate(true)}
	check(JOB.validate(value,"가상시")=="","checked preview contract")
	value.places[0].bbox[2]=-180
	check(JOB.validate(value,"가상시")!="","forged extent rejected")
	ui.osm_panel.dialog.hide()
	ui.osm_panel.start_search()
	directory=ui.import_job.directory
	ui._cancel_operation()
	await finish(ui)
	check(ui.store.document==before and not DirAccess.dir_exists_absolute(directory),"cancel keeps document and cleans worker")
	check(FileAccess.get_sha256(source)==hash,"source PBF preserved")
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("pbf_places_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
