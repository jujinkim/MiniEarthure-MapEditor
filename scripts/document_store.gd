extends RefCounted
## MapDocument is authoritative; views never become saved state.
signal changed
const PAYLOADS := preload("./authoring_files.gd")
const FILES := preload("./document_files.gd")
const HISTORY_BYTES := 16 * 1024 * 1024
const HISTORY_COMMANDS := 200
const RECORD_FIELDS := ["nodes", "roads", "buildings", "zones", "assets", "placements", "repetitions", "heightmaps", "attributions"]
const VALUE_FIELDS := ["bounds", "cell_size_cm", "seed", "recipe_version", "theme", "terrain_base_cm"]
var document: Dictionary = {}
var project_path := ""
var undo_stack: Array[Dictionary] = []
var redo_stack: Array[Dictionary] = []
# Serialized UTF-8 memento budget, shared by BOTH stacks (not process RSS).
var history_bytes := 0
var dirty := false
var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
var files := FILES.new()
var _saved_signature := ""
var _disk_path := ""
var _disk_digest := ""
var _recovery_id := ""
var _autosaved_signature := ""
var _gesture: Dictionary = {}

func new_document() -> void:
	bridge = ClassDB.instantiate("MapKitBridge")
	var stamp := Time.get_datetime_string_from_system(true) + "Z"
	document = {
		"map_id": "map-" + Crypto.new().generate_random_bytes(8).hex_encode(),
		"revision": 1, "bounds": {"min": [0, 0], "max": [102400, 102400]},
		"cell_size_cm": 51200, "seed": 42, "recipe_version": 1, "theme": "default",
		"terrain_base_cm": 0, "heightmaps": [], "nodes": [], "roads": [],
		"buildings": [], "zones": [], "assets": [], "placements": [], "attributions": [],
		"provenance": {"tool_id": "MiniEarthure-MapEditor", "version": "0.1.0", "build_id": "development", "fingerprint": "miniearthure-mapeditor-mit", "first_created": stamp, "last_edited": stamp},
	}
	document = _validate(document).data.document
	project_path = ""
	_reset_session()
	_after_edit()

func open_project(path: String) -> String:
	# A failed native open clears its bridge: retain the live bridge until success.
	var candidate: RefCounted = ClassDB.instantiate("MapKitBridge")
	var disk := path.path_join("document.json")
	var digest_before := files.digest(disk)
	var result: Dictionary = JSON.parse_string(candidate.open_project(path))
	if not result.ok:
		return reason(result) + " Use Recover to select a previous or pending snapshot."
	if files.digest(disk) != digest_before:
		return "Project changed while opening; retry Open."
	document = JSON.parse_string(candidate.document_json()).data
	bridge = candidate
	project_path = ProjectSettings.globalize_path(path).simplify_path()
	_reset_session()
	_disk_path = project_path.path_join("document.json")
	_disk_digest = digest_before
	_saved_signature = _signature(document)
	dirty = false
	changed.emit()
	return ""

func _reset_session() -> void:
	undo_stack.clear()
	redo_stack.clear()
	history_bytes = 0
	_gesture.clear()
	_saved_signature = ""
	_disk_path = ""
	_disk_digest = ""
	_recovery_id = Crypto.new().generate_random_bytes(12).hex_encode()
	_autosaved_signature = ""

func _validate(value: Dictionary) -> Dictionary:
	return JSON.parse_string(bridge.validate_document(JSON.stringify(value)))

func _signature(value: Dictionary) -> String:
	var content := value.duplicate(true)
	if content.get("provenance") is Dictionary:
		content.provenance.erase("last_edited")
	return JSON.stringify(content).sha256_text()

func _json_copy(value: Variant) -> Variant:
	return JSON.parse_string(JSON.stringify(value))

func record_id(field: String, record: Dictionary) -> String:
	if field == "attributions":
		return JSON.stringify([record.get("source", ""), record.get("license", ""), record.get("notice", "")])
	if field == "heightmaps":
		var cell: Variant = record.get("cell", {})
		if cell is not Dictionary or not cell.has_all(["x", "y"]): return ""
		if (cell.x is not int and cell.x is not float) or (cell.y is not int and cell.y is not float): return ""
		return JSON.stringify({"x": int(cell.get("x", 0)), "y": int(cell.get("y", 0))})
	return str(record.get("id", ""))

func _get_value(target: Dictionary, field: String, id: String) -> Variant:
	if field in VALUE_FIELDS:
		return target[field]
	for record: Dictionary in target.get(field, []):
		if record_id(field, record) == id:
			return record
	return null

func _patch_error(patch: Variant) -> String:
	if patch is not Dictionary or not patch.has_all(["field", "before", "after"]):
		return "A command requires field, before and after mementos."
	var field := str(patch.field)
	if field in VALUE_FIELDS:
		if patch.get("id", "") != "":
			return "Map-value commands have no record ID."
		return "Map values cannot be removed." if patch.before == null or patch.after == null else ""
	if field not in RECORD_FIELDS:
		return "Unsupported command field: " + field
	if not patch.get("id") is String or str(patch.id).is_empty():
		return "A record command requires a stable ID."
	for value in [patch.before, patch.after]:
		if value != null and (value is not Dictionary or record_id(field, value) != patch.id):
			return "Command ID must match both record mementos."
	return ""

func _apply(target: Dictionary, patches: Array, reverse: bool) -> String:
	var ordered := patches.duplicate()
	if reverse:
		ordered.reverse()
	for patch in ordered:
		var failure := _patch_error(patch)
		if failure != "":
			return failure
		var field := str(patch.field)
		var id := str(patch.get("id", ""))
		var before: Variant = patch.after if reverse else patch.before
		var after: Variant = patch.before if reverse else patch.after
		if _json_copy(_get_value(target, field, id)) != _json_copy(before):
			return "Document changed since command creation."
		if field in VALUE_FIELDS:
			target[field] = _json_copy(after)
			continue
		var records: Array = target.get(field, [])
		var matches := 0
		for record: Dictionary in records:
			if record_id(field, record) == id:
				matches += 1
		if matches > 1:
			return "Ambiguous duplicate record identity; no document changes were applied."
		target[field] = records
		for i in range(records.size()):
			if record_id(field, records[i]) == id:
				records.remove_at(i)
				break
		if after != null:
			records.append(_json_copy(after))
	return ""

func apply_command(label: String, patches: Array) -> String:
	if has_gesture():
		return "Finish or cancel the current gesture first."
	return _commit_command(label, patches)

func _commit_command(label: String, patches: Array, binary_mementos: Dictionary = {}) -> String:
	var candidate := document.duplicate(true)
	var failure := _apply(candidate, patches, false)
	if failure != "":
		return failure
	var validation := _validate(candidate)
	if not validation.ok:
		return reason(validation)
	candidate = validation.data.document
	# Keep canonical first-before/final-after for touched records only. Native
	# normalization adds defaults and sorts records; undo must match that result.
	var mementos: Array = []
	var seen := {}
	for patch: Dictionary in patches:
		var field := str(patch.field)
		var id := str(patch.get("id", ""))
		var key := JSON.stringify([field, id])
		if seen.has(key):
			continue
		seen[key] = true
		var before: Variant = _get_value(document, field, id)
		var after: Variant = _get_value(candidate, field, id)
		if _json_copy(before) != _json_copy(after):
			mementos.append({"field": field, "id": id, "before": before, "after": after})
	if mementos.is_empty():
		return ""
	var command: Dictionary = _json_copy({"label": label, "patches": mementos})
	var bytes := JSON.stringify(command).to_utf8_buffer().size()
	for blob: PackedByteArray in binary_mementos.values(): bytes += blob.size()
	if bytes > HISTORY_BYTES:
		return "Command exceeds the 16 MiB undo budget; split this operation."
	command.bytes = bytes
	if not binary_mementos.is_empty(): command.binary_mementos = binary_mementos.duplicate()
	for discarded: Dictionary in redo_stack:
		history_bytes -= int(discarded.bytes)
	redo_stack.clear()
	undo_stack.append(command)
	history_bytes += bytes
	while undo_stack.size() > HISTORY_COMMANDS or history_bytes > HISTORY_BYTES:
		history_bytes -= int(undo_stack.pop_front().bytes)
	document = candidate
	_after_edit()
	return ""

func undo() -> String:
	return _travel_history(true)

func redo() -> String:
	return _travel_history(false)

func _travel_history(reverse: bool) -> String:
	if has_gesture():
		return "Finish or cancel the current gesture first."
	var source := undo_stack if reverse else redo_stack
	if source.is_empty():
		return ""
	var command: Dictionary = source.back()
	var candidate := document.duplicate(true)
	var failure := _apply(candidate, command.patches, reverse)
	if failure != "":
		return failure
	var validation := _validate(candidate)
	if not validation.ok:
		return reason(validation)
	if command.has("binary_mementos"):
		# Detect external changes; never restore by rewriting an original source.
		for path: String in command.binary_mementos:
			var payload_source := PAYLOADS.read(project_path.path_join(path), HISTORY_BYTES)
			if payload_source.has("error") or payload_source.bytes != command.binary_mementos[path]:
				return "History payload changed or is missing: " + path
		failure = PAYLOADS.validate(self, candidate)
		if failure != "": return failure
	# Transfer only after every patch and invariant passed.
	source.pop_back()
	(redo_stack if reverse else undo_stack).append(command)
	document = validation.data.document
	_after_edit()
	return ""

func has_gesture() -> bool:
	return not _gesture.is_empty()

func begin_gesture(label: String) -> String:
	if has_gesture():
		return "A gesture is already active."
	_gesture = {"label": label, "signature": _signature(document), "patches": []}
	return ""

func stage_patches(patches: Array) -> String:
	if not has_gesture() or _gesture.signature != _signature(document):
		return "The gesture is stale; cancel it and start again."
	var staged: Array = _gesture.patches.duplicate(true)
	for patch in patches:
		var failure := _patch_error(patch)
		if failure != "":
			return failure
		var index := -1
		for i in range(staged.size()):
			if staged[i].field == patch.field and staged[i].get("id", "") == patch.get("id", ""):
				index = i
				break
		var expected: Variant = staged[index].after if index >= 0 else _get_value(document, patch.field, str(patch.get("id", "")))
		if _json_copy(expected) != _json_copy(patch.before):
			return "Gesture memento changed; no patches were staged."
		if index >= 0:
			staged[index].after = _json_copy(patch.after)
		else:
			staged.append(_json_copy(patch))
	var bytes := JSON.stringify({"label": _gesture.label, "patches": staged}).to_utf8_buffer().size()
	if bytes > HISTORY_BYTES:
		return "Gesture exceeds the 16 MiB undo budget."
	_gesture.patches = staged
	return ""

func commit_gesture() -> String:
	if not has_gesture() or _gesture.signature != _signature(document):
		return "The gesture is stale; cancel it and start again."
	var failure := _commit_command(_gesture.label, _gesture.patches)
	if failure == "":
		cancel_gesture()
	return failure

func cancel_gesture() -> void:
	_gesture.clear()

func _after_edit() -> void:
	document.provenance.last_edited = Time.get_datetime_string_from_system(true) + "Z"
	dirty = _signature(document) != _saved_signature
	changed.emit()

func save_project(path: String) -> String:
	if has_gesture():
		return "Finish or cancel the current gesture before saving."
	if path.is_empty():
		return "Choose a project directory first."
	var validation := _validate(document)
	if not validation.ok:
		return reason(validation)
	var absolute := ProjectSettings.globalize_path(path).simplify_path()
	# E02 never moves imported binaries; file-copy Save As belongs to the file tools.
	if absolute != project_path and (not document.heightmaps.is_empty() or not document.assets.is_empty()):
		return "This document references project files. Save in its original directory; file-copy Save As is pending."
	var destination := absolute.path_join("document.json")
	var expected := _disk_digest if destination == _disk_path else ""
	var failure := files.write(destination, str(validation.data.canonical), expected)
	if failure == "":
		document = validation.data.document
		project_path = absolute
		_disk_path = destination
		_disk_digest = str(validation.data.canonical).sha256_text()
		_saved_signature = _signature(document)
		dirty = false
	return failure

func recovery_path() -> String:
	return "user://recovery/" + str(document.get("map_id", "new")).sha256_text() + "-" + _recovery_id + ".json"

func autosave() -> String:
	if document.is_empty():
		return ""
	var validation := _validate(document)
	if not validation.ok:
		return reason(validation)
	var snapshot := {"recovery_version": 1, "project_path": project_path,
		"base_sha256": _disk_digest, "document": validation.data.document,
		"document_sha256": str(validation.data.canonical).sha256_text()}
	var text := JSON.stringify(snapshot)
	if text.sha256_text() == _autosaved_signature and FileAccess.file_exists(recovery_path()):
		return ""
	var failure := files.write(recovery_path(), text, files.digest(recovery_path()))
	if failure == "":
		_autosaved_signature = text.sha256_text()
	return failure

func recover(path: String) -> String:
	var result := files.read_json(path)
	if result.has("error"):
		return str(result.error)
	var value: Dictionary = result.value
	var envelope := value.has("document")
	var content: Variant = value.get("document") if envelope else value
	if content is not Dictionary:
		return "Invalid recovery document."
	var validation := _validate(content)
	if not validation.ok:
		return reason(validation)
	if envelope and value.has("recovery_version"):
		if value.recovery_version != 1 or value.get("document_sha256") != str(validation.data.canonical).sha256_text():
			return "Unsupported or corrupt recovery snapshot."
		if value.get("project_path") is not String or value.get("base_sha256") is not String:
			return "Invalid recovery origin."
	var origin := str(value.get("project_path", "")) if envelope else ProjectSettings.globalize_path(path).get_base_dir()
	if not origin.is_empty() and not origin.is_absolute_path():
		return "Recovery project path must be absolute."
	document = validation.data.document
	project_path = origin.simplify_path() if not origin.is_empty() else ""
	bridge = ClassDB.instantiate("MapKitBridge")
	_reset_session()
	_disk_path = project_path.path_join("document.json") if not project_path.is_empty() else ""
	# Envelopes retain their original base to detect stale autosaves. Explicitly
	# selected raw backups bind the current file; subsequent external edits conflict.
	_disk_digest = str(value.get("base_sha256", "")) if envelope else files.digest(_disk_path)
	_after_edit()
	return ""

func reason(result: Dictionary) -> String:
	return "%s: %s" % [result.error.code, result.error.message]
