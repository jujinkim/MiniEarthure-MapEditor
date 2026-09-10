extends RefCounted
## Bounded supplemental source provenance; authored MapKit contracts are unchanged.
const VERTICAL := preload("./import_vertical.gd")
const MAX_BYTES := 256 * 1024
const MAX_NODES := 4096
const ORDER := "fill missing original nodes before graph normalization, datum conversion and crop"

static func hex_digest(v: Variant) -> bool:
	if v is not String or v.length() != 64: return false
	for c in v:
		if c not in "0123456789abcdef": return false
	return true

static func unique_keys(raw: String) -> bool:
	# Tokenize strings in full so braces/colons inside provenance text are ignored.
	# JSON syntax is checked separately. Decode keys to catch escaped duplicates.
	var tokens := RegEx.new()
	tokens.compile('"(?:[^"\\\\]|\\\\.)*"[ \t\r\n]*:?|[{}]')
	var objects: Array[Dictionary] = []
	for match_result in tokens.search_all(raw):
		var token: String = match_result.get_string()
		if token == "{": objects.append({})
		elif token == "}":
			if objects.is_empty(): return false
			objects.pop_back()
		elif token.ends_with(":"):
			if objects.is_empty(): return false
			var key: Variant = JSON.parse_string(token.left(-1).strip_edges())
			if key is not String or objects.back().has(key): return false
			objects.back()[key] = true
	return objects.is_empty()

static func source_error(raw: Variant) -> String:
	if raw is not String or raw.to_utf8_buffer().is_empty() or raw.to_utf8_buffer().size() > MAX_BYTES: return "Height supplement requires UTF-8 JSON of at most 256 KiB."
	var parser := JSON.new()
	if parser.parse(raw) != OK: return "Invalid height supplement JSON."
	var value: Variant = parser.data
	var keys := ["format", "osm_sha256", "source", "license", "accuracy", "vertical_crs", "nodes"]
	if value is not Dictionary or value.size() != keys.size() or not value.has_all(keys): return "Invalid height supplement fields."
	if not unique_keys(raw): return "Duplicate height supplement JSON keys."
	if value.format != "miniearthure-osm-node-heights-v1" or value.vertical_crs != VERTICAL.CRS.EGM96: return "Height supplement requires absolute EGM96 metres before target conversion."
	if not hex_digest(value.osm_sha256): return "Height supplement requires the exact OSM snapshot SHA-256."
	for key in ["source", "license", "accuracy"]:
		if not VERTICAL.bounded_text(value[key]): return "Height source, license and declared accuracy are required."
	if value.nodes is not Array or value.nodes.is_empty() or value.nodes.size() > MAX_NODES: return "Height supplement requires 1..4096 original nodes."
	var seen := {}
	var pattern := RegEx.new()
	pattern.compile("^[1-9][0-9]{0,18}$")
	for node: Variant in value.nodes:
		if node is not Dictionary or node.size() != 2 or not node.has_all(["node_id", "height_m"]): return "Supplement nodes require node_id and height_m."
		if node.node_id is not String or pattern.search(node.node_id) == null or (node.node_id.length() == 19 and node.node_id > "9223372036854775807"): return "Node ID must be a canonical positive int64 string."
		if seen.has(node.node_id): return "Duplicate height supplement node ID."
		seen[node.node_id] = true
		if not VERTICAL.finite(node.height_m, -10000, 10000): return "Supplement heights must be finite metres within ±10000."
	return ""

static func validate(raw: Dictionary, requested: Dictionary) -> String:
	if not raw.coordinates.has("osm_height_supplement"):
		return "Missing requested height supplement." if requested.has("height_supplement") else ""
	var meta: Variant = raw.coordinates.osm_height_supplement
	if raw.adapter != "osm-extract-v1" or meta is not Dictionary or meta.size() != 4 or not meta.has_all(["profile", "order", "source", "applied_nodes"]): return "Invalid height supplement provenance."
	if meta.profile != "osm-node-heights-v1" or meta.order != ORDER: return "Unsupported height supplement order/profile."
	var s: Variant = meta.source
	if s is not Dictionary or s.size() != 3 or not s.has_all(["json", "bytes", "sha256"]): return "Missing height supplement snapshot."
	var failure := source_error(s.json)
	if failure != "": return failure
	if s.bytes != s.json.to_utf8_buffer().size() or s.sha256 != s.json.sha256_text(): return "Height supplement source identity changed."
	var source: Dictionary = JSON.parse_string(s.json)
	if source.osm_sha256 != raw.source.sha256: return "Height supplement OSM snapshot mismatch."
	if not VERTICAL.count(meta.applied_nodes, 1, MAX_NODES) or meta.applied_nodes != source.nodes.size(): return "Incomplete height supplement application."
	var v: Variant = raw.coordinates.get("vertical")
	if v is not Dictionary or meta.applied_nodes > v.explicit_points: return "Height supplement requires complete explicit source profiles."
	if requested.has("height_supplement"):
		if requested.height_supplement != s.json: return "Height supplement differs from captured request."
	elif not requested.is_empty(): return "Unrequested height supplement."
	return ""

static func summary(meta: Dictionary) -> String:
	var source: Dictionary = JSON.parse_string(meta.source.json)
	return "Local height supplement: %d originally missing structural/approach nodes\nSource: %s\nLicense: %s\nDeclared accuracy: %s (not independently verified)\nAbsolute %s · OSM SHA-256: %s\n%d bytes · supplement SHA-256: %s\n%s. Existing OSM elevations are preserved; no inferred heights.\n" % [meta.applied_nodes, source.source, source.license, source.accuracy, source.vertical_crs, source.osm_sha256, meta.source.bytes, meta.source.sha256, meta.order]
