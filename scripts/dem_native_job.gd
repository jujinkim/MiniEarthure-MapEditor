extends "./raster_native_job.gd"
## Local DEM request admission; lifecycle and binary commands are shared.
var ground_layers := {}
var fit_index := {}

func start_dem(store: RefCounted, data: Dictionary, reviewed: Dictionary, destination: String, adopt: bool, selection: String, token: String, previous: Dictionary = {}, ground_buildings: bool = false) -> String:
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
	var outputs: Variant = data.get("outputs")
	generation_limit = preload("./dem_import_layer.gd").MAX_CELLS
	if reviewed.get("adapter") != "copernicus-dem-v1" or outputs is not Array or outputs.is_empty() or outputs.size() > generation_limit: return "Invalid DEM output count."
	for output: Variant in outputs:
		if output is not Dictionary or not LAYER._hex(output.get("png_sha256"), 64): return "Invalid DEM PNG identity."
	expected_cells = outputs.size() if not store.document.roads.is_empty() or (ground_buildings and not store.document.buildings.is_empty()) else 0
	structural = expected_cells > 0
	if ground_buildings: ground_layers = preload("./dem_building_grounding.gd").layers(store.document)
	request = {"kind":"dem", "request":token, "document":store.document.duplicate(true), "project":project_source,
		"data":data.duplicate(true), "reviewed":reviewed.duplicate(true), "destination":destination,"ground_buildings":ground_buildings,
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
	if bytes.size() > request_limit: return "Native DEM request exceeds 1.5 GiB."
	return _start_request(bytes)

func _additional_patch(patch: Dictionary) -> bool:
	if patch.get("field") in ["roads", "nodes"]:
		if fit_index.is_empty(): fit_index = preload("./dem_structure_fit.gd").index(request.document)
		return preload("./dem_structure_fit.gd").valid_patch(patch,fit_index)
	return ground_layers.has(str(patch.get("id","")).left(40)) and preload("./dem_building_grounding.gd").valid_patch(patch,request.get("ground_buildings",false))
