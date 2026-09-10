extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const JOB := preload("res://scripts/import_job.gd")
var failures: Array[String] = []
var checks := 0
func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+60000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"stream worker terminates: "+ui.status_label.text)
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	root.size = Vector2i(1024,720)
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_origin_x.value=512
	ui.import_origin_y.value=512
	var path := ProjectSettings.globalize_path("user://large-synthetic.pbf")
	var fixture_output: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_stream_fixture.py"),path]),fixture_output,true)==0,"large synthetic PBF: "+str(fixture_output))
	var file := FileAccess.open(path,FileAccess.READ)
	if file==null: quit(1); return
	var source_size := file.get_length()
	file.close()
	check(source_size>32*1024*1024,"fixture really exceeds former whole-source limit")
	var source_hash := FileAccess.get_sha256(path)
	var before: Dictionary=ui.store.document.duplicate(true)
	ui._start_import(path,LAYER.OSM_LICENSE)
	check(not ui.busy and ui.pending_import==null,"large source requires explicit streaming selection")
	ui.osm_panel.streaming.button_pressed=true
	check(ui.osm_panel.error()!="","streaming requires crop")
	ui.osm_panel.enabled.button_pressed=true
	var bbox := [8.9999,54.9999,9.006,55.006]
	for i in range(4): ui.osm_panel.fields[i].value=bbox[i]
	ui.osm_panel.open()
	await process_frame
	check(ui.osm_panel.error()=="","bounded stream crop")
	check(ui.osm_panel.dialog.size.x<=1024 and ui.osm_panel.dialog.size.y<=720,"stream selection fits minimum window")
	ui.osm_panel.dialog.hide()
	ui._start_import(path,LAYER.OSM_LICENSE)
	check(ui.import_job!=null and ui.import_job.timeout_seconds==900,"stream job has explicit 15-minute deadline")
	var directory: String=ui.import_job.directory
	await wait_import(ui)
	check(not DirAccess.dir_exists_absolute(directory),"successful snapshot/index/job cleanup")
	check(ui.pending_import!=null,"large stream native review: "+ui.status_label.text)
	if ui.pending_import==null:
		ui.queue_free(); await process_frame; quit(1); return
	check(ui.store.document==before,"review leaves accepted document unchanged")
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(raw.source.bytes==source_size and raw.source.sha256==source_hash,"full source byte count and hash retained")
	check(raw.coordinates.osm_stream.scan.nodes>raw.coordinates.osm_stream.selected.nodes,"outside source nodes excluded before normalization")
	check(ui.import_summary.text.contains("pbf-area-stream-v1") and ui.import_summary.text.contains("ODbL"),"selection policy and attribution reviewed")
	for mutation in ["profile","hash","passes","counts","missing","request"]:
		var bad: Dictionary=raw.duplicate(true)
		var request: Dictionary=ui.import_coordinates_request.duplicate(true)
		match mutation:
			"profile": bad.coordinates.osm_stream.profile="forged"
			"hash": bad.coordinates.osm_stream.source_sha256="0".repeat(64)
			"passes": bad.coordinates.osm_stream.passes=2
			"counts": bad.coordinates.osm_stream.selected.nodes=200001
			"missing": bad.coordinates.erase("osm_stream")
			"request": request.erase("osm_stream")
		check(LAYER.new().load_value(bad,ui.import_identity,request)!="","reject streaming provenance "+mutation)
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.roads.size()==1 and ui.store.document.buildings.size()==3 and ui.store.document.zones.size()==3,"complete roads/multipart/hole/island atomic native adoption: "+ui.status_label.text)
	var adopted: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.roads.is_empty(),"one-command Undo")
	check(ui.store.redo()=="" and ui.store.document==adopted,"exact Redo")
	var base := ProjectSettings.globalize_path("user://stream-project")
	check(ui.store.save_project(base)=="","save source provenance")
	var package := base+".memap"
	check(JSON.parse_string(ui.store.bridge.export_project(base,package)).ok,"build streaming package")
	var package_hash := FileAccess.get_sha256(package)
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok,"reopen streaming package")
	check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)).ok,"generate adopted native geometry")
	# Abort while owned index/snapshot exists, not only before process creation.
	ui._start_import(path,LAYER.OSM_LICENSE)
	directory=ui.import_job.directory
	var deadline := Time.get_ticks_msec()+15000
	while ui.import_job!=null and ui.import_job.progress.stage not in ["index_nodes","index_ways","index_relations"] and Time.get_ticks_msec()<deadline: await process_frame
	check(ui.import_job!=null,"worker remains cancellable during indexing")
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import==null and ui.store.document==adopted and not DirAccess.dir_exists_absolute(directory),"index cancellation cleans owned files and retains accepted layer")
	ui._start_import(path,LAYER.OSM_LICENSE)
	directory=ui.import_job.directory
	ui.import_job.poll(ui.import_job.deadline_ms)
	await wait_import(ui)
	check(ui.pending_import==null and ui.store.document==adopted and not DirAccess.dir_exists_absolute(directory),"controlled deadline retains layer and cleans workspace")
	ui._start_import(path,LAYER.OSM_LICENSE)
	ui.osm_panel.fields[0].value+=0.000001
	ui.osm_panel.fields[0].value-=0.000001
	await wait_import(ui)
	check(ui.pending_import==null and ui.store.document==adopted,"changed-restored bbox blocks late output")
	ui._start_import(path,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import!=null,"fresh retry after cancellation/timeout/stale response")
	check(ui.store.undo()=="","change document after review")
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.roads.is_empty(),"stale review cannot overwrite edited document")
	check(FileAccess.get_sha256(path)==source_hash and FileAccess.get_sha256(package)==package_hash,"original PBF and previous package immutable")
	ui._start_import(path,LAYER.OSM_LICENSE)
	var owned: RefCounted=ui.import_job
	directory=owned.directory
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.exited and owned.pid==-1 and not DirAccess.dir_exists_absolute(directory),"owner close stops worker and cleans only owned files")
	# Streaming IPC may not skip an incomplete scan or regress byte progress.
	for mode in ["skip","regress"]:
		var job := JOB.new()
		job.identity="a".repeat(32)
		job.timeout_seconds=900
		job.stages=["read","index_nodes","complete"]
		job._event(JSON.stringify({"request":job.identity,"seq":1,"stage":"read","completed":5,"total":10,"unit":"bytes"}).to_utf8_buffer())
		job._event(JSON.stringify({"request":job.identity,"seq":2,"stage":"index_nodes" if mode=="skip" else "read","completed":0,"total":10,"unit":"bytes"}).to_utf8_buffer())
		check(job.cancelled and job.failure!="","reject "+mode+" streaming progress")
	print("osm_stream_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
