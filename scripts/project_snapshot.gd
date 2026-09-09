extends RefCounted
## Detached, bounded file snapshots; only operation-owned scratch is removed.
const PAYLOADS := preload("./authoring_files.gd")
const FILES := preload("./document_files.gd")
const MAX_BYTES := 64 * 1024 * 1024

static func error(message: String) -> Dictionary:
	return {"ok": false, "error": {"code": "E_PROJECT_COPY", "message": message}}

static func capture(document: Dictionary, source: String, history: Array = []) -> Dictionary:
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	var checked: Dictionary = JSON.parse_string(native.validate_document(JSON.stringify(document)))
	if not checked.ok: return checked
	var paths := {}
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in checked.data.document.get(field, []): paths[str(record.path)] = true
	# Save As keeps Undo/Redo usable, including old immutable raster versions.
	for command: Dictionary in history:
		for patch: Dictionary in command.patches:
			if patch.field in ["assets", "heightmaps"]:
				for value in [patch.before, patch.after]:
					if value != null: paths[str(value.path)] = true
	var blobs := {}
	var hashes := {}
	var total := 0
	for path: String in paths:
		if source.is_empty(): return error("Referenced files require their original project directory.")
		if not safe_relative(path): return error("Unsafe project payload path: " + path)
		var full := source.path_join(path)
		if not FileAccess.file_exists(full): return error("Referenced file is missing: " + path)
		var before := FileAccess.get_sha256(full)
		var read := PAYLOADS.read(full, MAX_BYTES - total)
		if read.has("error"): return error(read.error)
		var hash := PAYLOADS.digest(read.bytes)
		if before != hash or FileAccess.get_sha256(full) != hash:
			return error("Source changed during snapshot: " + path)
		blobs[path] = read.bytes
		hashes[path] = hash
		total += read.bytes.size()
	for command: Dictionary in history:
		for path: String in command.get("binary_mementos", {}):
			if not blobs.has(path) or blobs[path] != command.binary_mementos[path]:
				return error("History payload changed: " + path)
	return {"ok": true, "data": {"canonical": checked.data.canonical, "document": checked.data.document,
		"blobs": blobs, "hashes": hashes, "bytes": total}}

static func safe_relative(path: String) -> bool:
	if path.is_absolute_path() or path.contains("\\") or path.contains(":"): return false
	for part in path.split("/"):
		if part in ["", ".", ".."]: return false
	return path != "document.json" and not path.begins_with("document.json.")

static func stage(snapshot: Dictionary) -> Dictionary:
	var scratch := ProjectSettings.globalize_path("user://export-snapshots/" + Crypto.new().generate_random_bytes(12).hex_encode())
	var failure := PAYLOADS.write_new(scratch.path_join("document.json"), str(snapshot.canonical).to_utf8_buffer())
	for path: String in snapshot.blobs:
		if failure != "": break
		failure = PAYLOADS.write_new(scratch.path_join(path), snapshot.blobs[path])
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	var result: Dictionary = JSON.parse_string(native.open_project(scratch)) if failure == "" else error(failure)
	if not result.ok:
		PAYLOADS.remove_scratch(scratch)
		return result
	return {"ok": true, "data": {"path": scratch, "bridge": native, "inspection": result.data}}

static func copy_to(snapshot: Dictionary, destination: String) -> String:
	# New project only; never overwrite an unrelated project or follow target links.
	if FileAccess.file_exists(destination.path_join("document.json")):
		return "Save As requires a directory without document.json."
	for path: String in snapshot.blobs:
		var cursor := destination.path_join(path)
		while cursor != cursor.get_base_dir():
			var parent := DirAccess.open(cursor.get_base_dir())
			if parent != null and parent.is_link(cursor.get_file()): return "Save As refuses a destination symlink: " + cursor
			cursor = cursor.get_base_dir()
		if FileAccess.file_exists(destination.path_join(path)) and FileAccess.get_sha256(destination.path_join(path)) != snapshot.hashes[path]:
			return "Save As payload conflict: " + path
	var staged := stage(snapshot)
	if not staged.ok: return str(staged.error.code) + ": " + str(staged.error.message)
	for path: String in snapshot.blobs:
		var failure := install_payload(destination.path_join(path), snapshot.blobs[path], snapshot.hashes[path])
		if failure != "":
			PAYLOADS.remove_scratch(staged.data.path)
			return failure
	# Verify the installed candidate before publishing its document last.
	for path: String in snapshot.blobs:
		if FileAccess.get_sha256(destination.path_join(path)) != snapshot.hashes[path]:
			PAYLOADS.remove_scratch(staged.data.path)
			return "Copied payload changed before document publication: " + path
	var failure := FILES.new().write(destination.path_join("document.json"), snapshot.canonical, "")
	PAYLOADS.remove_scratch(staged.data.path)
	return failure

static func install_payload(destination: String, bytes: PackedByteArray, hash: String) -> String:
	if FileAccess.file_exists(destination):
		return "" if FileAccess.get_sha256(destination) == hash else "Save As payload conflict: " + destination
	var pending := destination + ".pending-" + Crypto.new().generate_random_bytes(8).hex_encode()
	var failure := PAYLOADS.write_new(pending, bytes)
	if failure != "": return failure + " Pending payload retained."
	if FileAccess.get_sha256(pending) != hash: return "Copy verification failed; pending payload retained."
	if FileAccess.file_exists(destination): return "Destination appeared; pending payload retained."
	var err := DirAccess.rename_absolute(pending, destination)
	return "" if err == OK else "Cannot publish copied payload; pending file retained: " + error_string(err)
