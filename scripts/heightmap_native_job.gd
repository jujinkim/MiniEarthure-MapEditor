extends "./raster_native_job.gd"
## Independent PNG authoring shares the owned raster worker contract.
const PNG := preload("./terrain_png.gd")
const OUTPUT_MARKER := "png-output.json"

func start_png(store: RefCounted, options: Dictionary, adopt: bool, selection: String, token: String, previous: Dictionary = {}) -> String:
	if _attempted or cancelled: return "PNG jobs are single use."
	_attempted = true
	if not LAYER._hex(token, 32) or store.project_path == "" or store.has_gesture(): return "Save the project and finish gestures before PNG validation."
	if options.get("path") is not String or not options.path.is_absolute_path(): return "Choose an absolute local PNG path."
	if adopt and (not LAYER._hex(previous.get("payloads"), 64) or not LAYER._hex(previous.get("layer_id"), 32)): return "Missing reviewed PNG identity."
	identity = token
	import_kind = "native"
	adopting = adopt
	selection_signature = selection
	project_source = store.project_path
	document_signature = JSON.stringify(store.document).sha256_text()
	document_epoch = store.command_epoch
	_store_id = store.get_instance_id()
	expected_cells = 0 if store.document.roads.is_empty() else 1
	structural = expected_cells > 0
	request = {"kind":"png", "request":token, "document":store.document.duplicate(true), "project":project_source,
		"options":options.duplicate(true), "layer_id":previous.layer_id if adopt else token, "expected_payloads":previous.get("payloads", "")}
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in store.document.get(field, []):
			if not SNAPSHOT.safe_relative(str(record.path)): return "Unsafe PNG dependency path."
			if record.path not in owned_payloads: owned_payloads.append(record.path)
	var bytes := JSON.stringify(request).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "PNG request exceeds 24 MiB."
	return _start_request(bytes)

func cleanup() -> void:
	if not _owns_directory or (_child_started and not exited): return
	# The child registers the single content-addressed output BEFORE writing any
	# candidate files. Cancellation can therefore retire it without a directory scan.
	var root := DirAccess.open(directory)
	if root != null and not root.is_link(OUTPUT_MARKER) and FileAccess.file_exists(directory.path_join(OUTPUT_MARKER)):
		var read := PAYLOADS.read(directory.path_join(OUTPUT_MARKER), 512)
		var marker: Variant = JSON.parse_string(read.bytes.get_string_from_utf8()) if not read.has("error") else null
		if marker is Dictionary and marker.get("request") == identity and LAYER._hex(marker.get("sha256"), 64):
			var path := "editor/" + str(marker.sha256) + ".png"
			if path not in owned_payloads: owned_payloads.append(path)
			DirAccess.remove_absolute(directory.path_join(OUTPUT_MARKER))
	super.cleanup()
