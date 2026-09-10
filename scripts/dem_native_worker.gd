extends RefCounted
const FILES := preload("./authoring_files.gd")
const TYPES := preload("./import_layer.gd")
const SNAPSHOT := preload("./project_snapshot.gd")

static func inputs(request: Dictionary) -> Dictionary:
	var files := {}
	var groups := {"original":0, "capture":0, "png":0, "project":0}
	var reviewed: Dictionary = request.reviewed
	var data: Dictionary = request.data
	var sources: Variant = reviewed.get("sources", [{"source":reviewed.get("source")}])
	if sources is not Array or sources.is_empty() or sources.size() > 4: return {"error":"Invalid DEM source count."}
	var entries: Array = []
	for index in range(sources.size()):
		if sources[index] is not Dictionary or sources[index].get("source") is not Dictionary: return {"error":"Invalid DEM source identity."}
		var source: Dictionary = sources[index].source
		if source.get("path") is not String: return {"error":"DEM requires a reviewed local source."}
		var capture: String = request.destination + (".source-%d.tif" % index if reviewed.get("adapter") == "copernicus-dem-v2" else "")
		entries.append([source.path, source.get("bytes"), source.get("sha256"), "original"])
		entries.append([capture, source.get("bytes"), source.get("sha256"), "capture"])
	var outputs: Variant = data.get("outputs", [data])
	if outputs is not Array or outputs.is_empty() or outputs.size() > 16: return {"error":"Invalid DEM output count."}
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
		if entry[3] != "project" and (not TYPES._count(entry[1], FILES.MAX_PAYLOAD_BYTES) or size != int(entry[1]) or not TYPES._hex(entry[2], 64)): return {"error":"DEM input identity changed."}
		groups[entry[3]] += size
		if groups[entry[3]] > FILES.MAX_PAYLOAD_BYTES: return {"error":"DEM input group exceeds 64 MiB."}
		files[path] = {"bytes":size, "sha256":entry[2]}
	return {"files":files}

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
	var layer := preload("./dem_import_layer.gd").new()
	var retained := {}
	if failure == "":
		progress.call("validate", 0, 1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var terrain := preload("./terrain_tools.gd").new()
		terrain.store = store
		failure = layer.stage_dem(terrain, request.data, request.reviewed, request.destination,
			{"layer_id":request.layer_id, "scratch":directory.path_join("candidate"), "hashes":{}, "retained":retained, "progress":progress})
	if failure == "": failure = check_files(captured.files, "recheck", progress)
	if failure == "":
		var bundle := var_to_bytes({"value":layer.value, "patches":layer._patches, "retained":retained, "blob_paths":layer._blobs.keys()})
		if bundle.size() > 24 * 1024 * 1024: failure = "DEM transfer exceeds 24 MiB."
		else:
			failure = FILES.write_new(directory.path_join("bundle.bin"), bundle)
			if failure == "": output.merge({"payloads":fingerprint, "bundle_bytes":bundle.size(), "bundle_sha256":FILES.digest(bundle)})
	layer.discard()
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.left(2000)}
	return output
