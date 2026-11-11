extends ConfirmationDialog
## File → New real-city map: collects a real-city recipe (scripts/real_city_recipe.gd)
## and runs it in this Editor, or saves it for the headless
## `-- --real-city-recipe recipe.json` build. Both use the same steps. A named place
## (village, station, campus …) fills the centre; radius remains explicit.
## traffic set to Automatic follows the country found in the PBF.
const I18N := preload("./locale_text.gd")
const RECIPE := preload("./real_city_recipe.gd")
const AUTO := preload("./real_city_auto.gd")
var ui: Control
var pbf: LineEdit
var query: LineEdit
var matches: ItemList
## Areas, then named places, as listed in `matches`: {kind: "area"|"place", value}.
var entries: Array = []
var latitude: SpinBox
var longitude: SpinBox
var radius: SpinBox
var scale: SpinBox
var driving_side: OptionButton
var signal_style: OptionButton
var dem: LineEdit
var project: LineEdit
var package: LineEdit
var full_check: CheckBox
var mobile_check: CheckBox
var status: Label
var picker: FileDialog
var pick_target: LineEdit

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	title = I18N.t("New real-city map")
	ok_button_text = I18N.t("Build map")
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(720, 0)
	add_child(column)
	ui._label(column, "Builds a game map from OpenStreetMap: roads and buildings follow the data; street furniture, parks, signs and missing heights are generated. Every step keeps the Editor's review and limits.")
	var grid := GridContainer.new()
	grid.columns = 3
	column.add_child(grid)
	pbf = _path_row(grid, "OSM PBF file", "*.pbf", FileDialog.FILE_MODE_OPEN_FILE)
	ui._label(grid, "Area name")
	query = LineEdit.new()
	query.placeholder_text = I18N.t("Area or place name in this PBF")
	query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(query)
	ui._button(grid, "Find areas", _find)
	matches = ItemList.new()
	matches.select_mode = ItemList.SELECT_MULTI
	matches.custom_minimum_size.y = 110
	matches.multi_selected.connect(_selected)
	column.add_child(matches)
	var coordinates := GridContainer.new()
	coordinates.columns = 6
	column.add_child(coordinates)
	latitude = _number(coordinates, "Latitude", -80, 84, 0.000001, 0)
	longitude = _number(coordinates, "Longitude", -180, 180, 0.000001, 0)
	radius = _number(coordinates, "Radius (km)", 0.001, 20, 0.001, 2.0)
	var options := GridContainer.new()
	options.columns = 4
	column.add_child(options)
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
	var outputs := GridContainer.new()
	outputs.columns = 3
	column.add_child(outputs)
	dem = _path_row(outputs, "Copernicus DEM folder (optional)", "", FileDialog.FILE_MODE_OPEN_DIR)
	project = _path_row(outputs, "Project folder", "", FileDialog.FILE_MODE_OPEN_DIR)
	package = _path_row(outputs, "Exported map (.memap)", "*.memap", FileDialog.FILE_MODE_SAVE_FILE)
	full_check = CheckBox.new()
	full_check.text = I18N.t("Full 3D check of every cell")
	full_check.button_pressed = true
	column.add_child(full_check)
	mobile_check = CheckBox.new()
	mobile_check.text = I18N.t("Check that phones can open it (1.5 GiB)")
	column.add_child(mobile_check)
	status = ui._label(column, "Choose a PBF and enter a centre and radius, or find a place.")
	add_button(I18N.t("Save recipe…"), false, "save_recipe")
	custom_action.connect(func(action: StringName): if action == "save_recipe": _pick(null, "*.json;Recipe JSON", FileDialog.FILE_MODE_SAVE_FILE))
	confirmed.connect(_build)
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_selected.connect(_picked)
	picker.dir_selected.connect(_picked)
	add_child(picker)

func _number(grid: GridContainer, label: String, low: float, high: float, step: float, value: float) -> SpinBox:
	ui._label(grid, label)
	var control := SpinBox.new()
	control.min_value = low; control.max_value = high; control.step = step; control.value = value
	control.value_changed.connect(func(_value): if status != null: _describe())
	grid.add_child(control)
	return control

func _path_row(grid: GridContainer, label: String, filter: String, mode: int) -> LineEdit:
	ui._label(grid, label)
	var edit := LineEdit.new()
	edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	edit.custom_minimum_size.x = 420
	grid.add_child(edit)
	ui._button(grid, "Choose…", _pick.bind(edit, filter, mode))
	return edit

func _pick(target: LineEdit, filter: String, mode: int) -> void:
	pick_target = target
	picker.file_mode = mode
	picker.filters = PackedStringArray([filter]) if filter != "" else PackedStringArray()
	picker.popup_centered_ratio(0.7)

func _picked(path: String) -> void:
	if pick_target != null:
		pick_target.text = path
		return
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		status.text = I18N.t("Could not write %s") % path
		return
	file.store_string(JSON.stringify(recipe(), "  "))
	status.text = I18N.t("Recipe saved: %s") % path

func open() -> void:
	if ui.busy: return
	if pbf.text == "" and ui.last_import_source.get_extension() == "pbf": pbf.text = ui.last_import_source
	popup_centered(Vector2i(780, 600))

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
	popup_centered(Vector2i(780, 600))

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
		var item: Dictionary = entries[index].value
		var point: Array = item.get("point", [])
		if point.is_empty(): point = [(item.bbox[0] + item.bbox[2]) * .5, (item.bbox[1] + item.bbox[3]) * .5]
		longitude.value = point[0]
		latitude.value = point[1]
	_describe()

func _chosen() -> Array:
	return Array(matches.get_selected_items()).map(func(i): return entries[i])

## The automatic extent of a chosen place, or {} for areas.
func extent() -> Dictionary:
	return AUTO.circle([longitude.value, latitude.value], radius.value, int(scale.value), RECIPE.CELL_CM)

## The convention the build will use: the selectors, else the chosen country's.
func traffic() -> Dictionary:
	var chosen := _chosen()
	var value: Dictionary = AUTO.traffic(chosen[0].value.get("context", {}).get("country", {}) if not chosen.is_empty() else {})
	if driving_side.selected > 0: value.driving_side = "right" if driving_side.selected == 1 else "left"
	if signal_style.selected > 0: value.signal_style = "horizontal" if signal_style.selected == 1 else "vertical"
	return value

func _describe() -> void:
	var lines: Array[String] = []
	var choice := extent()
	if not choice.is_empty(): lines.append(I18N.t("Play area: %s") % AUTO.describe(choice))
	var convention := traffic()
	lines.append("%s · %s · %s" % [I18N.t("Left-hand traffic" if convention.driving_side == "left" else "Right-hand traffic"), I18N.t("Vertical signals" if convention.signal_style == "vertical" else "Horizontal signals"), convention.country if convention.country != "" else "?"])
	status.text = "\n".join(lines)

func recipe() -> Dictionary:
	var value := {"version":RECIPE.VERSION, "pbf":pbf.text, "scale":int(scale.value),
		"project":project.text, "package":package.text, "full_check":full_check.button_pressed, "mobile_check":mobile_check.button_pressed}
	value.center = [longitude.value, latitude.value]
	value.radius_km = radius.value
	var traffic := {}
	if driving_side.selected > 0: traffic.driving_side = "right" if driving_side.selected == 1 else "left"
	if signal_style.selected > 0: traffic.signal_style = "horizontal" if signal_style.selected == 1 else "vertical"
	if not traffic.is_empty(): value.traffic = traffic
	if dem.text != "": value.dem = dem.text
	return value

func _build() -> void:
	var parsed: Dictionary = RECIPE.parse(JSON.stringify(recipe()))
	if not parsed.ok:
		status.text = I18N.t(parsed.error)
		popup_centered(Vector2i(780, 600))
		return
	var preview: bool = ui.preview_enabled
	var runner: RefCounted = RECIPE.new(ui, func(text: String): ui._status(I18N.t("New real-city map: %s") % I18N.t(text)))
	var report: Dictionary = await runner.run(parsed.recipe)
	ui.preview_enabled = preview
	if report.ok: ui._status(I18N.t("Real-city map built: %d cells, %s") % [report.cells, parsed.recipe.package])
	else: ui._status(I18N.t("New real-city map stopped at %s: %s") % [report.failed_step, report.get("error", report.get("status", ""))])
