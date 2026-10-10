extends RefCounted
## Source coordinates stay in provenance. Only newly adopted OSM records scale.
const OSM_DENOMINATOR := 8

static func osm_patches(source: Array, city := false) -> Array:
	var result := source.duplicate(true)
	for patch: Dictionary in result:
		var record: Dictionary = patch.after
		for key in ["position", "points", "footprint", "polygon", "exclusions", "entrances", "courtyards", "holes"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["widths_cm"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["height_cm", "base_cm", "clearance_cm", "sidewalk_cm", "spacing_cm"]:
			if record.get(key) != null: record[key] = roundi(float(record[key]) / OSM_DENOMINATOR)
		if city:
			# Scaling to whole game centimetres can collapse adjacent source
			# vertices. Remove only exact duplicates, never a road endpoint,
			# vertical step, material boundary or nonempty courtyard.
			if patch.field == "roads" and record.kind == "ground": _road_duplicates(record)
			for key in ["footprint","polygon"]:
				if record.has(key): record[key] = _ring_duplicates(record[key])
			for key in ["courtyards","holes","exclusions"]:
				if record.has(key):
					for i in range(record[key].size()): record[key][i] = _ring_duplicates(record[key][i])
	return result

static func _ring_duplicates(source: Array) -> Array:
	var result: Array = []
	for point: Variant in source:
		if result.is_empty() or result[-1] != point: result.append(point)
	if result.size() > 1 and result[0] == result[-1]: result.pop_back()
	return result if result.size() >= 3 else source

static func _road_duplicates(record: Dictionary) -> void:
	var retained: Array[int] = [0]
	for i in range(1,record.points.size()-1):
		if record.points[i] != record.points[retained[-1]] and record.points[i] != record.points[i+1]: retained.append(i)
	retained.append(record.points.size()-1)
	if retained.size() == record.points.size(): return
	var points: Array = []
	var widths: Array = []
	var surfaces: Array = []
	for i in range(retained.size()):
		points.append(record.points[retained[i]])
		if i == retained.size()-1: break
		var first: int = retained[i]
		for edge in range(first,retained[i+1]):
			if record.widths_cm[edge] != record.widths_cm[first] or record.surfaces[edge] != record.surfaces[first]: return
		widths.append(record.widths_cm[first]); surfaces.append(record.surfaces[first])
	record.points = points
	record.widths_cm = widths
	record.surfaces = surfaces

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
