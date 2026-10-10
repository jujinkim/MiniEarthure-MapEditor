extends RefCounted
var ui: Control
var dialog: AcceptDialog
var fields := {}
var encoding: OptionButton
var crop: CheckBox

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	dialog = AcceptDialog.new()
	dialog.title = "Facility CSV columns"
	dialog.ok_button_text = "Keep mapping"
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(760, 480)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	dialog.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.custom_minimum_size.x = 720
	scroll.add_child(box)
	ui._label(box, "Enter exact CSV header names. Coordinates use the import origin and current map scale. Rows outside the map are excluded; invalid rows require review.")
	ui._button(box, "Use imported OSM coordinates", use_imported_frame)
	encoding = OptionButton.new()
	for value in ["UTF-8 (optional BOM)", "CP949", "EUC-KR"]: encoding.add_item(value)
	box.add_child(encoding)
	crop = CheckBox.new()
	crop.text = "Restrict facilities to the selected OSM crop"
	crop.button_pressed = true
	crop.toggled.connect(func(_value): ui._import_controls_changed())
	box.add_child(crop)
	for entry in [["name_column", "Name column", "name"], ["latitude_column", "Latitude column", "latitude"], ["longitude_column", "Longitude column", "longitude"], ["category", "Facility category", "library"], ["source_url", "Source page / reference", ""]]:
		ui._label(box, entry[1])
		var field := LineEdit.new()
		field.text = entry[2]
		box.add_child(field)
		fields[entry[0]] = field
		field.text_changed.connect(func(_value): ui._import_controls_changed())
	encoding.item_selected.connect(func(_value): ui._import_controls_changed())
	dialog.confirmed.connect(func(): ui.import_dialog.popup_centered(Vector2i(760, 550)))
	dialog.canceled.connect(func(): ui.import_dialog.popup_centered(Vector2i(760, 550)))
	ui.add_child(dialog)

func capture() -> Dictionary:
	var result := {"encoding":["utf-8-sig", "cp949", "euc-kr"][encoding.selected], "source_denominator":preload("./import_units.gd").dem_denominator(ui.store.document)}
	for key: String in fields: result[key] = fields[key].text
	var bounds: Dictionary = ui.store.document.bounds
	result.bounds_cm = [int(bounds.min[0]), int(bounds.min[1]), int(bounds.max[0]), int(bounds.max[1])]
	if crop.button_pressed:
		if ui.osm_panel.enabled.button_pressed and ui.osm_panel.error() == "": result.geographic_bbox = ui.osm_panel.bbox()
		else:
			for attribution: Dictionary in ui.store.document.attributions:
				var meta: Variant = JSON.parse_string(attribution.get("notice",""))
				if meta is Dictionary and meta.get("adapter") == "osm-extract-v1" and meta.get("coordinates",{}).has("osm_crop"): result.geographic_bbox = meta.coordinates.osm_crop.bbox
	return result

func open() -> void:
	if ui.busy: return
	ui.import_dialog.hide()
	dialog.popup_centered(Vector2i(780, 560))

func use_imported_frame() -> void:
	var frames := preload("./dem_building_grounding.gd").layers(ui.store.document)
	if frames.is_empty(): ui._status("No imported OSM coordinate frame."); return
	var coordinates: Dictionary = frames.values()[0]
	for frame: Dictionary in frames.values():
		for key in ["mode", "origin", "local_origin_m"]:
			if frame.get(key) != coordinates.get(key): ui._status("Imported OSM coordinate frames differ."); return
	ui.import_coordinate_mode.select(1)
	ui.import_origin_lon.value = coordinates.origin[0]
	ui.import_origin_lat.value = coordinates.origin[1]
	ui.import_origin_x.value = coordinates.local_origin_m[0]
	ui.import_origin_y.value = coordinates.local_origin_m[1]
	ui._import_controls_changed()
