extends RefCounted
const I18N := preload("./locale_text.gd")
## Source selection is separate from derived geometry crop and map adoption.
var ui: Control
var dialog: AcceptDialog
var enabled: CheckBox
var streaming: CheckBox
var exclusions: CheckBox
var fields: Array[SpinBox] = []
var area: Control
var status: Label
var revision := 0
var place_query: LineEdit
var source_path: LineEdit
var place_choices: OptionButton
var place_status: Label
var places: Array = []
var source_dialog: FileDialog
const PLACES_JOB := preload("./pbf_places_job.gd")

func setup(owner_ui: Control) -> void:
	ui = owner_ui
	dialog = AcceptDialog.new()
	dialog.title = I18N.t("OSM derived geometry crop")
	dialog.ok_button_text = I18N.t("Keep selection")
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(800,560)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	dialog.add_child(scroll)
	var layout := VBoxContainer.new()
	layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(layout)
	ui._label(layout,"Find a place in your PBF — coordinates are filled from its boundary")
	var search := HBoxContainer.new()
	layout.add_child(search)
	place_query = LineEdit.new()
	place_query.placeholder_text = "Area name, e.g. 수원시 / Yeongtong-gu"
	place_query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.add_child(place_query)
	ui._button(search,"Find area by name",start_search).custom_minimum_size.x = 180
	var source_row := HBoxContainer.new()
	layout.add_child(source_row)
	source_path = LineEdit.new()
	source_path.placeholder_text = "Choose the downloaded .osm.pbf"
	source_path.editable = false
	source_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	source_row.add_child(source_path)
	ui._button(source_row,"Choose PBF…",func(): source_dialog.popup_centered_ratio(0.7)).custom_minimum_size.x = 180
	source_dialog = FileDialog.new()
	source_dialog.access = FileDialog.ACCESS_FILESYSTEM
	source_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	source_dialog.use_native_dialog = true
	source_dialog.filters = PackedStringArray(["*.pbf ; OSM PBF"])
	source_dialog.file_selected.connect(func(path):
		source_path.text = path
		places.clear()
		place_choices.clear()
		area.set_places([])
		place_status.text = "PBF selected. Enter the administrative area name and press Find area by name."
	)
	ui.add_child(source_dialog)
	place_choices = OptionButton.new()
	place_choices.item_selected.connect(select_place)
	layout.add_child(place_choices)
	place_status = ui._label(layout,"Search reads the local PBF only; no login or online geocoding. Original files stay unchanged.")
	enabled = CheckBox.new()
	enabled.text = I18N.t("Crop OSM PBF/XML during import (source stays unchanged)")
	layout.add_child(enabled)
	ui._label(layout, "Road centerlines and building/vegetation polygons are intersected with this box.\nHoles and split parts survive. Road width may extend outside; new cut walls are artificial.")
	streaming = CheckBox.new()
	streaming.text = I18N.t("PBF streaming · local source up to 2 GiB (requires crop)")
	layout.add_child(streaming)
	exclusions = CheckBox.new()
	exclusions.text = "Review and exclude unsupported source objects (PBF streaming)"
	layout.add_child(exclusions)
	ui._label(layout, "Streaming: source bytes + 2 GiB index + 64 MiB free disk; 15-minute deadline.\nThree byte-counted passes; complete candidate ways/relations before crop.\nOther vector inputs stay at 32 MiB.")
	var grid := GridContainer.new()
	grid.columns = 4
	layout.add_child(grid)
	for item in [["West",-180,180],["South",-80,84],["East",-180,180],["North",-80,84]]:
		fields.append(ui._import_number(grid,item[0],item[1],item[2],0,0.000001))
	area = preload("./area_selector.gd").new()
	area.custom_minimum_size.y = 220
	layout.add_child(area)
	area.bounds_selected.connect(func(b: Array):
		for i in range(4): fields[i].value = b[i]
		set_origin(Vector2((b[0]+b[2])*0.5,(b[1]+b[3])*0.5))
	)
	area.center_selected.connect(set_origin)
	var actions := HBoxContainer.new()
	layout.add_child(actions)
	ui._button(actions,"Fit coordinates",func(): area.toggle_fit()).custom_minimum_size.x = 220
	ui._button(actions,"Area at import origin",func():
		var b := [ui.import_origin_lon.value,ui.import_origin_lat.value,ui.import_origin_lon.value+0.001,ui.import_origin_lat.value+0.001]
		for i in range(4): fields[i].value = b[i]
		area.toggle_fit()
	).custom_minimum_size.x = 240
	status = ui._label(layout,"")
	ui._label(layout,"© OpenStreetMap contributors · ODbL · openstreetmap.org/copyright\nBoundary preview is simplified; the crop is a rectangle and includes surrounding areas.\nClick the map to place the origin at your current map centre; drag to choose a crop.")
	for child in layout.get_children():
		if child is Label: child.custom_minimum_size.x = 780
	for field in fields: field.value_changed.connect(func(_v): changed())
	enabled.toggled.connect(func(_v): changed())
	streaming.toggled.connect(func(_v): changed())
	exclusions.toggled.connect(func(_v): changed())
	dialog.confirmed.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	dialog.canceled.connect(func(): ui.import_dialog.popup_centered(Vector2i(760,550)))
	ui.add_child(dialog)
	changed()

func bbox() -> Array:
	var result := []
	# Match the displayed six-decimal source boundary, not SpinBox step noise.
	for field in fields: result.append(float("%.6f" % field.value))
	return result

func error() -> String:
	if exclusions.button_pressed and not streaming.button_pressed: return "Object exclusion review requires PBF streaming."
	if streaming.button_pressed and not enabled.button_pressed: return "Enable crop and select a bbox for PBF streaming."
	if not enabled.button_pressed: return ""
	var b := bbox()
	if b[0] >= b[2] or b[1] >= b[3]: return "Require west < east and south < north; no dateline crossing."
	return ""

func changed() -> void:
	revision += 1
	ui._discard_import()
	ui.osm_crop_button.set_meta("action_label", "Find area / OSM crop: %s…" % (I18N.t("on") if enabled.button_pressed else I18N.t("off")))
	preload("./workbench_style.gd").refresh_label(ui.osm_crop_button)
	area.set_bounds(bbox())
	status.text = I18N.diagnostic(error()) if error() != "" else ("Crop enabled. All corners must be within 20 km of the projection origin.\nReview counts, estimates and exact exclusions before adoption." if enabled.button_pressed else I18N.t("Crop disabled: import the complete supported snapshot."))
	if enabled.button_pressed and error() == "":
		var b := bbox()
		var metres := Vector2((b[2]-b[0])*111320.0*cos(deg_to_rad((b[1]+b[3])*0.5)),(b[3]-b[1])*111320.0)/8.0
		status.text += "\n1:8 approximate map size: %.0f × %.0f m. Origin: %.6f, %.6f (longitude, latitude)." % [metres.x,metres.y,ui.import_origin_lon.value,ui.import_origin_lat.value]

func open() -> void:
	if ui.busy: return
	if source_path.text == "" and ui.last_import_source.get_extension() == "pbf": source_path.text = ui.last_import_source
	ui.import_dialog.hide()
	dialog.popup_centered(Vector2i(840,680))

func start_search() -> void:
	if ui.busy: return
	var job := PLACES_JOB.new()
	var failure := job.search(source_path.text,place_query.text,ui.import_python.text.strip_edges(),Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "": place_status.text = failure; return
	dialog.hide()
	ui.dem_mode = ""
	ui.import_job = job
	ui.worker_generation = ui.generation
	ui.busy = true
	ui.import_progress.value = 0
	ui.import_progress.visible = true
	ui._status("Finding named boundaries in local PBF · Cancel keeps the current map and source.")

func finish_search(_job: RefCounted, result: Dictionary) -> void:
	if ui.generation != ui.worker_generation:
		ui._status("Document changed during PBF lookup; search again.")
		return
	if result.get("ok",false):
		places = result.data.places.duplicate(true)
		place_choices.clear()
		for place: Dictionary in places:
			place_choices.add_item("%s · admin %s · %s%s" % [place.name,place.admin_level,place.source_id," · unavailable" if place.issue != "" else ""])
		area.set_places(places)
		place_status.text = "%d matching areas in %s. Select a name to inspect its boundary." % [places.size(),result.data.source_name] if not places.is_empty() else "No matching administrative area in this PBF. Try a local/English name or enter coordinates manually."
		if not places.is_empty(): select_place(0)
	else: place_status.text = str(result.get("error",{}).get("message","PBF lookup failed."))
	ui._status(place_status.text)
	dialog.popup_centered(Vector2i(840,680))

func select_place(index: int) -> void:
	if index < 0 or index >= places.size(): return
	var place: Dictionary = places[index]
	if place.issue != "": place_status.text = place.issue; return
	var b: Array = place.bbox
	# Round outward to the UI precision so a boundary is never clipped by rounding.
	for i in range(4): fields[i].value = (floorf(b[i]*1000000.0) if i < 2 else ceilf(b[i]*1000000.0))/1000000.0
	enabled.button_pressed = true
	streaming.button_pressed = true
	set_origin(Vector2((b[0]+b[2])*0.5,(b[1]+b[3])*0.5))
	area.toggle_fit()
	place_status.text = "%s · source %s. Drag for another crop, or click to move its projection origin." % [place.name,place.source_id]
	ui._status(place_status.text)

func set_origin(point: Vector2) -> void:
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = point.x
	ui.import_origin_lat.value = point.y
	var bounds: Dictionary = ui.store.document.bounds
	# OSM adoption divides all source metres by eight, including this placement.
	ui.import_origin_x.value = (bounds.min[0]+bounds.max[0])*0.005*8
	ui.import_origin_y.value = (bounds.min[1]+bounds.max[1])*0.005*8
	area.center = point
	area.queue_redraw()
	changed()
