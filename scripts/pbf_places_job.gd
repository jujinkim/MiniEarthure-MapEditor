extends "./import_job.gd"
## Reuses the bounded, cancelable worker transport without creating map records.
var query := ""
## Limit warnings the adapter already formatted ("Limit warning: …"), e.g. more
## matches than the 32 shown or a thinned boundary preview. Shown as received.
var adapter_texts: Array[String] = []
const MAX_ADAPTER_TEXTS := 64

## `point` ([lon, lat], optional) also lists that point's containing areas and
## country (`point_context`); the name may then be empty.
var point: Array = []

func search(source: String, name: String, python: String, token: String, at: Array = []) -> String:
	if _attempted or cancelled: return "PBF search instances are single use."
	_attempted = true
	query = name.strip_edges()
	point = at.duplicate()
	if (query.is_empty() and point.is_empty()) or query.length() > 128: return "Enter an administrative area name (1–128 characters)."
	if not point.is_empty() and not _point(point): return "Invalid/stale PBF place preview."
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
	stages = ["read", "index_relations", "index_ways", "index_nodes", "context_relations", "context_ways", "context_named_ways", "context_nodes", "context_named_nodes", "write", "complete"]
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
	var arguments := PackedStringArray(["-B", "-u", directory.path_join("pbf_places.py"), source, output_path, "--query", query, "--request", token])
	if not point.is_empty(): arguments.append_array(["--point", "%.7f,%.7f" % [point[0], point[1]]])
	if not _launch(python, arguments):
		return "Python could not start. Choose a Python 3 executable."
	deadline_ms = Time.get_ticks_msec() + timeout_seconds * 1000
	progress = {"stage":"starting", "completed":0, "total":size, "unit":"bytes"}
	return ""

## Display bounds only: more matches or preview points warn, never refuse.
## The adapter shows at most 32 matches and reports the rest in limit_warnings.
static func validate(value: Variant, name: String, notes: Array = [], texts: Array = [], at: Array = []) -> String:
	if value is not Dictionary or value.get("profile") != "pbf-place-preview-v1" or value.get("query") != name: return "Invalid/stale PBF place preview."
	if value.has("point_context") == at.is_empty(): return "Invalid/stale PBF place preview."
	if value.has("point_context") and not _context(value.point_context): return "Invalid PBF place preview."
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
		if not _context(place.get("context")): return "Invalid PBF place preview."
		if place.outlines.is_empty(): return "Missing boundary preview."
		for line: Variant in place.outlines:
			if line is not Array or line.is_empty(): return "Invalid boundary line."
			points += line.size()
			for point: Variant in line:
				if not _point(point) or point[0] < box[0] or point[0] > box[2] or point[1] < box[1] or point[1] > box[3]: return "Boundary point outside extent."
	LIMITS.over(notes, "pbf_place_points", points, 20000, "Boundary preview points")
	var anchors: Variant = value.get("anchors")
	if anchors is not Array or anchors.size() > 64: return "Invalid PBF place preview."
	for anchor: Variant in anchors:
		if anchor is not Dictionary or not LAYER._text(anchor.get("name")) or str(anchor.name).length() > 256 or anchor.get("kind") is not String or str(anchor.kind).length() > 64 or anchor.get("issue") is not String or not LAYER._count(anchor.get("tier"), 100): return "Invalid place label."
		var source_id: Variant = anchor.get("source_id")
		if source_id is not String or ids.has(source_id) or not (source_id.begins_with("node/") or source_id.begins_with("way/") or source_id.begins_with("relation/")) or not source_id.get_slice("/", 1).is_valid_int() or int(source_id.get_slice("/", 1)) <= 0: return "Invalid boundary source identity."
		ids[source_id] = true
		if anchor.get("point") is not Array or (anchor.issue == "") != _point(anchor.point) or (anchor.issue != "" and not anchor.point.is_empty()): return "Invalid boundary geometry."
		if not _context(anchor.get("context")): return "Invalid PBF place preview."
	return ""

## {areas: [{name, source_id, admin_level, bbox, km2}] (largest first), country:
## {} or {code, name, driving_side, basis}}.
static func _context(value: Variant) -> bool:
	if value is not Dictionary or value.get("areas") is not Array or value.areas.size() > 16 or value.get("country") is not Dictionary: return false
	var last := INF
	for area: Variant in value.areas:
		if area is not Dictionary or area.get("name") is not String or str(area.name).length() > 256 or area.get("admin_level") is not String: return false
		var source_id: Variant = area.get("source_id")
		if source_id is not String or not source_id.begins_with("relation/") or not source_id.trim_prefix("relation/").is_valid_int(): return false
		var box: Variant = area.get("bbox")
		if box is not Array or box.size() != 4 or not _point([box[0],box[1]]) or not _point([box[2],box[3]]) or box[0] > box[2] or box[1] > box[3]: return false
		if not LAYER._finite(area.get("km2"), 0, 200000000) or float(area.km2) > last: return false
		last = float(area.km2)
	var country: Dictionary = value.country
	if country.is_empty(): return true
	return country.get("code") is String and str(country.code).length() == 2 and country.get("name") is String and str(country.name).length() <= 256 and country.get("driving_side") in ["", "left", "right"] and country.get("basis") in ["boundary", "subdivision", "partial", "extract"]

static func _point(value: Variant) -> bool:
	return value is Array and value.size() == 2 and LAYER._finite(value[0],-180,180) and LAYER._finite(value[1],-80,84)

func _finish_result() -> void:
	if not result.get("ok",false): return
	var error := validate(result.get("data"), query, limit_warnings, adapter_texts, point)
	if error != "": result = {"ok":false,"error":{"code":"E_PBF_SEARCH","message":error}}
