extends RefCounted
## Import provenance only. No changes to authored terrain or MapKit coordinates.
const MAX_GRID_BYTES := 64 * 1024
const CRS := {"EGM96":"EPSG:5773 / EGM96 metres", "EGM2008":"EPSG:3855 / EGM2008 metres"}
const ORDER := "source vertices before crop; target heights linearly interpolated at cuts; round once to cm"

static func finite(n: Variant, low: float, high: float) -> bool:
	return (n is int or n is float) and is_finite(float(n)) and n >= low and n <= high

static func count(n: Variant, low: int, high: int) -> bool:
	return finite(n, low, high) and n == floor(float(n))

static func bounded_text(v: Variant) -> bool:
	if v is not String or v.strip_edges().is_empty() or v.length() > 512: return false
	for c in v:
		if c.unicode_at(0) < 32: return false
	return true

static func options_error(o: Variant) -> String:
	if o is not Dictionary or o.size() != 3 or not o.has_all(["target", "zero_m", "grid"]) or o.target not in CRS: return "Select a supported vertical datum."
	if not finite(o.zero_m, -10000, 10000) or abs(o.zero_m * 100 - round(o.zero_m * 100)) > 0.00000001: return "Vertical zero must be finite whole centimetres within ±10000 m."
	if o.target == "EGM96": return "" if o.grid == null else "EGM96 offset must not include a grid."
	if o.grid is not String or o.grid.to_utf8_buffer().is_empty() or o.grid.to_utf8_buffer().size() > MAX_GRID_BYTES: return "Select a local UTF-8 correction grid of at most 64 KiB."
	var g: Variant = JSON.parse_string(o.grid)
	var keys := ["format", "source", "license", "accuracy", "horizontal_crs", "source_crs", "target_crs", "quantity", "bbox", "columns", "rows", "values_m"]
	if g is not Dictionary or g.size() != keys.size() or not g.has_all(keys): return "Invalid correction grid fields."
	if g.format != "miniearthure-height-delta-v1" or g.horizontal_crs != "EPSG:4326" or g.source_crs != CRS.EGM96 or g.target_crs != CRS.EGM2008 or g.quantity != "H_EGM2008-minus-H_EGM96": return "Unsupported correction grid datum, axes or sign."
	for key in ["source", "license", "accuracy"]:
		if not bounded_text(g[key]): return "Grid source, license and accuracy descriptions are required."
	if not count(g.columns, 2, 33) or not count(g.rows, 2, 33) or g.values_m is not Array or g.values_m.size() != g.columns * g.rows: return "Grid requires 2..33 complete rows and columns."
	if g.bbox is not Array or g.bbox.size() != 4: return "Invalid correction grid bounds."
	for i in range(4):
		if not finite(g.bbox[i], -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84): return "Invalid correction grid bounds."
	if g.bbox[2] <= g.bbox[0] or g.bbox[3] <= g.bbox[1] or g.bbox[2] - g.bbox[0] > 1 or g.bbox[3] - g.bbox[1] > 1: return "Grid bounds must be ordered and at most one degree per side."
	for n in g.values_m:
		if not finite(n, -200, 200): return "Grid deltas must be finite metres within ±200; nodata is unsupported."
	return ""

static func validate(raw: Dictionary, requested: Dictionary) -> String:
	var v: Variant = raw.coordinates.get("vertical")
	if not raw.coordinates.has("vertical"): return "Missing requested vertical conversion." if requested.has("vertical") else ""
	var keys := ["profile", "source_crs", "target_crs", "vertical_zero_m", "order", "method", "grid_source", "explicit_points", "explicit_roads", "delta_range_m"]
	if raw.adapter != "osm-extract-v1" or v is not Dictionary or v.size() != keys.size() or not v.has_all(keys): return "Invalid vertical conversion metadata."
	if v.profile != "osm-vertical-v1" or v.source_crs != CRS.EGM96 or v.target_crs not in CRS.values() or v.order != ORDER: return "Unsupported vertical conversion contract."
	var o := {"target":"EGM96" if v.target_crs == CRS.EGM96 else "EGM2008", "zero_m":v.vertical_zero_m, "grid":null}
	if o.target == "EGM2008":
		var s: Variant = v.grid_source
		if s is not Dictionary or s.size() != 3 or not s.has_all(["json", "bytes", "sha256"]) or s.json is not String: return "Missing correction source snapshot."
		if s.json.to_utf8_buffer().size() > MAX_GRID_BYTES or s.bytes != s.json.to_utf8_buffer().size() or s.sha256 != s.json.sha256_text(): return "Correction source identity changed."
		o.grid = s.json
	elif v.grid_source != null: return "Offset conversion must not contain a correction grid."
	var failure := options_error(o)
	if failure != "": return failure
	if v.method != ("offset" if o.target == "EGM96" else "bilinear-local-delta-grid-v1"): return "Incorrect vertical method."
	if requested.has("vertical"):
		if options_error(requested.vertical) != "": return "Invalid requested vertical conversion."
		for key in ["target", "zero_m", "grid"]:
			if requested.vertical[key] != o[key]: return "Vertical selection differs from captured request."
	elif not requested.is_empty() and (o.target != "EGM96" or o.zero_m != 0 or o.grid != null): return "Unrequested vertical conversion."
	if not count(v.explicit_points, 0, 200000) or not count(v.explicit_roads, 0, 20000) or v.explicit_points < v.explicit_roads * 2: return "Invalid vertical conversion counts."
	if v.explicit_points == 0:
		if v.explicit_roads != 0 or v.delta_range_m != null or o.target != "EGM96" or o.zero_m != 0: return "Conversion requires explicit source heights."
	else:
		if v.explicit_roads == 0 or v.delta_range_m is not Array or v.delta_range_m.size() != 2: return "Invalid vertical correction range."
		for n in v.delta_range_m:
			if not finite(n, -200, 200): return "Invalid vertical correction range."
		if v.delta_range_m[0] > v.delta_range_m[1] or (o.target == "EGM96" and (v.delta_range_m[0] != 0 or v.delta_range_m[1] != 0)): return "Invalid vertical correction range."
	return ""

static func _terrain_key(record: Variant) -> String:
	if record is not Dictionary or record.get("cell") is not Dictionary: return ""
	return JSON.stringify([record.cell.get("x"), record.cell.get("y"), record.get("path"), record.get("spacing_cm"), record.get("offset_cm"), record.get("step_cm"), record.get("source_accuracy_cm")])

static func frame_error(doc: Dictionary, frame: Dictionary, coordinates: Dictionary) -> String:
	# Only still-present imported records constrain the frame. Historical notices
	# of replaced terrain/deleted vectors remain preserved without locking the map.
	var layers := {}
	var paths := {}
	for node: Dictionary in doc.nodes:
		if node.id.begins_with("import-") and node.id.substr(39).begins_with("-osm-node-"): layers[node.id.substr(7, 32)] = true
	for heightmap: Dictionary in doc.heightmaps: paths[_terrain_key(heightmap)] = true
	for attribution: Dictionary in doc.attributions:
		var parser := JSON.new()
		if parser.parse(attribution.notice) != OK: continue
		var meta: Variant = parser.data
		if meta is not Dictionary: continue
		var other := {}
		var horizontal := {}
		if meta.get("adapter") == "osm-extract-v1" and meta.get("coordinates") is Dictionary and meta.get("layer_id") is String:
			if not layers.has(meta.layer_id): continue
			horizontal = meta.coordinates
			# Source-connected estimated ground loops have no vertical datum.
			if horizontal.has("osm_ground_loops") and horizontal.get("vertical", {}).get("explicit_points", 0) == 0: continue
			var declared: Variant = horizontal.get("vertical", {"target_crs":CRS.EGM96, "vertical_zero_m":0})
			if declared is not Dictionary: return "Existing OSM vertical provenance is incomplete."
			other = declared
		elif meta.get("adapter") in ["copernicus-dem-v1", "copernicus-dem-v2"] and meta.get("dem") is Dictionary:
			var active := false
			var maps: Variant = meta.get("heightmaps", [meta.get("heightmap", {})])
			if maps is not Array: return "Existing DEM provenance is incomplete."
			for old: Variant in maps:
				if paths.has(_terrain_key(old)): active = true; break
			if not active: continue
			var receipt: Variant = meta.dem.get("receipt")
			if receipt is not Dictionary or receipt.get("options") is not Dictionary: return "Existing DEM vertical provenance is incomplete."
			if receipt.options.get("coordinates") is not Dictionary: return "Existing DEM projection provenance is incomplete."
			horizontal = receipt.options.coordinates
			other = {"target_crs":CRS.EGM2008, "vertical_zero_m":receipt.options.get("vertical_zero_m")}
		else: continue
		if other.get("target_crs") != frame.get("target_crs") or other.get("vertical_zero_m") != frame.get("vertical_zero_m"):
			return "Vertical frame conflicts with active imported data. Match its datum and local-zero height; existing terrain/roads are never shifted."
		for key in ["mode", "origin", "local_origin_m"]:
			if horizontal.get(key) != coordinates.get(key): return "Projection origin conflicts with active imported height data."
	return ""

static func summary(v: Dictionary) -> String:
	var result := "%s → %s minus %s m at local zero\nMethod: %s · %d source vertices / %d roads · delta range (m): %s\n%s\nUnreferenced authored data is not certified. Ground roads follow terrain; structural aprons still require native terrain agreement.\n" % [v.source_crs, v.target_crs, str(v.vertical_zero_m), v.method, v.explicit_points, v.explicit_roads, str(v.delta_range_m), v.order]
	if v.grid_source is Dictionary:
		var grid: Dictionary = JSON.parse_string(v.grid_source.json)
		result += "Correction source: %s\nLicense: %s\nDeclared accuracy: %s (not independently verified)\n%s bytes · SHA-256: %s\nBounds: %s · %s × %s nodes; south-to-north rows, west-to-east columns.\n" % [grid.source, grid.license, grid.accuracy, v.grid_source.bytes, v.grid_source.sha256, str(grid.bbox), grid.columns, grid.rows]
	return result
