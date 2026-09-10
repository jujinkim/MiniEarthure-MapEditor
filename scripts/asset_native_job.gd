extends "./import_native_job.gd"
## Killable asset preparation. The live document receives one prepared command.
const OUTPUT_MARKER := "asset-output.json"
var request := {}
var bundle := {}
var source_total := -1

func start_asset(store: RefCounted, record: Dictionary, source: String, selection: String, token: String) -> String:
	if _attempted or cancelled: return "Asset jobs are single use."
	_attempted = true
	if not LAYER._hex(token, 32) or store.project_path.is_empty() or store.has_gesture(): return "Save the project and finish gestures before asset validation."
	if record.get("id") is not String or record.id.is_empty(): return "Choose an asset ID."
	if source != "" and (not source.is_absolute_path() or source.get_extension().to_lower() not in ["glb", "png", "webp"]): return "Choose an absolute local GLB, PNG or WebP path."
	identity = token
	import_kind = "native"
	adopting = true
	selection_signature = selection
	project_source = store.project_path
	document_signature = JSON.stringify(store.document).sha256_text()
	document_epoch = store.command_epoch
	_store_id = store.get_instance_id()
	request = {"kind":"asset", "request":token, "document":store.document.duplicate(true), "project":project_source, "record":record.duplicate(true), "source":source}
	for field in ["assets", "heightmaps"]:
		for payload: Dictionary in store.document.get(field, []):
			if not SNAPSHOT.safe_relative(str(payload.path)): return "Unsafe asset dependency path."
			if payload.path not in owned_payloads: owned_payloads.append(payload.path)
	var bytes := JSON.stringify(request).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "Asset request exceeds 24 MiB."
	return _start_request(bytes)

func matches(store: RefCounted, selection: String) -> bool:
	return store.get_instance_id() == _store_id and store.command_epoch == document_epoch and selection == selection_signature and store.project_path == project_source and not store.has_gesture() and JSON.stringify(store.document).sha256_text() == document_signature

func _source_bytes() -> int: return source_total

func _event(line: PackedByteArray) -> void:
	super._event(line)
	if not cancelled and progress.get("stage") == "source": source_total = int(progress.total)

func _decode_command(output: Dictionary) -> void:
	var decoded := COMMAND.read_bundle(directory, output)
	var failure := str(decoded.get("error", ""))
	if failure == "" and (decoded.get("request") != identity or decoded.get("blob_paths") is not Array or decoded.blob_paths.size() > 1): failure = "Invalid asset transfer."
	if failure == "":
		_prepared = COMMAND.decode(decoded.get("prepared"), true)
		failure = str(_prepared.get("error", ""))
	if failure == "":
		decoded.retained = _prepared.command.get("binary_mementos", {})
		for path: Variant in decoded.blob_paths:
			if path is not String or path.get_extension() not in ["glb", "png", "webp"] or not decoded.retained.has(path) or path != "editor/" + PAYLOADS.digest(decoded.retained[path]) + "." + path.get_extension():
				failure = "Invalid immutable asset transfer."
				break
	if failure == "":
		var asset_count := 0
		for patch: Dictionary in _prepared.command.patches:
			if patch.field != "assets": continue
			asset_count += 1
			if patch.id != request.record.id or patch.after.get("id") != patch.id or not decoded.retained.has(patch.after.get("path")) or (patch.before != null and not decoded.retained.has(patch.before.get("path"))): failure = "Missing asset binary memento."
			if request.source != "" and patch.after.get("path") not in decoded.blob_paths: failure = "Missing new asset payload."
		if asset_count != 1: failure = "Invalid asset command count."
	if failure != "":
		result = {"ok":false, "error":{"code":"E_IMPORT_NATIVE", "message":failure}}
		_prepared = {}
		return
	decoded.erase("prepared")
	bundle = decoded

func commit(store: RefCounted) -> String:
	if _consumed or not adopting or not done or not exited or cancelled or _prepared.is_empty() or bundle.is_empty() or not matches(store, selection_signature): return "Stale or incomplete asset adoption."
	_consumed = true
	for path: String in bundle.blob_paths:
		var failure := PAYLOADS.write_new(store.project_path.path_join(path), bundle.retained[path])
		if failure != "":
			_prepared = {}
			bundle = {}
			return failure
	var prepared := _prepared
	_prepared = {}
	bundle = {}
	return store._install_command(prepared)

func cleanup() -> void:
	if not _owns_directory or (_child_started and not exited): return
	var root := DirAccess.open(directory)
	if root != null and not root.is_link(OUTPUT_MARKER) and FileAccess.file_exists(directory.path_join(OUTPUT_MARKER)):
		var read := PAYLOADS.read(directory.path_join(OUTPUT_MARKER), 512)
		var marker: Variant = JSON.parse_string(read.bytes.get_string_from_utf8()) if not read.has("error") else null
		if marker is Dictionary and marker.get("request") == identity and marker.get("path") is String:
			var path: String = marker.path
			if path.get_extension() in ["glb", "png", "webp"] and path == "editor/" + path.get_file().get_basename() + "." + path.get_extension() and LAYER._hex(path.get_file().get_basename(), 64):
				if path not in owned_payloads: owned_payloads.append(path)
				DirAccess.remove_absolute(directory.path_join(OUTPUT_MARKER))
	super.cleanup()
