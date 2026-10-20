extends RefCounted
const FILES := preload("./authoring_files.gd")
const TYPES := preload("./import_layer.gd")
const PNG := preload("./terrain_png.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const INPUTS := preload("./dem_native_worker.gd")
const LIMITS := preload("./limit_warnings.gd")
const HISTORY := preload("./history_codec.gd")

static func validate(request: Dictionary, directory: String, identity: String, progress: Callable) -> Dictionary:
	var output := {"ok":false, "request":identity}
	var failure := ""
	if request.get("request") != identity or request.get("document") is not Dictionary or request.get("project") is not String or request.get("options") is not Dictionary or not TYPES._hex(request.get("layer_id"), 32): failure = "Invalid PNG request."
	var options: Dictionary = request.options if request.get("options") is Dictionary else {}
	if failure == "":
		if options.get("path") is not String or not options.path.is_absolute_path() or options.get("cell") is not Array or options.cell.size() != 2 or options.get("attribution") is not Dictionary: failure = "Invalid PNG source/options."
		for key in ["spacing", "offset", "step", "accuracy"]:
			if not _integer(options.get(key)): failure = "Invalid PNG numeric option."
		if options.get("cell") is Array:
			for value: Variant in options.cell:
				if not _integer(value): failure = "Invalid PNG cell."
	var files := {}
	if failure == "":
		var source := FileAccess.open(options.path, FileAccess.READ)
		if source == null: failure = "Cannot read original PNG."
		elif source.get_length() > PNG.MAX_BYTES: failure = "PNG source exceeds 256 MiB."
		else: files[options.path] = {"bytes":source.get_length(), "sha256":""}
		if source != null: source.close()
	var total := 0
	var counted := {}
	var notes: Array = []
	if failure == "":
		for field in ["assets", "heightmaps"]:
			for record: Dictionary in request.document.get(field, []):
				if not SNAPSHOT.safe_relative(str(record.path)):
					failure = "Unsafe PNG project payload."
					break
				var path: String = request.project.path_join(record.path)
				if counted.has(path): continue
				counted[path] = true
				var file := FileAccess.open(path, FileAccess.READ)
				if file == null:
					failure = "Missing PNG project payload."
					break
				total += file.get_length()
				files[path] = {"bytes":file.get_length(), "sha256":""}
				file.close()
				# Hashed in blocks, never loaded whole: the former 64 MiB only warns.
				if total > INPUTS.GROUP_LIMIT:
					failure = "PNG project payloads exceed 2 GiB."
					break
			if failure != "": break
	LIMITS.over(notes, "png_project_bytes", total, INPUTS.WARN_GROUP_BYTES, "Project payload bytes checked for the PNG")
	if failure == "": failure = INPUTS.check_files(files, "source", progress)
	var fingerprint := JSON.stringify(files).sha256_text()
	if failure == "" and request.get("expected_payloads", "") not in ["", fingerprint]: failure = "PNG source or project payload changed since review; stage again."
	var layer := preload("./heightmap_import_layer.gd").new()
	var prepared := {}
	var retained := {}
	if failure == "":
		progress.call("validate", 0, 1)
		var sha: String = files[options.path].sha256
		# The stored payload may be a re-encoded copy: the layer registers the
		# STORED content address before any candidate file is written.
		var register := func(path: String) -> String: return FILES.write_new(directory.path_join("png-output.json"), JSON.stringify({"request":identity, "sha256":path.get_file().get_basename()}).to_utf8_buffer())
		if failure == "":
			var store := preload("./document_store.gd").new()
			store.document = request.document
			store.project_path = request.project
			var terrain := preload("./terrain_tools.gd").new()
			terrain.store = store
			failure = layer.stage(terrain, options.path, Vector2i(options.cell[0], options.cell[1]), int(options.spacing), int(options.offset), int(options.step), int(options.accuracy), options.attribution, true, request.layer_id,
				{"scratch":directory.path_join("candidate"), "hashes":{}, "prepared":prepared, "retained":retained, "progress":progress, "expected_source":sha, "limit_warnings":notes, "register_output":register})
	if failure == "" and prepared.command.get("history_released", false):
		prepared.retained = retained
		LIMITS.note(notes, "undo_history", int(prepared.command.bytes), HISTORY.RETAINED_LIMIT, "Applying this change releases earlier Undo history")
	if failure == "":
		var mementos: Dictionary = prepared.command.get("binary_mementos", prepared.get("retained", {}))
		for path: String in mementos:
			if layer._blobs.has(path): continue
			var original: Dictionary = files.get(request.project.path_join(path), {})
			if original.is_empty() or FILES.digest(mementos[path]) != original.sha256:
				failure = "PNG previous payload changed while preparing Undo."
				break
	if failure == "":
		var command := preload("./import_command.gd")
		failure = command.write_bundle(directory, {"value":layer.value, "prepared":command.encode(prepared), "blob_paths":layer._blobs.keys()}, output)
		if failure == "": output.payloads = fingerprint
	if failure == "": failure = INPUTS.check_files(files, "recheck", progress)
	LIMITS.merge(notes, output.get("limit_warnings", []))
	output.limit_warnings = notes
	layer.discard()
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.replace("DEM input", "PNG input").left(2000)}
	return output

static func _integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value)) and absf(float(value)) <= 10000000
