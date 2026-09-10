extends RefCounted
const FILES := preload("./authoring_files.gd")
const TYPES := preload("./import_layer.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const INPUTS := preload("./dem_native_worker.gd")
const TERRAIN := preload("./terrain_tools.gd")

static func check_stroke(value: Dictionary) -> String:
	if value.get("stroke") is not Array or value.stroke.is_empty() or value.stroke.size() > 2048 or value.get("options") is not Dictionary: return "Terrain needs 1–2048 stroke points and brush options."
	for point: Variant in value.stroke:
		if point is not Array or point.size() != 2: return "Invalid terrain point."
		for axis: Variant in point:
			if not preload("./heightmap_native_worker.gd")._integer(axis): return "Invalid terrain coordinate."
	if value.options.get("mode") not in ["raise", "lower", "flatten", "smooth"]: return "Unknown terrain brush mode."
	for key in ["spacing_cm", "radius_cm", "amount_cm", "target_cm"]:
		if not preload("./heightmap_native_worker.gd")._integer(value.options.get(key)): return "Invalid terrain numeric option."
	if value.options.amount_cm < 0: return "Terrain amount must be nonnegative."
	return ""

static func validate(request: Dictionary, directory: String, identity: String, progress: Callable) -> Dictionary:
	var output := {"ok":false, "request":identity}
	var failure := ""
	if request.get("request") != identity or request.get("document") is not Dictionary or request.get("project") is not String or not request.project.is_absolute_path() or request.get("stroke") is not Dictionary or request.get("layer_id") != identity: failure = "Invalid terrain request."
	if failure == "": failure = check_stroke(request.stroke)
	var files := {}
	var total := 0
	if failure == "":
		for field in ["assets", "heightmaps"]:
			for record: Dictionary in request.document.get(field, []):
				if not SNAPSHOT.safe_relative(str(record.path)):
					failure = "Unsafe terrain project payload."
					break
				var path: String = request.project.path_join(record.path)
				if files.has(path): continue
				var file := FileAccess.open(path, FileAccess.READ)
				if file == null:
					failure = "Missing terrain project payload."
					break
				total += file.get_length()
				files[path] = {"bytes":file.get_length(), "sha256":""}
				file.close()
				if total > FILES.MAX_PAYLOAD_BYTES:
					failure = "Terrain project payloads exceed 64 MiB."
					break
			if failure != "": break
	if failure == "": failure = INPUTS.check_files(files, "source", progress)
	var expected := {}
	for path: String in files: expected[path.trim_prefix(request.project + "/")] = files[path].sha256
	var prepared := {}
	var plan := {}
	if failure == "":
		progress.call("validate", 0, 1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var terrain := TERRAIN.new()
		terrain.store = store
		terrain.settings = request.stroke.options
		for point: Array in request.stroke.stroke: terrain.stroke.append(Vector2(point[0], point[1]))
		plan = terrain._plan({"expected":expected})
		failure = str(plan.get("error", ""))
		if failure == "" and plan.patches.is_empty(): failure = "Terrain stroke has no changes."
		if failure == "":
			var hashes: Array = []
			for path: String in plan.blobs: hashes.append(FILES.digest(plan.blobs[path]))
			failure = FILES.write_new(directory.path_join("terrain-output.json"), JSON.stringify({"request":identity, "hashes":hashes}).to_utf8_buffer())
		if failure == "":
			progress.call("validate", 1, 1)
			var context := {"scratch":directory.path_join("candidate"), "hashes":{}, "prepared":prepared, "progress":progress}
			failure = FILES.apply(store, "Terrain " + str(terrain.settings.mode), plan.patches, plan.blobs, plan.cells, true, context)
			if failure == "":
				for path: String in context.hashes:
					if context.hashes[path] != expected.get(path): failure = "Terrain payload changed during candidate snapshot."
	if failure == "":
		for path: String in prepared.command.get("binary_mementos", {}):
			if plan.blobs.has(path): continue
			if FILES.digest(prepared.command.binary_mementos[path]) != expected.get(path):
				failure = "Terrain previous payload changed while preparing Undo."
				break
	if failure == "":
		var command := preload("./import_command.gd")
		failure = command.write_bundle(directory, {"value":{"layer_id":identity}, "prepared":command.encode(prepared), "blob_paths":plan.blobs.keys()}, output)
		if failure == "": output.payloads = JSON.stringify(files).sha256_text()
	if failure == "": failure = INPUTS.check_files(files, "recheck", progress)
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.replace("DEM input", "Terrain input").left(2000)}
	return output
