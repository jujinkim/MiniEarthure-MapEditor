extends ConfirmationDialog
## File → New real-city map. Pick a location (web search, a pin on the map or typed
## coordinates), a circle or square of up to 2.5 km and where the data comes from:
##
## - Download automatically: OpenStreetMap through Overpass and Copernicus GLO-30
##   tiles are saved as immutable local snapshots (`acquire_city_sources.py`).
## - Local files: the user's own PBF (with the offline name search in that PBF)
##   and optional Copernicus tile folder.
##
## Both paths pass the same coverage check (`preflight`) and then build through
## the real-city recipe (scripts/real_city_recipe.gd), exactly like the headless
## `-- --real-city-recipe recipe.json` run. Save recipe… writes that recipe.
const I18N := preload("./locale_text.gd")
const RECIPE := preload("./real_city_recipe.gd")
const AUTO := preload("./real_city_auto.gd")
const CATALOG := preload("res://addons/mapkit/godot/regional_catalog.json")
const JOB := preload("./city_source_job.gd")
const MAP := preload("./slippy_map.gd")
const SOURCE_CACHE := "user://city-sources"
const SIZE := Vector2i(1200, 760)
const STYLE := preload("./workbench_style.gd")
const SOURCES_NOTICE := "Downloads OpenStreetMap through Overpass (ODbL), place search by Nominatim and Copernicus GLO-30 terrain. Credits stay in the map; sharing a map built from OpenStreetMap carries ODbL attribution and share-alike duties."
var ui: Control
var map: Control
var query: LineEdit
var matches: ItemList
## Search results as listed in `matches`: {kind: "web"|"area"|"place", value}.
var entries: Array = []
var source_mode: OptionButton
var local_box: Container
var auto_box: Container
var pbf: LineEdit
var latitude: SpinBox
var longitude: SpinBox
var shape: OptionButton
var radius: SpinBox
var guidance: Label
var terrain: CheckBox
var agree: CheckBox
var scale: SpinBox
var driving_side: OptionButton
var signal_style: OptionButton
## Automatic (the country's), plain city buildings without a regional profile, or
## one catalogue architecture (CATALOG architectures in order, from item 2).
var architecture: OptionButton
var dem: LineEdit
var project: LineEdit
var package: LineEdit
var full_check: CheckBox
var mobile_check: CheckBox
var progress: ProgressBar
var status: Label
var picker: FileDialog
var pick_target: LineEdit
## The running source job and what to do with its result.
var job: RefCounted
var _then := Callable()
## Country of the chosen web result or downloaded snapshot (traffic defaults).
var country := {}
var _outputs_edited := false
var _syncing := false

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	title = I18N.t("New real-city map")
	ok_button_text = I18N.t("Build map")
	dialog_hide_on_ok = false
	var split := HBoxContainer.new()
	split.add_theme_constant_override("separation", 12)
	add_child(split)
	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.add_child(left)
	var search_row := HBoxContainer.new()
	left.add_child(search_row)
	query = LineEdit.new()
	query.placeholder_text = I18N.t("Search a place, address or landmark")
	query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	query.text_submitted.connect(func(_text): _search())
	search_row.add_child(query)
	ui._button(search_row, "Search", _search)
	matches = ItemList.new()
	matches.select_mode = ItemList.SELECT_MULTI
	matches.custom_minimum_size.y = 96
	matches.multi_selected.connect(_selected)
	left.add_child(matches)
	map = MAP.new()
	map.size_flags_vertical = Control.SIZE_EXPAND_FILL
	map.custom_minimum_size = Vector2(560, 400)
	map.pin_changed.connect(_pinned)
	left.add_child(map)
	# A wrapping label in this column would size the dialog for a zero width.
	var hint: Label = ui._label(left, "Click the map to place the centre; drag to pan, scroll to zoom.")
	hint.autowrap_mode = TextServer.AUTOWRAP_OFF
	hint.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	hint.clip_text = true
	# Settings scroll so the dialog (and the map centre) stays on screen.
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(560, 0)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	split.add_child(scroll)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(right)
	_heading(right, "Extent")
	var coordinates := GridContainer.new()
	coordinates.columns = 4
	right.add_child(coordinates)
	latitude = _number(coordinates, "Latitude", -80, 84, 0.000001, 37.5)
	longitude = _number(coordinates, "Longitude", -180, 180, 0.000001, 127.0)
	ui._label(coordinates, "Shape")
	shape = OptionButton.new()
	for label in ["Circle", "Square"]: shape.add_item(I18N.t(label))
	shape.item_selected.connect(func(_index): _extent_changed())
	coordinates.add_child(shape)
	radius = _number(coordinates, "Radius / half side (km)", 0.1, AUTO.MAX_RADIUS_KM, 0.05, 2.0)
	guidance = ui._label(right, "")
	guidance.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_heading(right, "Data")
	source_mode = OptionButton.new()
	for label in ["Download automatically (OpenStreetMap, Copernicus)", "Use local files"]: source_mode.add_item(I18N.t(label))
	source_mode.item_selected.connect(func(_index): _mode_changed())
	right.add_child(source_mode)
	auto_box = VBoxContainer.new()
	right.add_child(auto_box)
	var notice: Label = ui._label(auto_box, SOURCES_NOTICE)
	notice.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	agree = CheckBox.new()
	agree.text = I18N.t("Use these sources under their licences")
	auto_box.add_child(agree)
	STYLE.decorate(ui._button(auto_box, "Open source cache folder", func(): OS.shell_open(_cache())), "Open source cache folder", "", "open")
	local_box = VBoxContainer.new()
	right.add_child(local_box)
	var local_grid := GridContainer.new()
	local_grid.columns = 3
	local_box.add_child(local_grid)
	pbf = _path_row(local_grid, "OSM PBF file", "*.pbf", FileDialog.FILE_MODE_OPEN_FILE)
	dem = _path_row(local_grid, "Copernicus DEM folder (optional)", "", FileDialog.FILE_MODE_OPEN_DIR)
	ui._button(local_box, "Find areas in this PBF", _find)
	terrain = CheckBox.new()
	terrain.text = I18N.t("Terrain from Copernicus DEM")
	terrain.button_pressed = true
	right.add_child(terrain)
	_heading(right, "Map")
	var options := GridContainer.new()
	options.columns = 4
	right.add_child(options)
	ui._label(options, "Scale 1:")
	scale = SpinBox.new()
	scale.min_value = 1; scale.max_value = 8; scale.value = 3
	scale.value_changed.connect(func(_value): _describe())
	options.add_child(scale)
	driving_side = OptionButton.new()
	for label in ["Automatic traffic", "Right-hand traffic", "Left-hand traffic"]: driving_side.add_item(I18N.t(label))
	driving_side.item_selected.connect(func(_index): _describe())
	options.add_child(driving_side)
	signal_style = OptionButton.new()
	for label in ["Automatic signals", "Horizontal signals", "Vertical signals"]: signal_style.add_item(I18N.t(label))
	signal_style.item_selected.connect(func(_index): _describe())
	options.add_child(signal_style)
	ui._label(options, "Architecture")
	architecture = OptionButton.new()
	for label in ["Automatic architecture", "Plain city buildings"]: architecture.add_item(I18N.t(label))
	for id: String in CATALOG.data.architectures: architecture.add_item(I18N.builtin(id))
	architecture.item_selected.connect(func(_index): _describe())
	options.add_child(architecture)
	var outputs := GridContainer.new()
	outputs.columns = 3
	right.add_child(outputs)
	project = _path_row(outputs, "Project folder", "", FileDialog.FILE_MODE_OPEN_DIR)
	package = _path_row(outputs, "Exported map (.memap)", "*.memap", FileDialog.FILE_MODE_SAVE_FILE)
	for edit: LineEdit in [project, package]: edit.text_changed.connect(func(_text): if not _syncing: _outputs_edited = true)
	full_check = CheckBox.new()
	full_check.text = I18N.t("Full 3D check of every cell")
	full_check.button_pressed = true
	right.add_child(full_check)
	mobile_check = CheckBox.new()
	mobile_check.text = I18N.t("Check that phones can open it (1.5 GiB)")
	right.add_child(mobile_check)
	progress = ProgressBar.new()
	progress.visible = false
	right.add_child(progress)
	status = ui._label(right, "Search a place or click the map, then choose the extent.")
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	# A plain dialog button like OK/Cancel: the Editor's icon styling would clip it.
	add_button(I18N.t("Save recipe…"), false, "save_recipe").set_meta("action_label", "Save recipe…")
	custom_action.connect(_custom)
	confirmed.connect(_build)
	canceled.connect(_stop)
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_selected.connect(_picked)
	picker.dir_selected.connect(_picked)
	add_child(picker)
	_mode_changed()
	_extent_changed()

func _heading(parent: Node, text: String) -> void:
	var label: Label = ui._label(parent, text)
	label.add_theme_font_size_override("font_size", 15)

func _number(grid: GridContainer, label: String, low: float, high: float, step: float, value: float) -> SpinBox:
	ui._label(grid, label)
	var control := SpinBox.new()
	control.min_value = low; control.max_value = high; control.step = step; control.value = value
	control.custom_minimum_size.x = 150
	control.value_changed.connect(func(_value): if status != null and not _syncing: _extent_changed())
	grid.add_child(control)
	return control

func _path_row(grid: GridContainer, label: String, filter: String, mode: int) -> LineEdit:
	ui._label(grid, label)
	var edit := LineEdit.new()
	edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	edit.custom_minimum_size.x = 300
	grid.add_child(edit)
	STYLE.decorate(ui._button(grid, "Choose…", _pick.bind(edit, filter, mode)), "Choose…", "", "open")
	return edit

func _pick(target: LineEdit, filter: String, mode: int) -> void:
	pick_target = target
	picker.file_mode = mode
	picker.filters = PackedStringArray([filter]) if filter != "" else PackedStringArray()
	picker.popup_centered_ratio(0.7)

func _picked(path: String) -> void:
	if pick_target != null:
		pick_target.text = path
		if pick_target in [project, package]: _outputs_edited = true
		return
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		status.text = I18N.t("Could not write %s") % path
		return
	file.store_string(JSON.stringify(recipe(), "  "))
	status.text = I18N.t("Recipe saved: %s") % path

func _custom(action: StringName) -> void:
	if action != "save_recipe" or job != null: return
	if downloading():
		# A saved recipe names local snapshots: acquire them first.
		_acquire(func(): _pick(null, "*.json;Recipe JSON", FileDialog.FILE_MODE_SAVE_FILE))
	else: _pick(null, "*.json;Recipe JSON", FileDialog.FILE_MODE_SAVE_FILE)

func open() -> void:
	if ui.busy: return
	if pbf.text == "" and ui.last_import_source.get_extension() == "pbf": pbf.text = ui.last_import_source
	popup_centered(SIZE)
	if map.pin.is_finite(): map.fit_extent()

func downloading() -> bool:
	return source_mode.selected == 0

func _mode_changed() -> void:
	auto_box.visible = downloading()
	local_box.visible = not downloading()
	_describe()

# Location -------------------------------------------------------------------

func _search() -> void:
	var text := query.text.strip_edges()
	if text == "" or job != null: return
	if not downloading():
		_find()
		return
	var language := TranslationServer.get_locale().left(2)
	_run("search", PackedStringArray(["--query", text, "--language", language, "--cache", _cache()]), _web_found, "Searching…")

func _web_found(data: Dictionary) -> void:
	entries = data.get("results", []).filter(func(r): return r.get("supported", false)).map(func(r): return {"kind":"web", "value":r})
	matches.clear()
	for entry: Dictionary in entries:
		var item: Dictionary = entry.value
		matches.add_item("%s · %s" % [item.display_name, item.kind])
	if entries.is_empty(): status.text = I18N.t("No matching place. Try another name or click the map.")
	else:
		matches.select(0)
		_selected(0, true)
		status.text = I18N.t("Search by Nominatim · © OpenStreetMap contributors")

## Offline lookup inside the chosen PBF (areas and named places).
func _find() -> void:
	if ui.busy or pbf.text == "" or query.text.strip_edges() == "": return
	ui._ensure_import_ui()
	var panel: RefCounted = ui.osm_panel
	panel.source_path.text = pbf.text
	panel.place_query.text = query.text.strip_edges()
	panel.search_callback = _found
	hide()
	panel.start_search()

func _found(data: Dictionary) -> void:
	ui.osm_panel.search_callback = Callable()
	entries = data.get("places", []).filter(func(p): return p.issue == "").map(func(p): return {"kind":"area", "value":p})
	entries.append_array(data.get("anchors", []).filter(func(a): return a.issue == "").map(func(a): return {"kind":"place", "value":a}))
	matches.clear()
	for entry: Dictionary in entries:
		var item: Dictionary = entry.value
		if entry.kind == "area": matches.add_item("%s · admin %s · %s" % [item.name, item.admin_level, item.source_id])
		else: matches.add_item("◆ %s · %s · %s" % [item.name, item.kind, _within(item)])
	if not entries.is_empty():
		matches.select(0)
		_selected(0, true)
	_describe()
	if entries.is_empty(): status.text = I18N.t("No matching area or place. Try its local name.")
	popup_centered(SIZE)

## "Chuo, Osaka" for a named place: its two smallest containing areas.
func _within(anchor: Dictionary) -> String:
	var names: Array = anchor.context.areas.map(func(a): return str(a.name)).filter(func(n): return n != "")
	names.reverse()
	return ", ".join(names.slice(0, 2)) if not names.is_empty() else str(anchor.source_id)

## One search result fills the centre coordinates.
func _selected(index: int, selected: bool) -> void:
	if selected:
		for other in matches.get_selected_items():
			if other != index: matches.deselect(other)
		var entry: Dictionary = entries[index]
		var item: Dictionary = entry.value
		var point: Array = item.get("point", [])
		if point.is_empty(): point = [(item.bbox[0] + item.bbox[2]) * .5, (item.bbox[1] + item.bbox[3]) * .5]
		country = {"code":item.country, "basis":"search"} if entry.kind == "web" and str(item.get("country", "")) != "" else item.get("context", {}).get("country", {})
		_set_centre(float(point[0]), float(point[1]))
		map.fit_extent()
		_suggest_outputs(str(item.get("name", "")))

func _pinned(point: Vector2) -> void:
	matches.deselect_all()
	country = {}
	# A click is as precise as the map view (float32 is about 0.5 m); typed or
	# searched centres keep full precision.
	_set_centre(snappedf(point.x, 0.000001), snappedf(point.y, 0.000001))
	_suggest_outputs("")

func _set_centre(lon: float, lat: float) -> void:
	_syncing = true
	longitude.value = lon
	latitude.value = lat
	_syncing = false
	_extent_changed()

func _extent_changed() -> void:
	var point := Vector2(longitude.value, latitude.value)
	map.set_extent(radius.value, "square" if shape.selected == 1 else "circle")
	map.set_pin(point)
	if not map.get_rect().has_point(map.to_screen(point) + map.position): map.show_point(point)
	_describe()

## Default project and package under Documents/MiniEarthure maps until edited.
func _suggest_outputs(name: String) -> void:
	if _outputs_edited: return
	var slug := name.strip_edges().to_lower().replace(" ", "-").validate_filename()
	if slug == "": slug = "city-%.4f-%.4f" % [latitude.value, longitude.value]
	var stamp := Time.get_datetime_string_from_system(false, false).replace(":", "").replace("-", "").replace("T", "-")
	var root := OS.get_system_dir(OS.SYSTEM_DIR_DOCUMENTS).path_join("MiniEarthure maps").path_join("%s-%s" % [slug, stamp])
	_syncing = true
	project.text = root.path_join("project")
	package.text = root.path_join(slug + ".memap")
	_syncing = false

func _chosen() -> Array:
	return Array(matches.get_selected_items()).map(func(i): return entries[i])

## The centred extent the build will use.
func extent() -> Dictionary:
	return AUTO.shaped("square" if shape.selected == 1 else "circle", [longitude.value, latitude.value], radius.value, int(scale.value), RECIPE.CELL_CM)

## The convention the build will use: the selectors, else the chosen country's.
func traffic() -> Dictionary:
	var value: Dictionary = AUTO.traffic(country)
	if driving_side.selected > 0: value.driving_side = "right" if driving_side.selected == 1 else "left"
	if signal_style.selected > 0: value.signal_style = "horizontal" if signal_style.selected == 1 else "vertical"
	return value

## The catalogue architecture the build will use, "" for plain city buildings.
func chosen_architecture() -> String:
	if architecture.selected == 1: return ""
	if architecture.selected > 1: return CATALOG.data.architectures.keys()[architecture.selected - 2]
	var automatic: String = AUTO.architecture(country)
	return automatic if automatic != "" else "modern"

func _describe() -> void:
	var choice := extent()
	guidance.text = AUTO.guidance(choice)
	if AUTO.estimate(choice).level == "high": guidance.add_theme_color_override("font_color", Color("e8590c"))
	else: guidance.remove_theme_color_override("font_color")
	if job != null: return
	var convention := traffic()
	status.text = "%s\n%s · %s · %s" % [I18N.t("Play area: %s") % AUTO.describe(choice), I18N.t("Left-hand traffic" if convention.driving_side == "left" else "Right-hand traffic"),
		I18N.t("Vertical signals" if convention.signal_style == "vertical" else "Horizontal signals") + " · " + I18N.t("White centre line" if convention.centre_line == "white" else "Yellow centre line"), convention.country if convention.country != "" else "?"]
	status.text += " · " + (I18N.t("Plain city buildings") if chosen_architecture() == "" else I18N.builtin(chosen_architecture()))

# Recipe and build ------------------------------------------------------------

func recipe() -> Dictionary:
	var value := {"version":RECIPE.VERSION, "pbf":pbf.text, "scale":int(scale.value),
		"project":project.text, "package":package.text, "full_check":full_check.button_pressed, "mobile_check":mobile_check.button_pressed}
	value.center = [longitude.value, latitude.value]
	value.radius_km = radius.value
	if shape.selected == 1: value.shape = "square"
	var convention := {}
	if driving_side.selected > 0: convention.driving_side = "right" if driving_side.selected == 1 else "left"
	if signal_style.selected > 0: convention.signal_style = "horizontal" if signal_style.selected == 1 else "vertical"
	# A downloaded snapshot holds no country boundary: use the country it reported.
	if downloading() and str(country.get("code", "")) != "":
		var automatic: Dictionary = AUTO.traffic(country)
		convention.merge({"driving_side":automatic.driving_side, "signal_style":automatic.signal_style, "centre_line":automatic.centre_line})
	if not convention.is_empty(): value.traffic = convention
	# A regional profile styles the buildings; automatic leaves the architecture to
	# the recipe's country lookup unless this wizard already knows the country.
	if architecture.selected != 1:
		var profile := {}
		if architecture.selected > 1 or AUTO.architecture(country) != "": profile.architecture = chosen_architecture()
		value.regional = {"version":1, "road_conflicts":"trim_buildings", "profile":profile}
	if terrain.button_pressed and dem.text != "": value.dem = dem.text
	return value

func _extent_json() -> String:
	var choice := extent()
	return JSON.stringify({"center":choice.center, "radius_km":choice.radius_km, "shape":choice.kind})

func _cache() -> String:
	var path := ProjectSettings.globalize_path(SOURCE_CACHE)
	DirAccess.make_dir_recursive_absolute(path)
	return path

func _build() -> void:
	if job != null: return
	if project.text == "" or package.text == "": _suggest_outputs("")
	if downloading(): _acquire(_start_recipe)
	else: _check_local(_start_recipe)

## Download OSM (and DEM tiles), then check coverage, then continue.
func _acquire(next: Callable) -> void:
	if not agree.button_pressed:
		status.text = I18N.t("Confirm the source licences to download.")
		return
	var choice := extent()
	var arguments := PackedStringArray(["--center", str(choice.center[0]), str(choice.center[1]), "--radius-km", str(choice.radius_km), "--shape", choice.kind, "--cache", _cache()])
	_run("osm", arguments, _osm_ready.bind(next), "Downloading OpenStreetMap…")

func _osm_ready(snapshot: Dictionary, next: Callable) -> void:
	pbf.text = str(snapshot.path)
	if snapshot.get("country") is Dictionary and not snapshot.country.is_empty(): country = snapshot.country
	var note: String = I18N.t("OSM snapshot ready: %d ways (%s)") % [int(snapshot.counts.ways), I18N.t("cached") if snapshot.cached else str(snapshot.fetched_at)]
	if not terrain.button_pressed:
		dem.text = ""
		_check_local(next, note)
		return
	_run("dem", PackedStringArray(["--extent", _extent_json(), "--folder", _tile_folder()]), _dem_ready.bind(next, note), "Downloading terrain…")

func _dem_ready(tiles: Dictionary, next: Callable, note: String) -> void:
	if tiles.get("absent", []).is_empty(): dem.text = _tile_folder()
	else:
		# Copernicus has no tile over open sea; such an extent stays flat.
		dem.text = ""
		note += "\n" + I18N.t("No Copernicus terrain for part of this extent (open sea): the map stays flat.")
	_check_local(next, note)

func _tile_folder() -> String:
	return _cache().path_join("copernicus-glo30")

## The same coverage check for downloaded and user-chosen files.
func _check_local(next: Callable, note := "") -> void:
	if pbf.text == "":
		status.text = I18N.t("Choose an OSM PBF file.")
		return
	var arguments := PackedStringArray(["--extent", _extent_json(), "--pbf", pbf.text])
	if terrain.button_pressed and dem.text != "": arguments.append_array(["--dem", dem.text])
	_run("preflight", arguments, _checked.bind(next, note), "Checking source coverage…")

func _checked(check: Dictionary, next: Callable, note: String) -> void:
	if not check.get("ok", false):
		status.text = I18N.t("The sources do not cover this extent:") + "\n" + "\n".join(check.get("errors", []))
		return
	var lines: Array = [note] if note != "" else []
	lines.append_array(check.get("warnings", []))
	if not lines.is_empty(): status.text = "\n".join(lines)
	next.call()

func _start_recipe() -> void:
	var parsed: Dictionary = RECIPE.parse(JSON.stringify(recipe()))
	if not parsed.ok:
		status.text = I18N.t(parsed.error)
		return
	hide()
	var preview: bool = ui.preview_enabled
	var runner: RefCounted = RECIPE.new(ui, func(text: String): ui._status(I18N.t("New real-city map: %s") % I18N.t(text)))
	var report: Dictionary = await runner.run(parsed.recipe)
	ui.preview_enabled = preview
	if report.ok:
		ui._status(I18N.t("Real-city map built: %d cells, %s") % [report.cells, parsed.recipe.package])
		ui.set_editor_mode("city")
		_finished(parsed.recipe, report)
	else: ui._status(I18N.t("New real-city map stopped at %s: %s") % [report.failed_step, report.get("error", report.get("status", ""))])

## Export is done and the map stays open: keep editing or open the folder.
func _finished(value: Dictionary, report: Dictionary) -> void:
	var done := AcceptDialog.new()
	# Another Editor dialog may hold the exclusive slot; this notice never blocks it.
	done.exclusive = false
	done.title = I18N.t("Real-city map ready")
	done.dialog_text = I18N.t("Exported %s (%d cells). The map stays open for editing; export again after changes.") % [str(value.package).get_file(), int(report.cells)]
	done.ok_button_text = I18N.t("Keep editing")
	done.add_button(I18N.t("Show exported map"), false, "show")
	done.custom_action.connect(func(_action): OS.shell_show_in_file_manager(str(value.package)); done.hide())
	done.visibility_changed.connect(func(): if not done.visible: done.queue_free())
	ui.add_child(done)
	done.popup_centered()

# Source jobs ----------------------------------------------------------------

func _run(command: String, arguments: PackedStringArray, then: Callable, label: String) -> void:
	var started: RefCounted = JOB.new()
	var failure: String = started.start(ui.import_python_path(), command, arguments)
	if failure != "":
		status.text = I18N.t(failure)
		return
	job = started
	_then = then
	progress.visible = true
	progress.value = 0
	status.text = I18N.t(label)
	get_ok_button().disabled = true

func _process(_delta: float) -> void:
	if job == null: return
	job.poll()
	var step: Dictionary = job.progress
	if int(step.get("total", 0)) > 0: progress.value = 100.0 * float(step.done) / float(step.total)
	if not job.done: return
	var finished: RefCounted = job
	job = null
	progress.visible = false
	get_ok_button().disabled = false
	if finished.result.get("ok", false): _then.call(finished.result.data)
	else: status.text = I18N.t("Stopped: %s") % I18N.diagnostic(str(finished.result.get("error", "")))

## Cancel closes the dialog and stops a running download or check.
func _stop() -> void:
	if job != null:
		job.shutdown()
		job = null
		progress.visible = false
		get_ok_button().disabled = false
