extends SceneTree
const SCRATCH := preload("res://tests/validator_scratch.gd")
const STORE := preload("res://scripts/document_store.gd")
const JOB := preload("res://scripts/generation_native_job.gd")
var scratch: String = SCRATCH.fresh(get_script().resource_path.get_file().get_basename())
var failed := false
func _finalize() -> void: SCRATCH.remove(scratch)
func check(ok: bool, message: String) -> void:
	if not ok: failed = true; push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var python := OS.get_environment("MINIEARTHURE_PYTHON")
	var output: Array = []
	var status := OS.execute(python,[ProjectSettings.globalize_path("res://tests/regional_fixture.py"),scratch],output,true)
	check(status == 0,"synthetic regional inputs: "+str(output))
	var store := STORE.new()
	check(store.open_project(scratch) == "","open synthetic regional input")
	var original: String = store._signature(store.document)
	var request: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(scratch.path_join("request.json")))
	var job := JOB.new()
	check(job.start_generation(store,{"mode":"fill","regional":request},python) == "","start native local-source regional composition")
	var deadline := Time.get_ticks_msec()+30000
	while (not job.done or not job.exited) and Time.get_ticks_msec()<deadline:
		job.poll()
		await process_frame
	if not job.done or not job.exited: job.shutdown()
	check(not job.bundle.is_empty(),"native geometry/worker validation: "+str(job.result).left(4000))
	var failure: String = job.commit(store)
	check(failure == "","apply native source composition: "+failure)
	if failure == "":
		check(store.document.buildings.size() == 4,"auxiliary parts and parent remainder keep independent source heights")
		check(store.document.surface_areas.size()>1,"WorldCover residual geometry applied")
		check(store.undo() == "" and store._signature(store.document)==original,"one undo restores every original source record")
	job.cleanup()
	print("regional_native_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
