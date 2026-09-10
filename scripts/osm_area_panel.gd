extends RefCounted
## Source selection is separate from derived geometry crop and map adoption.
var ui: Control
var dialog: AcceptDialog
var enabled: CheckBox
var streaming: CheckBox
var fields: Array[SpinBox] = []
var area: Control
var status: Label
var revision := 0

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	dialog = AcceptDialog.new()
	dialog.title = "OSM derived geometry crop"
	dialog.ok_button_text = "Keep selection"
	var layout := VBoxContainer.new()
	layout.custom_minimum_size = Vector2(690, 400)
	dialog.add_child(layout)
	enabled = CheckBox.new()
	enabled.text = "Crop OSM PBF/XML during import (source stays unchanged)"
	layout.add_child(enabled)
	ui._label(layout, "Road centerlines and building/vegetation polygons are intersected with this box.\nHoles and split parts survive. Road width may extend outside; new cut walls are artificial.")
	streaming = CheckBox.new()
	streaming.text = "PBF streaming · local source up to 2 GiB (requires crop)"
	layout.add_child(streaming)
	ui._label(layout, "Streaming: source bytes + 2 GiB index + 64 MiB free disk; 15-minute deadline.\nThree byte-counted passes; complete candidate ways/relations before crop.\nOther vector inputs stay at 32 MiB.")
	var grid := GridContainer.new()
	grid.columns = 4
	layout.add_child(grid)
	for item in [["West",-180,180],["South",-80,84],["East",-180,180],["North",-80,84]]:
		fields.append(ui._import_number(grid,item[0],item[1],item[2],0,0.000001))
	area = preload("./area_selector.gd").new()
	layout.add_child(area)
	area.bounds_selected.connect(func(b: Array):
		for i in range(4): fields[i].value = b[i]
	)
	var actions := HBoxContainer.new()
	layout.add_child(actions)
	ui._button(actions,"Fit coordinates",func(): area.toggle_fit())
	ui._button(actions,"Area at import origin",func():
		var b := [ui.import_origin_lon.value,ui.import_origin_lat.value,ui.import_origin_lon.value+0.001,ui.import_origin_lat.value+0.001]
		for i in range(4): fields[i].value = b[i]
		area.toggle_fit()
	)
	status = ui._label(layout,"")
	for child in layout.get_children():
		if child is Label: child.custom_minimum_size.x = 690
	for field in fields: field.value_changed.connect(func(_v): changed())
	enabled.toggled.connect(func(_v): changed())
	streaming.toggled.connect(func(_v): changed())
	dialog.confirmed.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	dialog.canceled.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	ui.add_child(dialog)
	changed()

func bbox() -> Array:
	var result := []
	for field in fields: result.append(field.value)
	return result

func error() -> String:
	if streaming.button_pressed and not enabled.button_pressed: return "Enable crop and select a bbox for PBF streaming."
	if not enabled.button_pressed: return ""
	var b := bbox()
	if b[0] >= b[2] or b[1] >= b[3]: return "Require west < east and south < north; no dateline crossing."
	if b[2]-b[0] > 0.02 or b[3]-b[1] > 0.02: return "Select at most 0.02 degrees per side."
	return ""

func changed() -> void:
	revision += 1
	ui._discard_import()
	ui.osm_crop_button.text = "OSM crop: %s…" % ("on" if enabled.button_pressed else "off")
	area.set_bounds(bbox())
	status.text = error() if error() != "" else ("Crop enabled. Import next, review counts/estimates, then explicitly adopt." if enabled.button_pressed else "Crop disabled: import the complete supported snapshot.")

func open() -> void:
	if ui.busy: return
	ui.import_dialog.hide()
	dialog.popup_centered(Vector2i(750,540))
