extends "res://tests/heightmap_import_validator.gd"
const JOB := preload("res://scripts/heightmap_native_job.gd")

class PausedJob extends JOB:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var index := arguments.find("--")
		arguments.insert(index, "--script")
		arguments.insert(index + 1, ProjectSettings.globalize_path("res://tests/command_worker_fixture.gd"))
		return super._spawn(path, arguments)

class StopJob extends JOB:
	var reached := false
	var target := "validate"
	func _event(line: PackedByteArray) -> void:
		super._event(line)
		if progress.get("stage") == target and not reached:
			reached = true
			cancel()

class MissingJob extends JOB:
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary: return {}

class FaultJob extends JOB:
	var mode := "wait"
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON"), PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/native_child_fixture.py"), mode, identity, directory]), false)

class CorruptJob extends JOB:
	func _finish_result() -> void:
		if result.get("ok", false) and result.data.get("ok", false):
			var file := FileAccess.open(directory.path_join("bundle.bin"), FileAccess.WRITE)
			file.store_8(0); file.close()
		super._finish_result()

var options := {}
var original := PackedByteArray()
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func accepted(job: RefCounted) -> bool:
	return job.result.get("ok", false) and job.result.get("data", {}).get("ok", false) and not job.bundle.is_empty()
func start(job: RefCounted, previous: Dictionary = {}, store: RefCounted = null, id: String = "") -> String:
	return job.start_png(ui.store if store == null else store, options, not previous.is_empty(), "test", token() if id == "" else id, previous)
func reviewed(job: RefCounted) -> Dictionary:
	return {"layer_id":job.bundle.value.layer_id, "payloads":job.result.data.payloads}
func wait_job(job: RefCounted, prepare: bool = false) -> void:
	var until := Time.get_ticks_msec() + 20000
	var frames := 0
	while not job.done and Time.get_ticks_msec() < until:
		job.poll()
		if prepare and job.progress.get("stage") == "prepare": break
		frames += 1
		await process_frame
	check(job.progress.get("stage") == "prepare" and not job.done if prepare else job.done, "PNG reaches requested state: " + str(job.progress) + " " + str(job.result).left(600))
	check(frames > 0, "PNG work yields frames")
	if Time.get_ticks_msec() >= until: job.shutdown()
	if not prepare: check(job.exited and job.pid == -1, "owned PNG child exits/reaps")
func stage_ui() -> void:
	ui.author_panel._stage_heightmap(options.path, Vector2i.ZERO, 3200, 0, 1, 500, options.attribution)
	await wait_png()
	check(ui.author_panel.heightmap_candidate != null, "UI gets fresh reviewed PNG: " + ui.status_label.text)

func run() -> void:
	root.size = Vector2i(1024, 720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var project := ProjectSettings.globalize_path("user://png-native-project")
	check(ui.store.save_project(project) == "", "save synthetic PNG project")
	var heights := PackedInt64Array(); heights.resize(17 * 17); heights.fill(0); heights[8 * 17 + 8] = 100
	original = PNG.encode(heights, 17).bytes
	options = {"path":ProjectSettings.globalize_path("user://original.png"), "cell":[0,0], "spacing":3200, "offset":0, "step":1, "accuracy":500, "attribution":{"source":"Synthetic PNG", "license":"MIT", "notice":"private test fixture"}}
	write(options.path, original)
	var package := ProjectSettings.globalize_path("user://original.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project, package)).ok, "baseline package")
	var package_hash := FileAccess.get_sha256(package)
	var bridge: String = ui.store.bridge.document_json()
	var before := state()
	var review := JOB.new()
	check(start(review) == "", "start async PNG review")
	await wait_job(review)
	check(accepted(review) and review.generated_all and review.expected_cells == 0 and review.command_prepared, "PNG native and command preparation succeeds: " + str(review.result))
	if not accepted(review): finish(); return
	var previous := reviewed(review)
	check(review.bundle.blob_paths.size() == 1 and review.bundle.patches.size() == 2, "one tile plus source notice")
	check(not DirAccess.dir_exists_absolute(review.directory), "dynamic PNG candidate retired after success")
	check(review.commit(ui.store) != "" and state() == before, "review cannot publish")
	check(not FileAccess.file_exists(project.path_join(review.bundle.value.heightmap.path)), "review installs no project file")
	for phase in ["validate", "open", "generate"]:
		var stopped := StopJob.new(); stopped.target = phase
		check(start(stopped) == "", "start cancellation at " + phase)
		await wait_job(stopped)
		check(stopped.reached and stopped.cancelled and not accepted(stopped) and not DirAccess.dir_exists_absolute(stopped.directory), "cancel retires registered PNG at " + phase)
	for mode in ["cancel", "deadline", "eof", "source"]:
		var paused := PausedJob.new()
		check(start(paused, previous) == "", "start real prepare barrier " + mode)
		await wait_job(paused, true)
		if paused.done: continue
		match mode:
			"cancel": paused.cancel()
			"deadline": paused.deadline_ms = 0
			"eof": paused.stdio.close(); paused.stdio = null; paused.output_eof = true
			"source":
				var changed := original.duplicate(); changed[changed.size()-1] ^= 1
				write(options.path, changed)
				write(paused.directory.path_join("test-prepare-release"), PackedByteArray([1]))
		await wait_job(paused)
		check(not accepted(paused) and paused.commit(ui.store) != "" and not DirAccess.dir_exists_absolute(paused.directory), "prepare fault refuses and retires " + mode)
		check(state() == before, "fault preserves document/history " + mode)
		write(options.path, original)
	# Ready results still require matching owner/epoch and can be cancelled.
	for mode in ["cancel-ready", "save", "owner"]:
		var ready := JOB.new(); check(start(ready, previous) == "", "start ready-result guard " + mode)
		await wait_job(ready)
		check(accepted(ready), "ready result before guard " + mode)
		var target: RefCounted = ui.store
		match mode:
			"cancel-ready": ready.cancel()
			"save": check(ui.store.save_project(project) == "", "unchanged save advances epoch")
			"owner":
				target = STORE.new(); target.document = ui.store.document.duplicate(true); target.project_path = project; target.command_epoch = ui.store.command_epoch
		check(ready.commit(target) != "" and state() == before, "ready result cannot bypass guard " + mode)
	# A changed original after review must require new review, even if it is valid.
	heights[8 * 17 + 8] = 200
	var updated: PackedByteArray = PNG.encode(heights, 17).bytes
	write(options.path, updated)
	var changed := JOB.new(); check(start(changed, previous) == "", "start changed original adoption")
	await wait_job(changed)
	check(not accepted(changed) and str(changed.result).contains("since review"), "changed original rejected before native publication")
	write(options.path, original)
	var corrupt := CorruptJob.new(); check(start(corrupt) == "", "start corrupt transfer")
	await wait_job(corrupt)
	check(not accepted(corrupt) and corrupt.commit(ui.store) != "", "corrupt PNG bundle rejected")
	var missing := MissingJob.new()
	check(start(missing) != "" and not DirAccess.dir_exists_absolute(missing.directory), "missing native executable retires reservation")
	var occupied := ProjectSettings.globalize_path("user://import-jobs/").path_join(token())
	DirAccess.make_dir_recursive_absolute(occupied)
	var collision := JOB.new()
	check(start(collision, {}, null, occupied.get_file()) != "" and DirAccess.dir_exists_absolute(occupied), "existing scratch preserved")
	DirAccess.remove_absolute(occupied)
	for mode in ["wrong-request", "regress", "flood", "partial", "crash", "diagnostic", "premature-success", "invalid-error"]:
		var fault := FaultJob.new(); fault.mode = mode
		check(start(fault) == "", "start faulty PNG IPC " + mode)
		await wait_job(fault)
		check(not accepted(fault) and state() == before, "invalid IPC cannot publish " + mode)
	# The output registry never follows links, malformed identities or unknown paths.
	var unknown := FaultJob.new(); check(start(unknown) == "", "start unknown scratch fixture")
	write(unknown.directory.path_join("user-file"), PackedByteArray([1]))
	write(unknown.directory.path_join(JOB.OUTPUT_MARKER), JSON.stringify({"request":token(), "sha256":"f".repeat(64)}).to_utf8_buffer())
	unknown.shutdown()
	check(FileAccess.file_exists(unknown.directory.path_join("user-file")) and FileAccess.file_exists(unknown.directory.path_join(JOB.OUTPUT_MARKER)), "unknown and wrong-owner marker retained")
	for file in ["user-file", JOB.OUTPUT_MARKER, unknown.PRESENCE.MARKER]: DirAccess.remove_absolute(unknown.directory.path_join(file))
	DirAccess.remove_absolute(unknown.directory)
	var large := options.duplicate(true); large.extension = "x".repeat(JOB.REQUEST_LIMIT)
	var over := JOB.new()
	check(over.start_png(ui.store, large, false, "test", token()).contains("24 MiB") and over.directory == "", "request cap before launch")
	check(JOB.new().start_png(ui.store, options, true, "test", token()).contains("reviewed"), "no unreviewed adoption")
	for mode in ["oversized", "png", "spacing", "cell", "attribution"]:
		var saved := options.duplicate(true)
		match mode:
			"oversized":
				var bytes := PackedByteArray(); bytes.resize(PNG.MAX_BYTES + 1); write(options.path, bytes)
			"png": write(options.path, PackedByteArray([1,2,3]))
			"spacing": options.spacing = 3000
			"cell": options.cell = null
			"attribution": options.attribution.license = ""
		var invalid := JOB.new(); check(start(invalid) == "", "start invalid PNG " + mode)
		await wait_job(invalid)
		check(not accepted(invalid) and state() == before, "invalid PNG refuses atomically " + mode)
		options = saved; write(options.path, original)
	check(ui.store.bridge.document_json() == bridge and state() == before, "all rejected jobs preserve live bridge/history")
	# The independent authoring panel has its own cancel control and selections.
	ui.author_panel.open()
	for mode in ["option", "layer", "document", "project", "candidate", "gesture", "close", "cancel"]:
		await stage_ui()
		if ui.author_panel.heightmap_candidate == null: finish(); return
		ui.author_panel._adopt_heightmap()
		var pending: RefCounted = ui.import_job
		check(pending is JOB and ui.busy and ui.author_panel.heightmap_cancel.visible, "authoring starts owned adoption " + mode)
		var saved_document: Dictionary = ui.store.document.duplicate(true)
		match mode:
			"option":
				ui.author_panel.heightmap_controls.step.value += 1
				ui.author_panel.heightmap_controls.step.value -= 1
			"layer":
				ui.canvas.set_layer_state("heightmaps", {"locked":true}); ui.layers.state_changed.emit()
				ui.canvas.set_layer_state("heightmaps", {}); ui.layers.state_changed.emit()
			"document": ui.store.document.theme += " changed"
			"project": ui.store.project_path += "-changed"
			"candidate": ui.author_panel.heightmap_candidate.value.layer_id = token()
			"gesture": check(ui.store.begin_gesture("temporary") == "", "begin gesture"); ui.store.cancel_gesture()
			"close": ui.author_panel.hide()
			"cancel": ui.author_panel.heightmap_cancel.pressed.emit()
		await wait_png()
		check(pending.exited and ui.author_panel.heightmap_candidate == null and not ui.author_panel.heightmap_cancel.visible, "stale/cancelled UI refuses " + mode)
		ui.store.document = saved_document; ui.store.project_path = project
		if mode == "close": ui.author_panel.open()
	check(state() == before, "UI faults retain state")
	# Actual pointer discard and keyboard activation in the nested review window.
	await stage_ui()
	await click(ui.author_panel.heightmap_review.get_cancel_button())
	check(ui.author_panel.heightmap_candidate == null and state() == before, "pointer discards review")
	await stage_ui()
	await capture("png-review")
	ui.author_panel.heightmap_review.get_ok_button().grab_focus()
	for down in [true, false]:
		var key := InputEventKey.new(); key.keycode = KEY_ENTER; key.pressed = down
		ui.author_panel.heightmap_review.push_input(key)
		await process_frame
	await wait_png()
	check(ui.store.document.heightmaps.size() == 1, "keyboard adopts reviewed PNG")
	check(ui.store.undo() == "", "undo keyboard adoption")
	ui.store.redo_stack.clear(); ui.store.history_bytes = 0
	ui.author_panel.open()
	before = state()
	var roads := STORE.new(); roads.document = ui.store.document.duplicate(true); roads.project_path = project
	roads.document.nodes = [{"id":"a","position":[10000,0,20000],"level":0},{"id":"b","position":[30000,0,20000],"level":0}]
	roads.document.roads = [{"id":"road","from":"a","to":"b","points":[[10000,0,20000],[30000,0,20000]],"widths_cm":[800],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}]
	var generated := JOB.new(); check(start(generated, {}, roads) == "", "start PNG road generation")
	await wait_job(generated)
	check(accepted(generated) and generated.expected_cells == 1 and generated.generated_all, "one real affected terrain/road cell generated")
	var guarded := preload("res://tests/command_guard_store.gd").new()
	guarded.document = ui.store.document.duplicate(true); guarded.project_path = project
	var guard := JOB.new(); check(start(guard, previous, guarded) == "", "start guarded PNG adoption")
	await wait_job(guard)
	check(accepted(guard), "guarded command prepared")
	if accepted(guard):
		var reentrant := []
		guarded.changed.connect(func(): reentrant.append(guard.commit(guarded)), CONNECT_ONE_SHOT)
		guarded.forbid_preparation = true
		check(guard.commit(guarded) == "" and guarded.forbidden_calls == 0, "final PNG install skips native/command preparation")
		guarded.forbid_preparation = false
		check(reentrant.size() == 1 and reentrant[0] != "" and guard.commit(guarded) != "", "single-use publication before changed callbacks")
		check(guarded.undo() == "" and guarded.redo() == "", "prepared binary Undo/Redo")
	# Real UI adoption/replacement retains both exact byte images and provenance.
	await stage_ui(); ui.author_panel._adopt_heightmap(); await wait_png()
	check(ui.store.undo_stack.size() == 1 and ui.store.document.heightmaps.size() == 1, "UI publishes exactly one complete command")
	var first: Dictionary = ui.store.document.heightmaps[0].duplicate(true)
	check(ui.store.save_project(project) == "", "save PNG adoption")
	write(options.path, updated)
	await stage_ui()
	var old_path: String = project.path_join(first.path)
	write(old_path, original + PackedByteArray([1]))
	ui.author_panel._adopt_heightmap(); await wait_png()
	check(ui.store.document.heightmaps[0] == first, "changed prior file rejects replacement")
	write(old_path, original)
	await stage_ui(); ui.author_panel._adopt_heightmap(); await wait_png()
	var second: Dictionary = ui.store.document.heightmaps[0].duplicate(true)
	check(second.path != first.path and ui.store.document.attributions.size() == 2, "new layer retains old provenance")
	check(ui.store.undo_stack.back().binary_mementos.size() == 2, "both binary before/after images retained")
	check(ui.store.undo() == "" and ui.store.document.heightmaps[0] == first and not ui.store.dirty, "single Undo reaches saved prior tile")
	DirAccess.remove_absolute(project.path_join(second.path))
	check(ui.store.redo().contains("missing") and ui.store.document.heightmaps[0] == first, "missing immutable file atomically blocks Redo")
	write(project.path_join(second.path), updated)
	check(ui.store.redo() == "" and FILES.read(old_path).bytes == original, "Redo restores descriptor while old source bytes remain")
	check(ui.store.save_project(project) == "", "save replacement")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "" and reopened.document.attributions == ui.store.document.attributions, "reopen exact notices")
	check(FileAccess.get_sha256(package) == package_hash and FILES.read(options.path).bytes == updated, "original package/input preserved")
	# Owner close shuts down actual native work, not a mock task.
	ui.author_panel._stage_heightmap(options.path, Vector2i.ZERO, 3200, 0, 1, 500, options.attribution)
	var closing: RefCounted = ui.import_job
	ui.store.dirty = false; ui.queue_free(); await process_frame
	check(closing.exited and closing.pid == -1 and not DirAccess.dir_exists_absolute(closing.directory), "Editor close reaps PNG child/scratch")
	ui = null
	finish()

func finish() -> void:
	if ui != null:
		ui.store.dirty = false; ui.queue_free(); await process_frame
	print("heightmap_native_validator: ", "PASS" if failures.is_empty() else failures, "; checks=", checks)
	quit(0 if failures.is_empty() else 1)

func click(target: Button) -> void:
	check(target.is_visible_in_tree() and not target.disabled, "review button is available")
	await process_frame
	var point := target.get_global_rect().get_center() + Vector2(target.get_window().position)
	for down in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point; event.global_position = point
		event.button_index = MOUSE_BUTTON_LEFT; event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0; event.pressed = down
		root.push_input(event)
		await process_frame

func capture(name: String) -> void:
	var directory := OS.get_environment("MAPEDITOR_UX_CAPTURE_DIR")
	if directory == "" or DisplayServer.get_name() == "headless": return
	DirAccess.make_dir_recursive_absolute(directory)
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(directory.path_join(name + ".png")) == OK, "capture PNG review")
