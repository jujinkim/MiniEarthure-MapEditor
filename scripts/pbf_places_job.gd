extends "./import_job.gd"
## Reuses the bounded, cancelable worker transport without creating map records.
var query := ""

func search(source: String, name: String, python: String, token: String) -> String:
	if _attempted or cancelled: return "PBF search instances are single use."
	_attempted = true
	query = name.strip_edges()
	if query.is_empty() or query.length() > 128: return "Enter an administrative area name (1–128 characters)."
	identity = token
	if not LAYER._hex(token, 32): return "Invalid search token."
	var input := FileAccess.open(source, FileAccess.READ)
	if input == null: return "Cannot open selected PBF."
	var size := input.get_length()
	input.close()
	progress_limit = 2 * 1024 * 1024 * 1024
	timeout_seconds = 900
	stages = ["read", "index_relations", "index_ways", "index_nodes", "write", "complete"]
	if size <= 0 or size > progress_limit: return "Choose a nonempty local PBF up to 2 GiB."
	var reservation := _reserve_directory(token)
	if reservation != "": return reservation
	var files := FILES.new()
	for module in MODULES:
		var code := FileAccess.get_file_as_string("res://scripts/importers/" + module)
		var error := files.write(directory.path_join(module), code, "") if code != "" else "Importer module is missing."
		if error != "": cleanup(); return error
	output_path = directory.path_join("layer.json")
	if not _launch(python, PackedStringArray(["-B", "-u", directory.path_join("pbf_places.py"), source, output_path, "--query", query, "--request", token])):
		return "Python could not start. Choose a Python 3 executable."
	deadline_ms = Time.get_ticks_msec() + timeout_seconds * 1000
	progress = {"stage":"starting", "completed":0, "total":size, "unit":"bytes"}
	return ""

static func validate(value: Variant, name: String) -> String:
	if value is not Dictionary or value.get("profile") != "pbf-place-preview-v1" or value.get("query") != name: return "Invalid/stale PBF place preview."
	if not LAYER._hex(value.get("source_sha256"),64) or not LAYER._count(value.get("source_bytes"),2*1024*1024*1024) or not LAYER._text(value.get("source_name")): return "Invalid PBF source receipt."
	if value.get("places") is not Array or value.places.size() > 32: return "PBF search result budget exceeded."
	var points := 0
	var ids := {}
	for place: Variant in value.places:
		if place is not Dictionary or not LAYER._text(place.get("name")) or str(place.name).length() > 256 or place.get("admin_level") is not String or place.get("issue") is not String: return "Invalid place label."
		var source_id: Variant = place.get("source_id")
		if source_id is not String or not source_id.begins_with("relation/") or not source_id.trim_prefix("relation/").is_valid_int() or int(source_id.trim_prefix("relation/")) <= 0 or ids.has(source_id): return "Invalid boundary source identity."
		ids[source_id] = true
		var box: Variant = place.get("bbox")
		if box is not Array or place.get("outlines") is not Array: return "Invalid boundary geometry."
		if place.issue != "":
			if not box.is_empty() or not place.outlines.is_empty(): return "An incomplete boundary cannot supply guessed geometry."
			continue
		if box.size() != 4 or not _point([box[0],box[1]]) or not _point([box[2],box[3]]) or box[0] >= box[2] or box[1] >= box[3] or box[2]-box[0] > 180: return "Invalid boundary extent."
		if place.outlines.is_empty(): return "Missing boundary preview."
		for line: Variant in place.outlines:
			if line is not Array or line.is_empty(): return "Invalid boundary line."
			points += line.size()
			if points > 20000: return "Boundary preview budget exceeded."
			for point: Variant in line:
				if not _point(point) or point[0] < box[0] or point[0] > box[2] or point[1] < box[1] or point[1] > box[3]: return "Boundary point outside extent."
	return ""

static func _point(value: Variant) -> bool:
	return value is Array and value.size() == 2 and LAYER._finite(value[0],-180,180) and LAYER._finite(value[1],-80,84)

func _finish_result() -> void:
	if not result.get("ok",false): return
	var error := validate(result.get("data"), query)
	if error != "": result = {"ok":false,"error":{"code":"E_PBF_SEARCH","message":error}}
