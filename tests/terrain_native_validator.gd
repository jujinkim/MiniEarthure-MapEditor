extends "res://tests/heightmap_import_validator.gd"
const JOB := preload("res://scripts/terrain_native_job.gd")
class PausedJob extends JOB:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var index := arguments.find("--")
		arguments.insert(index, "--script")
		arguments.insert(index + 1, ProjectSettings.globalize_path("res://tests/command_worker_fixture.gd"))
		return super._spawn(path, arguments)
class PlanJob extends JOB:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var index := arguments.find("--")
		arguments.insert(index, "--script")
		arguments.insert(index + 1, ProjectSettings.globalize_path("res://tests/terrain_worker_fixture.gd"))
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
class MalformedJob extends JOB:
	var mode := "duplicate-output"
	func _finish_result() -> void:
		if result.get("ok", false) and result.data.get("ok", false):
			var transfer := COMMAND.read_bundle(directory, result.data)
			var command: Dictionary = JSON.parse_string(transfer.prepared.command_json)
			match mode:
				"duplicate-output": transfer.blob_paths.append(transfer.blob_paths[0])
				"extra-output":
					var bytes := PackedByteArray([1,2,3])
					var path := "editor/" + PAYLOADS.digest(bytes) + ".png"
					transfer.blob_paths.append(path); transfer.prepared.retained[path] = bytes
				"attribution": command.patches = [{"field":"attributions","id":"unexpected","before":null,"after":{"source":"unexpected","license":"MIT","notice":"synthetic"}}]
				"duplicate-tile": command.patches.append(command.patches[0].duplicate(true))
				"foreign-cell": command.patches[0].after.cell = {"x":99,"y":99}
				"changed-before": command.patches[0].before = {"cell":{"x":0,"y":0},"path":transfer.blob_paths[0]}
			transfer.prepared.command_json = JSON.stringify(command)
			DirAccess.remove_absolute(directory.path_join("bundle.bin"))
			COMMAND.write_bundle(directory, transfer, result.data)
		super._finish_result()
var stroke_request := {"stroke":[[6100,6100],[6700,6700]], "options":{"mode":"raise", "spacing_cm":800, "radius_cm":1600, "amount_cm":200, "target_cm":0}}
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func accepted(job: RefCounted) -> bool:
	return job.result.get("ok", false) and job.result.get("data", {}).get("ok", false) and not job.bundle.is_empty()
func start(job: RefCounted, store: RefCounted = null, id: String = "") -> String:
	return job.start_terrain(ui.store if store == null else store, stroke_request, "test", token() if id == "" else id)
func wait_job(job: RefCounted, prepare: bool = false, target: String = "prepare") -> void:
	var until := Time.get_ticks_msec() + 20000
	var frames := 0
	while not job.done and Time.get_ticks_msec() < until:
		job.poll()
		if prepare and job.progress.get("stage") == target: break
		frames += 1
		await process_frame
	check(job.progress.get("stage") == target and not job.done if prepare else job.done, "terrain reaches state: " + str(job.progress) + " " + str(job.result).left(600))
	check(frames > 0, "terrain work yields frames")
	if Time.get_ticks_msec() >= until: job.shutdown()
	if not prepare: check(job.exited and job.pid == -1, "terrain child reaped")
func wait_ui() -> void:
	var until := Time.get_ticks_msec() + 20000
	while ui.import_job != null and Time.get_ticks_msec() < until: await process_frame
	check(ui.import_job == null and not ui.busy, "terrain UI job completes: " + ui.status_label.text)
func run() -> void:
	root.size = Vector2i(1024,720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	check(ui.store.apply_command("Synthetic small terrain", [{"field":"bounds", "before":ui.store.document.bounds, "after":{"min":[0,0],"max":[12800,12800]}},{"field":"cell_size_cm","before":51200,"after":6400}]) == "", "small fixture")
	var project := ProjectSettings.globalize_path("user://terrain-native-project")
	check(ui.store.save_project(project) == "", "save synthetic terrain")
	var package := ProjectSettings.globalize_path("user://original.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project, package)).ok, "baseline package")
	var package_hash := FileAccess.get_sha256(package)
	var before := state()
	var bridge: String = ui.store.bridge.document_json()
	for phase in ["validate", "open", "generate"]:
		var stopped := StopJob.new(); stopped.target = phase
		check(start(stopped) == "", "start cancel at " + phase)
		await wait_job(stopped)
		check(stopped.reached and stopped.cancelled and not accepted(stopped) and not DirAccess.dir_exists_absolute(stopped.directory), "cancel retires terrain outputs at " + phase)
	for mode in ["cancel", "deadline", "eof"]:
		var paused := PausedJob.new()
		check(start(paused) == "", "prepare barrier " + mode)
		await wait_job(paused, true)
		if paused.done: continue
		match mode:
			"cancel": paused.cancel()
			"deadline": paused.deadline_ms = 0
			"eof": paused.stdio.close(); paused.stdio = null; paused.output_eof = true
		await wait_job(paused)
		check(not accepted(paused) and paused.commit(ui.store) != "" and not DirAccess.dir_exists_absolute(paused.directory), "prepare fault retires all terrain outputs " + mode)
	for mode in ["cancel-ready", "save", "owner", "gesture"]:
		var ready := JOB.new(); check(start(ready) == "", "ready guard " + mode)
		await wait_job(ready)
		check(accepted(ready) and ready.generated_all and ready.command_prepared and ready.bundle.patches.size() == 4, "four seam owners prepared with complete command: " + str(ready.result))
		if not accepted(ready): finish(); return
		check(not DirAccess.dir_exists_absolute(ready.directory), "success retires dynamic terrain candidate")
		for path: String in ready.bundle.blob_paths: check(not FileAccess.file_exists(project.path_join(path)), "prepared terrain publishes no payload")
		var target: RefCounted = ui.store
		match mode:
			"cancel-ready": ready.cancel()
			"save": check(ui.store.save_project(project) == "", "save advances epoch")
			"owner": target = STORE.new(); target.document = ui.store.document.duplicate(true); target.project_path = project; target.command_epoch = ui.store.command_epoch
			"gesture": check(ui.store.begin_gesture("temporary") == "", "temporary gesture"); ui.store.cancel_gesture()
		check(ready.commit(target) != "" and state() == before, "stale ready command refuses " + mode)
	var corrupt := CorruptJob.new(); check(start(corrupt) == "", "corrupt terrain transfer")
	await wait_job(corrupt)
	check(not accepted(corrupt) and corrupt.commit(ui.store) != "", "corrupt transfer cannot publish")
	for mode in ["duplicate-output", "extra-output", "attribution", "duplicate-tile", "foreign-cell", "changed-before"]:
		var malformed := MalformedJob.new(); malformed.mode = mode
		check(start(malformed) == "", "hash-valid malformed transfer " + mode)
		await wait_job(malformed)
		check(not accepted(malformed) and malformed.commit(ui.store) != "" and state() == before, "malformed terrain transfer refuses before installation " + mode)
	var missing := MissingJob.new()
	check(start(missing) != "" and not DirAccess.dir_exists_absolute(missing.directory), "missing engine retires reservation")
	for mode in ["wrong-request", "regress", "flood", "partial", "crash", "diagnostic", "premature-success", "invalid-error"]:
		var fault := FaultJob.new(); fault.mode = mode
		check(start(fault) == "", "terrain faulty IPC " + mode)
		await wait_job(fault)
		check(not accepted(fault) and state() == before, "invalid IPC cannot publish " + mode)
	var unknown := FaultJob.new(); check(start(unknown) == "", "unknown scratch fixture")
	write(unknown.directory.path_join("user-file"), PackedByteArray([1]))
	write(unknown.directory.path_join(JOB.OUTPUT_MARKER), JSON.stringify({"request":token(), "hashes":["f".repeat(64)]}).to_utf8_buffer())
	unknown.shutdown()
	check(FileAccess.file_exists(unknown.directory.path_join("user-file")) and FileAccess.file_exists(unknown.directory.path_join(JOB.OUTPUT_MARKER)), "unknown and wrong-owner marker preserved")
	for file in ["user-file", JOB.OUTPUT_MARKER, unknown.PRESENCE.MARKER]: DirAccess.remove_absolute(unknown.directory.path_join(file))
	DirAccess.remove_absolute(unknown.directory)
	for mode in ["spacing", "points", "radius", "nan", "mode"]:
		var saved := stroke_request.duplicate(true)
		match mode:
			"spacing": stroke_request.options.spacing_cm = 700
			"points": stroke_request.stroke.resize(2049)
			"radius": stroke_request.options.radius_cm = 999999
			"nan": stroke_request.options.amount_cm = NAN
			"mode": stroke_request.options.mode = "unknown"
		check(start(JOB.new()) != "", "invalid terrain refused before launch " + mode)
		stroke_request = saved
	check(ui.store.bridge.document_json() == bridge and state() == before, "all rejected work preserves live bridge/history")
	ui._set_tool("Terrain")
	ui.author_panel.open(); ui.author_panel.hide()
	for mode in ["tool", "layer", "options", "restore-option", "restore-brush", "document", "project", "cancel", "interaction"]:
		if mode == "restore-option": ui.canvas.author.options.radius_cm = roundi(ui.author_panel.fields.radius_cm.value * 100)
		var option_snapshot := JSON.stringify(ui.canvas.author.options)
		ui._start_terrain(stroke_request)
		var pending: RefCounted = ui.import_job
		check(pending is JOB and ui.busy, "UI starts asynchronous terrain " + mode)
		var document: Dictionary = ui.store.document.duplicate(true)
		match mode:
			"tool": ui.canvas.tool = "Select"; ui.canvas.tool = "Terrain"
			"layer": ui.canvas.set_layer_state("heightmaps", {"locked":true}); ui.canvas.set_layer_state("heightmaps", {})
			"options": ui.canvas.author.options.radius_cm += 1
			"restore-option":
				var control: SpinBox = ui.author_panel.fields.radius_cm
				control.value += control.step; control.value -= control.step
			"restore-brush":
				var control: OptionButton = ui.author_panel.fields.mode
				var original_mode := control.selected
				control.item_selected.emit((original_mode + 1) % control.item_count); control.item_selected.emit(original_mode)
			"document": ui.store.document.theme += " changed"
			"project": ui.store.project_path += "-changed"
			"cancel": ui._cancel_operation()
			"interaction": ui.canvas.cancel_interaction()
		if mode in ["restore-option", "restore-brush"]:
			check(JSON.stringify(ui.canvas.author.options) == option_snapshot and ui._terrain_selection() != pending.selection_signature, "same-frame restored options still invalidate terrain " + mode)
		await wait_ui()
		check(pending.exited and pending.cancelled, "UI mutation/cancel rejects terrain " + mode)
		ui.store.document = document; ui.store.project_path = project
	check(state() == before, "UI cancelled work leaves document/history intact")
	var guarded := preload("res://tests/command_guard_store.gd").new()
	guarded.document = ui.store.document.duplicate(true); guarded.project_path = project
	var guard := JOB.new(); check(start(guard, guarded) == "", "guarded terrain starts")
	await wait_job(guard)
	check(accepted(guard), "guarded command prepared")
	if accepted(guard):
		var reentrant := []
		guarded.changed.connect(func(): reentrant.append(guard.commit(guarded)), CONNECT_ONE_SHOT)
		guarded.forbid_preparation = true
		check(guard.commit(guarded) == "" and guarded.forbidden_calls == 0, "terrain final commit skips preparation")
		guarded.forbid_preparation = false
		check(reentrant.size() == 1 and reentrant[0] != "" and guard.commit(guarded) != "", "terrain is single use before callbacks")
		check(guarded.undo() == "" and guarded.redo() == "", "prepared binary Undo/Redo")
	ui._start_terrain(stroke_request); await wait_ui()
	check(ui.store.document.heightmaps.size() == 4, "UI adopts four seam owners")
	check(ui.store.save_project(project) == "", "save first terrain")
	before = state()
	var original := {}
	for tile: Dictionary in ui.store.document.heightmaps: original[tile.path] = FILES.read(project.path_join(tile.path)).bytes
	for mode in ["cancel", "source"]:
		var planning := PlanJob.new(); check(start(planning) == "", "actual raster plan barrier " + mode)
		await wait_job(planning, true, "validate")
		if planning.done: continue
		var path: String = original.keys()[0]
		if mode == "cancel": planning.cancel()
		else:
			write(project.path_join(path), original[path] + PackedByteArray([1]))
			write(planning.directory.path_join("test-plan-release"), PackedByteArray([1]))
		await wait_job(planning)
		check(not accepted(planning) and planning.commit(ui.store) != "" and state() == before and not DirAccess.dir_exists_absolute(planning.directory), "raster preparation fault preserves state and retires " + mode)
		if mode == "source":
			check(str(planning.result).contains("during brush preparation"), "decoded old raster is bound to initial input hash")
			write(project.path_join(path), original[path])
	var paused := PausedJob.new(); check(start(paused) == "", "prepare replacement for source mutation")
	await wait_job(paused, true)
	if not paused.done:
		var path: String = original.keys()[0]
		write(project.path_join(path), original[path] + PackedByteArray([1]))
		write(paused.directory.path_join("test-prepare-release"), PackedByteArray([1]))
		await wait_job(paused)
		check(not accepted(paused) and paused.commit(ui.store) != "" and state() == before, "source mutation during prepare rejects atomically")
		write(project.path_join(path), original[path])
	ui._start_terrain(stroke_request); await wait_ui()
	var after: Dictionary = ui.store.document.duplicate(true)
	check(after.heightmaps.size() == 4 and ui.store.undo_stack.back().binary_mementos.size() >= 4, "replacement retains old and new images")
	check(ui.store.undo() == "" and state() != before and not ui.store.dirty, "single Undo reaches saved terrain")
	check(ui.store.redo() == "" and ui.store.document == after, "Redo exact terrain descriptors")
	for path: String in original: check(FILES.read(project.path_join(path)).bytes == original[path], "original terrain image preserved")
	check(FileAccess.get_sha256(package) == package_hash, "original package preserved")
	var road_store := STORE.new(); road_store.document = ui.store.document.duplicate(true); road_store.project_path = project
	road_store.document.nodes = [{"id":"a","position":[2000,0,3000],"level":0},{"id":"b","position":[10000,0,3000],"level":0}]
	road_store.document.roads = [{"id":"road","from":"a","to":"b","points":[[2000,0,3000],[10000,0,3000]],"widths_cm":[800],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}]
	var generated := JOB.new(); check(start(generated, road_store) == "", "terrain road candidate starts")
	await wait_job(generated)
	check(accepted(generated) and generated.expected_cells == 4 and generated.generated_all, "all four actual terrain/road cells generate")
	ui._start_terrain(stroke_request)
	var closing: RefCounted = ui.import_job
	ui.store.dirty = false; ui.queue_free(); await process_frame
	check(closing.exited and closing.pid == -1 and not DirAccess.dir_exists_absolute(closing.directory), "owner close reaps terrain child and scratch")
	ui = null
	finish()
func finish() -> void:
	if ui != null:
		ui.store.dirty = false; ui.queue_free(); await process_frame
	print("terrain_native_validator: ", "PASS" if failures.is_empty() else failures, "; checks=", checks)
	quit(0 if failures.is_empty() else 1)
