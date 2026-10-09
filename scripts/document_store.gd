extends RefCounted
## MapDocument is authoritative; views never become saved state.
signal changed
signal draft_changed(context: Dictionary)
signal validated_changed
signal file_operation_finished(result: Dictionary)
signal lock_changed
signal terrain_preview_changed(cells: Array)
signal dirty_changed
signal track_edit_finished(failure: String)
const TRACK_JOB := preload("./track_edit_job.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const PAYLOADS := preload("./authoring_files.gd")
const FILES := preload("./document_files.gd")
const HISTORY_BYTES := 16 * 1024 * 1024
const HISTORY_COMMANDS := 200
const RECORD_FIELDS := ["nodes", "roads", "buildings", "water_bodies", "surface_areas", "zones", "assets", "placements", "gimmicks", "repetitions", "heightmaps", "attributions", "courses", "grind_lines", "surface_attachments"]
const VALUE_FIELDS := ["map_id", "free_roam", "bounds", "cell_size_cm", "seed", "recipe_version", "theme", "terrain_base_cm", "environment", "assembled_track"]
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
var _saved_canonical := ""
var _disk_path := ""
var _disk_digest := ""
var _gesture: Dictionary = {}
# Monotonic even when undo/redo or a gesture restores the same document.
var command_epoch := 0
var session_id := 0
var track_edit_busy := false
var track_edit_job: RefCounted
var track_request_id := 0
var prepared_track_preview: Dictionary = {}
# Published preparation is immutable and shared with the next worker.
var track_preview_cache: Dictionary = {}
var last_track_apply_ms := 0.0
var last_track_timings: Dictionary = {}
const EDIT_BUSY := "Wait for the explicit operation to finish."
var draft: Dictionary = {}
var draft_revision := 0
var validated_revision := 0
var pending_track: Dictionary = {}
var draft_error: Dictionary = {}
var pending_since := -1
var clock: Callable = Time.get_ticks_msec
var track_job_factory: Callable = func(): return TRACK_JOB.new()
var file_job: RefCounted
var file_request: Dictionary = {}
var external_lock := false
var file_sequence := 0
var file_job_factory: Callable = func(): return load("res://scripts/document_file_job.gd").new()
var draft_paths: Dictionary = {}
var paths_revision := -1
var cached_pieces: Array = []
var save_token: RefCounted
var working: RefCounted
var _working_epoch := -1
var terrain_revision := 0
var terrain_state := 0
var saved_terrain_state := 0
var terrain_sequence := 0
var active_terrain: RefCounted
var water_job: RefCounted
var water_request := 0
var water_pending := {}
var _file_saved_terrain := 0

func working_snapshot() -> RefCounted:
	if working == null:
		working = ClassDB.instantiate("MapKitWorkingSnapshot")
		working.configure(JSON.stringify(document), project_path)
		_working_epoch = command_epoch
	elif _working_epoch != command_epoch:
		working.set_document(JSON.stringify(document), project_path)
		_working_epoch = command_epoch
	return working

func finish_active_terrain() -> String:
	return active_terrain.finish() if active_terrain != null else ""

func terrain_preview(cells: Array) -> void:
	terrain_revision += 1
	dirty = true
	dirty_changed.emit()
	terrain_preview_changed.emit(cells)

func start_water(point: Vector2, remove := false, refresh := false, delta := PackedInt32Array()) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	water_request += 1
	water_pending = {"id":water_request,"session":session_id,"revision":command_epoch,"delta":delta}
	water_job = preload("./water_edit_job.gd").new()
	var failure: Error = water_job.start(working_snapshot().fork(), point, remove, refresh)
	if failure != OK:
		water_job = null
		water_pending = {}
		return error_string(failure)
	lock_changed.emit()
	return ""

func cancel_water() -> void:
	if water_job != null: water_job.cancel()

func poll_water() -> void:
	if water_job == null or water_job.is_alive(): return
	var result: Dictionary = water_job.finish()
	water_job = null
	var pending := water_pending
	water_pending = {}
	var valid: bool = pending.id == water_request and pending.session == session_id and pending.revision == command_epoch
	if valid:
		var failure := reason(result) if not result.ok else install_terrain_command(pending.delta, result.data)
		if failure != "":
			if not pending.delta.is_empty(): working.apply_delta(pending.delta, true)
			dirty = _signature(document) != _saved_signature or (working != null and working.has_changes())
			dirty_changed.emit()
			terrain_revision += 1
			terrain_preview_changed.emit([])
			track_edit_finished.emit(failure)
			if not file_request.is_empty(): _finish_file({"ok":false,"error":failure})
	lock_changed.emit()
	_poll_file()

func install_terrain_command(delta: PackedInt32Array, water: Array) -> String:
	var patches: Array = []
	var next := document.duplicate(true)
	next.water_bodies = water
	if not delta.is_empty() and next.get("assembled_track") is Dictionary and next.assembled_track.get("authoring") is Dictionary:
		next.assembled_track.authoring.terrain_integration = true
	var checked := _validate(next)
	if not checked.ok: return reason(checked)
	next = checked.data.document
	if next.get("assembled_track") != document.get("assembled_track"):
		patches.append({"field":"assembled_track","before":document.assembled_track,"after":next.assembled_track})
	for record: Dictionary in document.get("water_bodies", []):
		var after: Variant = _get_value(next, "water_bodies", record.id)
		if record != after: patches.append({"field":"water_bodies","id":record.id,"before":record,"after":after})
	for record: Dictionary in next.get("water_bodies", []):
		if _get_value(document,"water_bodies",record.id) == null: patches.append({"field":"water_bodies","id":record.id,"before":null,"after":record})
	if delta.is_empty() and patches.is_empty():
		dirty = _signature(document) != _saved_signature or (working != null and working.has_changes())
		dirty_changed.emit()
		return ""
	var command := {"label":"Terrain / water", "patches":patches, "terrain_delta":delta,
		"terrain_before":terrain_state,"terrain_after":terrain_state}
	command.bytes = delta.size()*4 + JSON.stringify(patches).to_utf8_buffer().size()
	if command.bytes > HISTORY_BYTES: return "Command exceeds the 16 MiB undo budget; split this operation."
	if not delta.is_empty():
		terrain_sequence += 1
		command.terrain_after = terrain_sequence
	terrain_state = command.terrain_after
	_record_command(command)
	document = next
	_after_edit()
	terrain_revision += 1
	terrain_preview_changed.emit([])
	return ""



func editing_locked() -> bool:
	return external_lock or not file_request.is_empty() or water_job != null

func set_external_lock(value: bool) -> void:
	if external_lock == value: return
	external_lock = value
	lock_changed.emit()

func draft_pending() -> bool:
	return draft_revision != validated_revision

func applying_visible() -> bool:
	return track_edit_busy and pending_since >= 0 and int(clock.call()) - pending_since >= 500

func track_pieces() -> Array:
	if paths_revision == draft_revision: return cached_pieces
	var rows: Array = []
	var retained := {}
	for item: Dictionary in track_source().get("instances", []):
		var key := JSON.stringify(item)
		var row: Dictionary = draft_paths.get(key, {})
		if row.is_empty():
			var result: Dictionary = JSON.parse_string(bridge.track_instance(key))
			row = result.data if result.ok else {"path":[]}
		retained[key] = row
		rows.append(row)
	draft_paths = retained
	paths_revision = draft_revision
	cached_pieces = rows
	return rows

func start_track_edit(source: Dictionary, expected_epoch := -1, context: Dictionary = {}) -> String:
	if editing_locked(): return EDIT_BUSY
	if expected_epoch >= 0 and expected_epoch != command_epoch: return "Stale track edit; current map retained."
	if has_gesture(): return "Finish or cancel the current gesture first."
	var before := track_source()
	if before == source:
		retry_track_edit()
		return ""
	var command := {"label":"Track assembly", "patches":[], "track_before":before, "track_after":source.duplicate(true)}
	command.bytes = JSON.stringify(command).to_utf8_buffer().size()
	if command.bytes > HISTORY_BYTES: return "Command exceeds the 16 MiB undo budget; split this operation."
	_record_command(command)
	_accept_draft(command.track_after, context)
	return ""

func _record_command(command: Dictionary) -> void:
	for discarded: Dictionary in redo_stack: history_bytes -= int(discarded.bytes)
	redo_stack.clear()
	undo_stack.append(command)
	history_bytes += int(command.bytes)
	while undo_stack.size() + redo_stack.size() > HISTORY_COMMANDS or history_bytes > HISTORY_BYTES:
		history_bytes -= int(undo_stack.pop_front().bytes)

func _accept_draft(source: Dictionary, context: Dictionary = {}) -> void:
	draft = source.duplicate(true)
	draft_revision += 1
	command_epoch += 1
	dirty = true
	draft_error = {}
	if pending_since < 0: pending_since = int(clock.call())
	pending_track = {"source":draft, "revision":draft_revision, "context":context.duplicate(true)}
	# Publish the new source/view before returning to the release handler.
	draft_changed.emit(context)
	_launch_track()

func start_track_history(forward: bool) -> String:
	if editing_locked(): return EDIT_BUSY
	if has_gesture(): return "Finish or cancel the current gesture first."
	var history := redo_stack if forward else undo_stack
	if history.is_empty():
		retry_track_edit()
		return ""
	var command: Dictionary = history.back()
	if not command.has("track_before"):
		if draft_pending(): return "Finish applying the draft before changing map properties."
		return _travel_history(not forward)
	history.pop_back()
	(undo_stack if forward else redo_stack).append(command)
	_accept_draft(command.track_after if forward else command.track_before)
	return ""

func retry_track_edit() -> void:
	if not draft_pending(): return
	if track_edit_job != null and track_edit_job.matches(self, track_request_id): return
	draft_error = {}
	if pending_since < 0: pending_since = int(clock.call())
	pending_track = {"source":draft, "revision":draft_revision, "context":{}}
	_launch_track()

func _launch_track() -> void:
	if track_edit_job != null or pending_track.is_empty(): return
	var request := pending_track
	pending_track = {}
	track_request_id += 1
	track_edit_job = track_job_factory.call()
	track_edit_busy = true
	var failure: Error = track_edit_job.start(self, track_request_id, "edit", request.source, request.context)
	if failure != OK:
		track_edit_job = null
		track_edit_busy = false
		_track_failure(error_string(failure))

func _track_failure(message: String) -> void:
	draft_error = {"revision":draft_revision, "target":file_request.get("path", ""), "message":message}
	pending_since = -1
	track_edit_finished.emit(message)
	if not file_request.is_empty(): _finish_file({"ok":false, "error":message})

func cancel_track_edit() -> void:
	if not file_request.is_empty() and not file_request.cancelled: return
	pending_track = {}
	pending_since = -1
	if track_edit_job != null:
		track_request_id += 1
		track_edit_job.cancel()

func poll_track_edit() -> void:
	if track_edit_job == null or track_edit_job.is_alive(): return
	var job: RefCounted = track_edit_job
	var prepared: Dictionary = job.finish()
	var valid: bool = job.matches(self, track_request_id)
	job.consumed = true
	track_edit_job = null
	track_edit_busy = false
	if valid:
		if prepared.has("error"): _track_failure(prepared.error)
		else:
			var begin := Time.get_ticks_usec()
			if not prepared.get("noop", false):
				document = prepared.candidate
				prepared_track_preview = prepared.preview
				track_preview_cache = prepared.preview
			if prepared.get("noop", false): prepared_track_preview = track_preview_cache
			validated_revision = draft_revision
			_working_epoch = -1
			pending_since = -1
			draft_error = {}
			dirty = _signature(document) != _saved_signature or (working != null and working.has_changes())
			validated_changed.emit()
			last_track_apply_ms = (Time.get_ticks_usec() - begin) / 1000.0
			last_track_timings = prepared.get("timings", {})
			track_edit_finished.emit("")
	_launch_track()
	_poll_file()

func shutdown_track_edit() -> void:
	if track_edit_job != null: track_edit_job.shutdown()
	if file_job != null: file_job.shutdown()
	if water_job != null: water_job.shutdown(); water_job = null
	track_edit_job = null
	file_job = null
	pending_track = {}
	track_edit_busy = false

func start_file_operation(operation: String, path: String, options: Dictionary = {}) -> String:
	if external_lock or not file_request.is_empty(): return EDIT_BUSY
	if operation not in ["save", "export"]: return "Unsupported file operation."
	var finish_failure := finish_active_terrain()
	if finish_failure != "": return finish_failure
	if has_gesture():
		finish_failure = commit_gesture()
		if finish_failure != "": return finish_failure
	_file_saved_terrain = terrain_state
	file_sequence += 1
	file_request = {"id":file_sequence, "session":session_id, "revision":draft_revision,
		"operation":operation, "path":path, "options":options.duplicate(true), "cancelled":false}
	lock_changed.emit()
	if draft_pending(): retry_track_edit()
	else: _poll_file()
	return ""

func cancel_file_operation() -> void:
	if file_request.is_empty(): return
	file_request.cancelled = true
	if file_job != null: file_job.cancel()
	else:
		cancel_track_edit()
		if track_edit_job == null: _finish_file({"ok":false, "cancelled":true, "error":"Operation cancelled; draft retained."})

func poll_file_operation() -> void:
	_poll_file()

func _poll_file() -> void:
	if file_request.is_empty(): return
	if file_job == null:
		if water_job != null: return
		if file_request.cancelled:
			if track_edit_job == null: _finish_file({"ok":false, "cancelled":true, "error":"Operation cancelled; draft retained."})
			return
		if draft_pending(): return
		_file_saved_terrain = terrain_state
		file_request.revision = draft_revision
		file_job = file_job_factory.call()
		var failure: Error = file_job.start(self, file_request)
		if failure != OK:
			file_job = null
			_finish_file({"ok":false, "error":error_string(failure)})
		return
	if file_job.is_alive(): return
	var result: Dictionary = file_job.finish()
	file_job = null
	# A successful publication wins over a cancellation arriving after rename.
	if file_request.session != session_id or file_request.revision != draft_revision:
		result = {"ok":false, "error":"File operation belongs to another document session."}
	elif result.ok and file_request.operation == "save":
		project_path = result.path
		_disk_path = project_path.path_join("document.json")
		_disk_digest = result.digest
		_saved_signature = result.signature
		_saved_canonical = result.canonical
		if working != null: working.accept_saved(result.canonical, project_path)
		command_epoch += 1
		_working_epoch = command_epoch
		saved_terrain_state = _file_saved_terrain
		dirty = false
		dirty_changed.emit()
		changed.emit()
	_finish_file(result)

func _finish_file(result: Dictionary) -> void:
	result.request = file_request.duplicate(true)
	file_request = {}
	lock_changed.emit()
	file_operation_finished.emit(result)

func new_document() -> void:
	if editing_locked(): return
	bridge = ClassDB.instantiate("MapKitBridge")
	var stamp := Time.get_datetime_string_from_system(true) + "Z"
	document = {
		"map_id": "map-" + Crypto.new().generate_random_bytes(8).hex_encode(),
		"free_roam": false, "revision": 1, "bounds": {"min": [0, 0], "max": [102400, 102400]},
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
	if editing_locked(): return EDIT_BUSY
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
	_saved_canonical = JSON.stringify(document)
	dirty = false
	changed.emit()
	return ""

func _reset_session() -> void:
	cancel_track_edit()
	draft = {}
	draft_revision = 0
	validated_revision = 0
	draft_error = {}
	draft_paths = {}
	paths_revision = -1
	cached_pieces = []
	session_id += 1
	prepared_track_preview = {}
	track_preview_cache = {}
	command_epoch += 1
	undo_stack.clear()
	redo_stack.clear()
	history_bytes = 0
	_gesture.clear()
	_saved_signature = ""
	_disk_path = ""
	_disk_digest = ""
	working = null
	_working_epoch = -1
	terrain_state = 0
	saved_terrain_state = 0
	terrain_revision += 1
	active_terrain = null

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
	if field == "courses": return str(record.get("course_id", ""))
	if field == "attributions":
		return JSON.stringify([record.get("source", ""), record.get("license", ""), record.get("notice", "")])
	if field == "heightmaps":
		var cell: Variant = record.get("cell", {})
		if cell is not Dictionary or not cell.has_all(["x", "y"]): return ""
		if (cell.x is not int and cell.x is not float) or (cell.y is not int and cell.y is not float): return ""
		return JSON.stringify({"x": int(cell.get("x", 0)), "y": int(cell.get("y", 0))})
	return str(record.get("id", ""))

func _get_value(target: Dictionary, field: String, id: String) -> Variant:
	if field == "track_document": return target
	if field in VALUE_FIELDS:
		return target.get(field)
	for record: Dictionary in target.get(field, []):
		if record_id(field, record) == id:
			return record
	return null

func _patch_error(patch: Variant) -> String:
	if patch is not Dictionary or not patch.has_all(["field", "before", "after"]):
		return "A command requires field, before and after mementos."
	var field := str(patch.field)
	if field == "track_document":
		return "" if patch.before is Dictionary and patch.after is Dictionary else "Track document mementos required"
	if field in VALUE_FIELDS:
		if patch.get("id", "") != "":
			return "Map-value commands have no record ID."
		if field in ["environment", "assembled_track"]: return "" # Optional map profile: Undo restores its absence.
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
		if (_signature(target) != _signature(before)) if field == "track_document" else (_json_copy(_get_value(target, field, id)) != _json_copy(before)):
			return "Document changed since command creation."
		if field == "track_document":
			target.clear()
			target.merge(_json_copy(after))
			continue
		if field in VALUE_FIELDS:
			if field in ["environment", "assembled_track"] and after == null: target.erase(field)
			else: target[field] = _json_copy(after)
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
	if editing_locked() or draft_pending(): return EDIT_BUSY
	var prepared := _prepare_command(label, patches, binary_mementos)
	if prepared.has("error"): return prepared.error
	_install_command(prepared)
	return ""

# Pure with respect to this store. Owned import workers use the same canonical
# mementos/budget as synchronous authoring; no live bridge/history is transferred.
func _prepare_command(label: String, patches: Array, binary_mementos: Dictionary = {}) -> Dictionary:
	var candidate := document.duplicate(true)
	var failure := _apply(candidate, patches, false)
	if failure != "":
		return {"error": failure}
	var validation := _validate(candidate)
	if not validation.ok:
		return {"error": reason(validation)}
	if working != null:
		var memory_check: Dictionary = JSON.parse_string(working.fork().set_document(JSON.stringify(candidate),project_path))
		if not memory_check.ok: return {"error":reason(memory_check)}
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
		if before != after:
			mementos.append({"field": field, "id": id, "before": before, "after": after})
	if mementos.is_empty():
		return {"noop": true}
	var command: Dictionary = {"label": label, "patches": mementos.duplicate(true)}
	var command_json := JSON.stringify(command)
	var bytes := command_json.to_utf8_buffer().size()
	for blob: PackedByteArray in binary_mementos.values(): bytes += blob.size()
	if bytes > HISTORY_BYTES:
		return {"error": "Command exceeds the 16 MiB undo budget; split this operation."}
	command.bytes = bytes
	if not binary_mementos.is_empty(): command.binary_mementos = binary_mementos.duplicate()
	return {"candidate": candidate, "command": command, "canonical": str(validation.data.canonical),
		"command_json": command_json, "signature": _signature(candidate)}

# Internal trusted preparation result only; never accepts adapter output directly.
# The native job checks its one-shot ownership, epoch and immutable request first.
func _install_command(prepared: Dictionary) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	if prepared.get("noop", false): return ""
	var command: Dictionary = prepared.command
	var candidate: Dictionary = prepared.candidate
	for discarded: Dictionary in redo_stack:
		history_bytes -= int(discarded.bytes)
	redo_stack.clear()
	undo_stack.append(command)
	history_bytes += int(command.bytes)
	while undo_stack.size() > HISTORY_COMMANDS or history_bytes > HISTORY_BYTES:
		history_bytes -= int(undo_stack.pop_front().bytes)
	document = candidate
	_after_edit(prepared.signature)
	return ""

func undo() -> String:
	return start_track_history(false) if not undo_stack.is_empty() and undo_stack.back().has("track_before") else _travel_history(true)

func redo() -> String:
	return start_track_history(true) if not redo_stack.is_empty() and redo_stack.back().has("track_before") else _travel_history(false)

func _travel_history(reverse: bool) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	if has_gesture():
		return "Finish or cancel the current gesture first."
	var source := undo_stack if reverse else redo_stack
	if source.is_empty():
		return ""
	var command: Dictionary = source.back()
	var prepared := _prepare_history(command, reverse)
	if prepared.has("error"): return prepared.error
	_install_history(prepared, reverse)
	return ""

func _prepare_history(command: Dictionary, reverse: bool) -> Dictionary:
	var candidate := document.duplicate(true)
	var failure := _apply(candidate, command.patches, reverse)
	if failure != "":
		return {"error":failure}
	var validation := _validate(candidate)
	if not validation.ok:
		return {"error":reason(validation)}
	if command.has("binary_mementos"):
		# Detect external changes; never restore by rewriting an original source.
		for path: String in command.binary_mementos:
			var payload_source := PAYLOADS.read(project_path.path_join(path), HISTORY_BYTES)
			if payload_source.has("error") or payload_source.bytes != command.binary_mementos[path]:
				return {"error":"History payload changed or is missing: " + path}
	var native: RefCounted = working_snapshot().fork()
	if command.has("terrain_delta") and not command.terrain_delta.is_empty():
		var applied: Dictionary = JSON.parse_string(native.apply_delta(command.terrain_delta, reverse))
		if not applied.ok: return {"error":reason(applied)}
	var replayed: Dictionary = JSON.parse_string(native.replay_document(JSON.stringify(validation.data.document),project_path))
	if not replayed.ok: return {"error":reason(replayed)}
	if command.has("binary_mementos"):
		replayed = JSON.parse_string(native.validate_memory())
		if not replayed.ok: return {"error":reason(replayed)}
	return {"candidate":validation.data.document, "signature":_signature(validation.data.document),"working":native}

func _install_history(prepared: Dictionary, reverse: bool) -> void:
	# Transfer only after every patch and invariant passed.
	var source := undo_stack if reverse else redo_stack
	var command: Dictionary = source.pop_back()
	(redo_stack if reverse else undo_stack).append(command)
	document = prepared.candidate
	working = prepared.working
	if command.has("terrain_before"): terrain_state = command.terrain_before if reverse else command.terrain_after
	_after_edit(prepared.signature)
	terrain_revision += 1
	terrain_preview_changed.emit([])

func has_gesture() -> bool:
	return not _gesture.is_empty()

func begin_gesture(label: String) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	if has_gesture():
		return "A gesture is already active."
	command_epoch += 1
	_gesture = {"label": label, "signature": _signature(document), "patches": []}
	return ""

func stage_patches(patches: Array) -> String:
	if editing_locked(): return EDIT_BUSY
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
	if not _gesture.is_empty(): command_epoch += 1
	_gesture.clear()

func _after_edit(prepared_signature: String = "") -> void:
	draft = {}
	draft_revision += 1
	validated_revision = draft_revision
	draft_paths = {}
	paths_revision = -1
	cached_pieces = []
	command_epoch += 1
	document.provenance.last_edited = Time.get_datetime_string_from_system(true) + "Z"
	dirty = (prepared_signature if prepared_signature != "" else _signature(document)) != _saved_signature or (working != null and working.has_changes())
	dirty_changed.emit()
	changed.emit()

func save_project(path: String) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	var failure := finish_active_terrain()
	if failure != "": return failure
	if has_gesture() or water_job != null: return "Wait for the current edit before synchronous saving."
	if path.is_empty(): return "Choose a project directory first."
	var absolute := ProjectSettings.globalize_path(path).simplify_path()
	var destination := absolute.path_join("document.json")
	var expected := _disk_digest if destination == _disk_path else ""
	if files.digest(destination) != expected: return "The file changed on disk. Open it again or Save As to a new directory."
	if absolute == project_path and not dirty and expected != "":
		command_epoch += 1
		_working_epoch = command_epoch
		changed.emit()
		return ""
	if save_token != null and save_token.is_cancelled(): return "Operation cancelled; draft retained."
	var captured := SNAPSHOT.capture_working(working_snapshot(), project_path, undo_stack + redo_stack)
	if not captured.ok: return reason(captured)
	if save_token != null and save_token.is_cancelled(): return "Operation cancelled; draft retained."
	failure = SNAPSHOT.publish(captured.data, absolute, expected, files, save_token)
	if failure != "": return failure
	project_path = absolute
	_disk_path = destination
	_disk_digest = str(captured.data.canonical).sha256_text()
	_saved_canonical = captured.data.canonical
	_saved_signature = _signature(document)
	saved_terrain_state = terrain_state
	working.accept_saved(_saved_canonical, project_path)
	command_epoch += 1
	_working_epoch = command_epoch
	dirty = false
	dirty_changed.emit()
	changed.emit()
	return ""

func recover(path: String) -> String:
	if editing_locked(): return EDIT_BUSY
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
	if envelope:
		if value.get("recovery_version") != 1 or value.get("document_sha256") != JSON.stringify(content).sha256_text():
			return "Unsupported or corrupt recovery snapshot."
		if not value.get("draft") is Dictionary or value.get("draft_sha256") != JSON.stringify(value.draft).sha256_text():
			return "Unsupported or corrupt recovery draft."
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
	if envelope and not value.draft.is_empty(): _accept_draft(value.draft)
	return ""

func reason(result: Dictionary) -> String:
	return "%s: %s" % [result.error.code, result.error.message]

func open_generated(value: Dictionary, preview: Dictionary = {}) -> String:
	if editing_locked(): return EDIT_BUSY
	var checked := _validate(value)
	if not checked.ok: return reason(checked)
	document = checked.data.document
	project_path = ""
	bridge = ClassDB.instantiate("MapKitBridge")
	_reset_session()
	prepared_track_preview=preview
	track_preview_cache=preview
	_after_edit()
	return ""

func set_free_roam(value: bool) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	var candidate := document.duplicate(true)
	candidate.free_roam = value
	var patches: Array = [{"field":"free_roam", "id":"", "before":document.free_roam, "after":value}]
	if candidate.has("assembled_track"):
		var result: Dictionary = JSON.parse_string(bridge.reseal_track_document(JSON.stringify(candidate)))
		if not result.ok: return reason(result)
		for course: Dictionary in document.get("courses",[]):
			patches.append({"field":"courses", "id":course.course_id, "before":course, "after":null})
		for course: Dictionary in result.data.document.get("courses",[]):
			patches.append({"field":"courses", "id":course.course_id, "before":null, "after":course})
	return apply_command("Free roam map", patches)

func track_source() -> Dictionary:
	if not draft.is_empty(): return draft.duplicate(true)
	var assembly: Dictionary = document.get("assembled_track", {})
	for field in ["authoring", "seed_source"]:
		if assembly.get(field) is Dictionary:
			var source: Dictionary=assembly[field].duplicate(true)
			if not source.get("terrain_integration", false): source.grind_lines=document.get("grind_lines",[]).duplicate(true)
			return source
	var result: Dictionary = JSON.parse_string(bridge.track_authoring_source(JSON.stringify(document)))
	return result.data if result.ok else {}

func edit_track(source: Dictionary, expected_epoch: int = -1) -> String:
	if editing_locked(): return EDIT_BUSY
	if draft_pending(): return start_track_edit(source, expected_epoch)
	if has_gesture(): return "Finish or cancel the current gesture first."
	if expected_epoch >= 0 and expected_epoch != command_epoch: return "Stale track edit; current map retained."
	var prepared := _prepare_track(source)
	if prepared.has("error"): return prepared.error
	return _install_command(prepared)

func document_patches(candidate: Dictionary) -> Array:
	var patches: Array = []
	for field: String in VALUE_FIELDS:
		if document.get(field) != candidate.get(field):
			patches.append({"field":field, "before":document.get(field), "after":candidate.get(field)})
	for field: String in RECORD_FIELDS:
		var before := {}
		var after := {}
		for item: Dictionary in document.get(field, []): before[record_id(field,item)] = item
		for item: Dictionary in candidate.get(field, []): after[record_id(field,item)] = item
		var ids := before.duplicate()
		ids.merge(after)
		for id: String in ids:
			if before.get(id) != after.get(id):
				patches.append({"field":field, "id":id, "before":before.get(id), "after":after.get(id)})
	return patches

func edit_road(id: String, design: Dictionary, width_cm: int) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	var result: Dictionary = JSON.parse_string(bridge.edit_road_design(JSON.stringify(document), id, JSON.stringify(design), width_cm))
	if not result.ok: return reason(result)
	return apply_command("Road alignment and terrain fit", document_patches(result.data.document))

func edit_surface_attachments(items: Array) -> String:
	if editing_locked() or draft_pending(): return EDIT_BUSY
	var result: Dictionary = JSON.parse_string(bridge.apply_surface_attachments(JSON.stringify(document), JSON.stringify(items)))
	if not result.ok: return reason(result)
	return apply_command("Surface attachment", document_patches(result.data.document))

func _prepare_track(source: Dictionary, record_history := true) -> Dictionary:
	if document.get("assembled_track", {}).get("authoring") == source: return {"noop":true}
	var authored: Variant=document.get("assembled_track",{}).get("authoring")
	var mixed: bool = not document.has("assembled_track") or (authored is Dictionary and authored.get("terrain_integration",false))
	var result: Dictionary = JSON.parse_string(bridge.apply_track_source(JSON.stringify(document), JSON.stringify(source)) if mixed else bridge.compile_track_source(JSON.stringify(source)))
	if not result.ok: return {"error":reason(result)}
	var candidate: Dictionary = result.data.document
	if not mixed:
		candidate.free_roam = document.free_roam
		candidate.provenance = document.provenance.duplicate(true)
		candidate.attributions = document.get("attributions",[]).duplicate(true)
		if candidate.free_roam:
			result = JSON.parse_string(bridge.reseal_track_document(JSON.stringify(candidate)))
			if not result.ok: return {"error":reason(result)}
			candidate=result.data.document
	var validation := _validate(candidate)
	if not validation.ok: return {"error":reason(validation)}
	candidate = validation.data.document
	if not record_history: return {"candidate":candidate, "signature":_signature(candidate)}
	return _prepare_command("Track assembly", document_patches(candidate))

func new_track(free_roam := false) -> void:
	if editing_locked(): return
	new_document()
	if free_roam:
		document.free_roam=true
	else:
		var result: Dictionary=JSON.parse_string(bridge.compile_track_source(JSON.stringify(track_source())))
		if result.ok:
			result.data.document.provenance=document.provenance.duplicate(true)
			document=result.data.document
	_reset_session()
	_after_edit()
