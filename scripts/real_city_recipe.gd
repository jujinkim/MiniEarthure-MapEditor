extends RefCounted
## Real-city map recipe (Editor tool format v1). One JSON object drives the same
## Editor steps as File → New real-city map: new free-roam map → OSM city import at
## 1:D of an explicit WGS84 centre/radius, named PBF areas, one `bbox` rectangle
## or a named `place` centre (`real_city_auto.gd`) → review → adopt → optional facility CSV →
## optional Copernicus DEM (structure/water fit, grounded buildings) → save → Export
## (optional full 3D check, optional mobile 1.5 GiB open). `traffic` keys left out
## follow the country found in the PBF. Paths in a recipe file are relative to that
## file. The Editor's own steps keep every limit and review.
const AUTO := preload("./real_city_auto.gd")
const VERSION := 1
const KEYS := ["version","pbf","areas","bbox","place","center","radius_km","scale","cell_cm","traffic","python","facilities","dem","dem_zero_m","road_overrides","regional","project","package","full_check","mobile_check"]
const FACILITY_KEYS := ["csv","license","encoding","name_column","latitude_column","longitude_column","category","source_url","accuracy"]
const ENCODINGS := ["utf-8","cp949","euc-kr"]
const MOBILE_BYTES := 1536 * 1024 * 1024
const CELL_CM := 12800
var ui: Control
var progress := Callable()
var report := {}

func _init(editor: Control, on_progress := Callable()) -> void:
	ui = editor
	progress = on_progress

## {ok, recipe} or {ok:false, error}; resolves relative paths against `base`.
static func parse(text: String, base := "") -> Dictionary:
	var value: Variant = JSON.parse_string(text)
	if value is not Dictionary: return _error("A recipe is one JSON object")
	var recipe: Dictionary = value
	for key: String in recipe:
		if key not in KEYS: return _error("Unknown recipe key: " + key)
	if int(recipe.get("version", 0)) != VERSION: return _error("Recipe version must be 1")
	for key in ["pbf","project","package"]:
		if str(recipe.get(key, "")) == "": return _error("Recipe needs " + key)
	if int(recipe.has("areas")) + int(recipe.has("bbox")) + int(recipe.has("place")) + int(recipe.has("center")) != 1: return _error("Recipe needs one of center, areas, place or bbox")
	if recipe.has("radius_km") and not (recipe.has("center") or recipe.has("place")): return _error("radius_km needs center or place")
	var radius: Variant = recipe.get("radius_km", 2.0)
	if (radius is not float and radius is not int) or not is_finite(float(radius)) or radius <= 0 or radius > 20: return _error("radius_km must be positive and at most 20")
	if recipe.has("center"):
		var point: Variant = recipe.center
		if point is not Array or point.size() != 2 or point.any(func(v): return (v is not float and v is not int) or not is_finite(float(v))): return _error("center needs [longitude, latitude]")
		if point[0] < -180 or point[0] > 180 or point[1] < -80 or point[1] > 84: return _error("center outside supported projection")
	elif recipe.has("place"):
		var place: Variant = recipe.place
		if place is not Dictionary or place.get("name") is not String or str(place.name).strip_edges() == "" or place.keys().any(func(k): return k not in ["name","source_id"]) or (place.has("source_id") and place.source_id is not String): return _error("place needs a name")
	elif recipe.has("bbox"):
		var box: Variant = recipe.bbox
		if box is not Array or box.size() != 4 or box.any(func(v): return v is not float and v is not int): return _error("bbox: [west, south, east, north] degrees")
		if box[0] < -180 or box[2] > 180 or box[1] < -80 or box[3] > 84 or box[0] >= box[2] or box[1] >= box[3]: return _error("bbox: [west, south, east, north] degrees")
	else:
		var areas: Variant = recipe.areas
		if areas is not Array or areas.is_empty(): return _error("Recipe needs areas: [{\"name\": ...}]")
		for area: Variant in areas:
			if area is not Dictionary or str(area.get("name", "")) == "": return _error("Every area needs a name")
	var scale := int(recipe.get("scale", 3))
	if scale < 1 or scale > 8: return _error("Scale must be 1..8 (1:D)")
	var traffic: Variant = recipe.get("traffic", {})
	if traffic is not Dictionary or traffic.keys().any(func(k): return k not in ["driving_side","signal_style"]) or str(traffic.get("driving_side","right")) not in ["right","left"] or str(traffic.get("signal_style","horizontal")) not in ["horizontal","vertical"]:
		return _error("traffic: driving_side right or left, signal_style horizontal or vertical")
	var overrides: Variant = recipe.get("road_overrides")
	if recipe.has("road_overrides"):
		var override_error: String = preload("./import_city.gd").road_override_error(overrides)
		if override_error != "": return _error(override_error)
	if recipe.has("regional") and (recipe.regional is not Dictionary or recipe.regional.get("version") != 1): return _error("regional requires a v1 input object")
	var facilities: Variant = recipe.get("facilities")
	if facilities != null:
		if facilities is not Dictionary: return _error("facilities is an object")
		for key: String in facilities:
			if key not in FACILITY_KEYS: return _error("Unknown facilities key: " + key)
		for key in ["csv","license","name_column","latitude_column","longitude_column"]:
			if str(facilities.get(key, "")) == "": return _error("facilities needs " + key)
		if str(facilities.get("encoding","utf-8")) not in ENCODINGS: return _error("facilities.encoding: utf-8, cp949 or euc-kr")
	var resolved := recipe.duplicate(true)
	for key in ["pbf","dem","project","package"]:
		if resolved.has(key): resolved[key] = _path(str(resolved[key]), base)
	for key: String in ["worldcover", "buildings"]:
		if resolved.get("regional", {}).has(key):
			if resolved.regional[key] is not Dictionary or resolved.regional[key].get("path") is not String: return _error("regional source needs a local snapshot path")
			resolved.regional[key].path = _path(str(resolved.regional[key].path), base)
	if facilities != null: resolved.facilities.csv = _path(str(facilities.csv), base)
	return {"ok":true, "recipe":resolved}

static func _path(path: String, base: String) -> String:
	if path == "" or path.is_absolute_path() or base == "": return path
	return base.path_join(path).simplify_path()

static func _error(message: String) -> Dictionary:
	return {"ok":false, "error":message}

func _say(text: String) -> void:
	if progress.is_valid(): progress.call(text)

func _status() -> String:
	return ui.status_label.text.replace("\n", " | ") if is_instance_valid(ui) else ""

func _fail(step: String) -> Dictionary:
	report.ok = false
	report.failed_step = step
	report.status = _status()
	return report

func _wait(condition: Callable, limit_ms: int) -> void:
	var end := Time.get_ticks_msec() + limit_ms
	# The DEM panel chains jobs; idle must hold for a few frames.
	var idle := 0
	while (limit_ms <= 0 or Time.get_ticks_msec() < end) and idle < 30:
		idle = 0 if condition.call() else idle + 1
		await ui.get_tree().process_frame

func _busy() -> bool:
	return is_instance_valid(ui) and (ui.busy or ui.store.editing_locked())

func _rejects() -> bool:
	return ui.store.limit_warnings.any(func(e): return e is Dictionary and bool(e.get("runtime_rejects", false)))

## One PBF lookup (pbf_places.py) by name and/or [lon, lat]; {} on failure.
func _search(pbf: String, name: String, point: Array = []) -> Dictionary:
	var panel: RefCounted = ui.osm_panel
	var data := {}  # Filled in place: a lambda captures locals by value.
	panel.source_path.text = pbf
	panel.search_callback = func(value: Dictionary): data.merge(value)
	panel.place_query.text = name
	panel.search_point = point
	panel.start_search()
	await _wait(_busy, 1800000)
	panel.search_callback = Callable()
	return data

## Finds each recipe area by name (and optional source_id / admin_level) in the PBF.
func _areas(recipe: Dictionary) -> Variant:
	var chosen: Array = []
	var panel: RefCounted = ui.osm_panel
	for wanted: Dictionary in recipe.areas:
		var found: Array = (await _search(recipe.pbf, str(wanted.name))).get("places", [])
		var matches: Array = []
		for place: Dictionary in found:
			if str(place.name) != str(wanted.name) or place.issue != "": continue
			if wanted.has("source_id") and str(place.source_id) != str(wanted.source_id): continue
			if wanted.has("admin_level") and str(place.admin_level) != str(wanted.admin_level): continue
			matches.append(place)
		if matches.size() != 1:
			report.area_candidates = found.map(func(p): return {"name":p.name, "source_id":p.source_id, "admin_level":p.admin_level, "issue":p.issue})
			report.error = "Area %s: %d exact matches; add source_id or admin_level from area_candidates" % [wanted.name, matches.size()]
			report.search_status = panel.place_status.text
			return null
		chosen.append(matches[0])
	return chosen

## The named place (anchor) of a `place` recipe: its source_id, else the only
## candidate of the best kind (settlements before landmarks before other features).
func _place(recipe: Dictionary) -> Variant:
	var wanted: Dictionary = recipe.place
	var found: Array = (await _search(recipe.pbf, str(wanted.name).strip_edges())).get("anchors", [])
	var matches: Array = found.filter(func(a): return a.issue == "" and (not wanted.has("source_id") or a.source_id == wanted.source_id))
	if not matches.is_empty():
		var best: int = matches.map(func(a): return int(a.tier)).min()
		matches = matches.filter(func(a): return int(a.tier) == best)
	if matches.size() != 1:
		report.place_candidates = found.map(func(a): return {"name":a.name, "source_id":a.source_id, "kind":a.kind, "point":a.point, "issue":a.issue})
		report.error = "Place %s: %d best matches; add source_id from place_candidates" % [wanted.name, matches.size()]
		report.search_status = ui.osm_panel.place_status.text
		return null
	return matches[0]

func run(recipe: Dictionary) -> Dictionary:
	# Requested coverage is fixed. Limits fail visibly without shrinking it.
	var result: Dictionary = await _run(recipe, 0.0)
	# The `outputs` stop leaves the open document untouched (possibly the user's map).
	if is_instance_valid(ui) and str(result.get("failed_step", "")) != "outputs":
		var document: Dictionary = ui.store.document
		result.inputs = inputs(recipe, document, result.has("dem_skipped"))
		result.source_names = source_names(document)
		result.code = code_identity()
		# A run that stopped before adopting OSM has no extent to tell it apart.
		var digest := fingerprint(result.inputs)
		if digest == "": result.input_fingerprint_reason = "no OSM adopted"
		else:
			result.input_fingerprint = digest
			result.input_id = digest.left(16)
	return result

## Renames the recipe's existing project folder and package to `<path><suffix>`; never
## deletes. The package moves first, so one inside the project folder is renamed too.
## Returns {project?, package?} of the new paths. An existing target moves nothing and
## gives {error}; a failed rename adds {error} to the renames before it.
func _set_aside(recipe: Dictionary, suffix: String) -> Dictionary:
	var moves: Array = []
	for key: String in ["package", "project"]:
		var path := str(recipe[key])
		if path == "" or not (DirAccess.dir_exists_absolute(path) or FileAccess.file_exists(path)): continue
		var target := path.trim_suffix("/") + suffix
		if DirAccess.dir_exists_absolute(target) or FileAccess.file_exists(target): return {"error":"%s at %s" % [key, target]}
		moves.append([key, path, target])
	var kept := {}
	for move: Array in moves:
		if DirAccess.rename_absolute(move[1], move[2]) != OK:
			kept.error = "%s at %s" % [move[0], move[2]]
			break
		kept[move[0]] = move[2]
	# A package inside the project folder now sits under the renamed folder.
	var inside := str(recipe.project).trim_suffix("/") + "/"
	if kept.has("project") and str(kept.get("package", "")).begins_with(inside):
		kept.package = str(kept.project) + "/" + str(kept.package).trim_prefix(inside)
	return kept

## Headless runs only: a failed run's project and package move to `<project>-failed`
## and `<package>-failed` (`.memap-failed`, outside the `*.memap` filter), so no output
## keeps the success name. Records `failed_outputs` and/or `set_aside_error`. An
## `outputs` stop belongs to an earlier run and is left alone; while a job still runs
## (a step that timed out) it could write the success path again, so nothing moves.
## The project folder moves only once this run saved its `document.json` there (the
## `outputs` guard refuses one that was there before), so a folder that already
## existed stays put; one that is or holds a `keep` path (the recipe and report
## files) keeps its path too.
func set_aside_failed(recipe: Dictionary, result: Dictionary, keep: PackedStringArray = []) -> void:
	if result.get("ok", false) or str(result.get("failed_step", "")) == "outputs": return
	if _busy():
		result.set_aside_error = "A job is still running; the outputs keep their paths"
		return
	var outputs := recipe.duplicate()
	var project := str(recipe.project).simplify_path()
	var errors: Array = []
	if not FileAccess.file_exists(project.path_join("document.json")): outputs.project = ""
	elif Array(keep).any(func(path: String) -> bool: return path != "" and (path.simplify_path() == project or path.simplify_path().begins_with(project.trim_suffix("/") + "/"))):
		outputs.project = ""
		errors.append("The project folder holds the recipe or report; it keeps its path")
	var kept := _set_aside(outputs, "-failed")
	if kept.has("error"):
		errors.append("Cannot keep the failed run's " + str(kept.error))
		kept.erase("error")
	if not errors.is_empty(): result.set_aside_error = "; ".join(errors)
	if not kept.is_empty(): result.failed_outputs = kept

## SHA-256 of the canonical `inputs` JSON (sorted keys, full precision); "" without OSM.
static func fingerprint(values: Dictionary) -> String:
	if values.get("osm", []).is_empty(): return ""
	return JSON.stringify(values, "", true, true).sha256_text()

## Stable source-object namespace; worker requests still use fresh nonces.
## Output locations and local tool/source paths do not choose scenery variants.
static func layer_identity(recipe: Dictionary, role: String, source_sha: String) -> String:
	var semantic := recipe.duplicate(true)
	for key in ["pbf","dem","project","package","python","full_check","mobile_check"]: semantic.erase(key)
	for key in ["worldcover","buildings"]:
		if semantic.get("regional", {}).has(key): semantic.regional[key].erase("path")
	if semantic.has("facilities"): semantic.facilities.erase("csv")
	return JSON.stringify({"recipe":semantic,"role":role,"source_sha256":source_sha},"",true,true).sha256_text().left(32)

## The adopted source notices of `document` that parse to a Dictionary with an adapter.
static func _notices(document: Dictionary) -> Array:
	var result: Array = []
	var json := JSON.new()  # Quiet: hand-written notices need not be JSON.
	for attribution: Variant in document.get("attributions", []):
		if attribution is not Dictionary or attribution.get("notice") is not String or json.parse(attribution.notice) != OK: continue
		var notice: Variant = json.data
		if notice is Dictionary and notice.get("adapter") is String: result.append(notice)
	return result

## [{role, name, bytes, sha256}] of the adopted OSM PBF, facility CSV and DEM tiles.
static func _sources(notices: Array) -> Array:
	var result: Array = []
	for notice: Dictionary in notices:
		var role: String = {"osm-extract-v1":"osm", "facility-csv-v1":"facilities"}.get(notice.adapter, "")
		var files: Array = []
		if role != "": files = [notice.get("source")]
		elif notice.adapter == "copernicus-dem-v1":
			role = "dem"
			var receipt: Variant = notice.get("dem", {}).get("receipt", {}) if notice.get("dem") is Dictionary else {}
			var tiles: Variant = receipt.get("sources", []) if receipt is Dictionary else []
			if tiles is Array: files = tiles.map(func(t): return t.get("source") if t is Dictionary else null)
		for file: Variant in files:
			if file is Dictionary: result.append({"role":role, "name":str(file.get("name", "")), "bytes":int(file.get("bytes", 0)), "sha256":str(file.get("sha256", ""))})
	result.sort_custom(func(a, b): return [a.role, a.sha256, a.name] < [b.role, b.sha256, b.name])
	return result

## What the run built from: adopted source bytes and hashes, the OSM crop and scale,
## cell size, traffic, facility and DEM settings. Paths, file names and the check-only
## keys (full_check, mobile_check) are left out, so the same bytes and settings give
## the same `inputs` wherever the files live. Attribution order does not matter.
static func inputs(recipe: Dictionary, document: Dictionary, dem_skipped: bool) -> Dictionary:
	var notices := _notices(document)
	var osm: Array = []
	for notice: Dictionary in notices:
		if notice.adapter != "osm-extract-v1": continue
		var coordinates: Dictionary = notice.get("coordinates", {}) if notice.get("coordinates") is Dictionary else {}
		var crop: Dictionary = coordinates.get("osm_crop", {}) if coordinates.get("osm_crop") is Dictionary else {}
		var areas: Array = crop.get("areas", []).map(func(a): return str(a.get("source_id", "")) if a is Dictionary else "") if crop.get("areas") is Array else []
		areas.sort()
		var units: Dictionary = notice.get("authored_units", {}) if notice.get("authored_units") is Dictionary else {}
		var city: Variant = coordinates.get("osm_city")
		var block := {"crop":{"bbox":crop.get("bbox", []), "areas":areas, "center":crop.get("center", []), "radius_km":crop.get("radius_km", 0), "shapely":crop.get("shapely", ""), "geos":crop.get("geos", "")},
			"scale_denominator":int(city.get("scale_denominator", 0)) if city is Dictionary else int(units.get("source_denominator", 0)),
			"units_profile":units.get("profile", "")}
		for key in ["pyproj", "proj"]:
			if coordinates.has(key): block[key] = coordinates[key]
		if coordinates.has("road_overrides"): block.road_overrides = coordinates.road_overrides.request
		if coordinates.has("regional"): block.regional = coordinates.regional.request
		osm.append(block)
	osm.sort_custom(func(a, b): return JSON.stringify(a, "", true) < JSON.stringify(b, "", true))
	var traffic: Variant = document.get("traffic")
	var result := {"recipe_version":VERSION, "sources":_sources(notices).map(func(s): return {"role":s.role, "bytes":s.bytes, "sha256":s.sha256}), "osm":osm,
		"cell_size_cm":int(document.get("cell_size_cm", 0)),
		"traffic":{"driving_side":traffic.get("driving_side", ""), "signal_style":traffic.get("signal_style", "")} if traffic is Dictionary else {}}
	var facilities: Variant = recipe.get("facilities")
	if facilities is Dictionary:
		var settings := {"encoding":"utf-8", "category":"", "source_url":"", "accuracy":"unknown"}
		settings.merge(facilities, true)
		settings.erase("csv")
		result.facilities = settings
	# The same condition as the DEM step in _run(): an empty `dem` builds no terrain.
	if str(recipe.get("dem", "")) != "": result.dem = {"zero_m":float(recipe.get("dem_zero_m", 0)), "skipped":dem_skipped}
	return result

## Display names of the fingerprinted sources, in `inputs.sources` order; not hashed.
static func source_names(document: Dictionary) -> Array:
	return _sources(_notices(document)).map(func(s): return {"role":s.role, "name":s.name, "sha256":s.sha256})

static var _code := {}

## Which code ran, apart from the input fingerprint. `editor_scripts` hashes
## res://scripts/*.{gd,py} and res://scripts/importers/*.py with the framing of the root
## scripts/implementation_fingerprint.py. An exported build (script_export_mode 2)
## holds tokenized scripts/*.gdc instead of .gd; those bytes are hashed as they are,
## so its digest differs from a source checkout. `mapkit` is the loaded MapKit
## library's build fingerprint (its Rust sources, schemas and Cargo files), empty
## with a `mapkit_reason` when MapKitBridge is not registered or the library has
## none. Python packages are not
## covered. A file that cannot be read leaves `editor_scripts` empty with an
## `editor_scripts_reason`.
static func code_identity() -> Dictionary:
	if not _code.is_empty(): return _code.duplicate()
	var files: Array = []
	var unreadable := ""
	for folder: Array in [["scripts", ["gd", "gdc", "py"]], ["scripts/importers", ["py"]]]:
		for file: String in DirAccess.get_files_at("res://" + folder[0]):
			if file.get_extension() not in folder[1]: continue
			var name: String = folder[0] + "/" + file
			var bytes := FileAccess.get_file_as_bytes("res://" + name)
			if FileAccess.get_open_error() != OK and unreadable == "": unreadable = name
			# Tokenized .gdc is binary: only text gets CRLF → LF.
			files.append([name, bytes if file.get_extension() == "gdc" else _lf(bytes)])
	_code = {"editor_scripts":digest_files(files), "godot":Engine.get_version_info().string, "mapkit":""}
	# A library built before the getter would stop the run with a script error.
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	if bridge == null: _code.mapkit_reason = "MapKitBridge is not registered"
	elif not bridge.has_method("build_fingerprint"): _code.mapkit_reason = "the loaded MapKit library has no build_fingerprint"
	else: _code.mapkit = str(bridge.build_fingerprint())
	if unreadable != "":
		_code.editor_scripts = ""
		_code.editor_scripts_reason = "cannot read " + unreadable
	return _code.duplicate()

## SHA-256 over [[relative name, bytes], ...] with the framing of the root
## scripts/implementation_fingerprint.py: sorted names, then for name and content
## an 8-byte little-endian length and the bytes. Bytes are hashed as given.
static func digest_files(files: Array) -> String:
	var sorted := files.duplicate()
	sorted.sort_custom(func(a, b): return str(a[0]) < str(b[0]))
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	for file: Array in sorted:
		for value: PackedByteArray in [str(file[0]).to_utf8_buffer(), file[1]]:
			var length := PackedByteArray()
			length.resize(8)
			length.encode_u64(0, value.size())
			hashing.update(length)
			# HashingContext refuses an empty chunk; hashlib treats one as a no-op.
			if value.size() > 0: hashing.update(value)
	return hashing.finish().hex_encode()

## Execute one fixed-coverage recipe; limits never reduce requested coverage.
func _run(recipe: Dictionary, _side_m: float) -> Dictionary:
	report = {"ok":false, "recipe_version":VERSION}
	var started := Time.get_ticks_msec()
	# Never build over earlier output: Save and Export keep existing files.
	if FileAccess.file_exists(recipe.package) or FileAccess.file_exists(str(recipe.project).path_join("document.json")):
		report.error = "The project or package already exists; choose new paths"
		return _fail("outputs")
	ui._ensure_import_ui()
	ui.preview_enabled = false
	ui.preview_due = 0
	if recipe.has("python"): ui.import_python.text = str(recipe.python)
	_say("New free-roam map")
	ui.store.new_track(true)
	await ui.get_tree().process_frame
	var doc: Dictionary = ui.store.document
	ui.store.apply_command("Map extent", [{"field":"cell_size_cm","id":"","before":doc.cell_size_cm,"after":int(recipe.get("cell_cm", CELL_CM))}])
	var areas: Variant = []
	var bbox: Array = recipe.get("bbox", [])
	var circle: Dictionary = {}
	if recipe.has("center"):
		circle = AUTO.circle(recipe.center, float(recipe.get("radius_km", 2.0)), int(recipe.get("scale", 3)), int(ui.store.document.cell_size_cm))
		bbox = circle.bbox
		report.extent = circle.duplicate(true)
	var country: Variant = {}
	var scale := int(recipe.get("scale", 3))
	if recipe.has("areas"):
		_say("Finding areas in the PBF")
		areas = await _areas(recipe)
		if areas == null: return _fail("areas")
		report.areas = areas.map(func(p): return {"name":p.name, "source_id":p.source_id})
		country = areas[0].get("context", {}).get("country", {})
	elif recipe.has("place"):
		_say("Finding the place in the PBF")
		var place: Variant = await _place(recipe)
		if place == null: return _fail("place")
		report.place = {"name":place.name, "source_id":place.source_id, "kind":place.kind, "point":place.point}
		circle = AUTO.circle(place.point, float(recipe.get("radius_km", 2.0)), scale, int(ui.store.document.cell_size_cm))
		report.extent = circle.duplicate(true)
		report.extent.text = AUTO.describe(circle)
		bbox = circle.bbox
		country = place.context.country
	elif recipe.get("traffic", {}).size() < 2:
		_say("Finding the country in the PBF")
		country = (await _search(recipe.pbf, "", [(bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5])).get("point_context", {}).get("country", {})
	if not recipe.has("areas"): report.bbox = bbox
	var traffic: Dictionary = AUTO.traffic(country)
	traffic.merge(recipe.get("traffic", {}), true)
	if recipe.get("traffic", {}).size() == 2: traffic.basis = "recipe"
	report.traffic = traffic
	# OSM city import (File → Import vector → OSM, city optimization, exclusions).
	var panel: RefCounted = ui.osm_panel
	ui.import_source_format.select(1); ui.import_source_format.item_selected.emit(1)
	panel.city.button_pressed = true
	panel.exclusions.button_pressed = true
	panel.scale.value = scale
	panel.driving_side.select(1 if traffic.get("driving_side") == "left" else 0)
	panel.signal_style.select(1 if traffic.get("signal_style") == "vertical" else 0)
	panel.selected_areas = areas
	if areas.is_empty(): panel.fit_bbox(bbox)
	else: panel._fit_areas()
	panel.circle = circle
	report.crop = {"bbox":panel.bbox(), "origin":[ui.import_origin_lon.value, ui.import_origin_lat.value], "local_origin_m":[ui.import_origin_x.value, ui.import_origin_y.value]}
	if panel.error() != "": report.error = panel.error(); return _fail("crop")
	_say("Importing OSM (review)")
	panel.road_overrides = recipe.get("road_overrides", {}).duplicate(true)
	panel.regional = recipe.get("regional", {}).duplicate(true)
	var osm_identity := layer_identity(recipe,"osm",FileAccess.get_sha256(recipe.pbf))
	ui.store.apply_command("Recipe identity",[{"field":"map_id","id":"","before":ui.store.document.map_id,"after":"city-"+osm_identity}])
	ui._start_import(recipe.pbf, ui.IMPORT_LAYER.OSM_LICENSE,osm_identity)
	panel.road_overrides = {}
	panel.regional = {}
	# Source workers own completion, failure and cancellation. Large local PBFs
	# have no elapsed-time limit, just as in interactive import.
	await _wait(_busy, 0)
	if ui.pending_import == null: return _fail("osm_review")
	report.osm_review = ui.pending_import.value.coordinates.get("osm_review", {}).duplicate(true)
	report.water_crossings = ui.pending_import.value.coordinates.get("osm_city", {}).get("water_crossing_evidence", []).duplicate(true)
	report.road_footprint_corrections = ui.pending_import.value.coordinates.get("osm_city", {}).get("road_footprint_corrections", []).duplicate(true)
	report.osm_regional = ui.pending_import.value.coordinates.get("regional",{}).duplicate(true)
	if ui.import_exclusions.visible: ui.import_exclusions.button_pressed = true
	_say("Applying OSM")
	ui._adopt_import()
	await _wait(_busy, 1500000)
	if ui.store.document.roads.is_empty() or _rejects(): return _fail("osm_adopt")
	report.roads = ui.store.document.roads.size()
	report.buildings = ui.store.document.buildings.size()
	var facilities: Variant = recipe.get("facilities")
	if facilities is Dictionary:
		_say("Importing facility CSV")
		var before: int = ui.store.document.get("pois", []).size()
		ui.import_source_format.select(6); ui.import_source_format.item_selected.emit(6)
		ui.csv_panel.use_imported_frame()
		ui.csv_panel.encoding.select(ENCODINGS.find(str(facilities.get("encoding", "utf-8"))))
		ui.csv_panel.crop.button_pressed = true
		for key: String in ["name_column","latitude_column","longitude_column","category","source_url"]:
			ui.csv_panel.fields[key].text = str(facilities.get(key, ""))
		ui.import_accuracy.text = str(facilities.get("accuracy", "unknown"))
		ui._start_import(facilities.csv, str(facilities.license),layer_identity(recipe,"facilities",FileAccess.get_sha256(facilities.csv)))
		await _wait(_busy, 1800000)
		if ui.pending_import == null: return _fail("facility_review")
		if ui.import_exclusions.visible: ui.import_exclusions.button_pressed = true
		ui._adopt_import()
		await _wait(_busy, 1800000)
		if ui.store.document.get("pois", []).size() <= before or _rejects(): return _fail("facility_adopt")
	if recipe.has("regional"):
		_say("Composing regional sources")
		var saved: String = ui.store.save_project(recipe.project)
		if saved != "": report.error = saved; return _fail("regional_save")
		var job := preload("./generation_native_job.gd").new()
		var failure: String = job.start_generation(ui.store,{"mode":"fill","regional":recipe.regional},ui.import_python_path())
		if failure != "": report.error = failure; job.cleanup(); return _fail("regional_start")
		var owner_generation: int = ui.generation
		var tree: SceneTree = ui.get_tree()
		var store: RefCounted = ui.store
		ui.regional_recipe_job = job
		ui.busy = true
		store.set_external_lock(true)
		while not job.done or not job.exited:
			if not is_instance_valid(ui) or not ui.is_inside_tree() or ui.generation != owner_generation or not job.matches(store): job.cancel()
			job.poll()
			await tree.process_frame
		store.set_external_lock(false)
		if not is_instance_valid(ui) or not ui.is_inside_tree():
			job.cleanup()
			return {"ok":false,"failed_step":"regional_owner_closed"}
		ui.regional_recipe_job = null
		ui.busy = false
		if not job.result.get("ok",false) or job.bundle.is_empty():
			report.error = job.result.get("error",job.result.get("data", {}).get("error",{}))
			job.cleanup()
			return _fail("regional_review")
		report.regional = job.bundle.report.diagnostics.regional
		failure = job.commit(ui.store)
		job.cleanup()
		if failure != "": report.error = failure; return _fail("regional_apply")
	if str(recipe.get("dem", "")) != "":
		# The DEM panel copies reviewed tiles into the saved project.
		var saved: String = ui.store.save_project(recipe.project)
		if saved != "": report.error = saved; return _fail("dem_save")
		var dem: ConfirmationDialog = ui.dem_panel
		dem.mosaic.button_pressed = true
		dem.source.text = recipe.dem
		dem.use_imported_frame()
		dem.fields["EGM2008 at local zero (m)"].value = float(recipe.get("dem_zero_m", 0))
		dem.ground_buildings.button_pressed = true
		_say("Planning DEM cells")
		dem.prepare()
		await _wait(_busy, 600000)
		if dem.plan.is_empty(): return _fail("dem_plan")
		_say("Sampling DEM (review)")
		dem.acquire()
		await _wait(_busy, 1800000)
		if dem.candidate == null: return _fail("dem_review")
		_say("Applying DEM")
		dem.adopt()
		await _wait(_busy, 1800000)
		if ui.store.document.heightmaps.is_empty() or _rejects(): return _fail("dem_adopt")
		report.heightmaps = ui.store.document.heightmaps.size()
	_say("Saving project")
	ui._start_save(recipe.project)
	await _wait(_busy, 1800000)
	if ui.store.project_path != recipe.project or ui.store.dirty: return _fail("save")
	DirAccess.make_dir_recursive_absolute(str(recipe.package).get_base_dir())
	ui.full_generation.button_pressed = bool(recipe.get("full_check", true))
	_say("Exporting map")
	ui.last_export_report = {}
	ui._start_package("export", recipe.package)
	await _wait(_busy, 5400000)
	var exported: Dictionary = ui.last_export_report
	if not FileAccess.file_exists(recipe.package) or int(exported.get("cell_count", 0)) <= 0: return _fail("export")
	report.cells = int(exported.get("cell_count", 0))
	report.full_check_cells = int(exported.get("full_generation_cells", 0))
	report.package_sha256 = FileAccess.get_sha256(recipe.package)
	if exported.get("limit_warnings", []).any(func(e): return e is Dictionary and bool(e.get("runtime_rejects", false))): return _fail("export_limits")
	if bool(recipe.get("mobile_check", false)):
		_say("Mobile 1.5 GiB open")
		var probe: RefCounted = ClassDB.instantiate("MapKitBridge")
		var opened: Dictionary = JSON.parse_string(probe.open_package_bytes_budgeted(FileAccess.get_file_as_bytes(recipe.package), MOBILE_BYTES))
		report.mobile_open = bool(opened.get("ok", false))
		if not report.mobile_open: report.error = JSON.stringify(opened.get("error")); return _fail("mobile_check")
	report.ok = true
	report.seconds = (Time.get_ticks_msec() - started) / 1000.0
	report.status = _status()
	return report

## The bytes with every CR LF pair turned into LF.
static func _lf(bytes: PackedByteArray) -> PackedByteArray:
	if not bytes.has(13): return bytes
	var result := PackedByteArray()
	for i in bytes.size():
		if bytes[i] != 13 or i + 1 >= bytes.size() or bytes[i + 1] != 10: result.append(bytes[i])
	return result
