extends RefCounted
var ui: Control
var dialog: AcceptDialog
var target: OptionButton
var zero: SpinBox
var path: LineEdit
var picker: FileDialog
var revision := 0

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	dialog = AcceptDialog.new()
	dialog.title = "OSM height reference"
	dialog.ok_button_text = "Keep selection"
	var column := VBoxContainer.new()
	column.custom_minimum_size.x = 690
	dialog.add_child(column)
	ui._label(column, "Only explicit OSM node heights are converted; missing heights are never inferred.\nMatch the existing DEM's EGM2008 local-zero height and WGS84 origins.\nGround follows terrain; source heights are not fitted to it.")
	target = OptionButton.new()
	target.add_item("EGM96 · subtract local-zero height (default 0 m)")
	target.add_item("EGM2008 · apply local correction grid, subtract local-zero height")
	column.add_child(target)
	var fields := GridContainer.new()
	fields.columns = 2
	column.add_child(fields)
	zero = ui._import_number(fields, "Target datum height at local zero (m)", -10000, 10000, 0, 0.01)
	path = LineEdit.new()
	path.placeholder_text = "Local height-delta JSON grid (EGM2008 only; ≤64 KiB)"
	column.add_child(path)
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	picker.filters = PackedStringArray(["*.json ; Local height-delta grid"])
	ui.add_child(picker)
	picker.file_selected.connect(func(value): path.text = value; changed())
	ui._button(column, "Choose local correction grid…", func(): picker.popup_centered(Vector2i(800,550)))
	ui._label(column, "Grid values are H(EGM2008) − H(EGM96), in metres; rows run south to north.\nPrepare the bounded grid externally from licensed local datum material.\nReview retains its exact bytes, source, license and declared accuracy.\nNo download, extrapolation, nodata repair or accuracy certification. See docs/IMPORTS.md.")
	for child in column.get_children():
		if child is Label: child.custom_minimum_size.x = 690
	target.item_selected.connect(func(_v): changed())
	zero.value_changed.connect(func(_v): changed())
	path.text_changed.connect(func(_v): changed())
	dialog.confirmed.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	dialog.canceled.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	ui.add_child(dialog)

func changed() -> void:
	revision += 1
	ui._discard_import()
	if ui.import_job != null and ui.dem_mode == "": ui.import_job.cancel()

func capture() -> Dictionary:
	var result := {"target":"EGM96" if target.selected == 0 else "EGM2008", "zero_m":zero.value, "grid":null}
	if target.selected == 1:
		var source := path.text.strip_edges()
		if not source.is_absolute_path() or source.contains("://"): return {"error":"Choose an absolute local correction grid path."}
		var file := FileAccess.open(source, FileAccess.READ)
		if file == null: return {"error":"Cannot open the local correction grid."}
		var length := file.get_length()
		if length <= 0 or length > preload("./import_vertical.gd").MAX_GRID_BYTES:
			file.close()
			return {"error":"Correction grid must be nonempty and at most 64 KiB."}
		var bytes := file.get_buffer(length)
		var final_length := file.get_length()
		file.close()
		var content := bytes.get_string_from_utf8()
		if length != final_length or bytes.size() != length or content.to_utf8_buffer() != bytes: return {"error":"Correction grid changed or is not valid UTF-8; retry."}
		result.grid = content
	var failure: String = preload("./import_vertical.gd").options_error(result)
	return result if failure == "" else {"error":failure}

func open() -> void:
	if ui.busy: return
	ui.import_dialog.hide()
	dialog.popup_centered(Vector2i(750,440))
