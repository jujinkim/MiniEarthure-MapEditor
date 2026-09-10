extends SceneTree
const JOB := preload("res://scripts/import_job.gd")
const DEM_JOB := preload("res://scripts/dem_job.gd")

class MissingVector extends JOB:
	func _spawn(_python: String, _arguments: PackedStringArray) -> Dictionary:
		return {}

class MissingDem extends DEM_JOB:
	func _spawn(_python: String, _arguments: PackedStringArray) -> Dictionary:
		return {}

class WaitingVector extends JOB:
	func _spawn(python: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(python, PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/import_child_fixture.py"), "wait", identity]), false)

class MissingPipeVector extends WaitingVector:
	var launched_pid := -1
	func _spawn(python: String, arguments: PackedStringArray) -> Dictionary:
		var child := super._spawn(python, arguments)
		launched_pid = int(child.get("pid", -1))
		if child.has("stderr"): child.stderr.close()
		child.erase("stderr")
		return child

class MissingPipeDem extends DEM_JOB:
	var launched_pid := -1
	func _spawn(python: String, _arguments: PackedStringArray) -> Dictionary:
		var child := OS.execute_with_pipe(python, PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/import_child_fixture.py"), "wait", identity]), false)
		launched_pid = int(child.get("pid", -1))
		if child.has("stderr"): child.stderr.close()
		child.erase("stderr")
		return child

var failures: Array[String] = []
var assertions := 0
var source := ""

func check(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures.append(message)
		push_error(message)

func write(path: String, value: String) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
	file.close()

func digest(path: String) -> String:
	return FileAccess.get_sha256(path) if FileAccess.file_exists(path) else ""

func start_job(job: RefCounted, token: String, dem: bool = false) -> String:
	if dem: return job.start_local({"mode":"dem-plan"}, "python3", token)
	return job.start(source, "MIT", "unknown", "python3", token)

func _initialize() -> void: run.call_deferred()

func run() -> void:
	source = ProjectSettings.globalize_path("user://scratch-source.geojson")
	write(source, '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[20,10],[20,20],[10,20],[10,10]]]}}]}')
	var original := digest(source)
	var root := ProjectSettings.globalize_path("user://import-jobs")
	# Every path here is synthetic and under the runner's isolated user directory.
	var linked_root := ProjectSettings.globalize_path("user://linked-scratch")
	write(linked_root.path_join("keep.memap"), "outside scratch")
	var output: Array = []
	check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.symlink(sys.argv[1],sys.argv[2],target_is_directory=True)", linked_root, root]), output, true) == 0, "create synthetic root link")
	for dem in [false, true]:
		var linked: RefCounted = DEM_JOB.new() if dem else JOB.new()
		check(start_job(linked, Crypto.new().generate_random_bytes(16).hex_encode(), dem) != "", "refuse linked scratch root")
		linked.shutdown()
		linked.cleanup()
	check(digest(linked_root.path_join("keep.memap")) == "outside scratch".sha256_text(), "linked root target preserved")
	check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.unlink(sys.argv[1])", root]), output, true) == 0, "remove only synthetic root link")
	for dem in [false, true]:
		var label := "DEM" if dem else "vector"
		var token := Crypto.new().generate_random_bytes(16).hex_encode()
		var directory := root.path_join(token)
		var preserved := {"geojson.py":"previous helper", "layer.json":"previous result", "source.pbf":"original PBF", "source.tif.part":"previous DEM", "keep.memap":"previous package", "nested/source.tif":"original DEM"}
		for name in preserved: write(directory.path_join(name), preserved[name])
		var blocked: RefCounted = DEM_JOB.new() if dem else JOB.new()
		check(start_job(blocked, token, dem) != "", label + " refuses an existing directory")
		check(blocked.directory == "" and blocked.pid == -1, label + " does not claim existing scratch")
		blocked.cleanup()
		blocked.shutdown()
		blocked.cleanup()
		for name in preserved:
			check(digest(directory.path_join(name)) == str(preserved[name]).sha256_text(), label + " preserves existing " + name)
		check(start_job(blocked, Crypto.new().generate_random_bytes(16).hex_encode(), dem).contains("single use"), label + " rejected request cannot be restarted")
		var closed: RefCounted = DEM_JOB.new() if dem else JOB.new()
		closed.shutdown()
		check(start_job(closed, Crypto.new().generate_random_bytes(16).hex_encode(), dem).contains("single use"), label + " closed request cannot launch")
		var missing: RefCounted = MissingDem.new() if dem else MissingVector.new()
		check(start_job(missing, Crypto.new().generate_random_bytes(16).hex_encode(), dem).contains("Python could not start"), label + " reports launch failure")
		check(not DirAccess.dir_exists_absolute(missing.directory), label + " cleans scratch when no process starts")
		missing.shutdown()
		missing.cleanup()
		check(not DirAccess.dir_exists_absolute(missing.directory), label + " failed-start cleanup is idempotent")
		check(start_job(missing, Crypto.new().generate_random_bytes(16).hex_encode(), dem).contains("single use"), label + " failed launch needs a fresh object")
		var partial: RefCounted = MissingPipeDem.new() if dem else MissingPipeVector.new()
		check(start_job(partial, Crypto.new().generate_random_bytes(16).hex_encode(), dem).contains("Python could not start"), label + " reports incomplete process handles")
		check(partial.launched_pid > 0 and partial.exited, label + " confirms partially launched child stopped")
		check(partial.pid == -1 and partial.stdio == null and partial.stderr_pipe == null, label + " releases partial process handles")
		check(not DirAccess.dir_exists_absolute(partial.directory), label + " cleans partial-launch scratch after exit")
		for link in [false, true]:
			var occupied_token := Crypto.new().generate_random_bytes(16).hex_encode()
			var occupied := root.path_join(occupied_token)
			if link:
				check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.symlink(sys.argv[1],sys.argv[2])", source, occupied]), output, true) == 0, label + " create occupied token link")
			else: write(occupied, "existing file")
			var rejected: RefCounted = DEM_JOB.new() if dem else JOB.new()
			check(start_job(rejected, occupied_token, dem) != "", label + " refuses occupied file/link token")
			rejected.shutdown()
			rejected.cleanup()
			check(digest(occupied) == (original if link else "existing file".sha256_text()), label + " preserves occupied file/link token")
	var invalid := JOB.new()
	var invalid_token := Crypto.new().generate_random_bytes(16).hex_encode()
	check(invalid.start(source, "MIT", "unknown", "python3", invalid_token, {"mode":"wgs84-utm"}) != "", "invalid origins fail after staging modules")
	check(invalid.pid == -1 and not DirAccess.dir_exists_absolute(root.path_join(invalid_token)), "pre-launch validation failure cleans newly owned scratch")
	check(start_job(invalid, Crypto.new().generate_random_bytes(16).hex_encode()).contains("single use"), "invalid pre-launch request cannot be reused")
	var token := Crypto.new().generate_random_bytes(16).hex_encode()
	var live := WaitingVector.new()
	check(start_job(live, token) == "", "start actual live worker")
	var deadline := Time.get_ticks_msec() + 10000
	while live.sequence == 0 and Time.get_ticks_msec() < deadline:
		live.poll()
		await process_frame
	check(live.sequence == 1, "worker is running before cleanup attempt")
	var helper_hash := digest(live.directory.path_join("geojson.py"))
	live.cleanup()
	check(helper_hash != "" and digest(live.directory.path_join("geojson.py")) == helper_hash, "cleanup cannot remove a live worker's files")
	live.shutdown()
	check(live.exited and not DirAccess.dir_exists_absolute(live.directory), "shutdown stops worker before disposing owned scratch")
	# A completed object's repeated cleanup must not affect a new request at the same path.
	var replacement := WaitingVector.new()
	check(start_job(replacement, token) == "", "vacated token can be reserved by a new owner")
	var replacement_hash := digest(replacement.directory.path_join("geojson.py"))
	live.cleanup()
	check(replacement_hash != "" and digest(replacement.directory.path_join("geojson.py")) == replacement_hash, "old owner cannot clean a replacement request")
	write(replacement.directory.path_join("keep.memap"), "unrecognized file")
	write(replacement.directory.path_join("nested/source.pbf"), "nested original")
	replacement.shutdown()
	check(replacement.exited, "replacement worker stopped")
	check(not FileAccess.file_exists(replacement.directory.path_join("geojson.py")), "known helper removed after exit")
	check(digest(replacement.directory.path_join("keep.memap")) == "unrecognized file".sha256_text(), "unknown files preserved")
	check(digest(replacement.directory.path_join("nested/source.pbf")) == "nested original".sha256_text(), "no recursive deletion")
	var retry := JOB.new()
	check(start_job(retry, Crypto.new().generate_random_bytes(16).hex_encode()) == "", "fresh retry after ownership failures")
	deadline = Time.get_ticks_msec() + 10000
	while not retry.done and Time.get_ticks_msec() < deadline:
		retry.poll()
		await process_frame
	check(retry.done and retry.result.get("ok", false), "retry publishes a verified result")
	if not retry.done: retry.shutdown()
	check(digest(source) == original, "all ownership failures preserve selected source")
	print("import_scratch_validator: %d assertions" % assertions)
	print("import_scratch_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
