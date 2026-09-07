extends RefCounted
## Editor-owned export/launch adapter. No game repository or runtime dependency.
var process_start: Callable = func(executable: String, arguments: PackedStringArray) -> int:
	return OS.create_process(executable, arguments, false)

static func error(code: String, message: String) -> Dictionary:
	return {"ok": false, "error": {"code": code, "message": message}}

static func check_client(executable: String) -> Dictionary:
	if executable.is_empty() or not FileAccess.file_exists(executable):
		return error("E_CLIENT_MISSING", "Choose an installed MiniEarthure Client executable.")
	return {"ok": true}

static func prepare(project: String, snapshot: String, expected_document: String, x_cm: int, y_cm: int, surface: String) -> Dictionary:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var exported: Dictionary = JSON.parse_string(bridge.export_project(project, snapshot))
	if not exported.ok:
		return exported
	var opened: Dictionary = JSON.parse_string(bridge.open_package(snapshot))
	if not opened.ok:
		return opened
	if str(bridge.canonical_document()) != expected_document:
		return error("E_SNAPSHOT_CHANGED", "Project changed while exporting. Snapshot retained; retry test drive.")
	var spawn: Dictionary = JSON.parse_string(bridge.spawn(x_cm, y_cm, surface))
	if not spawn.ok:
		return spawn
	return {"ok": true, "data": {"path": snapshot, "inspection": exported.data, "spawn": spawn.data}}

func launch(executable: String, snapshot: String, x_cm: int, y_cm: int, surface: String) -> Dictionary:
	var checked := check_client(executable)
	if not checked.ok:
		return checked
	if not FileAccess.file_exists(snapshot):
		return error("E_SNAPSHOT_MISSING", "Test-drive snapshot is missing.")
	# Argument vector, never a shell command. Spaces and metacharacters stay literal.
	var arguments := PackedStringArray(["--", "--test-drive", "--map-file", snapshot,
		"--spawn-x", "%.2f" % (float(x_cm) / 100), "--spawn-y", "%.2f" % (float(y_cm) / 100),
		"--surface-id", surface])
	var pid := int(process_start.call(executable, arguments))
	if pid <= 0:
		return error("E_CLIENT_START", "Client could not start. Check the executable and its permissions.")
	return {"ok": true, "data": {"pid": pid, "path": snapshot}}
