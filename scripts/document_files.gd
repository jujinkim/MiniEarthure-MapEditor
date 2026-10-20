extends RefCounted
## Atomic editor-owned file storage. Referenced source/asset files are immutable.
const LIMITS := preload("./limit_warnings.gd")
# Memory guard for one parsed snapshot; above WARN_BYTES the editor still works but warns.
const MAX_BYTES := 1024 * 1024 * 1024
const WARN_BYTES := 64 * 1024 * 1024
# MapKit v1 package document limit; the game refuses larger documents.
const RUNTIME_DOCUMENT_BYTES := 32 * 1024 * 1024

static func size_warnings(list: Array, bytes: int) -> void:
	if bytes > RUNTIME_DOCUMENT_BYTES: LIMITS.note(list, "document_bytes", bytes, RUNTIME_DOCUMENT_BYTES, "Document is larger than the v1 package document limit", true)
	if bytes > WARN_BYTES: LIMITS.note(list, "document_memory", bytes, WARN_BYTES, "Document snapshot is very large and needs a lot of memory")

func read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"error": "Cannot read document: " + error_string(FileAccess.get_open_error())}
	if file.get_length() > MAX_BYTES:
		return {"error": "Document snapshot exceeds 1 GiB."}
	var warnings: Array = []
	size_warnings(warnings, file.get_length())
	var text := file.get_as_text()
	var error := file.get_error()
	file.close()
	if error != OK:
		return {"error": "Cannot read document: " + error_string(error)}
	var parser := JSON.new()
	if parser.parse(text) != OK or parser.data is not Dictionary:
		return {"error": "Invalid document snapshot JSON."}
	return {"value": parser.data, "limit_warnings": warnings} if not warnings.is_empty() else {"value": parser.data}

func digest(path: String) -> String:
	return FileAccess.get_sha256(path) if FileAccess.file_exists(path) else ""

func write(path: String, text: String, expected_digest: String) -> String:
	var absolute := ProjectSettings.globalize_path(path)
	if text.to_utf8_buffer().size() > MAX_BYTES:
		return "Document snapshot exceeds 1 GiB."
	if (FileAccess.file_exists(absolute) and expected_digest == "") or digest(absolute) != expected_digest:
		return "The file changed on disk. Open it again or Save As to a new directory."
	var error := DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	if error != OK:
		return error_string(error)
	var pending := absolute + ".pending-" + Crypto.new().generate_random_bytes(8).hex_encode()
	var failure := _write_text(pending, text)
	if failure != "":
		return failure
	if expected_digest != "":
		var previous_pending := pending + ".previous"
		error = DirAccess.copy_absolute(absolute, previous_pending)
		if error != OK:
			return error_string(error)
		if digest(previous_pending) != expected_digest:
			return "The file changed while saving. Pending copies were preserved; open it again."
		error = _publish(previous_pending, absolute + ".previous")
		if error != OK:
			return error_string(error)
	if digest(absolute) != expected_digest:
		return "The file changed while saving. Pending copies were preserved; open it again."
	# Replace in one rename; never move the current document away first.
	error = _publish(pending, absolute)
	return "" if error == OK else "Save failed; current and pending files were preserved: " + error_string(error)

func _write_text(path: String, text: String) -> String:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return error_string(FileAccess.get_open_error())
	file.store_string(text)
	file.flush()
	var error := file.get_error()
	file.close()
	return "" if error == OK else error_string(error)

func _publish(source: String, destination: String) -> Error:
	return DirAccess.rename_absolute(source, destination)
