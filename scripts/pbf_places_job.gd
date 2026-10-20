extends "./import_job.gd"
## Reuses the bounded, cancelable worker transport without creating map records.
var query := ""
## Limit warnings the adapter already formatted ("Limit warning: …"), e.g. more
## matches than the 32 shown or a thinned boundary preview. Shown as received.
var adapter_texts: Array[String] = []
const MAX_ADAPTER_TEXTS := 64

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
	progress_limit = LAYER.MAX_STREAM_SOURCE_BYTES
	timeout_seconds = 900
	# The lookup streams the PBF as well: every pass must complete in order.
	streaming = true
	stages = ["read", "index_relations", "index_ways", "index_nodes", "write", "complete"]
	if size <= 0 or size > progress_limit: return "Choose a nonempty local PBF up to 64 GiB."
	LIMITS.over(limit_warnings, "stream_source_bytes", size, LAYER.WARN_STREAM_SOURCE_BYTES, "PBF source size in bytes")
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

## Display bounds only: more matches or preview points warn, never refuse.
## The adapter shows at most 32 matches and reports the rest in limit_warnings.
static func validate(value: Variant, name: String, notes: Array = [], texts: Array = []) -> String:
	if value is not Dictionary or value.get("profile") != "pbf-place-preview-v1" or value.get("query") != name: return "Invalid/stale PBF place preview."
	if not LAYER._hex(value.get("source_sha256"),64) or not LAYER._count(value.get("source_bytes"),LAYER.MAX_STREAM_SOURCE_BYTES) or not LAYER._text(value.get("source_name")): return "Invalid PBF source receipt."
	if value.get("places") is not Array: return "Invalid PBF place preview."
	var adapter: Variant = value.get("limit_warnings", [])
	if adapter is not Array or adapter.size() > MAX_ADAPTER_TEXTS: return "Invalid PBF place limit warnings."
	for entry: Variant in adapter:
		if not LAYER._text(entry): return "Invalid PBF place limit warnings."
	texts.append_array(adapter)
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
			for point: Variant in line:
				if not _point(point) or point[0] < box[0] or point[0] > box[2] or point[1] < box[1] or point[1] > box[3]: return "Boundary point outside extent."
	LIMITS.over(notes, "pbf_place_points", points, 20000, "Boundary preview points")
	return ""

static func _point(value: Variant) -> bool:
	return value is Array and value.size() == 2 and LAYER._finite(value[0],-180,180) and LAYER._finite(value[1],-80,84)

func _finish_result() -> void:
	if not result.get("ok",false): return
	var error := validate(result.get("data"), query, limit_warnings, adapter_texts)
	if error != "": result = {"ok":false,"error":{"code":"E_PBF_SEARCH","message":error}}
