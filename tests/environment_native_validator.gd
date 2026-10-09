extends SceneTree
const RECOVERY_FIXTURE := preload("res://tests/recovery_fixture.gd")
const JOB := preload("res://scripts/generation_native_job.gd")
const STORE := preload("res://scripts/document_store.gd")
const REGIONS := preload("res://scripts/import_regions.gd")
var checks := 0
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label);push_error(label)
func wait_job(job: RefCounted) -> void:
	var deadline := Time.get_ticks_msec()+120000
	while not job.done and Time.get_ticks_msec()<deadline:
		job.poll()
		await process_frame
	check(job.done and job.exited,"owned worker completes/reaps: "+str(job.result).left(1500))
	if not job.done: job.shutdown()
func run() -> void:
	var store := STORE.new()
	store.new_document()
	store.document.free_roam=true
	store.document.bounds={"min":[0,0],"max":[25600,25600]}
	var project := ProjectSettings.globalize_path("user://environment-infill")
	check(store.save_project(project)=="","save base")
	var original := JSON.stringify(store.document)
	var settings := {"mode":"fill","theme":"village","seed":9026,"bounds_cm":[0,0,25600,25600],"density":.25,"texture_profile":256}
	var python := OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var cancelled := JOB.new()
	check(cancelled.start_generation(store,settings,python)=="","start cancelled preview")
	cancelled.cancel();await wait_job(cancelled);cancelled.cleanup()
	check(cancelled.commit(store)!="" and JSON.stringify(store.document)==original,"cancel retains document")
	var job := JOB.new()
	check(job.start_generation(store,settings,python)=="","start fill preview")
	await wait_job(job)
	check(not job.bundle.is_empty(),"native fill preview: "+str(job.result).left(1600))
	check(JSON.stringify(store.document)==original and store.undo_stack.is_empty(),"preview does not apply")
	if job.bundle.is_empty(): finish();return
	check(job.commit(store)=="","apply prepared fill")
	check(store.undo_stack.size()==1 and not store.document.surface_areas.is_empty(),"one command and ground cover")
	var applied := JSON.stringify(store.document)
	check(job.commit(store)!="","consumed preview rejected")
	check(store.undo()=="" and store._signature(store.document)==store._signature(JSON.parse_string(original)),"one Undo restores all metadata and scenery")
	check(store.redo()=="" and store._signature(store.document)==store._signature(JSON.parse_string(applied)),"Redo restores exact environment")
	applied=JSON.stringify(store.document)
	check(RECOVERY_FIXTURE.write(store)=="","generation recovery write")
	var recovered := STORE.new()
	check(recovered.recover(RECOVERY_FIXTURE.path(store))=="" and recovered.document==store.document,"generation metadata recovery")
	job.cleanup()
	var stale := JOB.new();check(stale.start_generation(store,settings,python)=="","start stale preview")
	await wait_job(stale)
	store.command_epoch+=1
	check(stale.commit(store)!="" and JSON.stringify(store.document)==applied,"stale document epoch rejected")
	stale.cleanup()
	settings.mode="new";settings.bounds_cm=[0,0,112000,96000]
	var created := JOB.new();check(created.start_generation(store,settings,python)=="","new world starts")
	await wait_job(created)
	check(not created.bundle.is_empty(),"native new world preview: "+str(created.result).left(1800))
	var target := ProjectSettings.globalize_path("user://environment-new")
	if not created.bundle.is_empty():
		check(created.bundle.report.diagnostics.errors.is_empty(),"required facilities: "+str(created.bundle.report.diagnostics.errors))
		check(not DirAccess.dir_exists_absolute(target),"preview does not publish directory")
		check(created.commit(store,target)=="","atomic new project publication")
		check(JSON.stringify(store.document)==applied,"publish retains current editing document")
		var opened := STORE.new()
		var open_error: String=opened.open_project(target)
		check(open_error=="" and int(opened.document.bounds.max[0])==112000 and int(opened.document.bounds.max[1])==96000,"new project loads: "+open_error+" "+str(opened.document.get("bounds")))
		check(created.commit(store,target)!="","no overwrite/replay")
	created.cleanup()
	var region := {"id":"a","source_id":"relation/7","landuse":"farmland","protected":false,"polygon":[[0,0],[800,0],[800,800]],"holes":[[[80,80],[160,80],[160,160]]]}
	check(REGIONS.validate([region])=="","valid provenance")
	var scaled := REGIONS.scaled([region])
	check(scaled[0].polygon[1]==[100,0] and scaled[0].holes[0][0]==[10,10] and region.polygon[1]==[800,0],"1:8 exactly once with original holes retained")
	finish()
func finish() -> void:
	print("environment_native_validator: ","PASS" if failures.is_empty() else failures," checks=",checks)
	quit(0 if failures.is_empty() else 1)
