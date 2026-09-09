extends SceneTree
const JOB := preload("res://scripts/import_job.gd")
class FaultJob extends JOB:
	var mode := "wait"
	func _spawn(python: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(python, PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/import_child_fixture.py"), mode, identity]), false)
var failures: Array[String] = []
var pids: Array[int] = []
func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func finish(job: RefCounted) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while not job.done and Time.get_ticks_msec() < deadline:
		job.poll()
		await process_frame
	check(job.done, "job terminates: " + str(job.progress) + " / " + job.errors)
	if not job.done: job.shutdown()
func run() -> void:
	var source := ProjectSettings.globalize_path("user://source.geojson")
	var file := FileAccess.open(source, FileAccess.WRITE)
	file.store_string('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[20,10],[20,20],[10,20],[10,10]]]}}]}')
	file.close()
	var original := FileAccess.get_sha256(source)
	for mode in ["cancel", "timeout", "flood", "wrong-request", "partial", "crash", "owner-close"]:
		var job := FaultJob.new()
		job.mode = "wait" if mode in ["cancel", "timeout", "owner-close"] else mode
		check(job.start(source,"MIT","unknown","python3",Crypto.new().generate_random_bytes(16).hex_encode()) == "", "start " + mode)
		pids.append(job.pid)
		var request_pid := job.pid
		if mode in ["cancel", "timeout", "owner-close"]:
			var deadline := Time.get_ticks_msec() + 10000
			while job.sequence == 0 and Time.get_ticks_msec() < deadline:
				job.poll()
				await process_frame
			check(job.sequence == 1, "actual child progress before " + mode)
			if mode == "timeout": job.poll(job.deadline_ms)
			elif mode == "owner-close": job.shutdown()
			else:
				job.cancel()
				job.cancel()
		if mode == "owner-close":
			check(job.exited, "owner shutdown confirms killed child")
			check(job.stdio == null and job.stderr_pipe == null and job.pid == -1, "owner releases pipes")
			# This synthetic request is now confirmed stopped; dispose owned scratch.
			job.cleanup()
		else:
			await finish(job)
			check(not job.result.get("ok",false), "fault cannot publish " + mode)
			check(job.pid == -1 and job.stdio == null and job.stderr_pipe == null, "joined pipes " + mode)
			check(not DirAccess.dir_exists_absolute(job.directory), "owned scratch cleanup " + mode)
			if mode == "timeout": check(job.result.error.message.contains("timed out"), "deadline failure distinct from cancel")
			if mode == "crash": check(job.exit_code == 7 and job.result.error.message.contains("synthetic adapter crash"), "exit code/stderr captured")
		var sequence := job.sequence
		job.poll()
		check(job.sequence == sequence, "terminal polling idempotent")
	var success := JOB.new()
	check(success.start(source,"MIT","unknown","python3",Crypto.new().generate_random_bytes(16).hex_encode()) == "", "retry after failure")
	await finish(success)
	check(success.result.get("ok",false) and success.sequence >= 8, "actual conversion progress and complete payload hash")
	check(success.result.data.source.sha256 == original, "source snapshot hash")
	check(FileAccess.get_sha256(source) == original, "all faults preserve input")
	var verification: Array = []
	var verify_code := "import os,sys\nfor pid in map(int,sys.argv[1:]):\n try: os.kill(pid,0)\n except ProcessLookupError: continue\n raise SystemExit('child still alive: '+str(pid))\nprint('all child PIDs stopped')"
	var arguments := PackedStringArray(["-c", verify_code])
	for pid in pids: arguments.append(str(pid))
	check(OS.execute("python3", arguments, verification, true) == 0, "OS-level process exit: " + str(verification))
	print("import_job_validator children: " + str(pids))
	print("import_job_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
