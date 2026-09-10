extends SceneTree
const JOB := preload("res://scripts/asset_native_job.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const STORE := preload("res://scripts/document_store.gd")
class PausedJob extends JOB:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var index := arguments.find("--")
		arguments.insert(index, "--script")
		arguments.insert(index + 1, ProjectSettings.globalize_path("res://tests/command_worker_fixture.gd"))
		return super._spawn(path, arguments)
class MissingJob extends JOB:
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary: return {}
class CorruptJob extends JOB:
	func _finish_result() -> void:
		if result.get("ok", false) and result.data.get("ok", false):
			var file := FileAccess.open(directory.path_join("bundle.bin"), FileAccess.WRITE)
			file.store_8(0); file.close()
		super._finish_result()
class FaultJob extends JOB:
	var mode := "wait"
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON"), PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/native_child_fixture.py"), mode, identity, directory]), false)
class GuardedStore extends STORE:
	var forbidden := 0
	func _prepare_command(_label: String, _patches: Array, _mementos: Dictionary = {}) -> Dictionary:
		forbidden += 1
		return {"error":"Main-thread asset command preparation forbidden."}
var ui: Control
var checks := 0
var failures: Array[String] = []
var source := ""
var project := ""
var record := {"id":"asset", "path":"", "attribution":{"source":"Synthetic asset", "license":"MIT", "notice":"Original fixture"}, "collision":[{"center":[0,100,0],"size_cm":[200,200,200]}]}
func _initialize() -> void: run.call_deferred()
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func state() -> String: return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.history_bytes, ui.store.dirty])
func write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes); file.close()
func accepted(job: RefCounted) -> bool: return job.result.get("ok", false) and job.result.get("data", {}).get("ok", false) and not job.bundle.is_empty()
func start(job: RefCounted, value: Dictionary = {}, path: String = "DEFAULT", store: RefCounted = null) -> String:
	return job.start_asset(ui.store if store == null else store, record if value.is_empty() else value, source if path == "DEFAULT" else path, "test", token())
func wait_job(job: RefCounted, prepare: bool = false) -> void:
	var deadline := Time.get_ticks_msec() + 20000
	var frames := 0
	while not job.done and Time.get_ticks_msec() < deadline:
		job.poll()
		if prepare and job.progress.get("stage") == "prepare": break
		frames += 1
		await process_frame
	check(job.progress.get("stage") == "prepare" and not job.done if prepare else job.done, "owned asset state: " + str(job.progress) + " " + str(job.result).left(600))
	check(frames > 0, "asset work yields frames")
	if Time.get_ticks_msec() >= deadline: job.shutdown()
	if not prepare: check(job.exited and job.pid == -1, "asset process reaped")
func wait_ui() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "asset UI completes: " + ui.author_panel.feedback.text)
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate(); root.add_child(ui)
	await process_frame
	project = ProjectSettings.globalize_path("user://asset-project")
	check(ui.canvas.author.recipe(4, "default") == "", "recipe for native asset validation")
	check(ui.store.save_project(project) == "", "save isolated asset project")
	source = ProjectSettings.globalize_path("user://asset.png")
	var picture := Image.create(4,4,false,Image.FORMAT_RGBA8); picture.fill(Color.YELLOW)
	check(picture.save_png(source) == OK, "synthetic PNG")
	var original: PackedByteArray = FILES.read(source).bytes
	var package := ProjectSettings.globalize_path("user://original.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project, package)).ok, "baseline package")
	var package_hash := FileAccess.get_sha256(package)
	var bridge: String = ui.store.bridge.document_json()
	var before := state()
	for mode in ["cancel", "deadline", "eof", "source"]:
		var job := PausedJob.new(); check(start(job) == "", "start prepare barrier " + mode)
		await wait_job(job, true)
		if job.done: continue
		match mode:
			"cancel": job.cancel()
			"deadline": job.deadline_ms = 0
			"eof": job.stdio.close(); job.stdio = null; job.output_eof = true
			"source":
				write(source, PackedByteArray([1,2,3]))
				write(job.directory.path_join("test-prepare-release"), PackedByteArray([1]))
		await wait_job(job)
		check(not accepted(job) and job.commit(ui.store) != "" and state() == before, "fault prevents all publication " + mode)
		check(not DirAccess.dir_exists_absolute(job.directory), "registered asset scratch retired " + mode)
		write(source, original)
	var corrupt := CorruptJob.new(); check(start(corrupt) == "", "corrupted asset bundle")
	await wait_job(corrupt)
	check(not accepted(corrupt) and corrupt.commit(ui.store) != "" and state() == before, "corrupt binary transfer refused")
	var missing := MissingJob.new()
	check(start(missing) != "" and not DirAccess.dir_exists_absolute(missing.directory), "missing executable retires reservation")
	for mode in ["wrong-request", "regress", "flood", "partial", "crash", "diagnostic", "premature-success", "invalid-error"]:
		var fault := FaultJob.new(); fault.mode = mode
		check(start(fault) == "", "faulty asset IPC " + mode)
		await wait_job(fault)
		check(not accepted(fault) and fault.commit(ui.store) != "" and state() == before, "IPC refuses publication " + mode)
	var unknown := FaultJob.new(); check(start(unknown) == "", "unknown scratch owner")
	write(unknown.directory.path_join("user-file"), PackedByteArray([1]))
	write(unknown.directory.path_join(JOB.OUTPUT_MARKER), JSON.stringify({"request":token(), "path":"editor/" + "f".repeat(64) + ".png"}).to_utf8_buffer())
	unknown.shutdown()
	check(FileAccess.file_exists(unknown.directory.path_join("user-file")) and FileAccess.file_exists(unknown.directory.path_join(JOB.OUTPUT_MARKER)), "unknown/wrong owner paths preserved")
	for file in ["user-file", JOB.OUTPUT_MARKER, unknown.PRESENCE.MARKER]: DirAccess.remove_absolute(unknown.directory.path_join(file))
	DirAccess.remove_absolute(unknown.directory)
	var oversized := PackedByteArray(); oversized.resize(ui.store.HISTORY_BYTES + 1); write(source, oversized)
	var over_file := JOB.new(); check(start(over_file) == "", "large asset file")
	await wait_job(over_file)
	check(not accepted(over_file) and str(over_file.result).contains("16 MiB") and state() == before, "asset file refused before decode/history allocation")
	write(source, original)
	oversized.clear()
	var over_record := record.duplicate(true); over_record.attribution.notice = "x".repeat(JOB.REQUEST_LIMIT)
	var over_request := JOB.new()
	check(start(over_request, over_record).contains("24 MiB") and over_request.directory == "", "request refused before child directory")
	over_record.clear()
	for mode in ["cancel", "save", "owner", "gesture"]:
		var ready := JOB.new(); check(start(ready) == "", "ready result " + mode)
		await wait_job(ready)
		check(accepted(ready), "asset prepares native command " + str(ready.result))
		var target: RefCounted = ui.store
		match mode:
			"cancel": ready.cancel()
			"save": check(ui.store.save_project(project) == "", "save advances command epoch")
			"owner":
				target = STORE.new(); target.document = ui.store.document.duplicate(true); target.project_path = project; target.command_epoch = ui.store.command_epoch
			"gesture": ui.store.begin_gesture("pending")
		check(ready.commit(target) != "" and state() == before, "stale result cannot publish " + mode)
		if mode == "gesture": ui.store.cancel_gesture()
	var guarded := GuardedStore.new(); guarded.document = ui.store.document.duplicate(true); guarded.project_path = project
	var success := JOB.new(); check(start(success, {}, "DEFAULT", guarded) == "", "guarded store launch")
	await wait_job(success)
	check(accepted(success) and success.command_prepared and success.generated_all and success.source_rechecked, "native decode and final command proof")
	if not accepted(success): await finish(); return
	var new_path: String = success.bundle.blob_paths[0]
	check(not FileAccess.file_exists(project.path_join(new_path)), "prepare leaves project files absent")
	var reentrant: Array[String] = []
	guarded.changed.connect(func(): reentrant.append(success.commit(guarded)), CONNECT_ONE_SHOT)
	check(success.commit(guarded) == "" and guarded.forbidden == 0, "parent installs without command preparation")
	check(reentrant.size() == 1 and reentrant[0] != "", "changed callback cannot replay consumed asset")
	check(success.commit(guarded) != "", "consume before callback")
	check(guarded.document.assets.size() == 1 and guarded.undo_stack.size() == 1, "one atomic asset command")
	check(guarded.undo() == "" and guarded.document.assets.is_empty() and guarded.redo() == "", "binary undo and redo")
	# Regular live store and source replacement retain exact old bytes in history.
	var live := JOB.new(); check(start(live) == "", "live asset")
	await wait_job(live)
	check(live.commit(ui.store) == "", "live asset install")
	var first: Dictionary = ui.store.document.assets[0].duplicate(true)
	picture.fill(Color.RED); check(picture.save_png(source) == OK, "replacement fixture")
	var replacement: PackedByteArray = FILES.read(source).bytes
	var update := JOB.new(); check(start(update, first) == "", "replace asset source")
	await wait_job(update); check(update.commit(ui.store) == "", "replace source atomically")
	check(ui.store.undo() == "" and ui.store.document.assets[0] == first and FILES.read(project.path_join(first.path)).bytes == original, "undo exact old asset")
	check(ui.store.redo() == "" and FILES.read(project.path_join(ui.store.document.assets[0].path)).bytes == replacement, "redo exact replacement")
	var edited: Dictionary = ui.store.document.assets[0].duplicate(true)
	edited.material = {"albedo_rgba":[255,255,255,255], "metallic_per_mille":0, "roughness_per_mille":700, "double_sided":false}
	var material := JOB.new(); check(start(material, edited, "") == "", "metadata-only edit")
	await wait_job(material); check(material.commit(ui.store) == "", "native metadata-only candidate")
	before = state()
	var invalid := edited.duplicate(true); invalid.collision[0].size_cm = [-1,200,200]
	var bad := JOB.new(); check(start(bad, invalid, "") == "", "invalid proxy candidate")
	await wait_job(bad)
	check(not accepted(bad) and bad.commit(ui.store) != "" and state() == before, "invalid geometry preserves state")
	# Real worker checks previous files again after potentially expensive prepare.
	var prior := PausedJob.new(); check(start(prior, edited, "") == "", "prior payload mutation")
	await wait_job(prior, true)
	var prior_path: String = project.path_join(edited.path)
	if not prior.done:
		write(prior_path, PackedByteArray([8,9])); write(prior.directory.path_join("test-prepare-release"), PackedByteArray([1]))
		await wait_job(prior)
		check(not accepted(prior) and state() == before, "prior binary mutation rejects candidate")
		write(prior_path, replacement)
	check(ui.store.save_project(project) == "" and ui.store.autosave() == "", "save/recovery after asset adoption")
	var reopened := STORE.new(); check(reopened.open_project(project) == "" and reopened.document.assets == ui.store.document.assets, "asset reopens")
	check(FileAccess.get_sha256(package) == package_hash and FILES.read(source).bytes == replacement, "original package/source preserved")
	check(ui.store.bridge.document_json() == bridge, "candidate validation preserves previously loaded bridge")
	# Options can be changed and restored within one frame; revision still cancels.
	ui.author_panel.open(); ui.author_panel.tabs.current_tab = 3
	var ui_record := record.duplicate(true); ui_record.id = "ui-asset"
	before = state()
	ui.author_panel._start_asset(ui_record, source)
	check(ui.busy and ui.author_panel.asset_cancel.visible, "UI shows cancellable asset work")
	var controls: Dictionary = ui.author_panel.asset_fields
	var saved: String = controls.source.text
	controls.source.text = "changed"; controls.source.text_changed.emit("changed")
	controls.source.text = saved; controls.source.text_changed.emit(saved)
	await wait_ui()
	check(state() == before, "same-frame restored option still cancels")
	ui.author_panel._start_asset(ui_record, source); ui.author_panel.hide(); await wait_ui()
	check(state() == before, "closed authoring cancels")
	ui.author_panel.open(); ui.author_panel.tabs.current_tab = 3
	ui.author_panel._start_asset(ui_record, source); await wait_ui()
	check(ui.store.document.assets.size() == 2 and ui.author_panel.feedback.text.begins_with("Applied"), "UI applies one asset")
	check(ui.store.undo() == "" and ui.store.redo() == "", "UI command supports undo and redo")
	await finish()
func finish() -> void:
	ui.store.dirty = false; ui.queue_free(); await process_frame
	print("asset_native_validator: ", "PASS" if failures.is_empty() else failures, "; checks=", checks)
	quit(0 if failures.is_empty() else 1)
