extends SceneTree
const RECOVERY_FIXTURE := preload("res://tests/recovery_fixture.gd")
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/document_files.gd")
var failures: Array[String] = []
var checks := 0

class FailingFiles extends FILES:
	var phase := ""
	func _write_text(path: String, text: String) -> String:
		if phase == "write":
			super._write_text(path, "{incomplete")
			return "Injected write failure"
		return super._write_text(path, text)
	func _publish(source: String, destination: String) -> Error:
		if phase == "backup" and destination.ends_with(".previous"):
			return ERR_FILE_CANT_WRITE
		if phase == "primary" and not destination.ends_with(".previous"):
			return ERR_FILE_CANT_WRITE
		return super._publish(source, destination)

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func state(store: RefCounted) -> String:
	return JSON.stringify([store.document, store.undo_stack, store.redo_stack, store.history_bytes, store.dirty, store.project_path, store._disk_digest])

func edit(store: RefCounted, seed: int) -> String:
	return store.apply_command("Seed", [{"field": "seed", "before": store.document.seed, "after": seed}])

func write(path: String, value: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(value))
	file.close()

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var base := ProjectSettings.globalize_path("user://recovery-project")
	var store := STORE.new()
	store.new_document()
	check(store.save_project(base) == "", "initial project saved")
	var path := base.path_join("document.json")
	var original := FileAccess.get_sha256(path)
	check(edit(store, 43) == "", "unsaved edit")
	var before := state(store)
	for phase in ["write", "backup", "primary"]:
		var broken := FailingFiles.new()
		broken.phase = phase
		store.files = broken
		check(store.save_project(base) != "", phase + " failure reported")
		check(state(store) == before and FileAccess.get_sha256(path) == original, phase + " failure preserves memory/savepoint/primary")
		if phase == "primary":
			check(FileAccess.get_sha256(path + ".previous") == original, "failed primary publish retains complete previous document")
	store.files = FILES.new()
	check(store.save_project(base) == "" and not store.dirty, "retry succeeds without deleting interrupted candidates")
	check(FileAccess.get_sha256(path + ".previous") == original, "successful save preserves prior version")
	var restored := STORE.new()
	check(restored.recover(path + ".previous") == "" and restored.document.seed == 42 and restored.dirty, "explicit raw backup recovery")
	check(restored.save_project(base) == "", "selected backup can restore original project")
	check(store.save_project(base) != "", "stale editor detects changed primary")
	check(store.open_project(base) == "", "reopen updates disk baseline")
	var native := store.bridge
	before = state(store)
	check(store.open_project(base + "-missing") != "" and state(store) == before and store.bridge == native, "failed open preserves native session and document")
	check(edit(store, 55) == "" and RECOVERY_FIXTURE.write(store) == "", "retained checksummed recovery fixture")
	var recovery := RECOVERY_FIXTURE.path(store)
	var snapshot_digest := FileAccess.get_sha256(recovery)
	check(RECOVERY_FIXTURE.write(store) == "" and FileAccess.get_sha256(recovery) == snapshot_digest and not FileAccess.file_exists(recovery + ".previous"), "fixture does not rotate unchanged snapshots")
	check(restored.recover(recovery) == "" and restored.document.seed == 55 and restored.history_bytes == 0 and restored.undo_stack.is_empty() and restored.dirty, "recovery restores validated document with fresh history")
	check(restored.save_project(base) == "", "recovered edit saves when original base still matches")
	check(store.recover(recovery) == "" and store.save_project(base) != "", "old recovery cannot overwrite newer saved document")
	check(store.save_project(base + "-copy") == "", "Save As resolves stale recovery without replacing newer file")
	var prior_recovery := RECOVERY_FIXTURE.path(store)
	store.new_document()
	check(RECOVERY_FIXTURE.path(store) != prior_recovery and FileAccess.file_exists(recovery), "new session preserves old recovery and gets distinct path")
	var bad_path := base.path_join("bad.json")
	var valid: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(recovery))
	before = state(store)
	for kind in ["checksum", "version", "document", "origin"]:
		var bad := valid.duplicate(true)
		match kind:
			"checksum": bad.document.seed = 99
			"version": bad.recovery_version = 999
			"document": bad.document = []
			"origin": bad.project_path = "relative/path"
		write(bad_path, bad)
		check(store.recover(bad_path) != "" and state(store) == before, kind + " rejection preserves state")
	var file := FileAccess.open(bad_path, FileAccess.WRITE)
	file.store_string("{incomplete")
	file.close()
	check(store.recover(bad_path) != "" and state(store) == before, "truncated recovery rejected")
	file = FileAccess.open(bad_path, FileAccess.WRITE)
	file.seek(FILES.MAX_BYTES)
	file.store_8(0)
	file.close()
	check(store.recover(bad_path).contains("64 MiB") and state(store) == before, "oversized snapshot rejected before read")
	# A snapshot missing the current v1 envelope is rejected without mutation.
	write(bad_path, {"project_path": base, "document": valid.document})
	check(store.recover(bad_path) != "" and state(store) == before, "missing recovery version is rejected without changing memory or primary")
	# Process deaths are real, isolated child processes. No fixed sleep or shared data.
	for phase in ["before_backup", "before_primary", "after_primary"]:
		await crash_case(phase)
	await ui_failure_cases(recovery)
	print("document_recovery_validator: %s (%d assertions)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)

func crash_case(phase: String) -> void:
	var base := ProjectSettings.globalize_path("user://crash-" + phase)
	var store := STORE.new()
	store.new_document()
	check(store.save_project(base) == "", phase + " initial save")
	var original := FileAccess.get_sha256(base.path_join("document.json"))
	var output: Array = []
	# Godot consumes --path/--main-pack and can leave res:// without a disk root.
	var project := OS.get_environment("MAPEDITOR_TEST_PROJECT")
	if project == "": project = ProjectSettings.globalize_path("res://")
	var args := PackedStringArray(["--headless", "--path", project])
	var pack := OS.get_environment("MAPEDITOR_TEST_RESOURCE_PACK")
	if pack != "": args.append_array(["--main-pack", pack])
	# Test scripts are excluded from the pack; the child must inherit packed product code.
	args.append_array(["--script", project.path_join("tests/document_crash_writer.gd"), "--", base, phase])
	var exit_code := OS.execute(OS.get_executable_path(), args, output, true)
	check(exit_code != 0 and exit_code not in [2,3,4,5], phase + " child killed at save boundary, exit=" + str(exit_code))
	check(not str(output).contains("SCRIPT ERROR:"), phase + " child has no script failure")
	var marker := base.path_join("crash-phase.txt")
	check(FileAccess.file_exists(marker) and FileAccess.get_file_as_string(marker) == phase, phase + " child reached exact crash boundary: " + str(output))
	var reopened := STORE.new()
	check(reopened.open_project(base) == "", phase + " primary opens after process death")
	check(reopened.document.seed == (777 if phase == "after_primary" else 42), phase + " primary is complete old or complete new document")
	if phase != "before_backup":
		check(FileAccess.get_sha256(base.path_join("document.json.previous")) == original, phase + " previous version preserved")
	if phase != "after_primary":
		var pending := ""
		for name in DirAccess.get_files_at(base):
			if name.begins_with("document.json.pending-") and not name.ends_with(".previous"):
				pending = base.path_join(name)
		check(not pending.is_empty(), phase + " pending candidate discoverable")
		check(reopened.recover(pending) == "" and reopened.document.seed == 777, phase + " explicit pending recovery restores intended edit")
		check(reopened.save_project(base) == "", phase + " recovered candidate resaves normally")
	await process_frame

func ui_failure_cases(snapshot: String) -> void:
	var ui: Node = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var broken := FailingFiles.new()
	broken.phase = "write"
	ui.store.files = broken
	var original := state(ui.store)
	check(not ui.has_method("_autosave") and not ui.store.has_method("autosave"), "automatic recovery writer removed")
	for action in ["new", "recover", "close"]:
		ui._request_document_action(action, snapshot if action == "recover" else "")
		check(ui.unsaved_dialog.visible and state(ui.store)==original,"transition asks before discarding; no automatic write")
		ui.unsaved_dialog.hide()
		ui.unsaved_dialog.canceled.emit()
		check(ui.pending_document_action.is_empty() and state(ui.store)==original,"Cancel preserves current document")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
