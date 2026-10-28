extends ConfirmationDialog
## File → New real-city map: collects a real-city recipe (scripts/real_city_recipe.gd)
## and runs it in this Editor, or saves it for the headless
## `-- --real-city-recipe recipe.json` build. Both use the same steps.
const I18N := preload("./locale_text.gd")
const RECIPE := preload("./real_city_recipe.gd")
var ui: Control
var pbf: LineEdit
var query: LineEdit
var matches: ItemList
var places: Array = []
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
	query.placeholder_text = I18N.t("Administrative area name in this PBF")
	query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(query)
	ui._button(grid, "Find areas", _find)
	matches = ItemList.new()
	matches.select_mode = ItemList.SELECT_MULTI
	matches.custom_minimum_size.y = 110
	column.add_child(matches)
	var options := GridContainer.new()
	options.columns = 4
	column.add_child(options)
	ui._label(options, "Scale 1:")
	scale = SpinBox.new()
	scale.min_value = 1; scale.max_value = 8; scale.value = 3
	options.add_child(scale)
	driving_side = OptionButton.new()
	for label in ["Right-hand traffic", "Left-hand traffic"]: driving_side.add_item(I18N.t(label))
	options.add_child(driving_side)
	signal_style = OptionButton.new()
	for label in ["Horizontal signals", "Vertical signals"]: signal_style.add_item(I18N.t(label))
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
	status = ui._label(column, "Choose a PBF, find the area by name and select it.")
	add_button(I18N.t("Save recipe…"), false, "save_recipe")
	custom_action.connect(func(action: StringName): if action == "save_recipe": _pick(null, "*.json;Recipe JSON", FileDialog.FILE_MODE_SAVE_FILE))
	confirmed.connect(_build)
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_selected.connect(_picked)
	picker.dir_selected.connect(_picked)
	add_child(picker)

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

func _found(found: Array) -> void:
	ui.osm_panel.search_callback = Callable()
	places = found.filter(func(p): return p.issue == "")
	matches.clear()
	for place: Dictionary in places: matches.add_item("%s · admin %s · %s" % [place.name, place.admin_level, place.source_id])
	if not places.is_empty(): matches.select(0)
	status.text = I18N.t("%d matching areas. Select one or more.") % places.size() if not places.is_empty() else I18N.t("No matching administrative area. Try its local name.")
	popup_centered(Vector2i(780, 600))

func recipe() -> Dictionary:
	var areas: Array = []
	for index in matches.get_selected_items(): areas.append({"name":places[index].name, "source_id":places[index].source_id})
	var value := {"version":RECIPE.VERSION, "pbf":pbf.text, "areas":areas, "scale":int(scale.value),
		"traffic":{"driving_side":"left" if driving_side.selected == 1 else "right", "signal_style":"vertical" if signal_style.selected == 1 else "horizontal"},
		"project":project.text, "package":package.text, "full_check":full_check.button_pressed, "mobile_check":mobile_check.button_pressed}
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
