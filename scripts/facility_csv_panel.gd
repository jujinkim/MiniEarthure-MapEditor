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
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(600, 380)
	dialog.add_child(box)
	ui._label(box, "Enter exact CSV header names. Coordinates use the import origin and current map scale. Rows outside the map are excluded; invalid rows require review.")
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
	dialog.popup_centered()
