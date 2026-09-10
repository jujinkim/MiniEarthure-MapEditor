extends "./raster_native_job.gd"
## The released stroke is a snapshot. A disposable child owns raster/native work.
const TERRAIN := preload("./terrain_tools.gd")
const OUTPUT_MARKER := "terrain-output.json"
var touched_ids := {}
var previous_tiles := {}

func start_terrain(store: RefCounted, stroke: Dictionary, selection: String, token: String) -> String:
	if _attempted or cancelled: return "Terrain jobs are single use."
	_attempted = true
	if not LAYER._hex(token, 32) or store.project_path == "" or store.has_gesture(): return "Save the project and finish gestures before terrain preparation."
	var failure := preload("./terrain_native_worker.gd").check_stroke(stroke)
	if failure != "": return failure
	var terrain := TERRAIN.new()
	terrain.store = store
	terrain.settings = stroke.options.duplicate(true)
	for point: Array in stroke.stroke: terrain.stroke.append(Vector2(point[0], point[1]))
	var extent := terrain.region()
	if extent.has("error"): return extent.error
	for cell: Vector2i in extent.cells: touched_ids[store.record_id("heightmaps", {"cell":{"x":cell.x, "y":cell.y}})] = true
	for record: Dictionary in store.document.heightmaps: previous_tiles[store.record_id("heightmaps", record)] = record.duplicate(true)
	identity = token
	import_kind = "native"
	adopting = true
	selection_signature = selection
	project_source = store.project_path
	document_signature = JSON.stringify(store.document).sha256_text()
	document_epoch = store.command_epoch
	_store_id = store.get_instance_id()
	expected_cells = 0 if store.document.roads.is_empty() else extent.cells.size()
	structural = expected_cells > 0
	request = {"kind":"terrain", "request":token, "layer_id":token, "document":store.document.duplicate(true), "project":project_source, "stroke":stroke.duplicate(true)}
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in store.document.get(field, []):
			if not SNAPSHOT.safe_relative(str(record.path)): return "Unsafe terrain dependency path."
			if record.path not in owned_payloads: owned_payloads.append(record.path)
	var bytes := JSON.stringify(request).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "Terrain request exceeds 24 MiB."
	return _start_request(bytes)

func _decode_command(output: Dictionary) -> void:
	super._decode_command(output)
	if bundle.is_empty(): return
	# A brush may return only its touched tiles and their exact old/new images.
	# Reject a hash-valid but malformed transfer before any repeated file I/O.
	var failure := ""
	var outputs := {}
	if bundle.blob_paths.is_empty() or bundle.blob_paths.size() > TERRAIN.MAX_TILES or bundle.patches.size() > TERRAIN.MAX_TILES: failure = "Invalid terrain transfer count."
	for path: String in bundle.blob_paths:
		if outputs.has(path): failure = "Duplicate terrain output payload."
		outputs[path] = true
	var ids := {}
	var images := {}
	var used_outputs := {}
	for patch: Dictionary in bundle.patches:
		if failure != "": break
		if patch.field != "heightmaps" or not touched_ids.has(patch.id) or ids.has(patch.id) or patch.before != previous_tiles.get(patch.id):
			failure = "Unexpected terrain command tile."
			break
		var cell: Variant = patch.after.get("cell")
		if cell is not Dictionary or not preload("./heightmap_native_worker.gd")._integer(cell.get("x")) or not preload("./heightmap_native_worker.gd")._integer(cell.get("y")) or JSON.stringify({"x":int(cell.x), "y":int(cell.y)}) != patch.id:
			failure = "Invalid terrain command cell."
			break
		ids[patch.id] = true
		used_outputs[patch.after.path] = true
		images[patch.after.path] = true
		if patch.before != null: images[patch.before.path] = true
	if failure == "" and (used_outputs.size() != outputs.size() or images.size() != bundle.retained.size()): failure = "Unexpected terrain payload or memento."
	if failure == "":
		for path: String in bundle.retained:
			if not images.has(path): failure = "Unexpected terrain binary memento."
	if failure != "":
		result = {"ok":false, "error":{"code":"E_IMPORT_NATIVE", "message":failure}}
		_prepared = {}
		bundle = {}

func cleanup() -> void:
	if not _owns_directory or (_child_started and not exited): return
	var root := DirAccess.open(directory)
	if root != null and not root.is_link(OUTPUT_MARKER) and FileAccess.file_exists(directory.path_join(OUTPUT_MARKER)):
		var read := PAYLOADS.read(directory.path_join(OUTPUT_MARKER), 2048)
		var marker: Variant = JSON.parse_string(read.bytes.get_string_from_utf8()) if not read.has("error") else null
		var valid: bool = marker is Dictionary and marker.get("request") == identity and marker.get("hashes") is Array
		if valid:
			valid = marker.hashes.size() <= TERRAIN.MAX_TILES
			for hash: Variant in marker.hashes:
				if not LAYER._hex(hash, 64): valid = false
		if valid:
			for hash: String in marker.hashes:
				var path := "editor/" + hash + ".png"
				if path not in owned_payloads: owned_payloads.append(path)
			DirAccess.remove_absolute(directory.path_join(OUTPUT_MARKER))
	super.cleanup()
