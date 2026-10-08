extends RefCounted
## Source polygons remain in provenance; only this adopted copy uses game cm.
static func validate(regions: Variant) -> String:
	if regions is not Array or regions.size() > 20000: return "Invalid OSM region count."
	var points := 0
	var ids := {}
	for region: Variant in regions:
		if region is not Dictionary or region.get("id") is not String or ids.has(region.id) or region.get("source_id") is not String or region.get("landuse") is not String or region.get("protected") is not bool or region.get("polygon") is not Array or region.get("holes") is not Array:
			return "Invalid OSM region provenance."
		ids[region.id] = true
		for ring: Variant in [region.polygon] + region.holes:
			if ring is not Array or ring.size() < 3: return "Invalid OSM region ring."
			points += ring.size()
			if points > 200000: return "OSM region point budget exceeded."
			for point: Variant in ring:
				if point is not Array or point.size() != 2: return "Invalid OSM region point."
				for value: Variant in point:
					if (value is not int and value is not float) or not is_finite(float(value)) or abs(value) > 10000000: return "Invalid OSM region coordinate."
	return ""

static func scaled(regions: Array) -> Array:
	var result := regions.duplicate(true)
	for region: Dictionary in result:
		for key in ["polygon", "holes"]:
			region[key] = preload("./import_units.gd")._coordinates(region[key])
	return result
