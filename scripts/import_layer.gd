extends RefCounted
const I18N := preload("./locale_text.gd")
const LIMITS := preload("./limit_warnings.gd")
## Untrusted adapter output can only add a fresh, explicitly adopted vector layer.
## MAX_BYTES is the memory guard; the former budgets only warn now.
const MAX_BYTES := 1024 * 1024 * 1024
const WARN_BYTES := 12 * 1024 * 1024
const WARN_CITY_BYTES := 32 * 1024 * 1024
const MAX_STREAM_SOURCE_BYTES := 64 * 1024 * 1024 * 1024
const WARN_STREAM_SOURCE_BYTES := 2 * 1024 * 1024 * 1024
## Non-streamed sources are read whole by the helper (Python INPUT_CEILING).
const MAX_SOURCE_BYTES := 256 * 1024 * 1024
const WARN_SOURCE_BYTES := 32 * 1024 * 1024
## Overture area side: memory guard, warning above the former 0.02 degrees
## (Python overture_area.DEGREES_CEILING / MAX_DEGREES).
const OVERTURE_DEGREES_CEILING := 0.2
const WARN_OVERTURE_MICRODEGREES := 20000
const MAX_AREAS := 64
const WARN_AREAS := 8
## Every affected cell is still generated; this only bounds the cell list.
const MAX_CHECK_CELLS := 16384
## Count re-checks of own adapter output: shape sanity only, never a budget.
const SANITY := 1000000000000
const FIELDS := ["nodes", "roads", "buildings", "zones", "surface_areas", "pois"]
const OSM_LICENSE := "ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
const OVERTURE_LICENSE := "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings"
const OVERTURE_TRANSPORTATION_LICENSE := "ODbL-1.0; © OpenStreetMap contributors; TomTom; Overture Maps Foundation; https://docs.overturemaps.org/attribution/#transportation"
const OVERTURE_LAND_COVER_LICENSE := "ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; ESA WorldCover (CC-BY-4.0); © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium; https://docs.overturemaps.org/attribution/#base"
var value: Dictionary = {}
var limit_warnings: Array = []
var native_payload_digest := ""
var _review_prefix := ""

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

## A valid count of any size; above the former budget it is only noted.
## A non-crossing Overture area within the ceiling; a side above 0.02 degrees warns.
static func _overture_area(notes: Array, bbox: Array) -> bool:
	if bbox[0] >= bbox[2] or bbox[1] >= bbox[3] or bbox[2]-bbox[0] > OVERTURE_DEGREES_CEILING or bbox[3]-bbox[1] > OVERTURE_DEGREES_CEILING: return false
	LIMITS.over(notes, "overture_area_degrees", int(round(maxf(bbox[2]-bbox[0], bbox[3]-bbox[1]) * 1000000.0)), WARN_OVERTURE_MICRODEGREES, "Overture area side in microdegrees")
	return true

static func _soft(notes: Array, code: String, value: Variant, limit: int, message: String) -> bool:
	if not _count(value, SANITY): return false
	LIMITS.over(notes, code, int(value), limit, message)
	return true

static func _exclusion_review(raw: Dictionary, requested: Dictionary, notes: Array = []) -> String:
	var review: Variant = raw.coordinates.get("osm_review")
	if review == null: return "Missing requested OSM exclusion review." if requested.get("osm_review_exclusions", false) else ""
	if raw.adapter != "osm-extract-v1" or not raw.coordinates.has("osm_stream") or review is not Dictionary or review.get("profile") != "explicit-source-exclusions-v1" or review.get("excluded") is not Array: return "Invalid OSM exclusion review."
	LIMITS.over(notes, "osm_review_exclusions", review.excluded.size(), 20000, "Excluded OSM objects")
	if not requested.is_empty() and requested.get("osm_review_exclusions") != true: return "Unrequested OSM source exclusions."
	var ids := {}
	var pattern := RegEx.new()
	pattern.compile("^(way|relation)/[1-9][0-9]{0,19}$")
	for entry in review.excluded:
		if entry is not Dictionary or not _text(entry.get("source_id")) or pattern.search(entry.source_id) == null or ids.has(entry.source_id) or not _text(entry.get("reason")): return "Invalid/duplicate excluded source object."
		ids[entry.source_id] = true
	for source in raw.coordinates.get("source_objects", []):
		if source is not Dictionary or ids.has(source.get("source_id")): return "Excluded OSM object still has imported records."
	return ""

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
				# Compare the same JSON-decoded float representation used by the
				# helper response. SpinBox arithmetic can differ by one binary ULP.
				var wire_value: Variant = JSON.parse_string(JSON.stringify(requested[key][i], "", false, true))
				if c[key][i] != wire_value: return "Projection origin does not match request."
	if not _finite(c.origin[0], -180, 180) or not _finite(c.origin[1], -80, 84): return "Invalid geographic origin."
	for n in c.local_origin_m:
		if not _finite(n, -100000, 100000): return "Invalid local origin."
	var zone := mini(60, int(floor((float(c.origin[0]) + 180) / 6)) + 1)
	if c.get("target_crs") != "EPSG:%d" % ((32700 if c.origin[1] < 0 else 32600) + zone): return "Incorrect UTM zone/hemisphere."
	return ""

func load_value(raw: Variant, expected_id: String, requested: Dictionary = {}) -> String:
	value = {}
	limit_warnings = []
	native_payload_digest = ""
	_review_prefix = ""
	var notes: Array = []
	var failure := _load(raw, expected_id, requested, notes)
	if failure == "": limit_warnings = notes
	return failure

func _load(raw: Variant, expected_id: String, requested: Dictionary, notes: Array) -> String:
	if raw is not Dictionary: return "Invalid or oversized ImportLayer."
	var layer_bytes := JSON.stringify(raw).to_utf8_buffer().size()
	if layer_bytes > MAX_BYTES: return "Invalid or oversized ImportLayer."
	if raw.get("import_version") != 1 or raw.get("adapter") not in ["geojson-v1", "osm-extract-v1", "overture-buildings-v1", "overture-transportation-v1", "overture-land-cover-v1", "facility-csv-v1"]: return "Unsupported ImportLayer version/adapter."
	if requested.has("adapter") and raw.adapter != requested.adapter: return "Import adapter does not match request."
	if not _hex(raw.get("layer_id"), 32) or raw.layer_id != expected_id: return "Stale or invalid import identity."
	var source: Variant = raw.get("source")
	if source is not Dictionary or not _text(source.get("name")) or not _text(source.get("license")) or not _text(source.get("accuracy")) or not _hex(source.get("sha256"), 64) or not _count(source.get("bytes"), MAX_STREAM_SOURCE_BYTES): return "Invalid import source metadata."
	var coordinate_error := _coordinates(raw.get("coordinates"), requested)
	if coordinate_error != "": return coordinate_error
	var exclusion_error := _exclusion_review(raw, requested, notes)
	if exclusion_error != "": return exclusion_error
	var city_error: String = preload("./import_city.gd").validate(raw, requested, get_script(), notes)
	if city_error != "": return city_error
	var city: bool = raw.coordinates.has("osm_city")
	LIMITS.over(notes, "import_layer_bytes", layer_bytes, WARN_CITY_BYTES if city else WARN_BYTES, "ImportLayer size in bytes")
	var vertical_error: String = preload("./import_vertical.gd").validate(raw, requested, notes)
	if vertical_error != "": return vertical_error
	var height_error: String = preload("./import_height_supplement.gd").validate(raw, requested, notes)
	if height_error != "": return height_error
	if raw.adapter == "osm-extract-v1" and (source.license != OSM_LICENSE or raw.coordinates.mode != "wgs84-utm"): return "OSM requires geographic coordinates and ODbL attribution."
	var streaming: Variant = raw.coordinates.get("osm_stream")
	if streaming != null or requested.has("osm_stream"):
		if raw.adapter != "osm-extract-v1" or streaming is not Dictionary or streaming.get("profile") != "pbf-area-stream-v1" or streaming.get("passes") != 3 or not raw.coordinates.has("osm_crop"): return "Invalid PBF streaming provenance."
		if not requested.is_empty() and requested.get("osm_stream") != true: return "PBF streaming selection changed."
		if source.bytes <= 0 or streaming.get("source_bytes") != source.bytes or streaming.get("source_sha256") != source.sha256: return "PBF captured source mismatch."
		if streaming.get("scan") is not Dictionary or streaming.get("selected") is not Dictionary: return "Invalid PBF streaming counts."
		var scanned_text := {"nodes":"Scanned PBF nodes", "ways":"Scanned PBF ways", "relations":"Scanned PBF relations", "references":"Scanned PBF references"}
		var selected_text := {"nodes":"Selected PBF nodes", "ways":"Selected PBF ways", "relations":"Selected PBF relations", "references":"Selected PBF references"}
		for key in ["nodes", "ways", "relations", "references"]:
			var selected_limit := (4000000 if key == "references" else 2000000) if city else (200000 if key in ["nodes", "references"] else 250000)
			if not _soft(notes, "pbf_scan_" + key, streaming.scan.get(key), 80000000 if key == "references" else 100000000, scanned_text[key]) or not _soft(notes, "pbf_selected_" + key, streaming.selected.get(key), selected_limit, selected_text[key]): return "Invalid PBF streaming counts."
			if streaming.selected[key] > streaming.scan[key]: return "PBF selected counts exceed scanned source."
		if not _soft(notes, "pbf_selected_bytes", streaming.selected.get("bytes"), (256 if city else 32) * 1024 * 1024, "Selected PBF bytes"): return "Invalid PBF streaming counts."
		LIMITS.over(notes, "pbf_scan_entities", int(streaming.scan.nodes + streaming.scan.ways + streaming.scan.relations), 100000000, "Scanned PBF entities")
		LIMITS.over(notes, "pbf_selected_entities", int(streaming.selected.nodes + streaming.selected.ways + streaming.selected.relations), 2000000 if city else 250000, "Selected PBF entities")
		if streaming.has("structure_closure"):
			var closure: Variant = streaming.structure_closure
			if closure is not Dictionary or closure.get("profile") not in ["structural-incidence-v1", "loop-structural-incidence-v1"]: return "Invalid structural closure profile."
			var closure_text := {"ways":"Structural closure ways", "structures":"Structural closure structures", "nodes":"Structural closure nodes", "visits":"Structural closure visits"}
			for key in ["ways", "structures", "nodes", "visits"]:
				if not _soft(notes, "structure_closure_" + key, closure.get(key), 20000 if key in ["ways", "structures"] else 200000, closure_text[key]): return "Invalid structural closure counts."
			if closure.profile == "loop-structural-incidence-v1" and (not _soft(notes, "structure_closure_loops", closure.get("loops"), 20000, "Structural closure loops") or closure.loops < 1 or closure.loops + closure.structures > closure.ways or (not raw.coordinates.has("osm_ground_loops") and not raw.coordinates.has("osm_review"))): return "Invalid OSM loop closure counts."
			if closure.structures > closure.ways or closure.ways > streaming.selected.ways or closure.nodes > streaming.selected.nodes or closure.visits < closure.nodes: return "Invalid structural closure counts."
	elif source.bytes > MAX_SOURCE_BYTES:
		return "Non-streaming import source exceeds 256 MiB."
	else: LIMITS.over(notes, "source_bytes", int(source.bytes), WARN_SOURCE_BYTES, "Import source size in bytes")
	if streaming != null: LIMITS.over(notes, "stream_source_bytes", int(source.bytes), WARN_STREAM_SOURCE_BYTES, "PBF source size in bytes")
	var crop: Variant = raw.coordinates.get("osm_crop")
	if requested.has("osm_bbox") or crop != null:
		if raw.adapter != "osm-extract-v1" or crop is not Dictionary or crop.get("policy") != "geometry-intersection-v1" or crop.get("shapely") != "2.1.2" or not _text(crop.get("geos")): return "Invalid OSM crop provenance."
		var bbox: Variant = crop.get("bbox")
		if bbox is not Array or bbox.size() != 4: return "Invalid OSM crop area."
		for i in range(4):
			if not _finite(bbox[i], -180 if i % 2 == 0 else -80, 180 if i % 2 == 0 else 84): return "Invalid OSM crop coordinate."
		if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]: return "Invalid OSM crop size."
		if not requested.is_empty() and JSON.stringify(bbox) != JSON.stringify(requested.get("osm_bbox")): return "OSM crop selection changed."
		if requested.has("osm_areas") or crop.has("region"):
			var expected: Array = requested.get("osm_areas", []).map(func(id): return "relation/%d" % int(id))
			var areas: Variant = crop.get("areas")
			if crop.get("region") != "administrative-union-v1" or areas is not Array or areas.is_empty() or areas.size() > MAX_AREAS: return "Invalid administrative area crop."
			LIMITS.over(notes, "osm_areas", areas.size(), WARN_AREAS, "Combined administrative areas")
			if not requested.is_empty() and areas.map(func(a): return a.get("source_id") if a is Dictionary else null) != expected: return "OSM crop areas changed."
		if crop.get("counts") is not Dictionary: return "Invalid OSM crop counts."
		var crop_text := {"input_features":"Crop input features", "outside_features":"Crop outside features", "changed_features":"Crop changed features", "output_features":"Crop output features", "boundary_contacts":"Crop boundary contacts"}
		for key in ["input_features", "outside_features", "changed_features", "output_features", "boundary_contacts"]:
			if not _soft(notes, "osm_crop_" + key, crop.counts.get(key), 250000 if city else 200000, crop_text[key]): return "Invalid OSM crop count."
		if crop.counts.output_features != raw.get("feature_count"): return "OSM crop count mismatch."
		if city and crop.counts.get("pre_optimization_output_features") != raw.coordinates.osm_city.before.features: return "City crop source count mismatch."
		var vertical: Variant = crop.get("vertical")
		var profile := "explicit-connected-structure-crop-v1"
		if vertical is not Dictionary or vertical.get("profile") != profile or vertical.get("connection_sections") is not Array: return "Invalid OSM vertical crop profile."
		var vertical_text := {"clipped_ground_features":"Clipped ground features", "outside_explicit_features":"Explicit features outside the crop", "retained_structure_features":"Retained structure features"}
		for key in ["clipped_ground_features", "outside_explicit_features", "retained_structure_features"]:
			if not _soft(notes, "osm_vertical_" + key, vertical.get(key), 20000, vertical_text[key]): return "Invalid OSM vertical crop count."
		if vertical.clipped_ground_features > crop.counts.changed_features or vertical.outside_explicit_features > crop.counts.outside_features or vertical.retained_structure_features > crop.counts.output_features: return "OSM vertical crop count mismatch."
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
		if not _overture_area(notes, meta.bbox): return "Invalid Overture area size."
		overture_vertical = meta.get("include_parts", false) == true
		if meta.has("include_parts") and (meta.include_parts is not bool or not meta.include_parts): return "Invalid Overture vertical selection."
		if overture_vertical and (not _finite(meta.get("ground_m"), -9000, 9000) or meta.get("parent_sources") is not Array): return "Invalid Overture vertical provenance."
		if overture_vertical: LIMITS.over(notes, "overture_vertical_sources", meta.parent_sources.size() + meta.feature_sources.size(), 256, "Overture parts and parent buildings")
		var source_ids := {}
		for feature in meta.feature_sources:
			if feature is not Dictionary or not _text(feature.get("id")) or source_ids.has(feature.id) or feature.get("sources") is not Array or feature.sources.is_empty(): return "Invalid Overture feature sources."
			LIMITS.over(notes, "overture_sources", feature.sources.size(), 128, "Source datasets of one Overture building")
			source_ids[feature.id] = true
			if not _soft(notes, "overture_footprints", feature.get("footprint_count"), 256, "Footprints of one Overture building") or feature.footprint_count < 1 or feature.get("building_ids") is not Array or feature.building_ids.size() != feature.footprint_count: return "Invalid Overture footprint mapping."
			for building_id in feature.building_ids:
				if not _text(building_id) or overture_building_ids.has(building_id): return "Invalid Overture building mapping."
				overture_building_ids[building_id] = feature
			if overture_vertical and (not _finite(feature.get("base_cm"), -900000, 1000000) or not _count(feature.get("height_cm"), 100000) or feature.height_cm < 1): return "Invalid Overture vertical dimensions."
			for entry in feature.sources:
				if entry is not Dictionary or not _text(entry.get("dataset")): return "Invalid Overture source dataset."

		if overture_vertical:
			var linked := {}
			for parent in meta.parent_sources:
				if parent is not Dictionary or not _text(parent.get("id")) or source_ids.has(parent.id) or parent.get("part_ids") is not Array or parent.part_ids.is_empty() or parent.get("sources") is not Array or parent.sources.is_empty(): return "Invalid Overture parent source."
				LIMITS.over(notes, "overture_parent_parts", parent.part_ids.size(), 256, "Parts of one Overture parent building")
				LIMITS.over(notes, "overture_sources", parent.sources.size(), 128, "Source datasets of one Overture building")
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

	var count_text := {"feature_count":"Imported features", "point_count":"Imported points", "warning_count":"Adapter warnings"}
	for key in ["feature_count", "point_count", "warning_count"]:
		if not _soft(notes, "import_" + key, raw.get(key), 800000 if city else 200000, count_text[key]): return "Invalid import counts."
	# The adapter keeps at most 50 samples and reserves room for limit warnings.
	if raw.get("warnings") is not Array or raw.warnings.size() > 256 or raw.warning_count < raw.warnings.size(): return "Invalid import warnings."
	for warning in raw.warnings:
		if not _text(warning): return "Invalid import warning."
	if raw.get("estimates") is not Dictionary or raw.estimates.size() > 256: return "Invalid estimates."
	for key in raw.estimates:
		if not _text(key) or not _soft(notes, "estimated_fields", raw.estimates[key], 200000, "Estimated fields of one kind"): return "Invalid estimated-field count."
	if raw.get("extent_cm") is not Array or raw.extent_cm.size() != 4: return "Invalid import extent."
	for n in raw.extent_cm:
		if not _count(n + 10000000 if n is int or n is float else null, 20000000): return "Invalid import extent coordinate."
	if raw.extent_cm[0] > raw.extent_cm[2] or raw.extent_cm[1] > raw.extent_cm[3]: return "Invalid import extent ordering."
	if raw.get("patches") is not Array or (raw.patches.is_empty() and raw.coordinates.get("generation_regions", []).is_empty()): return "Invalid import records."
	LIMITS.over(notes, "import_records", raw.patches.size(), 180000 if city else 60000, "Imported records")
	if raw.adapter == "overture-buildings-v1" and overture_building_ids.size() != raw.patches.size(): return "Incomplete Overture footprint mapping."
	var region_error: String = preload("./import_regions.gd").validate(raw.coordinates.get("generation_regions", []), notes)
	if region_error != "": return region_error
	var ids := {}
	var nodes := {}
	var structure_count := 0
	var prefix := "import-" + expected_id + "-"
	var estimated: Variant = _estimated_structures(raw)
	if estimated == null: return "Invalid estimated city structures."
	for patch in raw.patches:
		if patch is not Dictionary or not patch.has_all(["field", "id", "before", "after"]): return "Invalid import patch."
		if raw.adapter == "overture-buildings-v1" and patch.field != "buildings": return "Overture profile may only add buildings."
		if patch.field not in FIELDS or patch.before != null or patch.after is not Dictionary: return "Import may only add supported records."
		if patch.field == "pois" and raw.adapter != "facility-csv-v1": return "Facility records require the CSV adapter."
		if patch.field == "surface_areas" and not raw.coordinates.has("osm_city"): return "Ground paint records require OSM city optimization."
		if patch.id is not String or not patch.id.begins_with(prefix) or patch.id.length() > 128 or patch.after.get("id") != patch.id or ids.has(patch.id): return "Invalid/duplicate import record identity."
		if raw.adapter == "overture-buildings-v1" and not overture_building_ids.has(patch.id): return "Unmapped Overture building."
		if overture_vertical:
			var dimensions: Dictionary = overture_building_ids[patch.id]
			if patch.after.get("base_cm") != dimensions.base_cm or patch.after.get("height_cm") != dimensions.height_cm: return "Overture vertical dimensions changed."
		ids[patch.id] = true
		if patch.field == "nodes": nodes[patch.id] = true
		if patch.field == "nodes" and patch.id.contains("-osm-node-") and raw.coordinates.has("vertical") and raw.coordinates.vertical.explicit_points == 0 and not raw.coordinates.has("osm_ground_loops"): return "Explicit OSM nodes require nonzero vertical source counts."
		if patch.field == "roads" and patch.after.get("kind") in ["bridge", "tunnel"] and not estimated.has(patch.id): structure_count += 1
	if crop is Dictionary and crop.vertical.retained_structure_features != structure_count: return "OSM retained structure count mismatch."
	for patch in raw.patches:
		if patch.field == "roads" and (not nodes.has(patch.after.get("from")) or not nodes.has(patch.after.get("to"))): return "Imported roads must reference their own layer nodes."
	var collection_error: String = preload("./import_collections.gd").validate(raw, get_script(), notes)
	if collection_error != "": return collection_error
	var multiline_error: String = preload("./import_multilines.gd").validate(raw, get_script(), notes)
	if multiline_error != "": return multiline_error
	var loop_error: String = preload("./import_osm_loops.gd").validate(raw, get_script(), notes)
	if loop_error != "": return loop_error
	var endpoint_error := _ground_endpoints(raw,prefix,notes)
	if endpoint_error != "": return endpoint_error
	var pedestrian: Variant = raw.coordinates.get("osm_pedestrian_roads", [])
	if pedestrian is not Array or (not pedestrian.is_empty() and raw.adapter != "osm-extract-v1"): return "Invalid OSM pedestrian road list."
	var road_ids := {}
	for patch: Dictionary in raw.patches:
		if patch.field == "roads": road_ids[patch.id] = true
	var listed := {}
	for id: Variant in pedestrian:
		if id is not String or not road_ids.has(id) or listed.has(id): return "Invalid OSM pedestrian road list."
		listed[id] = true
	var connection_error := _structure_connections(raw, prefix, notes)
	if connection_error != "": return connection_error
	if crop is Dictionary:
		var structure_error := _structure_crop(raw, prefix, notes)
		if structure_error != "": return structure_error
	if raw.adapter == "overture-transportation-v1":
		var transport_error: String = preload("./import_transportation.gd").validate(raw, get_script(), notes)
		if transport_error != "": return transport_error
	if raw.adapter == "overture-land-cover-v1":
		var land_error: String = preload("./import_land_cover.gd").validate(raw, get_script(), notes)
		if land_error != "": return land_error
	var csv_error: String = preload("./import_csv.gd").validate(raw, requested, get_script(), notes)
	if csv_error != "": return csv_error
	value = raw.duplicate(true)
	# These already validated, <=256 KiB source documents are parsed once here;
	# reopening the review does not parse raw JSON or traverse large mappings.
	if value.coordinates.has("vertical"):
		if value.coordinates.has("osm_ground_loops") and value.coordinates.vertical.explicit_points == 0:
			_review_prefix = I18N.t("No explicit OSM node heights. Ground heights are estimates; roads follow terrain. No source height datum was applied.\n")
		else:
			_review_prefix = preload("./import_vertical.gd").summary(value.coordinates.vertical) + "\n"
	if value.coordinates.has("osm_height_supplement"):
		_review_prefix += preload("./import_height_supplement.gd").summary(value.coordinates.osm_height_supplement) + "\n"
	if city: _review_prefix = preload("./import_city.gd").summary(value.coordinates.osm_city) + "\n" + _review_prefix
	return ""

## City structures with estimated heights: road IDs of bridge/tunnel records,
## joined to ordinary ground roads instead of explicit source-height graphs.
static func _estimated_structures(raw: Dictionary) -> Variant:
	var list: Variant = raw.coordinates.get("osm_estimated_structures", [])
	if list is not Array or (not list.is_empty() and not raw.coordinates.has("osm_city")): return null
	var kinds := {}
	for patch: Variant in raw.get("patches", []):
		if patch is Dictionary and patch.get("field") == "roads" and patch.get("after") is Dictionary: kinds[patch.id] = patch.after.get("kind")
	var result := {}
	for id: Variant in list:
		if id is not String or result.has(id) or kinds.get(id) not in ["bridge", "tunnel"]: return null
		result[id] = true
	return result

static func _ground_endpoints(raw: Dictionary, prefix: String, notes: Array = []) -> String:
	var entries: Variant = raw.coordinates.get("osm_ground_endpoints",[])
	if entries is not Array: return "Invalid OSM ground endpoint mapping."
	LIMITS.over(notes, "osm_ground_endpoints", entries.size(), 60000, "OSM ground endpoint mappings")
	var roads := {}; var nodes := {}; var expected := {}
	var estimated: Variant = _estimated_structures(raw)
	if estimated == null: return "Invalid estimated city structures."
	for patch: Dictionary in raw.patches:
		if patch.field == "roads":
			roads[patch.id] = patch.after
			if str(patch.after.from).contains("-osm-ground-node-") or str(patch.after.to).contains("-osm-ground-node-"): expected[patch.id] = true
		if patch.field == "nodes": nodes[patch.id] = patch.after
	var seen := {}
	for entry: Variant in entries:
		if raw.adapter != "osm-extract-v1" or entry is not Dictionary or not roads.has(entry.get("road_id")) or seen.has(entry.road_id) or entry.get("refs") is not Array or entry.refs.size() != 2: return "Invalid OSM ground endpoint mapping."
		seen[entry.road_id] = true
		var road: Dictionary = roads[entry.road_id]
		if road.kind != "ground" and not estimated.has(entry.road_id): return "Invalid OSM ground endpoint mapping."
		for i in 2:
			var ref: Variant = entry.refs[i]
			if ref != null and not preload("./import_osm_loops.gd").source_ref(ref): return "Invalid OSM ground endpoint mapping."
			var id: String = prefix+"osm-ground-node-"+ref if ref != null else entry.road_id+("-from" if i == 0 else "-to")
			if road["from" if i == 0 else "to"] != id or not nodes.has(id) or nodes[id].position != road.points[0 if i == 0 else -1]: return "Invalid OSM ground endpoint mapping."
		expected.erase(entry.road_id)
	return "" if expected.is_empty() else "Invalid OSM ground endpoint mapping."

static func _structure_connections(raw: Dictionary, prefix: String, notes: Array = []) -> String:
	var crop: Variant = raw.coordinates.get("osm_crop")
	var has_sections: bool = crop is Dictionary and not crop.vertical.connection_sections.is_empty()
	if not raw.coordinates.has("osm_connections"): return "Missing structure connections." if has_sections else ""
	var meta: Variant = raw.coordinates.osm_connections
	if raw.adapter != "osm-extract-v1" or meta is not Dictionary or meta.get("profile") != "explicit-structural-junctions-v1" or meta.get("joins") is not Array or meta.joins.is_empty(): return "Invalid structure connections."
	LIMITS.over(notes, "osm_structure_joins", meta.joins.size(), 20000, "Structural junctions")
	var incident := {}
	for patch: Dictionary in raw.patches:
		if patch.field != "roads": continue
		for endpoint: String in [patch.after.from, patch.after.to]:
			if not incident.has(endpoint): incident[endpoint] = []
			incident[endpoint].append(patch.after)
	var seen := {}
	var sections := {}
	var feature_sources := {}
	var loop_ids := _loop_feature_ids(raw)
	var total_arms := 0
	var source_id := RegEx.new()
	source_id.compile("^[1-9][0-9]{0,18}$")
	for join in meta.joins:
		if join is not Dictionary or join.get("ref") is not String or source_id.search(join.ref) == null or seen.has(join.ref): return "Invalid/duplicate source continuation."
		if not join.has("source_arms"): return "Missing structural source arms."
		if join.get("kind") not in ["bridge", "tunnel", "mixed"]: return "Invalid structural kind."
		seen[join.ref] = true
		var ways: Variant = join.get("source_ways")
		if ways is not Array or ways.size() < 2 or ways.size() > 32: return "Invalid continuation source ways."
		var unique_ways := {}
		for way in ways:
			if way is not String or source_id.search(way) == null or unique_ways.has(way): return "Invalid continuation source way."
			unique_ways[way] = true
		var expected := {}
		var expected_count := 2
		if join.source_arms is not Array or join.source_arms.size() < 2 or join.source_arms.size() > 32: return "Invalid structural arm budget."
		expected_count = join.source_arms.size()
		var source_kinds := {}
		var source_clearance: Variant = null
		var declared_ways := {}
		for arm in join.source_arms:
			if arm is not Dictionary or arm.get("source_way") not in ways or arm.get("end") not in ["from", "to"] or arm.get("kind") not in ["bridge", "tunnel"]: return "Invalid source structural arm."
			var key: String = arm.source_way + ":" + arm.end
			if expected.has(key): return "Duplicate source structural arm."
			expected[key] = arm
			if declared_ways.has(arm.source_way):
				var previous: Dictionary = declared_ways[arm.source_way]
				if previous.kind != arm.kind or previous.get("clearance_cm") != arm.get("clearance_cm"): return "Conflicting source-way structural profile."
			declared_ways[arm.source_way] = arm
			source_kinds[arm.kind] = true
			if arm.kind == "tunnel":
				if not _count(arm.get("clearance_cm"), 5000) or arm.clearance_cm < 200 or (source_clearance != null and source_clearance != arm.clearance_cm): return "Source tunnel clearance mismatch."
				source_clearance = arm.clearance_cm
			elif not arm.has("clearance_cm") or arm.clearance_cm != null: return "Bridge arm cannot declare tunnel clearance."
		if declared_ways.size() != ways.size() or join.kind != ("mixed" if source_kinds.size() == 2 else source_kinds.keys()[0]): return "Source structural kind/way mismatch."
		total_arms += expected_count
		var retained: Variant = join.get("retained")
		var roads: Array = incident.get(prefix + "osm-node-" + join.ref, [])
		if retained is not Array or retained.size() > expected_count or retained.size() != roads.size(): return "Incomplete continuation mapping."
		var mapped := {}
		var source_ways := {}
		var clearance: Variant = null
		for arm in retained:
			if arm is not Dictionary or not _count(arm.get("feature"), int(raw.feature_count)-1) or arm.get("source_way") not in ways: return "Invalid retained continuation arm."
			var source_key: String = arm.source_way
			if arm.get("end") not in ["from", "to"]: return "Missing retained structural direction."
			source_key += ":" + arm.end
			if not expected.has(source_key): return "Unknown retained structural arm."
			if source_ways.has(source_key): return "Duplicate retained source arm."
			var base_id := prefix + str(int(arm.feature))
			var id: String = loop_ids.get(base_id, base_id)
			if mapped.has(id): return "Duplicate continuation arm."
			if feature_sources.has(id) and feature_sources[id] != arm.source_way: return "Conflicting structural feature source."
			feature_sources[id] = arm.source_way
			mapped[id] = arm
			source_ways[source_key] = true
		for road: Dictionary in roads:
			if not mapped.has(road.id): return "Continuation road mismatch."
			var kind: String = join.kind
			var arm: Dictionary = mapped[road.id]
			var source_arm: Dictionary = expected[arm.source_way + ":" + arm.end]
			if road.get(arm.end) != prefix + "osm-node-" + join.ref or road.get("clearance_cm") != source_arm.clearance_cm: return "Structural direction/clearance mismatch."
			kind = source_arm.kind
			if road.get("kind") != kind: return "Continuation road kind mismatch."
			if kind == "tunnel":
				if not _count(road.get("clearance_cm"), 5000) or road.clearance_cm < 200 or (clearance != null and clearance != road.clearance_cm): return "Joined tunnel clearance mismatch."
				clearance = road.clearance_cm
		if roads.size() > 0 and roads.size() < expected_count: sections[join.ref] = true
		if roads.size() != expected_count and crop is not Dictionary: return "Missing uncropped continuation arms."
	if crop is Dictionary:
		var declared: Variant = crop.vertical.get("connection_sections")
		if declared is not Array or declared.size() != sections.size(): return "Invalid connection sections."
		for ref in declared:
			if ref is not String or ref not in sections: return "Unknown/duplicate connection section."
			sections.erase(ref)
	elif not sections.is_empty(): return "Connection sections require crop provenance."
	LIMITS.over(notes, "osm_structure_arms", total_arms, 200000, "Structural junction arms")
	return ""

static func _loop_feature_ids(raw: Dictionary) -> Dictionary:
	# Loop provenance is independently checked by import_osm_loops. Reuse the
	# same feature mapping for continuation and partial-structure validation.
	var ids := {}
	for patch: Dictionary in raw.patches:
		if patch.field == "roads" and patch.id.ends_with("-loop"):
			ids[patch.id.trim_suffix("-loop")] = patch.id
	return ids

static func _structure_crop(raw: Dictionary, prefix: String, notes: Array = []) -> String:
	var crop: Dictionary = raw.coordinates.osm_crop
	var v: Dictionary = crop.vertical
	var loop_ids := _loop_feature_ids(raw)
	var connection_sections := {}
	for ref: String in v.connection_sections: connection_sections[ref] = true
	var continuation_ways := {}
	if raw.coordinates.has("osm_connections"):
		for join: Dictionary in raw.coordinates.osm_connections.joins:
			for arm: Dictionary in join.retained:
				var feature := int(arm.feature)
				if continuation_ways.has(feature) and continuation_ways[feature] != arm.source_way: return "Conflicting continuation source mapping."
				continuation_ways[feature] = arm.source_way
	if not _soft(notes, "osm_partial_structure_ways", v.get("partial_structure_ways"), 20000, "Partly cropped structure ways") or not _soft(notes, "osm_section_endpoints", v.get("section_endpoints"), 40000, "Structure section endpoints"): return "Invalid partial structure counts."
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
		if continuation_ways.has(int(entry.feature)) and continuation_ways[int(entry.feature)] != entry.source_way: return "Crop/continuation source way mismatch."
		var span: Variant = entry.get("source_range")
		if span is not Array or span.size() != 2 or not _finite(span[0],0,SANITY) or not _finite(span[1],0,SANITY) or span[0] >= span[1]: return "Invalid structural source interval."
		var base_id := prefix + str(int(entry.feature))
		var id: String = loop_ids.get(base_id, base_id)
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
			var connection_section: bool = connection_sections.has(end.ref)
			if connection_section and end.role != "boundary-section": return "Lost continuation requires a section end."
			if end.role == "boundary-section" and not entry.partial and not connection_section: return "Section end requires a partial source way or lost continuation."
			sections += int(end.role == "boundary-section")
	var partial_ways := 0
	for partial: bool in ways.values(): partial_ways += int(partial)
	if sections != v.section_endpoints or v.partial_structure_ways != partial_ways: return "Structure section count mismatch."
	return ""

func patches(store: RefCounted) -> Array:
	var result: Array = value.patches.duplicate(true)
	var metadata := value.duplicate(true)
	metadata.erase("patches")
	if value.adapter == "osm-extract-v1":
		result = preload("./import_units.gd").osm_patches(value.patches,value.coordinates.has("osm_city"),int(store.document.get("terrain_base_cm",0)))
		preload("./import_units.gd").widen_roads(result,store.document.get("buildings",[]),value.coordinates.get("osm_pedestrian_roads",[]))
		var separated: int = preload("./import_units.gd").separate_junctions(result, store)
		metadata.authored_units = {"metres_per_unit": 1, "source_denominator": 8, "profile": "osm-import-1to8-v1", "road_width_floor_cm": preload("./import_units.gd").ROAD_WIDTH_FLOOR_CM}
		if separated > 0: metadata.authored_units.separated_junctions = separated
		if value.coordinates.has("osm_city"): metadata.authored_units.quantization_cleanup = "adjacent-equal-vertices-v1"
		metadata.authored_regions = preload("./import_regions.gd").scaled(value.coordinates.get("generation_regions", []))
	if value.adapter == "osm-extract-v1":
		var extent := empty_map_extent(store.document,result)
		if not extent.is_empty() and extent != store.document.bounds:
			result.append({"field":"bounds","id":"","before":store.document.bounds.duplicate(true),"after":extent})
	var attribution := {"source": value.source.name + "#" + value.layer_id, "license": value.source.license, "notice": JSON.stringify(metadata)}
	result.append({"field": "attributions", "id": store.record_id("attributions", attribution), "before": null, "after": attribution})
	result.append({"field":"free_roam","id":"","before":store.document.free_roam,"after":true})
	return result

# A blank project has no cell payloads to relocate. Fit its first imported
# region before native generation; populated maps retain their authored extent.
static func empty_map_extent(document: Dictionary, incoming: Array) -> Dictionary:
	if document.get("assembled_track") is not Dictionary: return {}
	for field in ["nodes","roads","buildings","placements","heightmaps","zones","surface_areas","water_bodies","pois","gimmicks"]:
		if not document.get(field,[]).is_empty(): return {}
	if not (document.get("assembled_track",{}) if document.get("assembled_track") is Dictionary else {}).get("pieces",[]).is_empty(): return {}
	var points: Array = []
	for patch: Dictionary in incoming:
		var record: Dictionary = patch.after
		match patch.field:
			"nodes": points.append([record.position[0],record.position[2]])
			"pois": points.append(record.position)
			"roads":
				for point: Array in record.points: points.append([point[0],point[2]])
			"buildings": points.append_array(record.footprint)
			"zones", "surface_areas": points.append_array(record.polygon)
	if points.is_empty(): return {}
	var low: Array = points[0].duplicate(); var high: Array = points[0].duplicate()
	for point: Array in points:
		for axis in 2: low[axis] = mini(low[axis],point[axis]); high[axis] = maxi(high[axis],point[axis])
	var size := int(document.cell_size_cm)
	for axis in 2:
		low[axis] = floori(float(low[axis]-1600)/size)*size
		high[axis] = ceili(float(high[axis]+1600)/size)*size
	return {"min":low,"max":high}

func has_structures() -> bool:
	if value.get("adapter") != "osm-extract-v1": return false
	for patch: Dictionary in value.get("patches", []):
		if patch.field == "roads" and patch.after.kind in ["bridge", "tunnel"]: return true
	return false

func requires_generation() -> bool:
	return value.get("coordinates", {}).has("osm_city") or has_structures() or not value.get("coordinates", {}).get("osm_ground_loops", {}).get("retained", []).is_empty()

## Hard bound of the cell list; every affected cell is generated and checked.
func generation_cell_limit() -> int:
	return MAX_CHECK_CELLS

## Above this many cells the check still runs, with a warning.
func generation_cell_warning() -> int:
	return 256 if value.get("coordinates", {}).has("osm_city") else 16

func validate_for(store: RefCounted, context: Dictionary = {}) -> String:
	if value.is_empty(): return "No import candidate."
	if value.adapter == "facility-csv-v1":
		var b: Dictionary = store.document.bounds
		if value.coordinates.csv.options.bounds_cm != [b.min[0],b.min[1],b.max[0],b.max[1]] or value.coordinates.csv.options.source_denominator != preload("./import_units.gd").dem_denominator(store.document): return "CSV map extent/scale changed; import again."
	if value.adapter == "osm-extract-v1":
		var explicit := false
		for patch: Dictionary in value.patches:
			if patch.field == "nodes" and patch.id.contains("-osm-node-"): explicit = true; break
		if explicit and (not value.coordinates.has("osm_ground_loops") or value.coordinates.get("vertical", {}).get("explicit_points", 0) > 0):
			var frame: Dictionary = value.coordinates.get("vertical", {"target_crs":"EPSG:5773 / EGM96 metres", "vertical_zero_m":0})
			var frame_error: String = preload("./import_vertical.gd").frame_error(store.document, frame, value.coordinates)
			if frame_error != "": return frame_error
	var staged: Dictionary = store._candidate_for_patches(patches(store))
	if staged.has("error"): return staged.error
	var result: Dictionary = store._validate(staged.candidate)
	if not result.ok: return store.reason(result)
	if value.adapter == "osm-extract-v1":
		if value.coordinates.has("osm_city"):
			var size := int(result.data.document.cell_size_cm)
			var bounds: Dictionary = result.data.document.bounds
			var columns := ceili(float(bounds.max[0]-bounds.min[0])/size)
			var rows := ceili(float(bounds.max[1]-bounds.min[1])/size)
			if columns * rows > generation_cell_limit(): return "City generation check exceeds 16384 cells; increase cell size or reduce the selected area."
			LIMITS.over(limit_warnings, "generation_cells", columns * rows, generation_cell_warning(), "Cells generated for the city check")
			var cells: Array = []
			for x in range(columns):
				for y in range(rows): cells.append(Vector2i(x,y))
			return preload("./authoring_files.gd").validate(store, result.data.document, {}, cells, context)
		if not value.coordinates.get("osm_ground_loops", {}).get("retained", []).is_empty():
			return _validate_structure_cells(store, result.data.document, context)
		for patch: Dictionary in value.patches:
			if patch.field == "roads" and patch.after.kind in ["bridge", "tunnel"]:
				return _validate_structure_cells(store, result.data.document, context)
	# The UI child also binds nonstructural reviews to immutable file payloads.
	# Keep synchronous API callers and structural generation requirements intact.
	if context.has("scratch"):
		return preload("./authoring_files.gd").validate(store, result.data.document, {}, [], context)
	return ""

func _validate_structure_cells(store: RefCounted, candidate: Dictionary, context: Dictionary = {}) -> String:
	# Document validation alone cannot detect generation-time apron/clearance
	# failures. Generate affected corridors in a disposable native candidate.
	# Bound before cell enumeration; existing authoring payload/native budgets apply.
	var roads: Array = []
	var margin := 0
	for patch: Dictionary in patches(store):
		if patch.field != "roads": continue
		roads.append(patch.after)
		for width in patch.after.widths_cm: margin = maxi(margin, int(width))
	var cells := {}
	var size := int(candidate.cell_size_cm)
	var origin: Array = candidate.bounds.min
	var last := Vector2i(ceili(float(candidate.bounds.max[0]-origin[0])/size)-1, ceili(float(candidate.bounds.max[1]-origin[1])/size)-1)
	for road: Dictionary in roads:
		var low := Vector2i(int(road.points[0][0]), int(road.points[0][2]))
		var high := low
		for point: Array in road.points:
			low.x = mini(low.x,int(point[0])); low.y = mini(low.y,int(point[2]))
			high.x = maxi(high.x,int(point[0])); high.y = maxi(high.y,int(point[2]))
		low = Vector2i(maxi(0, floori(float(low.x-margin-origin[0])/size)), maxi(0, floori(float(low.y-margin-origin[1])/size)))
		high = Vector2i(mini(last.x, floori(float(high.x+margin-origin[0])/size)), mini(last.y, floori(float(high.y+margin-origin[1])/size)))
		if (high.x-low.x+1)*(high.y-low.y+1) > generation_cell_limit(): return "OSM structural generation check exceeds 16384 cells; choose a smaller bbox."
		for x in range(low.x, high.x+1):
			for y in range(low.y, high.y+1):
				cells[Vector2i(x,y)] = true
				if cells.size() > generation_cell_limit(): return "OSM structural generation check exceeds 16384 cells; choose a smaller bbox."
	LIMITS.over(limit_warnings, "generation_cells", cells.size(), generation_cell_warning(), "Cells generated for the structure check")
	return preload("./authoring_files.gd").validate(store, candidate, {}, cells.keys(), context)

func adopt(store: RefCounted) -> String:
	var failure := validate_for(store)
	return failure if failure != "" else store.apply_command("Adopt import " + str(value.source.name), patches(store))

func summary() -> String:
	if value.is_empty(): return I18N.t("No import candidate.")
	var text := preload("./import_review_text.gd")
	var coordinates := {}
	for key in ["osm_city", "osm_review", "csv", "mode", "source_crs", "target_crs", "origin", "local_origin_m", "quantization_cm", "geojson_collections", "geojson_multilines", "osm_ground_loops", "osm_vertical", "osm_crop", "osm_connections", "osm_stream", "overture", "overture_transportation", "overture_land_cover"]:
		if value.coordinates.has(key): coordinates[key] = value.coordinates[key]
	var estimates := ""
	var count := 0
	for key: String in value.estimates:
		if count == 32: break
		estimates += "%s: %d\n" % [text.preview(key, 80), value.estimates[key]]
		count += 1
	var warnings := ""
	# Limit warnings from the adapter come first; ordinary samples follow.
	var ordered: Array = value.warnings.filter(func(w): return str(w).begins_with("Limit warning:")) + value.warnings.filter(func(w): return not str(w).begins_with("Limit warning:"))
	for index in range(mini(50, ordered.size())): warnings += ordered[index] + "\n"
	var limits := LIMITS.text(limit_warnings)
	var result := (limits + "\n\n" if limits != "" else "") + I18N.t("%s · %d bytes\nLicense: %s · source accuracy: %s\nSHA-256: %s\n%d features / %d records · local extent (cm): %s\n") % [value.source.name, value.source.bytes, value.source.license, value.source.accuracy, value.source.sha256, value.feature_count, value.patches.size(), str(value.extent_cm)]
	result += _review_prefix + I18N.t("\nProjection / processing summary:\n") + text.metadata(coordinates)
	if value.adapter == "osm-extract-v1": result += I18N.t("\nOSM adoption: source lengths, widths and heights ÷ 8, rounded to authored centimetres. One authored metre = one game metre. Source provenance above is retained.\n")
	result += I18N.t("\nEstimated fields (counts; showing %d of %d):\n%sWarnings: %d (showing %d of %d retained):\n%s") % [count, value.estimates.size(), estimates, value.warning_count, mini(50, value.warnings.size()), value.warnings.size(), warnings]
	result = result.substr(0, text.MAX_SUMMARY_CHARS - 320)
	return result + I18N.t("\nSummary is limited. Browse exact details for every retained field, mapping, warning and captured source JSON. Adapter warning samples may omit source warnings.\n\nAdopt adds a new layer as one Undo command. Existing objects and source files remain unchanged.")
