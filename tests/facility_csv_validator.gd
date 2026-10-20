extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const JOB := preload("res://scripts/import_job.gd")
const LAYER := preload("res://scripts/import_layer.gd")
var failed := false
func check(ok: bool, message: String) -> void:
	if not ok: failed=true; push_error(message)
func _initialize() -> void: run.call_deferred()
func finish(job: RefCounted) -> void:
	var until := Time.get_ticks_msec()+15000
	while not job.done and Time.get_ticks_msec()<until:
		job.poll()
		await process_frame
	check(job.done, "CSV worker terminates")
	if not job.done: job.shutdown()
func run() -> void:
	var store := STORE.new()
	store.new_document()
	var source := ProjectSettings.globalize_path("user://facilities.csv")
	var file := FileAccess.open(source,FileAccess.WRITE)
	file.store_string("name,latitude,longitude\n도서관,55,9\nMissing,,9\n")
	file.close()
	var hash := FileAccess.get_sha256(source)
	var options := {"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512],"adapter":"facility-csv-v1", "csv":{"encoding":"utf-8-sig","name_column":"name","latitude_column":"latitude","longitude_column":"longitude","category":"작은도서관","source_url":"https://example.org/synthetic","bounds_cm":[0,0,102400,102400],"source_denominator":1}}
	var python := OS.get_environment("MINIEARTHURE_PYTHON")
	check(python!="", "root Python selected")
	var job := JOB.new()
	var token := "a".repeat(32)
	check(job.start(source,"CC0-1.0","unknown",python,token,options,"csv")=="", "start mapped CSV worker")
	await finish(job)
	check(job.result.get("ok",false), "CSV worker: "+str(job.result.get("error")))
	if not job.result.get("ok",false): quit(1); return
	var layer := LAYER.new()
	var failure := layer.load_value(job.result.data,token,options)
	check(failure=="", "validate complete review: "+failure)
	if failure!="": quit(1); return
	check(layer.value.coordinates.csv.rejected.size()==1,"invalid row is reviewable")
	check(layer.adopt(store)=="", "atomic facility adoption")
	check(store.document.pois.size()==1 and store.document.pois[0].name=="도서관","Korean facility preserved")
	check(store.undo()=="" and store.document.get("pois",[]).is_empty(),"Undo removes the complete layer")
	check(store.redo()=="" and store.document.pois.size()==1,"Redo restores one facility")
	var directory := ProjectSettings.globalize_path("user://facilities-project")
	check(store.save_project(directory)=="" and store.open_project(directory)=="","project save/reopen")
	var path := directory+".memap"
	check(JSON.parse_string(store.bridge.export_project(directory,path)).ok,"facility package export")
	check(JSON.parse_string(store.bridge.open_package(path)).ok,"facility package reopen")
	var overview: Dictionary=JSON.parse_string(store.bridge.overview_json(1048576))
	check(overview.ok and overview.data.pois[0].name=="도서관","overview retains facility")
	var forged: Dictionary=job.result.data.duplicate(true)
	forged.coordinates.csv.accepted=2
	check(LAYER.new().load_value(forged,token,options)!="","forged accounting refused")
	var cancelled := JOB.new()
	check(cancelled.start(source,"CC0-1.0","unknown",python,"b".repeat(32),options,"csv")=="","start cancellable CSV")
	cancelled.cancel()
	await finish(cancelled)
	check(not cancelled.result.get("ok",false) and store.document.pois.size()==1,"cancel cannot publish a partial layer")
	# A 1:3 OSM map: the stored scale divides the same projected position by three.
	var third_options: Dictionary = options.duplicate(true)
	third_options.csv.source_denominator = 3
	var third := JOB.new()
	check(third.start(source,"CC0-1.0","unknown",python,"c".repeat(32),third_options,"csv")=="","start 1:3 CSV worker")
	await finish(third)
	var third_layer := LAYER.new()
	check(third.result.get("ok",false) and third_layer.load_value(third.result.data,"c".repeat(32),third_options)=="","1:3 CSV review validates")
	if not third_layer.value.is_empty():
		var exact: Array = job.result.data.patches[0].after.position
		check(third_layer.value.patches[0].after.position == [roundf(exact[0]/3.0),roundf(exact[1]/3.0)],"1:3 CSV positions divide by the stored scale once: %s %s" % [str(exact),str(third_layer.value.patches[0].after.position)])
	var bad_options: Dictionary = options.duplicate(true)
	bad_options.csv.source_denominator = 9
	var bad := JOB.new()
	var bad_start: String = bad.start(source,"CC0-1.0","unknown",python,"d".repeat(32),bad_options,"csv")
	var refused := bad_start != ""  # Refused before launch, or by the worker below.
	if not refused:
		await finish(bad)
		refused = not bad.result.get("ok",false) and str(bad.result.get("error","")).contains("1:1 to 1:8")
	check(refused,"a 1:9 CSV scale is refused: "+bad_start+str(bad.result.get("error","")))
	check(FileAccess.get_sha256(source)==hash,"all operations retain source bytes")
	print("facility_csv_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
