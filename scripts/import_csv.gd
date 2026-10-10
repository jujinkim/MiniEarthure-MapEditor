extends RefCounted
## Validate the full review accounting before the native candidate/adoption worker.
static func validate(raw: Dictionary, requested: Dictionary, types: Script) -> String:
	var meta: Variant = raw.coordinates.get("csv")
	if raw.adapter != "facility-csv-v1": return "Unexpected CSV metadata." if meta != null else ""
	if meta is not Dictionary or meta.get("options") is not Dictionary or meta.get("headers") is not Array or meta.headers.is_empty() or meta.headers.size() > 128: return "Invalid CSV review metadata."
	if not requested.is_empty():
		var wanted: Variant = requested.get("csv")
		if wanted is not Dictionary or wanted.keys().size() != meta.options.keys().size(): return "CSV mapping changed."
		for key in wanted:
			if key in ["bounds_cm", "geographic_bbox"]:
				if meta.options.get(key) is not Array or wanted[key].size() != meta.options[key].size(): return "CSV mapping changed."
				for i in range(wanted[key].size()):
					if wanted[key][i] != meta.options[key][i]: return "CSV map extent changed."
			elif wanted[key] != meta.options.get(key): return "CSV mapping changed: " + key
	var options: Dictionary = meta.options
	var geographic: Variant = options.get("geographic_bbox")
	if geographic != null:
		if geographic is not Array or geographic.size()!=4 or not types._finite(geographic[0],-180,180) or not types._finite(geographic[2],-180,180) or not types._finite(geographic[1],-80,84) or not types._finite(geographic[3],-80,84) or geographic[0]>=geographic[2] or geographic[1]>=geographic[3]: return "Invalid CSV geographic crop."
	if options.get("encoding") not in ["utf-8-sig", "cp949", "euc-kr"] or (not types._count(options.get("source_denominator"),8) or int(options.source_denominator) not in [1, 8]): return "Invalid CSV encoding/scale."
	for key in ["name_column", "latitude_column", "longitude_column", "category", "source_url"]:
		if not types._text(options.get(key)): return "Missing CSV mapping field."
	for key in ["name_column", "latitude_column", "longitude_column"]:
		if options[key] not in meta.headers: return "CSV mapped column is missing."
	if options.get("bounds_cm") is not Array or options.bounds_cm.size()!=4: return "Missing CSV map extent."
	for n in options.bounds_cm:
		if not types._finite(n,-10000000,10000000) or float(n)!=floor(float(n)): return "Invalid CSV map extent."
	if not types._count(meta.get("rows"),20000) or not types._count(meta.get("accepted"),20000) or meta.accepted != raw.feature_count or meta.accepted != raw.patches.size(): return "CSV accepted count mismatch."
	if meta.get("rejected") is not Array or meta.get("outside") is not Array or meta.accepted + meta.rejected.size() + meta.outside.size() != meta.rows: return "CSV row accounting mismatch."
	var lines := {}
	for rejected in meta.rejected:
		if rejected is not Dictionary or not types._count(rejected.get("line"),32000000) or not types._text(rejected.get("reason")) or rejected.get("name") is not String: return "Invalid CSV rejected row."
		if lines.has(rejected.line): return "Duplicate CSV row."
		lines[rejected.line]=true
	for line in meta.outside:
		if not types._count(line,32000000) or lines.has(line): return "Invalid CSV outside row."
		lines[line]=true
	for patch in raw.patches:
		if patch.get("field") != "pois" or patch.get("after") is not Dictionary: return "CSV may only add facility records."
		var record: Dictionary = patch.after
		if record.get("category") != options.category or record.get("source") is not Dictionary or record.source.get("source") != options.source_url or record.source.get("license") != raw.source.license: return "CSV facility source mismatch."
		var source: Variant = JSON.parse_string(record.source.get("notice", ""))
		if source is not Dictionary or source.get("sha256") != raw.source.sha256 or not types._count(source.get("line"),32000000) or lines.has(source.line) or patch.get("id") != "import-%s-csv-%d" % [raw.layer_id, source.line]: return "Invalid CSV source row mapping."
		if not types._finite(source.get("longitude"),-180,180) or not types._finite(source.get("latitude"),-80,84): return "Invalid facility source coordinates."
		if geographic != null and (source.longitude<geographic[0] or source.longitude>geographic[2] or source.latitude<geographic[1] or source.latitude>geographic[3]): return "Facility is outside the selected geographic crop."
		lines[source.line]=true
	return ""
