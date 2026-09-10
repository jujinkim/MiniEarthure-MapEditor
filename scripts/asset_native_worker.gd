extends RefCounted
const FILES := preload("./authoring_files.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const INPUTS := preload("./dem_native_worker.gd")
const COMMAND := preload("./import_command.gd")

static func validate(request: Dictionary, directory: String, identity: String, progress: Callable) -> Dictionary:
	var output := {"ok":false, "request":identity}
	var failure := ""
	if request.get("request") != identity or request.get("document") is not Dictionary or request.get("project") is not String or not request.project.is_absolute_path() or request.get("record") is not Dictionary or request.record.get("id") is not String or request.record.id.is_empty() or request.get("source") is not String: failure = "Invalid asset request."
	var files := {}
	if failure == "" and request.source != "":
		if not request.source.is_absolute_path() or request.source.get_extension().to_lower() not in ["glb", "png", "webp"]: failure = "Choose a local GLB, PNG or WebP."
		else:
			var file := FileAccess.open(request.source, FileAccess.READ)
			if file == null: failure = "Cannot read original asset."
			elif file.get_length() > COMMAND.HISTORY_LIMIT: failure = "Asset source exceeds the 16 MiB Undo budget."
			else: files[request.source] = {"bytes":file.get_length(), "sha256":""}
			if file != null: file.close()
	var total := 0
	var counted := {}
	if failure == "":
		for field in ["assets", "heightmaps"]:
			if request.document.get(field) is not Array:
				failure = "Invalid asset project payloads."
				break
			for record: Variant in request.document[field]:
				if record is not Dictionary or record.get("path") is not String or not SNAPSHOT.safe_relative(record.path):
					failure = "Unsafe asset project payload."
					break
				var path: String = request.project.path_join(record.path)
				if counted.has(path): continue
				counted[path] = true
				var file := FileAccess.open(path, FileAccess.READ)
				if file == null:
					failure = "Missing asset project payload."
					break
				total += file.get_length()
				files[path] = {"bytes":file.get_length(), "sha256":""}
				file.close()
				if total > FILES.MAX_PAYLOAD_BYTES:
					failure = "Asset project payloads exceed 64 MiB."
					break
			if failure != "": break
	if failure == "": failure = INPUTS.check_files(files, "source", progress)
	var fingerprint := JSON.stringify(files).sha256_text()
	var prepared := {}
	var blob_paths: Array = []
	if failure == "":
		progress.call("validate", 0, 1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var author := preload("./authoring_tools.gd").new()
		author.store = store
		var register := func(path: String) -> String: return FILES.write_new(directory.path_join("asset-output.json"), JSON.stringify({"request":identity, "path":path}).to_utf8_buffer())
		failure = author.asset(request.record.duplicate(true), request.source, true, {"scratch":directory.path_join("candidate"), "hashes":{}, "prepared":prepared, "progress":progress, "expected_source":files[request.source].sha256 if request.source != "" else "", "register_output":register, "blob_paths":blob_paths})
	if failure == "":
		for path: String in prepared.command.get("binary_mementos", {}):
			if path in blob_paths: continue
			var original: Dictionary = files.get(request.project.path_join(path), {})
			if original.is_empty() or FILES.digest(prepared.command.binary_mementos[path]) != original.sha256:
				failure = "Previous asset changed while preparing Undo."
				break
	if failure == "":
		failure = COMMAND.write_bundle(directory, {"request":identity, "prepared":COMMAND.encode(prepared), "blob_paths":blob_paths}, output)
		if failure == "": output.payloads = fingerprint
	if failure == "": failure = INPUTS.check_files(files, "recheck", progress)
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.replace("DEM input", "Asset input").left(2000)}
	return output
