extends RefCounted
## Immutable project payloads; disposable native candidate validation.
const MAX_PAYLOAD_BYTES := 64 * 1024 * 1024

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

static func validate(store: RefCounted, document: Dictionary, blobs: Dictionary = {}, cells: Array = []) -> String:
	var result: Dictionary = store._validate(document)
	if not result.ok: return store.reason(result)
	var payloads := {}
	var size := 0
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in document.get(field, []):
			var path := str(record.path)
			if payloads.has(path): continue
			var source: Dictionary = {"bytes": blobs[path]} if blobs.has(path) else read(store.project_path.path_join(path), MAX_PAYLOAD_BYTES - size)
			if source.has("error"): return source.error
			size += source.bytes.size()
			if size > MAX_PAYLOAD_BYTES: return "Candidate exceeds the 64 MiB authoring payload budget."
			payloads[path] = source.bytes
	var scratch := ProjectSettings.globalize_path("user://authoring-candidates/" + Crypto.new().generate_random_bytes(12).hex_encode())
	var failure := write_new(scratch.path_join("document.json"), str(result.data.canonical).to_utf8_buffer())
	for path: String in payloads:
		if failure != "": break
		failure = write_new(scratch.path_join(path), payloads[path])
	if failure == "":
		var native: RefCounted = ClassDB.instantiate("MapKitBridge")
		result = JSON.parse_string(native.open_project(scratch))
		if not result.ok: failure = store.reason(result)
		if failure == "":
			for cell: Vector2i in cells:
				result = JSON.parse_string(native.generate_chunk(cell.x, cell.y))
				if not result.ok:
					failure = "Cell %s: %s" % [cell, store.reason(result)]
					break
	remove_scratch(scratch)
	return failure

static func remove_scratch(path: String) -> void:
	# Called only on this operation's fresh random disposable directory.
	var dir := DirAccess.open(path)
	if dir == null: return
	for file in dir.get_files(): DirAccess.remove_absolute(path.path_join(file))
	for child in dir.get_directories(): remove_scratch(path.path_join(child))
	DirAccess.remove_absolute(path)

static func apply(store: RefCounted, label: String, patches: Array, blobs: Dictionary, cells: Array = []) -> String:
	if store.has_gesture(): return "Finish or cancel the active gesture first."
	if store.project_path.is_empty(): return "Save a project directory before editing file-backed terrain or assets."
	var candidate: Dictionary = store.document.duplicate(true)
	var failure: String = store._apply(candidate, patches, false)
	if failure != "": return failure
	var retained := blobs.duplicate()
	for patch: Dictionary in patches:
		if patch.field not in ["heightmaps", "assets"]: continue
		for value in [patch.before, patch.after]:
			if value == null or retained.has(str(value.path)): continue
			var source := read(store.project_path.path_join(str(value.path)), store.HISTORY_BYTES)
			if source.has("error"): return source.error
			retained[str(value.path)] = source.bytes
	var bytes := JSON.stringify({"label": label, "patches": patches}).to_utf8_buffer().size()
	for value: PackedByteArray in retained.values(): bytes += value.size()
	if bytes > store.HISTORY_BYTES: return "Command exceeds the shared 16 MiB binary/text undo budget."
	failure = validate(store, candidate, blobs, cells)
	if failure != "": return failure
	for path: String in blobs:
		# Only content-addressed new payloads may be installed, never original paths.
		if path != "editor/" + digest(blobs[path]) + "." + path.get_extension(): return "Invalid immutable payload identity."
		failure = write_new(store.project_path.path_join(path), blobs[path])
		if failure != "": return failure
	return store._commit_command(label, patches, retained)
