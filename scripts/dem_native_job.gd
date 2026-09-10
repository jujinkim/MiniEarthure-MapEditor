extends "./import_native_job.gd"
## Raster validation uses the same kill/reap/IPC contract as vector validation.
var request := {}
var bundle := {}
var source_total := -1
var expected_cells := 0

func start_dem(store: RefCounted, data: Dictionary, reviewed: Dictionary, destination: String, adopt: bool, selection: String, token: String, previous: Dictionary = {}) -> String:
	if _attempted or cancelled: return "Native DEM jobs are single use."
	_attempted = true
	if not LAYER._hex(token, 32) or store.project_path == "" or store.has_gesture(): return "Save the project and finish gestures before DEM validation."
	if adopt and (not LAYER._hex(previous.get("payloads"), 64) or not LAYER._hex(previous.get("layer_id"), 32)): return "Missing reviewed DEM identity."
	identity = token
	import_kind = "native"
	adopting = adopt
	selection_signature = selection
	project_source = store.project_path
	document_signature = JSON.stringify(store.document).sha256_text()
	document_epoch = store.command_epoch
	_store_id = store.get_instance_id()
	var outputs: Variant = data.get("outputs", [data])
	if reviewed.get("adapter") not in ["copernicus-dem-v1", "copernicus-dem-v2"] or outputs is not Array or outputs.is_empty() or outputs.size() > 16: return "Invalid DEM output count."
	for output: Variant in outputs:
		if output is not Dictionary or not LAYER._hex(output.get("png_sha256"), 64): return "Invalid DEM PNG identity."
	expected_cells = (data.get("outputs", []).size() if reviewed.get("adapter") == "copernicus-dem-v2" else 1) if not store.document.roads.is_empty() else 0
	if expected_cells > 16: return "DEM exceeds 16 candidate cells."
	structural = expected_cells > 0
	request = {"kind":"dem", "request":token, "document":store.document.duplicate(true), "project":project_source,
		"data":data.duplicate(true), "reviewed":reviewed.duplicate(true), "destination":destination,
		"layer_id":previous.layer_id if adopt else token, "expected_payloads":previous.get("payloads", "")}
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in store.document.get(field, []):
			if not SNAPSHOT.safe_relative(str(record.path)): return "Unsafe DEM dependency path."
			if record.path not in owned_payloads: owned_payloads.append(record.path)
	# Every new content-addressed output is known before the child starts, so
	# interrupted work can retire only these paths, without scanning unknown files.
	for output: Dictionary in outputs:
		if not LAYER._hex(output.get("png_sha256"), 64): return "Invalid DEM PNG identity."
		var path := "editor/" + str(output.png_sha256) + ".png"
		if path not in owned_payloads: owned_payloads.append(path)
	var bytes := JSON.stringify(request).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "Native DEM request exceeds 24 MiB."
	return _start_request(bytes)

func matches(store: RefCounted, selection: String) -> bool:
	return store.get_instance_id() == _store_id and store.command_epoch == document_epoch and selection == selection_signature and store.project_path == project_source and not store.has_gesture() and JSON.stringify(store.document).sha256_text() == document_signature

func _source_bytes() -> int: return source_total

func _event(line: PackedByteArray) -> void:
	super._event(line)
	if not cancelled and progress.get("stage") == "source": source_total = int(progress.total)
	if not cancelled and progress.get("stage") == "generate" and progress.total != expected_cells: _fail("Incomplete DEM cell validation.")

func _decode_command(output: Dictionary) -> void:
	var decoded := COMMAND.read_bundle(directory, output)
	var failure := str(decoded.get("error", ""))
	if failure == "" and (decoded.get("value") is not Dictionary or decoded.get("blob_paths") is not Array or decoded.value.get("layer_id") != request.layer_id): failure = "Invalid DEM candidate transfer."
	if failure == "":
		_prepared = COMMAND.decode(decoded.get("prepared"))
		failure = str(_prepared.get("error", ""))
	if failure == "":
		decoded.patches = _prepared.command.patches
		decoded.retained = _prepared.command.get("binary_mementos", {})
		for path: Variant in decoded.blob_paths:
			if path is not String or not decoded.retained.has(path) or path != "editor/" + PAYLOADS.digest(decoded.retained[path]) + ".png":
				failure = "Invalid immutable DEM payload."
				break
	if failure == "":
		for patch: Variant in decoded.patches:
			if patch.get("field") not in ["heightmaps", "attributions"] or patch.get("after") is not Dictionary or (patch.get("before") != null and patch.before is not Dictionary):
				failure = "Invalid DEM command transfer."
				break
			if patch.field == "heightmaps" and (patch.after.get("path") not in decoded.blob_paths or (patch.before != null and not decoded.retained.has(patch.before.get("path")))):
				failure = "Missing DEM binary memento."
				break
	if failure != "":
		result = {"ok":false, "error":{"code":"E_IMPORT_NATIVE", "message":failure}}
		_prepared = {}
		return
	decoded.erase("prepared")
	bundle = decoded

func commit(store: RefCounted) -> String:
	if _consumed or not adopting or not done or not exited or cancelled or _prepared.is_empty() or bundle.is_empty() or not matches(store, selection_signature): return "Stale or incomplete DEM adoption."
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
