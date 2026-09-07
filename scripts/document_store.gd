extends RefCounted
## Commands retain changed records only; snapshots are separate recovery state.
signal changed
const HISTORY_BYTES := 16 * 1024 * 1024
var document: Dictionary = {}
var project_path := ""
var undo_stack: Array[Dictionary] = []
var redo_stack: Array[Dictionary] = []
var history_bytes := 0
var dirty := false
var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")

func new_document() -> void:
	var stamp := Time.get_datetime_string_from_system(true) + "Z"
	document = {
		"map_id": "map-" + Crypto.new().generate_random_bytes(8).hex_encode(),
		"revision": 1, "bounds": {"min": [0, 0], "max": [102400, 102400]},
		"cell_size_cm": 51200, "seed": 42, "recipe_version": 1, "theme": "default",
		"terrain_base_cm": 0, "heightmaps": [], "nodes": [], "roads": [],
		"buildings": [], "zones": [], "assets": [], "placements": [], "attributions": [],
		"provenance": {"tool_id": "MiniEarthure-MapEditor", "version": "0.1.0", "build_id": "development", "fingerprint": "miniearthure-mapeditor-mit", "first_created": stamp, "last_edited": stamp},
	}
	project_path = ""
	_clear_history()
	_after_edit()

func open_project(path: String) -> String:
	var result: Dictionary = JSON.parse_string(bridge.open_project(path))
	if not result.ok:
		return reason(result)
	document = JSON.parse_string(bridge.document_json()).data
	project_path = path
	_clear_history()
	dirty = false
	changed.emit()
	return ""

func _clear_history() -> void:
	undo_stack.clear()
	redo_stack.clear()
	history_bytes = 0

func apply_command(label: String, patches: Array) -> String:
	var candidate := document.duplicate(true)
	var failure := _apply(candidate, patches, false)
	if failure != "":
		return failure
	var validation: Dictionary = JSON.parse_string(bridge.validate_document(JSON.stringify(candidate)))
	if not validation.ok:
		return reason(validation)
	var command := {"label": label, "patches": JSON.parse_string(JSON.stringify(patches))}
	var bytes := JSON.stringify(command).to_utf8_buffer().size()
	if bytes > HISTORY_BYTES:
		return "Command exceeds undo budget; split this import."
	document = validation.data.document
	undo_stack.append(command)
	history_bytes += bytes
	redo_stack.clear()
	while undo_stack.size() > 200 or history_bytes > HISTORY_BYTES:
		history_bytes -= JSON.stringify(undo_stack.pop_front()).to_utf8_buffer().size()
	_after_edit()
	return ""

func undo() -> void:
	if undo_stack.is_empty():
		return
	var command: Dictionary = undo_stack.pop_back()
	_apply(document, command.patches, true)
	history_bytes -= JSON.stringify(command).to_utf8_buffer().size()
	redo_stack.append(command)
	_after_edit()

func redo() -> void:
	if redo_stack.is_empty():
		return
	var command: Dictionary = redo_stack.pop_back()
	_apply(document, command.patches, false)
	undo_stack.append(command)
	history_bytes += JSON.stringify(command).to_utf8_buffer().size()
	_after_edit()

func _apply(target: Dictionary, patches: Array, reverse: bool) -> String:
	var ordered := patches.duplicate()
	if reverse:
		ordered.reverse()
	for patch: Dictionary in ordered:
		var field := str(patch.get("field", ""))
		if field not in ["nodes", "roads", "buildings", "zones", "assets", "placements", "heightmaps", "attributions"]:
			return "Unsupported command field: " + field
		var before: Variant = patch.get("after" if reverse else "before")
		var after: Variant = patch.get("before" if reverse else "after")
		var records: Array = target[field]
		var index := -1
		for i in range(records.size()):
			if str(records[i].get("id", records[i].get("source", JSON.stringify(records[i].get("cell", {}))))) == str(patch.id):
				index = i
				break
		if before == null and index >= 0:
			return "Object already exists: " + str(patch.id)
		if before != null and (index < 0 or JSON.parse_string(JSON.stringify(records[index])) != JSON.parse_string(JSON.stringify(before))):
			return "Document changed since command creation."
		if index >= 0:
			records.remove_at(index)
		if after != null:
			records.append(after.duplicate(true))
	return ""

func _after_edit() -> void:
	document.provenance.last_edited = Time.get_datetime_string_from_system(true) + "Z"
	dirty = true
	changed.emit()

func save_project(path: String) -> String:
	var validation: Dictionary = JSON.parse_string(bridge.validate_document(JSON.stringify(document)))
	if not validation.ok:
		return reason(validation)
	var failure := _atomic_write(path.path_join("document.json"), str(validation.data.canonical))
	if failure == "":
		project_path = path
		dirty = false
	return failure

func recovery_path() -> String:
	return "user://recovery/" + (project_path if project_path != "" else str(document.get("map_id", "new"))).sha256_text() + ".json"

func autosave() -> String:
	if document.is_empty():
		return ""
	return _atomic_write(recovery_path(), JSON.stringify({"project_path": project_path, "document": document}))

func recover(path: String) -> String:
	if not FileAccess.file_exists(path):
		return "Recovery snapshot does not exist."
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() > 64 * 1024 * 1024:
		return "Recovery snapshot exceeds supported size."
	var value: Variant = JSON.parse_string(file.get_as_text())
	if value is not Dictionary or value.get("document") is not Dictionary:
		return "Invalid recovery snapshot."
	var validation: Dictionary = JSON.parse_string(bridge.validate_document(JSON.stringify(value.document)))
	if not validation.ok:
		return reason(validation)
	document = validation.data.document
	project_path = str(value.get("project_path", ""))
	_clear_history()
	_after_edit()
	return ""

func _atomic_write(path: String, text: String) -> String:
	var absolute := ProjectSettings.globalize_path(path)
	var err := DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	if err != OK:
		return error_string(err)
	var temporary := absolute + ".tmp"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return error_string(FileAccess.get_open_error())
	file.store_string(text)
	file.flush()
	var write_error := file.get_error()
	file.close()
	if write_error != OK:
		return error_string(write_error)
	var backup := absolute + ".previous"
	if FileAccess.file_exists(absolute):
		if FileAccess.file_exists(backup):
			err = DirAccess.remove_absolute(backup)
			if err != OK:
				return error_string(err)
		err = DirAccess.rename_absolute(absolute, backup)
		if err != OK:
			return error_string(err)
	err = DirAccess.rename_absolute(temporary, absolute)
	if err != OK and FileAccess.file_exists(backup):
		DirAccess.rename_absolute(backup, absolute)
	return "" if err == OK else error_string(err)

func reason(result: Dictionary) -> String:
	return "%s: %s" % [result.error.code, result.error.message]
