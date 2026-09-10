extends RefCounted
## Validate the selected classification, complete source mapping and fixed estimates.
static func validate(raw: Dictionary, boundary: Script) -> String:
	var meta: Variant = raw.coordinates.get("overture_land_cover")
	if raw.source.license != boundary.OVERTURE_LAND_COVER_LICENSE or raw.coordinates.mode != "wgs84-utm": return "Land cover requires WGS84 and source attribution."
	if meta is not Dictionary or meta.get("provider") != "Overture" or meta.get("theme") != "base" or meta.get("type") != "land_cover" or meta.get("profile") != "forest-high-detail-v1" or meta.get("license") != raw.source.license: return "Invalid land cover profile."
	var pattern := RegEx.new()
	pattern.compile("^20[0-9]{2}-[0-9]{2}-[0-9]{2}\\.[0-9]+$")
	if not boundary._text(meta.get("release")) or pattern.search(meta.release) == null: return "Invalid land cover release."
	var bbox: Variant = meta.get("bbox")
	if bbox is not Array or bbox.size() != 4: return "Invalid land cover area."
	for i in range(4):
		if not boundary._finite(bbox[i], -180 if i%2 == 0 else -80, 180 if i%2 == 0 else 84): return "Invalid land cover coordinate."
	if bbox[0] >= bbox[2] or bbox[1] >= bbox[3] or bbox[2]-bbox[0] > 0.02 or bbox[3]-bbox[1] > 0.02: return "Invalid land cover area size."
	if not boundary._count(meta.get("source_feature_count"),256) or meta.get("feature_sources") is not Array or meta.feature_sources.size() != meta.source_feature_count: return "Invalid land cover source count."
	if not boundary._count(meta.get("source_point_count"),8192) or meta.source_point_count < raw.point_count: return "Invalid land cover point budget."
	var ids := {}
	var zones := {}
	var selected := 0
	for f in meta.feature_sources:
		if f is not Dictionary or not boundary._text(f.get("id")) or ids.has(f.id): return "Invalid land cover source ID."
		ids[f.id] = true
		if f.get("subtype") not in ["barren","crop","forest","grass","mangrove","moss","shrub","snow","urban","wetland"]: return "Unknown land cover subtype."
		if not boundary._count(f.get("min_zoom"),15) or not boundary._count(f.get("max_zoom"),15) or f.min_zoom > f.max_zoom: return "Invalid land cover resolution."
		var detail: bool = f.min_zoom == 8 and f.max_zoom == 15
		if not detail and f.max_zoom >= 8: return "Unsupported land cover resolution."
		var disposition := "forest" if f.subtype == "forest" and detail else "other-subtype" if f.subtype != "forest" else "lower-detail"
		if f.get("disposition") != disposition or f.get("zone_ids") is not Array or not boundary._count(f.get("part_count"),256) or f.part_count < 1: return "Invalid land cover disposition/mapping."
		if f.get("hole_counts") is not Array or f.hole_counts.size() != f.part_count: return "Invalid forest hole mapping."
		for holes in f.hole_counts:
			if not boundary._count(holes,16): return "Invalid forest hole count."
		if f.get("sources") is not Array or f.sources.is_empty() or f.sources.size() > 128: return "Missing land cover sources."
		for entry in f.sources:
			if entry is not Dictionary or not boundary._text(entry.get("dataset")): return "Invalid land cover attribution."
			if entry.get("license") != null and not boundary._text(entry.license): return "Invalid source license."
		if disposition != "forest":
			if not f.zone_ids.is_empty(): return "Excluded land class cannot create trees."
			continue
		if f.zone_ids.size() != f.part_count: return "Incomplete forest part mapping."
		var prefix := "import-%s-%d" % [raw.layer_id,selected]
		for i in range(f.zone_ids.size()):
			var expected := prefix if f.part_count == 1 else "%s-part-%d" % [prefix,i]
			if f.zone_ids[i] != expected or zones.has(expected): return "Invalid forest zone identity."
			zones[expected] = f.hole_counts[i]
		selected += 1
	if selected != raw.feature_count or zones.size() != raw.patches.size() or raw.estimates.get("vegetation_spacing_density") != zones.size(): return "Incomplete forest count/estimates."
	for patch in raw.patches:
		if patch.field != "zones" or not zones.has(patch.id) or patch.after.get("kind") != "forest" or patch.after.get("spacing_cm") != 800 or patch.after.get("density_per_mille") != 750: return "Forest profile may only add mapped estimated forest zones."
		if patch.after.get("exclusions") is not Array or patch.after.exclusions.size() != zones[patch.id]: return "Forest exclusion mapping changed."
	return ""
