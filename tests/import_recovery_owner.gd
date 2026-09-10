extends SceneTree
const JOB := preload("res://scripts/import_job.gd")
class HeldJob extends JOB:
	func _spawn(python: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(python, PackedStringArray(["-B", "-u", OS.get_environment("MAPEDITOR_TEST_PROJECT").path_join("tests/import_watch_fixture.py"), directory, identity]), false)
var job := HeldJob.new()
var phase := ""
var ready := ""
var announced := false
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	phase = args[0]
	ready = args[3]
	var failure := job._reserve_directory(args[1]) if phase == "reserved" else job.start(args[2], "MIT", "unknown", "python3", args[1])
	if failure != "":
		push_error(failure)
		quit(2)
func _process(_delta: float) -> bool:
	job.poll()
	if not announced and (phase == "reserved" or job.sequence == 1):
		var file := FileAccess.open(ready, FileAccess.WRITE)
		file.store_string(JSON.stringify({"phase":phase, "worker":job.pid}))
		file.close()
		announced = true
	return false
