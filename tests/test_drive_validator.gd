extends SceneTree
const LAUNCHER := preload("res://scripts/test_drive_launcher.gd")
var failures: Array[String] = []
var calls: Array[Dictionary] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	_run.call_deferred()

func settle(ui: Node) -> void:
	for _i in range(500):
		await create_timer(0.01).timeout
		if not ui.busy:
			return
	check(false, "packaging worker deadline")

func _run() -> void:
	var ui: Node = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var directory := ProjectSettings.globalize_path("user://drive contract $ literal " + Crypto.new().generate_random_bytes(6).hex_encode())
	check(ui.store.save_project(directory) == "", "save synthetic project")
	ui._test_drive()
	ui.drive_dialog.hide()
	ui.client_path.text = directory + "/missing-client"
	ui._launch_test_drive()
	check(ui.last_drive_result.error.code == "E_CLIENT_MISSING", "missing Client is actionable")
	ui.client_path.text = OS.get_executable_path()
	ui.test_drive_launcher.process_start = func(executable: String, arguments: PackedStringArray) -> int:
		calls.append({"executable": executable, "arguments": arguments})
		return 1234
	ui.drive_x.value = 120.25
	ui.drive_y.value = 130.75
	ui._launch_test_drive()
	await settle(ui)
	check(ui.last_drive_result.get("ok", false) and calls.size() == 1, "save/package/launch succeeds once")
	if calls.size() == 1:
		var path: String = ui.last_drive_result.data.path
		check(calls[0].arguments == PackedStringArray(["--", "--test-drive", "--map-file", path, "--spawn-x", "120.25", "--spawn-y", "130.75", "--surface-id", "terrain"]), "Client CLI contract and centimetre precision")
		var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
		check(JSON.parse_string(bridge.open_package(path)).ok, "launch snapshot is valid package")
		check(str(bridge.canonical_document()) == str(ui.drive_request.document), "snapshot matches current editor document")
		var mismatch := LAUNCHER.prepare(directory, directory + "/mismatch.memap", "{}", 12025, 13075, "terrain")
		check(not mismatch.ok and mismatch.error.code == "E_SNAPSHOT_CHANGED", "changed disk document cannot launch")
		var invalid := LAUNCHER.prepare(directory, directory + "/invalid.memap", ui.drive_request.document, 12025, 13075, "missing-surface")
		check(not invalid.ok, "invalid surface rejected before process launch")
		var adapter := LAUNCHER.new()
		adapter.process_start = func(_exe: String, args: PackedStringArray) -> int:
			check(args[3] == path and args[9] == "surface with $ literal", "arguments passed literally")
			return -1
		check(adapter.launch(OS.get_executable_path(), path, 0, 0, "surface with $ literal").error.code == "E_CLIENT_START", "process creation failure reported")
	ui._launch_test_drive()
	ui.store.new_document()
	await settle(ui)
	check(ui.last_drive_result.get("error", {}).get("code") == "E_DOCUMENT_CHANGED" and calls.size() == 1, "document replacement cancels stale launch")
	# Optional external integration: only an installed executable, no private source dependency.
	var installed := OS.get_environment("MINIEARTHURE_TEST_CLIENT")
	if not installed.is_empty():
		check(ui.store.save_project(directory + "/native") == "", "native test project")
		ui.client_path.text = installed
		ui.test_drive_launcher.process_start = func(executable: String, arguments: PackedStringArray) -> int:
			return OS.create_process(executable, PackedStringArray(["--headless", "--quit-after", "600"]) + arguments, false)
		ui._launch_test_drive()
		await settle(ui)
		check(ui.last_drive_result.get("ok", false), "installed native Client launched")
		if ui.last_drive_result.get("ok", false):
			var pid: int = ui.last_drive_result.data.pid
			for _i in range(1500):
				if not OS.is_process_running(pid):
					break
				await create_timer(0.02).timeout
			check(not OS.is_process_running(pid), "native Client exits bounded test")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("test_drive_validator: %s" % ("PASS" if failures.is_empty() else str(failures)))
	quit(0 if failures.is_empty() else 1)
