extends RefCounted
## Untrusted adapter output can only add a fresh, explicitly adopted vector layer.
const MAX_BYTES := 12 * 1024 * 1024
const FIELDS := ["nodes", "roads", "buildings", "zones"]
const OSM_LICENSE := "ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
const OVERTURE_LICENSE := "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings"
const OVERTURE_TRANSPORTATION_LICENSE := "ODbL-1.0; © OpenStreetMap contributors; TomTom; Overture Maps Foundation; https://docs.overturemaps.org/attribution/#transportation"
const OVERTURE_LAND_COVER_LICENSE := "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; ESA WorldCover (CC-BY-4.0); © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium; https://docs.overturemaps.org/attribution/#base"
var value: Dictionary = {}

static func _hex(text: Variant, length: int) -> bool:
	if text is not String or text.length() != length: return false
	for c in text:
		if c not in "0123456789abcdef": return false
	return true

static func _text(value: Variant) -> bool:
	if value is not String or value.strip_edges().is_empty() or value.length() > 512: return false
	for c in value:
		if c.unicode_at(0) < 32: return false
	return true

static func _count(value: Variant, maximum: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value)) and value >= 0 and value <= maximum

static func _finite(value: Variant, minimum: float, maximum: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and value >= minimum and value <= maximum

static func _coordinates(c: Variant, requested: Dictionary) -> String:
	if c is not Dictionary or c.get("quantization_cm") != 1: return "Unsupported import coordinates."
	if not requested.is_empty() and c.get("mode") != requested.get("mode"): return "Import coordinate selection changed."
	if c.get("mode") == "local-metres": return ""
	if c.get("mode") != "wgs84-utm" or c.get("source_crs") != "EPSG:4326" or c.get("axis_order") != "longitude-latitude" or c.get("pyproj") != "3.7.2" or not _text(c.get("proj")) or c.get("max_radius_m") != 20000: return "Invalid projection metadata."
	for key in ["origin", "local_origin_m"]:
		if c.get(key) is not Array or c[key].size() != 2: return "Invalid projection origin."
		if not requested.is_empty():
			if requested.get(key) is not Array or requested[key].size() != 2: return "Missing requested projection origin."
			for i in range(2):
				if c[key][i] != requested[key][i]: return "Projection origin does not match request."
	if not _finite(c.origin[0], -180, 180) or not _finite(c.origin[1], -80, 84): return "Invalid geographic origin."
	for n in c.local_origin_m:
		if not _finite(n, -100000, 100000): return "Invalid local origin."
	var zone := mini(60, int(floor((float(c.origin[0]) + 180) / 6)) + 1)
	if c.get("target_crs") != "EPSG:%d" % ((32700 if c.origin[1] < 0 else 32600) + zone): return "Incorrect UTM zone/hemisphere."
	return ""

func load_value(raw: Variant, expected_id: String, requested: Dictionary = {}) -> String:
	value = {}
	if raw is not Dictionary or JSON.stringify(raw).to_utf8_buffer().size() > MAX_BYTES: return "Invalid or oversized ImportLayer."
	if raw.get("import_version") != 1 or raw.get("adapter") not in ["geojson-local-v1", "geojson-v2", "osm-extract-v1", "overture-buildings-v1", "overture-transportation-v1", "overture-land-cover-v1"]: return "Unsupported ImportLayer version/adapter."
	if requested.has("adapter") and raw.adapter != requested.adapter: return "Import adapter does not match request."
	if not _hex(raw.get("layer_id"), 32) or raw.layer_id != expected_id: return "Stale or invalid import identity."
	var source: Variant = raw.get("source")
	if source is not Dictionary or not _text(source.get("name")) or not _text(source.get("license")) or not _text(source.get("accuracy")) or not _hex(source.get("sha256"), 64) or not _count(source.get("bytes"), 2 * 1024 * 1024 * 1024): return "Invalid import source metadata."
	var coordinate_error := _coordinates(raw.get("coordinates"), requested)
	if coordinate_error != "": return coordinate_error
	var vertical_error: String = preload("./import_vertical.gd").validate(raw, requested)
	if vertical_error != "": return vertical_error
	if raw.adapter == "osm-extract-v1" and (source.license != OSM_LICENSE or raw.coordinates.mode != "wgs84-utm"): return "OSM requires geographic coordinates and ODbL attribution."
	var streaming: Variant = raw.coordinates.get("osm_stream")
	if streaming != null or requested.has("osm_stream"):
		if raw.adapter != "osm-extract-v1" or streaming is not Dictionary or streaming.get("profile") != "pbf-area-stream-v1" or streaming.get("passes") != 3 or not raw.coordinates.has("osm_crop"): return "Invalid PBF streaming provenance."
		if not requested.is_empty() and requested.get("osm_stream") != true: return "PBF streaming selection changed."
		if source.bytes <= 0 or streaming.get("source_bytes") != source.bytes or streaming.get("source_sha256") != source.sha256: return "PBF captured source mismatch."
		if streaming.get("scan") is not Dictionary or streaming.get("selected") is not Dictionary: return "Invalid PBF streaming counts."
		for key in ["nodes", "ways", "relations", "references"]:
			if not _count(streaming.scan.get(key), 80000000 if key == "references" else 20000000) or not _count(streaming.selected.get(key), 200000 if key in ["nodes", "references"] else 250000): return "PBF streaming count budget exceeded."
			if streaming.selected[key] > streaming.scan[key]: return "PBF selected counts exceed scanned source."
		if streaming.scan.nodes + streaming.scan.ways + streaming.scan.relations > 20000000 or streaming.selected.nodes + streaming.selected.ways + streaming.selected.relations > 250000 or not _count(streaming.selected.get("bytes"), 32 * 1024 * 1024): return "PBF streaming selection budget exceeded."
	elif source.bytes > 32 * 1024 * 1024:
		return "Non-streaming import source exceeds 32 MiB."
	var crop: Variant = raw.coordinates.get("osm_crop")
	if requested.has("osm_bbox") or crop != null:
		if raw.adapter != "osm-extract-v1" or crop is not Dictionary or crop.get("policy") not in ["geometry-intersection-v1", "geometry-intersection-v2", "geometry-intersection-v3"] or crop.get("shapely") != "2.1.2" or not _text(crop.get("geos")): return "Invalid OSM crop provenance."
		var bbox: Variant = crop.get("bbox")
		if bbox is not Array or bbox.size() != 4: return "Invalid OSM crop area."
		for i in range(4):
			if not _finite(bbox[i], -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84): return "Invalid OSM crop coordinate."
		if bbox[0] >= bbox[2] or bbox[1] >= bbox[3] or bbox[2]-bbox[0] > 0.02 or bbox[3]-bbox[1] > 0.02: return "Invalid OSM crop size."
		if not requested.is_empty() and JSON.stringify(bbox) != JSON.stringify(requested.get("osm_bbox")): return "OSM crop selection changed."
		if crop.get("counts") is not Dictionary: return "Invalid OSM crop counts."
		for key in ["input_features", "outside_features", "changed_features", "output_features", "boundary_contacts"]:
			if not _count(crop.counts.get(key), 200000): return "Invalid OSM crop count."
		if crop.counts.output_features != raw.get("feature_count"): return "OSM crop count mismatch."
		if crop.policy in ["geometry-intersection-v2", "geometry-intersection-v3"]:
			var vertical: Variant = crop.get("vertical")
			if vertical is not Dictionary or vertical.get("profile") != ("explicit-structure-crop-v1" if crop.policy == "geometry-intersection-v3" else "explicit-ground-crop-v1"): return "Invalid OSM vertical crop profile."
			for key in ["clipped_ground_features", "outside_explicit_features", "retained_structure_features"]:
				if not _count(vertical.get(key), 20000): return "Invalid OSM vertical crop count."
			if vertical.clipped_ground_features > crop.counts.changed_features or vertical.outside_explicit_features > crop.counts.outside_features or vertical.retained_structure_features > crop.counts.output_features: return "OSM vertical crop count mismatch."
		elif crop.has("vertical"): return "OSM vertical crop requires version 2 or 3."
	var overture_building_ids := {}
	var overture_vertical := false
	if raw.adapter == "overture-buildings-v1":
		if source.license != OVERTURE_LICENSE or raw.coordinates.mode != "wgs84-utm": return "Overture requires WGS84 and attribution."
		var meta: Variant = raw.coordinates.get("overture")
		if meta is not Dictionary or meta.get("provider") != "Overture" or meta.get("type") != "building" or meta.get("license") != OVERTURE_LICENSE or not _text(meta.get("release")) or meta.get("bbox") is not Array or meta.bbox.size() != 4 or meta.get("feature_sources") is not Array or meta.feature_sources.size() != raw.get("feature_count"): return "Invalid Overture provenance."
		var release_pattern := RegEx.new()
		release_pattern.compile("^20[0-9]{2}-[0-9]{2}-[0-9]{2}\\.[0-9]+$")
		if release_pattern.search(meta.release) == null: return "Invalid Overture release."
		for i in range(4):
			if not _finite(meta.bbox[i], -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84): return "Invalid Overture area."
		if meta.bbox[0] >= meta.bbox[2] or meta.bbox[1] >= meta.bbox[3] or meta.bbox[2]-meta.bbox[0] > 0.02 or meta.bbox[3]-meta.bbox[1] > 0.02: return "Invalid Overture area size."
		overture_vertical = meta.get("include_parts", false) == true
		if meta.has("include_parts") and (meta.include_parts is not bool or not meta.include_parts): return "Invalid Overture vertical selection."
		if overture_vertical and (not _finite(meta.get("ground_m"), -9000, 9000) or meta.get("parent_sources") is not Array or meta.parent_sources.size() + meta.feature_sources.size() > 256): return "Invalid Overture vertical provenance."
		var source_ids := {}
		for feature in meta.feature_sources:
			if feature is not Dictionary or not _text(feature.get("id")) or source_ids.has(feature.id) or feature.get("sources") is not Array or feature.sources.is_empty() or feature.sources.size() > 128: return "Invalid Overture feature sources."
			source_ids[feature.id] = true
			if not _count(feature.get("footprint_count"), 256) or feature.footprint_count < 1 or feature.get("building_ids") is not Array or feature.building_ids.size() != feature.footprint_count: return "Invalid Overture footprint mapping."
			for building_id in feature.building_ids:
				if not _text(building_id) or overture_building_ids.has(building_id): return "Invalid Overture building mapping."
				overture_building_ids[building_id] = feature
			if overture_vertical and (not _finite(feature.get("base_cm"), -900000, 1000000) or not _count(feature.get("height_cm"), 100000) or feature.height_cm < 1): return "Invalid Overture vertical dimensions."
			for entry in feature.sources:
				if entry is not Dictionary or not _text(entry.get("dataset")): return "Invalid Overture source dataset."

		if overture_vertical:
			var linked := {}
			for parent in meta.parent_sources:
				if parent is not Dictionary or not _text(parent.get("id")) or source_ids.has(parent.id) or parent.get("part_ids") is not Array or parent.part_ids.is_empty() or parent.part_ids.size() > 256 or parent.get("sources") is not Array or parent.sources.is_empty() or parent.sources.size() > 128: return "Invalid Overture parent source."
				source_ids[parent.id] = true
				for source_entry in parent.sources:
					if source_entry is not Dictionary or not _text(source_entry.get("dataset")): return "Invalid Overture parent attribution."
				for part_id in parent.part_ids:
					if not _text(part_id) or linked.has(part_id): return "Duplicate/invalid Overture parent link."
					linked[part_id] = parent.id
			for feature in meta.feature_sources:
				if feature.has("parent_id"):
					if not _text(feature.parent_id) or linked.get(feature.id) != feature.parent_id: return "Missing Overture parent link."
					linked.erase(feature.id)
				elif linked.has(feature.id): return "Missing Overture part link."
			if not linked.is_empty(): return "Unknown Overture part link."

	for key in ["feature_count", "point_count", "warning_count"]:
		if not _count(raw.get(key), 200000): return "Invalid import counts."
	if raw.get("warnings") is not Array or raw.warnings.size() > 50 or raw.warning_count < raw.warnings.size(): return "Invalid import warnings."
	for warning in raw.warnings:
		if not _text(warning): return "Invalid import warning."
	if raw.get("estimates") is not Dictionary or raw.estimates.size() > 32: return "Invalid estimates."
	for key in raw.estimates:
		if not _text(key) or not _count(raw.estimates[key], 200000): return "Invalid estimated-field count."
	if raw.get("extent_cm") is not Array or raw.extent_cm.size() != 4: return "Invalid import extent."
	for n in raw.extent_cm:
		if not _count(n + 10000000 if n is int or n is float else null, 20000000): return "Invalid import extent coordinate."
	if raw.extent_cm[0] > raw.extent_cm[2] or raw.extent_cm[1] > raw.extent_cm[3]: return "Invalid import extent ordering."
	if raw.get("patches") is not Array or raw.patches.is_empty() or raw.patches.size() > 60000: return "Invalid import records."
	if raw.adapter == "overture-buildings-v1" and overture_building_ids.size() != raw.patches.size(): return "Incomplete Overture footprint mapping."
	var ids := {}
	var nodes := {}
	var structure_count := 0
	var prefix := "import-" + expected_id + "-"
	for patch in raw.patches:
		if patch is not Dictionary or not patch.has_all(["field", "id", "before", "after"]): return "Invalid import patch."
		if raw.adapter == "overture-buildings-v1" and patch.field != "buildings": return "Overture profile may only add buildings."
		if patch.field not in FIELDS or patch.before != null or patch.after is not Dictionary: return "Import may only add supported records."
		if patch.id is not String or not patch.id.begins_with(prefix) or patch.id.length() > 128 or patch.after.get("id") != patch.id or ids.has(patch.id): return "Invalid/duplicate import record identity."
		if raw.adapter == "overture-buildings-v1" and not overture_building_ids.has(patch.id): return "Unmapped Overture building."
		if overture_vertical:
			var dimensions: Dictionary = overture_building_ids[patch.id]
			if patch.after.get("base_cm") != dimensions.base_cm or patch.after.get("height_cm") != dimensions.height_cm: return "Overture vertical dimensions changed."
		ids[patch.id] = true
		if patch.field == "nodes": nodes[patch.id] = true
		if patch.field == "nodes" and patch.id.contains("-osm-node-") and raw.coordinates.has("vertical") and raw.coordinates.vertical.explicit_points == 0: return "Explicit OSM nodes require nonzero vertical source counts."
		if patch.field == "roads" and patch.after.get("kind") in ["bridge", "tunnel"]: structure_count += 1
	if crop is Dictionary and crop.get("policy") in ["geometry-intersection-v2", "geometry-intersection-v3"] and crop.vertical.retained_structure_features != structure_count: return "OSM retained structure count mismatch."
	for patch in raw.patches:
		if patch.field == "roads" and (not nodes.has(patch.after.get("from")) or not nodes.has(patch.after.get("to"))): return "Imported roads must reference their own layer nodes."
	if crop is Dictionary and crop.get("policy") == "geometry-intersection-v3":
		var structure_error := _structure_crop(raw, prefix)
		if structure_error != "": return structure_error
	if raw.adapter == "overture-transportation-v1":
		var transport_error: String = preload("./import_transportation.gd").validate(raw, get_script())
		if transport_error != "": return transport_error
	if raw.adapter == "overture-land-cover-v1":
		var land_error: String = preload("./import_land_cover.gd").validate(raw, get_script())
		if land_error != "": return land_error
	value = raw.duplicate(true)
	return ""

static func _structure_crop(raw: Dictionary, prefix: String) -> String:
	var crop: Dictionary = raw.coordinates.osm_crop
	var v: Dictionary = crop.vertical
	if not _count(v.get("partial_structure_ways"), 20000) or v.partial_structure_ways < 1 or not _count(v.get("section_endpoints"), 40000): return "Invalid partial structure counts."
	if v.get("structures") is not Array or v.structures.size() != v.retained_structure_features: return "Incomplete structure crop mapping."
	var roads := {}
	for patch: Dictionary in raw.patches:
		if patch.field == "roads": roads[patch.id] = patch.after
	var mapped := {}
	var ways := {}
	var sections := 0
	var source_id := RegEx.new()
	source_id.compile("^[1-9][0-9]{0,18}$")
	for entry in v.structures:
		if entry is not Dictionary or not _count(entry.get("feature"), int(crop.counts.output_features)-1) or not _count(entry.get("source_feature"), int(crop.counts.input_features)-1): return "Invalid structural source feature."
		if entry.get("source_way") is not String or source_id.search(entry.source_way) == null: return "Invalid structural source way."
		var span: Variant = entry.get("source_range")
		if span is not Array or span.size() != 2 or not _finite(span[0],0,200000) or not _finite(span[1],0,200000) or span[0] >= span[1]: return "Invalid structural source interval."
		var id := prefix + str(int(entry.feature))
		if not roads.has(id) or mapped.has(id) or roads[id].get("kind") not in ["bridge", "tunnel"]: return "Unmapped/duplicate cropped structure."
		mapped[id] = true
		if entry.get("partial") is not bool or (ways.has(entry.source_way) and ways[entry.source_way] != entry.partial): return "Inconsistent partial source-way mapping."
		ways[entry.source_way] = entry.partial
		if entry.get("endpoints") is not Array or entry.endpoints.size() != 2: return "Missing structure crop endpoints."
		for i in range(2):
			var end: Variant = entry.endpoints[i]
			if end is not Dictionary or not _text(end.get("ref")) or end.get("role") not in ["source-node", "boundary-section"]: return "Invalid structure endpoint role."
			if roads[id].get("from" if i == 0 else "to") != prefix + "osm-node-" + end.ref: return "Structure crop endpoint mismatch."
			if end.ref.begins_with("crop-"):
				if end.role != "boundary-section": return "Synthetic cut is not an original structure endpoint."
			elif source_id.search(end.ref) == null: return "Invalid structure source node."
			if end.role == "boundary-section" and not entry.partial: return "Section end requires a partial source way."
			sections += int(end.role == "boundary-section")
	var partial_ways := 0
	for partial: bool in ways.values(): partial_ways += int(partial)
	if sections < 1 or sections != v.section_endpoints or v.partial_structure_ways != partial_ways: return "Structure section count mismatch."
	return ""

func patches(store: RefCounted) -> Array:
	var result: Array = value.patches.duplicate(true)
	var metadata := value.duplicate(true)
	metadata.erase("patches")
	var attribution := {"source": value.source.name + "#" + value.layer_id, "license": value.source.license, "notice": JSON.stringify(metadata)}
	result.append({"field": "attributions", "id": store.record_id("attributions", attribution), "before": null, "after": attribution})
	return result

func validate_for(store: RefCounted) -> String:
	if value.is_empty(): return "No import candidate."
	if value.adapter == "osm-extract-v1":
		var explicit := false
		for patch: Dictionary in value.patches:
			if patch.field == "nodes" and patch.id.contains("-osm-node-"): explicit = true; break
		if explicit:
			var frame: Dictionary = value.coordinates.get("vertical", {"target_crs":"EPSG:5773 / EGM96 metres", "vertical_zero_m":0})
			var frame_error: String = preload("./import_vertical.gd").frame_error(store.document, frame, value.coordinates)
			if frame_error != "": return frame_error
	if value.adapter == "overture-land-cover-v1" and store.document.recipe_version < 3: return "Land cover vegetation requires explicit recipe 3 or newer."
	if value.adapter == "overture-buildings-v1" and value.coordinates.overture.get("include_parts", false) and store.document.recipe_version < 3: return "Vertical building parts require explicit recipe 3 or newer."
	var candidate: Dictionary = store.document.duplicate(true)
	var failure: String = store._apply(candidate, patches(store), false)
	if failure != "": return failure
	var result: Dictionary = store._validate(candidate)
	return "" if result.ok else store.reason(result)

func adopt(store: RefCounted) -> String:
	var failure := validate_for(store)
	return failure if failure != "" else store.apply_command("Adopt import " + str(value.source.name), patches(store))

func summary() -> String:
	var coordinates: Dictionary = value.coordinates.duplicate(true)
	var vertical := ""
	if coordinates.has("vertical"):
		vertical = preload("./import_vertical.gd").summary(coordinates.vertical) + "\n"
		coordinates.erase("vertical")
	return vertical + "%s · %d bytes\nLicense: %s · source accuracy: %s\n%d features / %d records · local extent (cm): %s\nProjection: %s\nEstimated fields (counts): %s\nWarnings: %d (showing %d)\n%s\n\nAdopt adds a new layer as one Undo command. Existing objects and source files remain unchanged." % [value.source.name, value.source.bytes, value.source.license, value.source.accuracy, value.feature_count, value.patches.size(), str(value.extent_cm), JSON.stringify(coordinates), JSON.stringify(value.estimates), value.warning_count, value.warnings.size(), "\n".join(value.warnings)]
