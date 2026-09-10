extends SceneTree
const JOB := preload("res://scripts/import_native_job.gd")
const STORE := preload("res://tests/command_guard_store.gd")
const COMMAND := preload("res://scripts/import_command.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const LAYER := preload("res://scripts/import_layer.gd")

class PausedJob extends JOB:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var index := arguments.find("--")
		arguments.insert(index, "--script")
		arguments.insert(index + 1, ProjectSettings.globalize_path("res://tests/command_worker_fixture.gd"))
		return super._spawn(path, arguments)

class CorruptJob extends JOB:
	func _finish_result() -> void:
		if result.get("ok", false) and result.data.get("ok", false):
			var file := FileAccess.open(directory.path_join("bundle.bin"), FileAccess.WRITE)
			file.store_8(0); file.close()
		super._finish_result()

var store := STORE.new()
var layer := LAYER.new()
var source := ""
var checks := 0
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func state() -> String: return JSON.stringify([store.document, store.undo_stack, store.redo_stack, store.history_bytes, store.dirty, store.project_path])
func write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes); file.close()
func accepted(job: RefCounted) -> bool: return job.result.get("ok", false) and job.result.get("data", {}).get("ok", false)
func start(job: RefCounted, adopt: bool = true) -> String:
	return job.start_validation(store, layer, adopt, "test", source, token())
func wait_job(job: RefCounted, prepare: bool = false) -> void:
	var until := Time.get_ticks_msec() + 20000
	var frames := 0
	while not job.done and Time.get_ticks_msec() < until:
		job.poll()
		if prepare and job.progress.get("stage") == "prepare": break
		frames += 1
		await process_frame
	check((job.progress.get("stage") == "prepare" and not job.done) if prepare else job.done, "child reached requested state: " + str(job.progress) + " " + str(job.result))
	check(frames > 0, "preparation yields UI frames")
	if Time.get_ticks_msec() >= until: job.shutdown()

func run() -> void:
	store.new_document()
	var project := ProjectSettings.globalize_path("user://command-project")
	check(store.save_project(project) == "", "saved baseline")
	source = project.path_join("source.geojson")
	var original := JSON.stringify({"type":"FeatureCollection", "features":[{"type":"Feature", "properties":{"height_m":12}, "geometry":{"type":"Polygon", "coordinates":[[[10,10],[30,10],[30,30],[10,30],[10,10]]]}}]}).to_utf8_buffer()
	write(source, original)
	var adapter := preload("res://scripts/import_job.gd").new()
	check(adapter.start(source, "MIT", "synthetic", OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON"), token()) == "", "start adapter")
	await wait_job(adapter)
	if not adapter.result.get("ok", false): check(false, "adapter failed"); finish(); return
	check(layer.load_value(adapter.result.data, adapter.identity) == "", "load immutable layer")
	var before := state()
	var review := JOB.new()
	check(start(review, false) == "", "start prepared review")
	await wait_job(review)
	check(accepted(review) and review.command_prepared and state() == before, "review prepares canonical command without mutation")
	if not accepted(review): finish(); return
	layer.native_payload_digest = review.result.data.payloads
	check(review.commit(store) != "" and state() == before, "review alone has no adoption authority")
	for mode in ["cancel", "deadline", "eof", "source"]:
		var job := PausedJob.new()
		check(start(job) == "", "start preparation barrier " + mode)
		await wait_job(job, true)
		if job.done: continue
		match mode:
			"cancel": job.cancel()
			"deadline": job.deadline_ms = 0
			"eof": job.stdio.close(); job.stdio = null; job.output_eof = true
			"source":
				write(source, original.get_string_from_utf8().replace('"height_m":12', '"height_m":13').to_utf8_buffer())
				write(job.directory.path_join("test-prepare-release"), PackedByteArray([1]))
		await wait_job(job)
		check(not accepted(job) and job.exited and not DirAccess.dir_exists_absolute(job.directory), "preparation fault retires owned child/scratch " + mode)
		check(job.commit(store) != "" and state() == before, "preparation fault cannot mutate history " + mode)
		if mode == "source": check(str(job.result).contains("source changed"), "source is rechecked after command preparation")
		write(source, original)
	# Stale history/session/gesture epochs survive exact content restoration.
	for mode in ["gesture", "history", "save", "owner", "cancel-ready"]:
		var job := JOB.new()
		check(start(job) == "", "start stale prepared result " + mode)
		await wait_job(job)
		check(accepted(job), "preparation completed " + mode)
		var target: RefCounted = store
		var saved_document: Dictionary = store.document.duplicate(true)
		match mode:
			"gesture": check(store.begin_gesture("Temporary") == "", "begin temporary gesture"); store.cancel_gesture()
			"history":
				check(store.apply_command("Seed", [{"field":"seed", "before":store.document.seed, "after":43}]) == "" and store.undo() == "", "change and undo during prepared command")
				store.document = saved_document
			"save": check(store.save_project(project) == "", "save same content changes command epoch")
			"owner":
				target = STORE.new(); target.document = store.document.duplicate(true); target.project_path = store.project_path; target.command_epoch = store.command_epoch
			"cancel-ready": job.cancel()
		var changed := state()
		check(job.commit(target) != "" and state() == changed and target.document.buildings.is_empty(), "stale/completed-cancelled command rejected " + mode)
	var corrupt := CorruptJob.new()
	check(start(corrupt) == "", "start corrupt prepared transfer")
	await wait_job(corrupt)
	check(not accepted(corrupt) and corrupt.commit(store) != "", "changed transfer cannot become history")
	# The accepted worker channel is bounded even if a child writes malformed data.
	var prepared: Dictionary = store._prepare_command("Fixture", layer.patches(store))
	var envelope := COMMAND.encode(prepared)
	for mode in ["version", "canonical", "command", "json", "missing", "path", "binary", "budget"]:
		var bad := envelope.duplicate(true)
		match mode:
			"version": bad.version = 2
			"canonical": bad.canonical = "[]"
			"json": bad.command_json = "{broken"
			"missing": bad.canonical = '{"provenance":{}}'
			"command": bad.command_json = '{"label":"bad","patches":[1]}'
			"path": bad.retained["../source"] = PackedByteArray([1])
			"binary": bad.retained["editor/source.png"] = "wrong type"
			"budget":
				var bytes := PackedByteArray(); bytes.resize(COMMAND.HISTORY_LIMIT)
				bad.retained["editor/source.png"] = bytes
		check(COMMAND.decode(bad).has("error"), "reject malformed prepared envelope " + mode)
	before = state()
	layer.value["test_large_provenance"] = "x".repeat(8 * 1024 * 1024)
	var oversized := JOB.new()
	check(start(oversized) == "", "start large provenance command")
	await wait_job(oversized)
	check(not accepted(oversized) and str(oversized.result).contains("E_LIMIT") and state() == before, "existing native manifest limit rejects large provenance before preparation: " + str(oversized.result).left(3000))
	layer.value.erase("test_large_provenance")
	var binary := PackedByteArray(); binary.resize(COMMAND.HISTORY_LIMIT)
	var rejected: Dictionary = store._prepare_command("Over binary budget", layer.patches(store), {"editor/fixture.png":binary})
	check(str(rejected.get("error", "")).contains("16 MiB") and state() == before, "shared preparation charges binary plus text before history mutation")
	var ready := JOB.new()
	check(start(ready) == "", "fresh successful retry")
	await wait_job(ready)
	check(accepted(ready), "accepted retry prepares exact canonical command")
	var reentrant := []
	store.changed.connect(func(): reentrant.append(ready.commit(store)), CONNECT_ONE_SHOT)
	store.forbid_preparation = true
	check(ready.commit(store) == "" and store.forbidden_calls == 0, "final installation performs no native/attribution/savepoint signature preparation")
	store.forbid_preparation = false
	check(reentrant.size() == 1 and reentrant[0] != "" and ready.commit(store) != "", "result consumed before changed callback and duplicate commit")
	check(store.document.buildings.size() == 1 and store.redo_stack.is_empty() and store.dirty, "atomic adoption branches current history and leaves savepoint")
	var notice: Dictionary = store.document.attributions.back()
	check(JSON.parse_string(notice.notice).source == layer.value.source, "complete original provenance retained")
	check(store.undo() == "" and store.document.buildings.is_empty() and not store.dirty, "one Undo reaches saved content")
	check(store.redo() == "" and store.document.buildings.size() == 1 and store.dirty, "Redo restores canonical command")
	check(store.save_project(project) == "", "save imported command")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "" and reopened.document == store.document, "saved canonical result reopens exactly")
	check(FILES.read(source).bytes == original, "original source retained")
	finish()

func finish() -> void:
	print("import_command_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)
