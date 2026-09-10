extends "./raster_native_job.gd"
## Local DEM request admission; lifecycle and binary commands are shared.

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
