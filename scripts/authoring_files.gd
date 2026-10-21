extends RefCounted
## Immutable project payloads; disposable native candidate validation.
const LIMITS := preload("./limit_warnings.gd")
# Memory guard for candidate payloads loaded for validation; warn above WARN_BYTES.
const MAX_PAYLOAD_BYTES := 2 * 1024 * 1024 * 1024
const PAYLOAD_WARN_BYTES := 64 * 1024 * 1024
# MapKit v1 package entry limit: the game refuses larger project files.
const RUNTIME_ENTRY_BYTES := 128 * 1024 * 1024

static func paths(record: Dictionary) -> Array[String]:
	var result: Array[String] = [str(record.path)]
	if record.get("distant_path") != null: result.append(str(record.distant_path))
	return result

static func read(path: String, limit: int = MAX_PAYLOAD_BYTES) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return {"error": "Cannot read source file: " + path}
	if file.get_length() > limit: return {"error": "Source exceeds authoring input budget."}
	var bytes := file.get_buffer(file.get_length())
	return {"bytes": bytes}

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func write_new(path: String, bytes: PackedByteArray) -> String:
	if FileAccess.file_exists(path):
		var existing := read(path)
		return "" if not existing.has("error") and existing.bytes == bytes else "Immutable payload conflict: " + path
	if DirAccess.make_dir_recursive_absolute(path.get_base_dir()) != OK: return "Cannot create payload directory."
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null: return "Cannot write payload."
	file.store_buffer(bytes)
	file.flush()
	var failure := file.get_error()
	file.close()
	return "" if failure == OK else "Payload write failed."

# Workers collect into context.limit_warnings; in-editor callers note on the store.
static func note(store: RefCounted, context: Dictionary, code: String, actual: int, limit: int, message: String, runtime_rejects := false) -> void:
	if context.get("limit_warnings") is Array: LIMITS.note(context.limit_warnings, code, actual, limit, message, runtime_rejects)
	elif store != null and store.has_method("note_limit"): store.note_limit(code, actual, limit, message, runtime_rejects)

# MapKit Authoring responses carry top-level warnings; route them the same way.
static func note_native(store: RefCounted, context: Dictionary, response: Variant) -> void:
	if context.get("limit_warnings") is Array: LIMITS.native(context.limit_warnings, response)
	elif store != null and store.has_method("note_native"): store.note_native(response)

static func _progress(context: Dictionary, stage: String, completed: int, total: int) -> void:
	if context.has("progress"): context.progress.call(stage, completed, total)

static func validate(store: RefCounted, document: Dictionary, blobs: Dictionary = {}, cells: Array = [], context: Dictionary = {}) -> String:
	var result: Dictionary = store._validate(document)
	if not result.ok: return store.reason(result)
	var payloads := {}
	var size := 0
	var total := MAX_PAYLOAD_BYTES
	if context.has("progress"):
		total = 0
		var counted := {}
		for field in ["assets", "heightmaps"]:
			for record: Dictionary in document.get(field, []):
				for path: String in paths(record):
					if counted.has(path): continue
					counted[path] = true
					if blobs.has(path):
						total += blobs[path].size()
						if total > MAX_PAYLOAD_BYTES: return "Candidate exceeds the 2 GiB authoring payload memory limit."
						continue
					var file := FileAccess.open(store.project_path.path_join(path), FileAccess.READ)
					if file == null: return "Cannot read candidate payload."
					total += file.get_length()
					file.close()
					if total > MAX_PAYLOAD_BYTES: return "Candidate exceeds the 2 GiB authoring payload memory limit."
	_progress(context, "snapshot", 0, total)
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in document.get(field, []):
			for path: String in paths(record):
				if payloads.has(path): continue
				var source: Dictionary = {"bytes": blobs[path]} if blobs.has(path) else read(store.project_path.path_join(path), MAX_PAYLOAD_BYTES - size)
				if source.has("error"): return source.error
				size += source.bytes.size()
				if size > MAX_PAYLOAD_BYTES: return "Candidate exceeds the 2 GiB authoring payload memory limit."
				if source.bytes.size() > RUNTIME_ENTRY_BYTES: note(store, context, "payload_entry", source.bytes.size(), RUNTIME_ENTRY_BYTES, "A terrain or asset file is larger than the v1 package entry limit", true)
				payloads[path] = source.bytes
				if context.has("hashes") and not blobs.has(path):
					context.hashes[path] = digest(source.bytes)
					if FileAccess.get_sha256(store.project_path.path_join(path)) != context.hashes[path]: return "Source changed during native candidate snapshot."
				_progress(context, "snapshot", size, total)
	if context.get("expected_payloads", "") != "" and JSON.stringify(context.hashes).sha256_text() != context.expected_payloads: return "Project payload changed since import review; import again."
	# Same code as MapKit's working-resource warning, so the two merge.
	if size > PAYLOAD_WARN_BYTES: note(store, context, "working_resources", size, PAYLOAD_WARN_BYTES, "Terrain and asset files are very large and need a lot of memory")
	_progress(context, "open", 0, 1)
	var native: RefCounted = store.working_snapshot().fork()
	result = JSON.parse_string(native.set_document(JSON.stringify(document),store.project_path))
	note_native(store, context, result)
	if not result.ok: return store.reason(result)
	result = JSON.parse_string(native.provide_resources(payloads))
	note_native(store, context, result)
	if not result.ok: return store.reason(result)
	result = JSON.parse_string(native.validate_memory())
	note_native(store, context, result)
	var failure: String = "" if result.ok else store.reason(result)
	if failure == "":
		_progress(context, "open", 1, 1)
		_progress(context, "generate", 0, cells.size())
		var completed := 0
		while completed < cells.size():
			# Each bounded batch reuses one immutable prepared native document.
			# Admission generates actual geometry without discarded render packing.
			var batch: Array[Vector2i] = []
			for i in range(completed, mini(completed+16,cells.size())): batch.append(cells[i])
			result = JSON.parse_string(native.validate_cells(batch, LIMITS.AUTHORING_TRIANGLES))
			note_native(store, context, result)
			if not result.ok:
				failure = store.reason(result)
				break
			if result.get("data",{}).get("cells",-1) != batch.size():
				failure = "Native cell validation did not complete the entire batch."
				break
			completed += batch.size()
			_progress(context, "generate", completed, cells.size())
	if context.has("hashes"):
		for path: String in context.hashes:
			if FileAccess.get_sha256(store.project_path.path_join(path)) != context.hashes[path]: failure = "Source changed during native candidate validation."
	return failure

static func remove_scratch(path: String) -> void:
	# Called only on this operation's fresh random disposable directory.
	var dir := DirAccess.open(path)
	if dir == null: return
	for file in dir.get_files(): DirAccess.remove_absolute(path.path_join(file))
	for child in dir.get_directories(): remove_scratch(path.path_join(child))
	DirAccess.remove_absolute(path)

static func apply(store: RefCounted, label: String, patches: Array, blobs: Dictionary, cells: Array = [], validate_only: bool = false, context: Dictionary = {}) -> String:
	if store.editing_locked(): return store.EDIT_BUSY
	if store.has_gesture(): return "Finish or cancel the active gesture first."
	if store.project_path.is_empty(): return "Save a project directory before editing file-backed terrain or assets."
	var candidate: Dictionary = store.document.duplicate(true)
	var failure: String = store._apply(candidate, patches, false)
	if failure != "": return failure
	var retained := blobs.duplicate()
	for patch: Dictionary in patches:
		if patch.field not in ["heightmaps", "assets"]: continue
		for value in [patch.before, patch.after]:
			if value == null: continue
			for path: String in paths(value):
				if retained.has(path): continue
				var source := read(store.project_path.path_join(path), MAX_PAYLOAD_BYTES)
				if source.has("error"): return source.error
				retained[path] = source.bytes
	# A command over the shared Undo budget is applied without Undo (history_codec).
	failure = validate(store, candidate, blobs, cells, context)
	if failure != "": return failure
	if context.has("retained"): context.retained.merge(retained, true)
	if context.has("prepared"):
		_progress(context, "prepare", 0, 1)
		var prepared: Dictionary = store._prepare_command(str(context.get("command_label", label)), patches, retained)
		if prepared.has("error"): return prepared.error
		if prepared.get("noop", false): return "Import command has no changes."
		context.prepared.merge(prepared, true)
		# The exact binary set given to retain(): encode() carries it even when
		# Undo was released, so the parent's decode reaches the same decision.
		context.prepared.retained = retained
		_progress(context, "prepare", 1, 1)
	if validate_only: return ""
	for path: String in blobs:
		# Only content-addressed new payloads may be installed, never original paths.
		if path != "editor/" + digest(blobs[path]) + "." + path.get_extension(): return "Invalid immutable payload identity."
		failure = write_new(store.project_path.path_join(path), blobs[path])
		if failure != "": return failure
	return store._commit_command(label, patches, retained)
