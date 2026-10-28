extends RefCounted
## Real-city map recipe (Editor tool format v1). One JSON object drives the same
## Editor steps as File → New real-city map: new free-roam map → OSM city import of
## named PBF areas at 1:D → review → adopt → optional facility CSV → optional
## Copernicus DEM (structure/water fit, grounded buildings) → save → Export
## (optional full 3D check, optional mobile 1.5 GiB open). Paths in a recipe file
## are relative to that file. The Editor's own steps keep every limit and review.
const VERSION := 1
const KEYS := ["version","pbf","areas","scale","cell_cm","traffic","python","facilities","dem","dem_zero_m","project","package","full_check","mobile_check"]
const FACILITY_KEYS := ["csv","license","encoding","name_column","latitude_column","longitude_column","category","source_url","accuracy"]
const ENCODINGS := ["utf-8","cp949","euc-kr"]
const MOBILE_BYTES := 1536 * 1024 * 1024
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
	var areas: Variant = recipe.get("areas")
	if areas is not Array or areas.is_empty(): return _error("Recipe needs areas: [{\"name\": ...}]")
	for area: Variant in areas:
		if area is not Dictionary or str(area.get("name", "")) == "": return _error("Every area needs a name")
	var scale := int(recipe.get("scale", 3))
	if scale < 1 or scale > 8: return _error("Scale must be 1..8 (1:D)")
	var traffic: Variant = recipe.get("traffic", {})
	if traffic is not Dictionary or str(traffic.get("driving_side","right")) not in ["right","left"] or str(traffic.get("signal_style","horizontal")) not in ["horizontal","vertical"]:
		return _error("traffic: driving_side right or left, signal_style horizontal or vertical")
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
	return ui.status_label.text.replace("\n", " | ")

func _fail(step: String) -> Dictionary:
	report.ok = false
	report.failed_step = step
	report.status = _status()
	return report

func _wait(condition: Callable, limit_ms: int) -> void:
	var end := Time.get_ticks_msec() + limit_ms
	# The DEM panel chains jobs; idle must hold for a few frames.
	var idle := 0
	while Time.get_ticks_msec() < end and idle < 30:
		idle = 0 if condition.call() else idle + 1
		await ui.get_tree().process_frame

func _busy() -> bool:
	return ui.busy or ui.store.editing_locked()

func _rejects() -> bool:
	return ui.store.limit_warnings.any(func(e): return e is Dictionary and bool(e.get("runtime_rejects", false)))

## Finds each recipe area by name (and optional source_id / admin_level) in the PBF.
func _areas(recipe: Dictionary) -> Variant:
	var chosen: Array = []
	var panel: RefCounted = ui.osm_panel
	panel.source_path.text = recipe.pbf
	for wanted: Dictionary in recipe.areas:
		var found: Array = []
		panel.search_callback = func(places: Array): found.append_array(places)
		panel.place_query.text = str(wanted.name)
		panel.start_search()
		await _wait(_busy, 1800000)
		panel.search_callback = Callable()
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

func run(recipe: Dictionary) -> Dictionary:
	report = {"ok":false, "recipe_version":VERSION}
	var started := Time.get_ticks_msec()
	ui._ensure_import_ui()
	ui.preview_enabled = false
	ui.preview_due = 0
	if recipe.has("python"): ui.import_python.text = str(recipe.python)
	_say("New free-roam map")
	ui.store.new_track(true)
	await ui.get_tree().process_frame
	var doc: Dictionary = ui.store.document
	ui.store.apply_command("Map extent", [{"field":"cell_size_cm","id":"","before":doc.cell_size_cm,"after":int(recipe.get("cell_cm", 12800))}])
	_say("Finding areas in the PBF")
	var areas: Variant = await _areas(recipe)
	if areas == null: return _fail("areas")
	report.areas = areas.map(func(p): return {"name":p.name, "source_id":p.source_id})
	# OSM city import (File → Import vector → OSM, city optimization, exclusions).
	var panel: RefCounted = ui.osm_panel
	ui.import_source_format.select(1); ui.import_source_format.item_selected.emit(1)
	panel.city.button_pressed = true
	panel.exclusions.button_pressed = true
	panel.scale.value = int(recipe.get("scale", 3))
	var traffic: Dictionary = recipe.get("traffic", {})
	panel.driving_side.select(1 if traffic.get("driving_side") == "left" else 0)
	panel.signal_style.select(1 if traffic.get("signal_style") == "vertical" else 0)
	panel.selected_areas = areas
	panel._fit_areas()
	report.crop = {"bbox":panel.bbox(), "origin":[ui.import_origin_lon.value, ui.import_origin_lat.value], "local_origin_m":[ui.import_origin_x.value, ui.import_origin_y.value]}
	if panel.error() != "": report.error = panel.error(); return _fail("crop")
	_say("Importing OSM (review)")
	ui._start_import(recipe.pbf, ui.IMPORT_LAYER.OSM_LICENSE)
	await _wait(_busy, 3000000)
	if ui.pending_import == null: return _fail("osm_review")
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
		ui._start_import(facilities.csv, str(facilities.license))
		await _wait(_busy, 1800000)
		if ui.pending_import == null: return _fail("facility_review")
		if ui.import_exclusions.visible: ui.import_exclusions.button_pressed = true
		ui._adopt_import()
		await _wait(_busy, 1800000)
		if ui.store.document.get("pois", []).size() <= before or _rejects(): return _fail("facility_adopt")
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
	ui._start_package("export", recipe.package)
	await _wait(_busy, 5400000)
	if not FileAccess.file_exists(recipe.package): return _fail("export")
	var exported: Dictionary = ui.last_export_report
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
