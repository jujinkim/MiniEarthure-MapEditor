extends "./import_native_job.gd"
## Shared raster transfer, immutable publication and native job lifetime.
var request := {}
var bundle := {}
var source_total := -1
var expected_cells := 0

func matches(store: RefCounted, selection: String) -> bool:
	return store.get_instance_id() == _store_id and store.command_epoch == document_epoch and selection == selection_signature and store.project_path == project_source and not store.has_gesture() and JSON.stringify(store.document).sha256_text() == document_signature

func _source_bytes() -> int: return source_total

func _event(line: PackedByteArray) -> void:
	super._event(line)
	if not cancelled and progress.get("stage") == "source": source_total = int(progress.total)
	if not cancelled and progress.get("stage") == "generate" and progress.total != expected_cells: _fail("Incomplete raster cell validation.")

func _decode_command(output: Dictionary) -> void:
	var decoded := COMMAND.read_bundle(directory, output)
	var failure := str(decoded.get("error", ""))
	if failure == "" and (decoded.get("value") is not Dictionary or decoded.get("blob_paths") is not Array or decoded.value.get("layer_id") != request.layer_id): failure = "Invalid raster candidate transfer."
	if failure == "":
		_prepared = COMMAND.decode(decoded.get("prepared"))
		failure = str(_prepared.get("error", ""))
	if failure == "":
		decoded.patches = _prepared.command.patches
		decoded.retained = _prepared.command.get("binary_mementos", {})
		for path: Variant in decoded.blob_paths:
			if path is not String or not decoded.retained.has(path) or path != "editor/" + PAYLOADS.digest(decoded.retained[path]) + ".png":
				failure = "Invalid immutable raster payload."
				break
	if failure == "":
		for patch: Variant in decoded.patches:
			if patch.get("field") not in ["heightmaps", "attributions"] or patch.get("after") is not Dictionary or (patch.get("before") != null and patch.before is not Dictionary):
				failure = "Invalid raster command transfer."
				break
			if patch.field == "heightmaps" and (patch.after.get("path") not in decoded.blob_paths or (patch.before != null and not decoded.retained.has(patch.before.get("path")))):
				failure = "Missing raster binary memento."
				break
	if failure != "":
		result = {"ok":false, "error":{"code":"E_IMPORT_NATIVE", "message":failure}}
		_prepared = {}
		return
	decoded.erase("prepared")
	bundle = decoded

func commit(store: RefCounted) -> String:
	if _consumed or not adopting or not done or not exited or cancelled or _prepared.is_empty() or bundle.is_empty() or not matches(store, selection_signature): return "Stale or incomplete raster adoption."
	# Only immutable installation remains synchronous. Canonical validation, full
	# attribution and memento serialization/charging completed in the owned child.
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
