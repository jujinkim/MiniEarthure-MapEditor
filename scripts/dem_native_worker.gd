extends RefCounted
const FILES := preload("./authoring_files.gd")
const TYPES := preload("./import_layer.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const LAYER := preload("./dem_import_layer.gd")
const LIMITS := preload("./limit_warnings.gd")
## Hashed in 1 MiB blocks, never loaded whole: derived PNGs and project
## payloads only warn above the former 64 MiB.
const GROUP_LIMIT := 2 * 1024 * 1024 * 1024
const WARN_GROUP_BYTES := 64 * 1024 * 1024

static func inputs(request: Dictionary) -> Dictionary:
	var files := {}
	var notes: Array = []
	var groups := {"original":0, "capture":0, "png":0, "project":0}
	var reviewed: Dictionary = request.reviewed
	var data: Dictionary = request.data
	var sources: Variant = reviewed.get("sources")
	if sources is not Array or sources.is_empty() or sources.size() > LAYER.MAX_SOURCES: return {"error":"Invalid DEM source count."}
	var entries: Array = []
	for index in range(sources.size()):
		if sources[index] is not Dictionary or sources[index].get("source") is not Dictionary: return {"error":"Invalid DEM source identity."}
		var source: Dictionary = sources[index].source
		if source.get("path") is not String: return {"error":"DEM requires a reviewed local source."}
		var capture: String = request.destination + (".source-%d.tif" % index)
		entries.append([source.path, source.get("bytes"), source.get("sha256"), "original"])
		entries.append([capture, source.get("bytes"), source.get("sha256"), "capture"])
	var outputs: Variant = data.get("outputs")
	if outputs is not Array or outputs.is_empty() or outputs.size() > LAYER.MAX_CELLS: return {"error":"Invalid DEM output count."}
	for output: Variant in outputs:
		if output is not Dictionary: return {"error":"Invalid DEM output identity."}
		entries.append([output.get("png_path"), output.get("png_bytes"), output.get("png_sha256"), "png"])
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in request.document.get(field, []):
			if not SNAPSHOT.safe_relative(str(record.path)): return {"error":"Unsafe project payload path."}
			var path: String = request.project.path_join(record.path)
			entries.append([path, -1, "", "project"])
	for entry: Array in entries:
		if entry[0] is not String or not str(entry[0]).is_absolute_path(): return {"error":"Invalid DEM input path."}
		var path: String = entry[0]
		if files.has(path): continue
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null: return {"error":"DEM input is missing: " + path}
		var size := file.get_length()
		file.close()
		var tile: bool = entry[3] in ["original", "capture"]
		if entry[3] != "project" and (not TYPES._count(entry[1], LAYER.MAX_SOURCE_BYTES if tile else FILES.MAX_PAYLOAD_BYTES) or size != int(entry[1]) or not TYPES._hex(entry[2], 64)): return {"error":"DEM input identity changed."}
		groups[entry[3]] += size
		if tile: LIMITS.over(notes, "dem_tile_bytes", size, LAYER.WARN_SOURCE_BYTES, "DEM tile size in bytes")
		elif groups[entry[3]] > GROUP_LIMIT: return {"error":"DEM input group exceeds 2 GiB."}
		else: LIMITS.over(notes, "dem_input_group_bytes", groups[entry[3]], WARN_GROUP_BYTES, "Derived terrain or project payload bytes checked for DEM")
		files[path] = {"bytes":size, "sha256":entry[2]}
	return {"files":files, "limit_warnings":notes}

static func check_files(files: Dictionary, stage: String, progress: Callable) -> String:
	var total := 0
	for item: Dictionary in files.values(): total += int(item.bytes)
	var completed := 0
	var reported := 0
	progress.call(stage, 0, total)
	for path: String in files:
		var item: Dictionary = files[path]
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null or file.get_length() != int(item.bytes): return "DEM input changed during validation."
		var hash := HashingContext.new()
		hash.start(HashingContext.HASH_SHA256)
		var remaining := int(item.bytes)
		while remaining > 0:
			var bytes := file.get_buffer(mini(1024 * 1024, remaining))
			if bytes.is_empty(): return "DEM input changed while reading."
			hash.update(bytes)
			remaining -= bytes.size()
			completed += bytes.size()
			if completed - reported >= 4 * 1024 * 1024 or completed == total:
				progress.call(stage, completed, total)
				reported = completed
		var digest := hash.finish().hex_encode()
		var stable := file.get_length() == int(item.bytes)
		file.close()
		if not stable or (item.sha256 != "" and digest != item.sha256): return "DEM input hash changed during validation."
		item.sha256 = digest
	return ""

static func validate(request: Dictionary, directory: String, identity: String, progress: Callable) -> Dictionary:
	var output := {"ok":false, "request":identity}
	var failure := ""
	if request.get("request") != identity or request.get("document") is not Dictionary or request.get("project") is not String or request.get("data") is not Dictionary or request.get("reviewed") is not Dictionary or request.get("destination") is not String or not TYPES._hex(request.get("layer_id"), 32): failure = "Invalid native DEM request."
	var captured := inputs(request) if failure == "" else {}
	if captured.has("error"): failure = captured.error
	if failure == "": failure = check_files(captured.files, "source", progress)
	var fingerprint := JSON.stringify(captured.get("files", {})).sha256_text()
	if failure == "" and request.get("expected_payloads", "") not in ["", fingerprint]: failure = "DEM source or project payload changed since review."
	var layer := LAYER.new()
	var retained := {}
	var prepared := {}
	if failure == "":
		progress.call("validate", 0, 1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var terrain := preload("./terrain_tools.gd").new()
		terrain.store = store
		failure = layer.stage_dem(terrain, request.data, request.reviewed, request.destination,
			{"layer_id":request.layer_id, "scratch":directory.path_join("candidate"), "hashes":{}, "retained":retained, "prepared":prepared, "command_label":"Adopt DEM terrain", "progress":progress,"ground_buildings":request.get("ground_buildings",false),"verified_files":captured.files})
	if failure == "" and prepared.command.get("history_released", false): prepared.retained = retained
	if failure == "":
		var command := preload("./import_command.gd")
		failure = command.write_bundle(directory, {"value":layer.value, "prepared":command.encode(prepared), "blob_paths":layer._blobs.keys()}, output)
		if failure == "": output.payloads = fingerprint
	if failure == "": failure = check_files(captured.files, "recheck", progress)
	var notes: Array = []
	for list: Variant in [captured.get("limit_warnings", []), layer.limit_warnings, output.get("limit_warnings", [])]: LIMITS.merge(notes, list)
	if failure == "" and prepared.get("command", {}).get("history_released", false):
		LIMITS.note(notes, "undo_history", int(prepared.command.bytes), preload("./history_codec.gd").RETAINED_LIMIT, "Applying this change releases earlier Undo history")
	output.limit_warnings = notes
	layer.discard()
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.left(2000)}
	return output
