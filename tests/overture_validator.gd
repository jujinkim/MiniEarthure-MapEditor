extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
const UI := preload("res://scripts/editor_main.gd")
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_job(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "Overture worker terminates: " + ui.status_label.text)
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var before: Dictionary=ui.store.document.duplicate(true)
	var source := ProjectSettings.globalize_path("user://overture_validator.gd.json")
	var output: Array = []
	check(OS.execute(ui.import_python.text, PackedStringArray(["-B", ProjectSettings.globalize_path("res://tests/overture_fixture.py"), "--snapshot", source]), output, true) == 0, "local synthetic snapshot")
	ui.import_source_format.select(3)
	ui.import_source_format.item_selected.emit(3)
	check(ui.import_license.text == LAYER.OVERTURE_LICENSE, "explicit local source attribution")
	if not FileAccess.file_exists(source): quit(1); return
	var original:=FileAccess.get_sha256(source)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_dialog.hide()
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null,"Overture native review: "+ui.status_label.text)
	if ui.pending_import==null: quit(1); return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(ui.store.document==before,"review leaves document unchanged")
	check(raw.adapter=="overture-buildings-v1" and raw.source.sha256==original,"snapshot identity preserved")
	check(ui.import_summary.text.contains("2026-08-19.0") and ui.import_summary.text.contains("synthetic fixture") and ui.import_summary.text.contains("base_m"),"release/source/estimate review")
	for field in ["license","adapter","provenance","bbox","release","sources"]:
		var bad:=raw.duplicate(true)
		if field=="license":bad.source.license="MIT"
		elif field=="adapter":bad.adapter="geojson-v2"
		elif field=="bbox":bad.coordinates.overture.bbox=[9,55,10,56]
		elif field=="release":bad.coordinates.overture.release="latest"
		elif field=="sources":bad.coordinates.overture.feature_sources[0].sources=[]
		else:bad.coordinates.erase("overture")
		check(LAYER.new().load_value(bad,raw.layer_id,ui.import_coordinates_request)!="","forged "+field+" rejected")
	ui._discard_import()
	check(ui.store.document==before,"discard preserves map")
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	await wait_job(ui)
	ui._adopt_import()
	check(ui.store.document.buildings.size()==1,"native atomic building adoption")
	ui._adopt_import()
	check(ui.store.document.buildings.size()==1,"one-shot candidate")
	var project:=ProjectSettings.globalize_path("user://overture-project")
	check(ui.store.save_project(project)=="","save provenance")
	check(ui.store.autosave()=="","recovery snapshot")
	var reopened:=STORE.new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==ui.store.document.attributions,"source notices roundtrip")
	check(reopened.recover(ui.store.recovery_path())=="","recover source layer")
	var pack:=ProjectSettings.globalize_path("user://overture.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,pack)).ok,"package imported building")
	var pack_hash:=FileAccess.get_sha256(pack)
	check(JSON.parse_string(ui.store.bridge.open_package(pack)).ok,"open package")
	check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)).ok,"same MapKit geometry generation")
	var update:=ProjectSettings.globalize_path("user://updated.overture.json")
	var snapshot:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source))
	snapshot.features[0].properties.height=23
	var f:=FileAccess.open(update,FileAccess.WRITE)
	f.store_string(JSON.stringify(snapshot));f.close()
	ui._start_import(update,LAYER.OVERTURE_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null and ui.pending_import.value.layer_id!=raw.layer_id,"source update is fresh layer")
	ui._adopt_import()
	check(ui.store.document.buildings.size()==2,"update retains old building")
	check(ui.store.undo()=="" and ui.store.document.buildings.size()==1,"undo updated layer")
	check(ui.store.redo()=="" and ui.store.document.buildings.size()==2,"redo updated layer")
	check(FileAccess.get_sha256(source)==original and FileAccess.get_sha256(pack)==pack_hash,"source/package preserved")
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	await wait_job(ui)
	check(ui.store.undo()=="","change document during review")
	ui._adopt_import()
	check(ui.store.document.buildings.size()==1,"stale review rejected")
	# Surviving local helper lifetime: deadline, stale response, retry and owner close.
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	var owned: RefCounted = ui.import_job
	owned.poll(owned.deadline_ms)
	await wait_job(ui)
	check(owned.result.error.message.contains("timed out"),"deadline terminates local helper")
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	ui.generation += 1
	await wait_job(ui)
	check(ui.pending_import == null,"stale document rejects local candidate")
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	await wait_job(ui)
	check(ui.pending_import != null,"fresh local retry succeeds")
	ui._discard_import()
	ui._start_import(source,LAYER.OVERTURE_LICENSE)
	owned=ui.import_job
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.pid==-1 and not DirAccess.dir_exists_absolute(owned.directory),"owner close stops local child")
	check(FileAccess.get_sha256(source)==original,"original snapshot retained after lifetime checks")
	print("overture_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
