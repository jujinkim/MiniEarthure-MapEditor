extends RefCounted
const FILES := preload("./authoring_files.gd")
const TYPES := preload("./import_layer.gd")
const PNG := preload("./terrain_png.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const INPUTS := preload("./dem_native_worker.gd")

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
		elif source.get_length() > PNG.MAX_BYTES: failure = "PNG source exceeds 4 MiB."
		else: files[options.path] = {"bytes":source.get_length(), "sha256":""}
		if source != null: source.close()
	var total := 0
	var counted := {}
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
				if total > FILES.MAX_PAYLOAD_BYTES:
					failure = "PNG project payloads exceed 64 MiB."
					break
			if failure != "": break
	if failure == "": failure = INPUTS.check_files(files, "source", progress)
	var fingerprint := JSON.stringify(files).sha256_text()
	if failure == "" and request.get("expected_payloads", "") not in ["", fingerprint]: failure = "PNG source or project payload changed since review; stage again."
	var layer := preload("./heightmap_import_layer.gd").new()
	var prepared := {}
	if failure == "":
		progress.call("validate", 0, 1)
		var sha: String = files[options.path].sha256
		failure = FILES.write_new(directory.path_join("png-output.json"), JSON.stringify({"request":identity, "sha256":sha}).to_utf8_buffer())
		if failure == "":
			var store := preload("./document_store.gd").new()
			store.document = request.document
			store.project_path = request.project
			var terrain := preload("./terrain_tools.gd").new()
			terrain.store = store
			failure = layer.stage(terrain, options.path, Vector2i(options.cell[0], options.cell[1]), int(options.spacing), int(options.offset), int(options.step), int(options.accuracy), options.attribution, true, request.layer_id,
				{"scratch":directory.path_join("candidate"), "hashes":{}, "prepared":prepared, "progress":progress, "expected_source":sha})
	if failure == "":
		for path: String in prepared.command.get("binary_mementos", {}):
			if layer._blobs.has(path): continue
			var original: Dictionary = files.get(request.project.path_join(path), {})
			if original.is_empty() or FILES.digest(prepared.command.binary_mementos[path]) != original.sha256:
				failure = "PNG previous payload changed while preparing Undo."
				break
	if failure == "":
		var command := preload("./import_command.gd")
		failure = command.write_bundle(directory, {"value":layer.value, "prepared":command.encode(prepared), "blob_paths":layer._blobs.keys()}, output)
		if failure == "": output.payloads = fingerprint
	if failure == "": failure = INPUTS.check_files(files, "recheck", progress)
	layer.discard()
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.replace("DEM input", "PNG input").left(2000)}
	return output

static func _integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value)) and absf(float(value)) <= 10000000
