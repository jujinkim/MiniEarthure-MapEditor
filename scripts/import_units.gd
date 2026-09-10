extends RefCounted
## Source coordinates stay in provenance. Only newly adopted OSM records scale.
const OSM_DENOMINATOR := 8

static func osm_patches(source: Array) -> Array:
	var result := source.duplicate(true)
	for patch: Dictionary in result:
		var record: Dictionary = patch.after
		for key in ["position", "points", "footprint", "polygon", "exclusions", "entrances", "courtyards", "holes"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["widths_cm"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["height_cm", "base_cm", "clearance_cm", "sidewalk_cm", "spacing_cm"]:
			if record.get(key) != null: record[key] = roundi(float(record[key]) / OSM_DENOMINATOR)
	return result

static func _coordinates(value: Variant) -> Variant:
	if value is Array:
		var result := []
		for part in value: result.append(_coordinates(part))
		return result
	return roundi(float(value) / OSM_DENOMINATOR)

static func dem_denominator(document: Dictionary) -> int:
	for notice: Dictionary in document.get("attributions", []):
		var parser := JSON.new()
		if parser.parse(notice.get("notice", "")) != OK: continue
		var meta: Variant = parser.data
		if meta is Dictionary and meta.get("adapter") == "osm-extract-v1" and meta.get("authored_units", {}).get("source_denominator") == OSM_DENOMINATOR:
			return OSM_DENOMINATOR
	return 1
