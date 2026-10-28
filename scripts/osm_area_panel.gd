extends RefCounted
const I18N := preload("./locale_text.gd")
## Source selection is separate from derived geometry crop and map adoption.
var ui: Control
var dialog: AcceptDialog
var enabled: CheckBox
var streaming: CheckBox
var exclusions: CheckBox
var city: CheckBox
## City map scale 1:D (D in 1..8); locked to the scale of OSM layers already in the map.
var scale: SpinBox
var driving_side: OptionButton
var signal_style: OptionButton
## Denominator the automatic origin was placed with; 0 after a manual origin.
var origin_denominator := 0
const UNITS := preload("./import_units.gd")
var fields: Array[SpinBox] = []
var area: Control
var status: Label
var revision := 0
var guided := false
var place_query: LineEdit
var source_path: LineEdit
var place_choices: OptionButton
var place_status: Label
var places: Array = []
## Set by a caller that consumes search results itself (real-city recipe/wizard);
## the crop dialog then stays closed.
var search_callback := Callable()
## Places whose exact boundary union clips the import (empty: rectangle crop).
var selected_areas: Array = []
const LIMITS := preload("./limit_warnings.gd")
## More areas than WARN_AREAS still combine; the review then shows a warning.
const MAX_AREAS := preload("./import_layer.gd").MAX_AREAS
const WARN_AREAS := preload("./import_layer.gd").WARN_AREAS
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
	place_query.placeholder_text = I18N.t("Area name in this PBF (local name or recorded alias)")
	place_query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.add_child(place_query)
	ui._button(search,"Find area by name",start_search).custom_minimum_size.x = 180
	var source_row := HBoxContainer.new()
	layout.add_child(source_row)
	source_path = LineEdit.new()
	source_path.placeholder_text = I18N.t("Choose the downloaded .osm.pbf")
	source_path.editable = false
	source_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	source_row.add_child(source_path)
	ui._button(source_row,"Choose PBF…",func(): source_dialog.popup_centered_ratio(0.7)).custom_minimum_size.x = 180
	source_dialog = FileDialog.new()
	source_dialog.access = FileDialog.ACCESS_FILESYSTEM
	source_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	source_dialog.use_native_dialog = OS.get_name() != "macOS"
	source_dialog.filters = PackedStringArray(["*.pbf ; OSM PBF"])
	source_dialog.file_selected.connect(func(path):
		source_path.text = path
		changed()
		places.clear()
		selected_areas.clear()
		place_choices.clear()
		area.set_places([])
		place_status.text = I18N.t("PBF selected. Enter the administrative area name and press Find area by name.")
		if guided: dialog.popup_centered(Vector2i(840,680))
	)
	ui.add_child(source_dialog)
	var choice_row := HBoxContainer.new()
	layout.add_child(choice_row)
	place_choices = OptionButton.new()
	place_choices.item_selected.connect(select_place)
	place_choices.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choice_row.add_child(place_choices)
	ui._button(choice_row,"Add selected area",add_place).custom_minimum_size.x = 180
	place_status = ui._label(layout,"Search reads the local PBF only; no login or online geocoding. Original files stay unchanged.")
	enabled = CheckBox.new()
	enabled.text = I18N.t("Crop OSM PBF/XML during import (source stays unchanged)")
	layout.add_child(enabled)
	ui._label(layout, "Road centerlines and building/vegetation polygons are intersected with this box.\nHoles and split parts survive. Road width may extend outside; new cut walls are artificial.")
	streaming = CheckBox.new()
	streaming.text = I18N.t("PBF streaming · local source up to 64 GiB, warning above 2 GiB (requires crop)")
	layout.add_child(streaming)
	city = CheckBox.new()
	city.text = I18N.t("Automatically merge and simplify city geometry")
	city.button_pressed = true
	layout.add_child(city)
	var scale_row := HBoxContainer.new()
	layout.add_child(scale_row)
	scale = ui._import_number(scale_row,"City map scale 1:",UNITS.MIN_DENOMINATOR,UNITS.MAX_DENOMINATOR,UNITS.CITY_DEFAULT_DENOMINATOR,1)
	scale.rounded = true
	ui._label(scale_row,"Smaller numbers make the city larger. Exact OSM without city optimization stays 1:8.")
	var traffic_row := HBoxContainer.new()
	layout.add_child(traffic_row)
	ui._label(traffic_row, "Driving side")
	driving_side = OptionButton.new()
	for label in ["Right-hand traffic", "Left-hand traffic"]: driving_side.add_item(I18N.t(label))
	traffic_row.add_child(driving_side)
	ui._label(traffic_row, "Signals")
	signal_style = OptionButton.new()
	for label in ["Horizontal signals", "Vertical signals"]: signal_style.add_item(I18N.t(label))
	traffic_row.add_child(signal_style)
	ui._label(layout, "City optimization combines compatible road chains, nearby unnamed low buildings and matching vegetation.\nRoad corridors, junctions, courtyards and landmarks are protected. Review before/after counts and approximations.")
	exclusions = CheckBox.new()
	exclusions.text = I18N.t("Review and exclude unsupported source objects (PBF streaming)")
	layout.add_child(exclusions)
	ui._label(layout, "Streaming: source bytes + index + free disk; a warning after 15 minutes, Cancel stops it.\nThree byte-counted passes; complete candidate ways/relations before crop.\nOther vector inputs: up to 256 MiB, warning above 32 MiB.")
	var grid := GridContainer.new()
	grid.columns = 4
	layout.add_child(grid)
	for item in [["West",-180,180],["South",-80,84],["East",-180,180],["North",-80,84]]:
		fields.append(ui._import_number(grid,item[0],item[1],item[2],0,0.000001))
	area = preload("./area_selector.gd").new()
	area.custom_minimum_size.y = 220
	layout.add_child(area)
	area.bounds_selected.connect(func(b: Array):
		selected_areas.clear()
		for i in range(4): fields[i].value = b[i]
		set_origin(Vector2((b[0]+b[2])*0.5,(b[1]+b[3])*0.5))
	)
	area.center_selected.connect(set_origin)
	var actions := HBoxContainer.new()
	layout.add_child(actions)
	ui._button(actions,"Fit coordinates",func(): area.toggle_fit()).custom_minimum_size.x = 220
	ui._button(actions,"Area at import origin",func():
		var b := [ui.import_origin_lon.value,ui.import_origin_lat.value,ui.import_origin_lon.value+0.001,ui.import_origin_lat.value+0.001]
		selected_areas.clear()
		for i in range(4): fields[i].value = b[i]
		area.toggle_fit()
	).custom_minimum_size.x = 240
	status = ui._label(layout,"")
	ui._label(layout,"© OpenStreetMap contributors · ODbL · openstreetmap.org/copyright\nSelected areas clip to their exact boundaries (the preview is simplified); a dragged crop is a rectangle and includes surrounding areas.\nClick the map to place the origin at your current map centre; drag to choose a crop.")
	for child in layout.get_children():
		if child is Label: child.custom_minimum_size.x = 780
	for field in fields: field.value_changed.connect(func(_v): changed())
	enabled.toggled.connect(func(_v): changed())
	streaming.toggled.connect(func(_v): changed())
	city.toggled.connect(func(_v): changed())
	scale.value_changed.connect(func(_v): changed())
	for origin_field: SpinBox in [ui.import_origin_x, ui.import_origin_y]:
		origin_field.value_changed.connect(func(_v):
			if not placing_origin: origin_denominator = 0)
	exclusions.toggled.connect(func(_v): changed())
	dialog.confirmed.connect(finish_selection)
	dialog.canceled.connect(func():
		if not guided: ui.import_dialog.popup_centered(Vector2i(760,550))
		else: ui._status(I18N.t("Import discarded · document unchanged")))
	ui.add_child(dialog)
	changed()

func bbox() -> Array:
	var result := []
	# Match the displayed six-decimal source boundary, not SpinBox step noise.
	for field in fields: result.append(float("%.6f" % field.value))
	return result

var _scale_key := ""
var _scale_value := {}
## The map's stored OSM scale ({"denominator": D, 0 without OSM} or {"error"}).
## City notices can be megabytes: parse them again only when the attribution
## list changes (open, new, adoption, Undo/Redo), keyed by source and length.
func map_scale() -> Dictionary:
	var parts := PackedStringArray()
	for attribution: Dictionary in ui.store.document.get("attributions", []):
		parts.append("%s\t%d" % [str(attribution.get("source", "")), str(attribution.get("notice", "")).length()])
	var key := "\n".join(parts)
	if key != _scale_key or _scale_value.is_empty():
		_scale_key = key
		_scale_value = UNITS.osm_scale(ui.store.document)
	return _scale_value

## Stored D of the map's OSM layers, 0 when it has none (or an invalid scale).
func locked_denominator() -> int:
	return int(map_scale().get("denominator", 0))

## Adoption scale 1:D of the next OSM import: the map's stored D for city
## optimization once the map has OSM layers, otherwise the chosen city scale;
## exact OSM is always 1:8.
## Road convention for generated markings and street furniture.
func traffic() -> Dictionary:
	return {"driving_side": "left" if driving_side.selected == 1 else "right", "signal_style": "vertical" if signal_style.selected == 1 else "horizontal"}

func denominator() -> int:
	if not (city.button_pressed and streaming.button_pressed): return UNITS.OSM_DENOMINATOR
	var locked := locked_denominator()
	return locked if locked > 0 else int(scale.value)

## Map-scale problems that refuse every OSM import before its job starts.
func scale_error() -> String:
	var stored := map_scale()
	if stored.has("error"): return stored.error
	var locked := int(stored.denominator)
	if locked > 0 and denominator() != locked: return "This map uses another OSM scale; import OSM with automatic city optimization (PBF streaming) at the map's scale."
	return ""

func error() -> String:
	var failure := scale_error()
	if failure != "": return failure
	if exclusions.button_pressed and not streaming.button_pressed: return "Object exclusion review requires PBF streaming."
	if streaming.button_pressed and not enabled.button_pressed: return "Enable crop and select a bbox for PBF streaming."
	if not enabled.button_pressed: return ""
	var b := bbox()
	if b[0] >= b[2] or b[1] >= b[3]: return "Require west < east and south < north; no dateline crossing."
	return ""

func changed() -> void:
	revision += 1
	city.disabled = not (enabled.button_pressed and streaming.button_pressed)
	# One map has one OSM scale: later imports reuse the scale already adopted.
	var locked := locked_denominator()
	if locked > 0 and int(scale.value) != locked: scale.set_value_no_signal(locked)
	scale.editable = locked == 0 and not city.disabled and city.button_pressed
	if origin_denominator > 0 and origin_denominator != denominator(): _place_origin()
	ui._discard_import()
	ui.osm_crop_button.set_meta("action_label", "Find area / OSM crop: %s…" % (I18N.t("on") if enabled.button_pressed else I18N.t("off")))
	preload("./workbench_style.gd").refresh_label(ui.osm_crop_button)
	area.set_bounds(bbox())
	var problem := error()
	status.text = I18N.diagnostic(problem) if problem != "" else (I18N.t("Crop enabled. All corners must be within 20 km of the projection origin.\nReview counts, estimates and exact exclusions before adoption.") if enabled.button_pressed else I18N.t("Crop disabled: import the complete supported snapshot."))
	if locked > 0 and problem != "" and scale_error() != "": status.text += "\n"+I18N.t("Map scale locked to 1:%d by the OSM layers already in this map.") % locked
	if guided: dialog.get_ok_button().disabled = problem != "" or source_path.text == ""
	if enabled.button_pressed and problem == "":
		var b := bbox()
		var d := denominator()
		var metres := Vector2((b[2]-b[0])*111320.0*cos(deg_to_rad((b[1]+b[3])*0.5)),(b[3]-b[1])*111320.0)/d
		status.text += "\n"+I18N.t("1:%d approximate map size: %.0f × %.0f m. Origin: %.6f, %.6f (longitude, latitude).") % [d,metres.x,metres.y,ui.import_origin_lon.value,ui.import_origin_lat.value]
		if locked > 0 and city.button_pressed and not city.disabled: status.text += "\n"+I18N.t("Map scale locked to 1:%d by the OSM layers already in this map.") % locked
		# The same area covers (8/D)² as many cells as at 1:8; warn before the import.
		var size := float(ui.store.document.get("cell_size_cm", 51200))
		var cells := ceili(metres.x*100.0/size)*ceili(metres.y*100.0/size)
		if city.button_pressed and not city.disabled and cells > 256: status.text += "\n"+I18N.t("About %d map cells at the current %d cm cell size: the city check warns above 256 cells and refuses more than 16384. Use larger cells, a smaller area or a larger scale number.") % [cells,int(size)]

func open() -> void:
	if ui.busy: return
	guided = false
	dialog.title = I18N.t("OSM derived geometry crop")
	dialog.ok_button_text = I18N.t("Keep selection")
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

func finish_search(job: RefCounted, result: Dictionary) -> void:
	if ui.generation != ui.worker_generation:
		ui._status("Document changed during PBF lookup; search again.")
		return
	if result.get("ok",false):
		places = result.data.places.duplicate(true)
		place_choices.clear()
		for place: Dictionary in places:
			place_choices.add_item("%s · admin %s · %s%s" % [place.name,place.admin_level,place.source_id," · unavailable" if place.issue != "" else ""])
		area.set_places(places)
		place_status.text = I18N.t("%d matching areas in %s. Select a name to inspect its boundary.") % [places.size(),result.data.source_name] if not places.is_empty() else I18N.t("No matching administrative area. Try its local name; English search needs an alias recorded in this PBF.")
		if not places.is_empty(): select_place(0)
		if job != null and not job.limit_warnings.is_empty(): place_status.text += "\n" + LIMITS.text(job.limit_warnings)
		if job != null and not job.adapter_texts.is_empty(): place_status.text += "\n" + "\n".join(job.adapter_texts)
	else: place_status.text = str(result.get("error",{}).get("message","PBF lookup failed."))
	ui._status(place_status.text)
	if search_callback.is_valid():
		search_callback.call(places.duplicate(true) if result.get("ok",false) else [])
		return
	dialog.popup_centered(Vector2i(840,680))

func select_place(index: int) -> void:
	if index < 0 or index >= places.size(): return
	var place: Dictionary = places[index]
	if place.issue != "": place_status.text = place.issue; return
	selected_areas = [place]
	_fit_areas()
	place_status.text = I18N.t("%s · source %s. Drag for another crop, or click to move its projection origin.") % [place.name,place.source_id]
	ui._status(place_status.text)

## Adds the chosen place to the union; the rectangle becomes their combined extent.
func add_place() -> void:
	var index := place_choices.selected
	if index < 0 or index >= places.size(): return
	var place: Dictionary = places[index]
	if place.issue != "": place_status.text = place.issue; return
	if selected_areas.any(func(p): return p.source_id == place.source_id): return
	if selected_areas.size() >= MAX_AREAS:
		place_status.text = I18N.t("At most %d areas can be combined.") % MAX_AREAS
		return
	selected_areas.append(place)
	_fit_areas()
	place_status.text = I18N.t("Combined areas: %s. The crop follows their exact boundaries.") % ", ".join(selected_areas.map(func(p): return str(p.name)))
	if selected_areas.size() > WARN_AREAS:
		var notes: Array = []
		LIMITS.note(notes, "osm_areas", selected_areas.size(), WARN_AREAS, "Combined administrative areas")
		place_status.text += "\n" + LIMITS.text(notes)
	ui._status(place_status.text)

func area_ids() -> Array:
	return selected_areas.map(func(p): return int(str(p.source_id).trim_prefix("relation/")))

func _fit_areas() -> void:
	var b: Array = selected_areas[0].bbox.duplicate()
	for place: Dictionary in selected_areas:
		b = [minf(b[0],place.bbox[0]),minf(b[1],place.bbox[1]),maxf(b[2],place.bbox[2]),maxf(b[3],place.bbox[3])]
	# Round outward to the UI precision so a boundary is never clipped by rounding.
	for i in range(4): fields[i].value = (floorf(b[i]*1000000.0) if i < 2 else ceilf(b[i]*1000000.0))/1000000.0
	enabled.button_pressed = true
	streaming.button_pressed = true
	set_origin(Vector2((b[0]+b[2])*0.5,(b[1]+b[3])*0.5))
	area.toggle_fit()

func set_origin(point: Vector2) -> void:
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = point.x
	ui.import_origin_lat.value = point.y
	_place_origin()
	area.center = point
	area.queue_redraw()
	changed()

var placing_origin := false
## OSM adoption divides all source metres by D, including this placement: the
## origin lands at the map centre. A later scale change places it again.
func _place_origin() -> void:
	var bounds: Dictionary = ui.store.document.bounds
	var d := denominator()
	placing_origin = true
	ui.import_origin_x.value = (bounds.min[0]+bounds.max[0])*0.005*d
	ui.import_origin_y.value = (bounds.min[1]+bounds.max[1])*0.005*d
	placing_origin = false
	origin_denominator = d

func open_guided() -> void:
	if ui.busy: return
	guided = true
	dialog.title = I18N.t("1. Choose PBF → 2. Select area → 3. Review → 4. Apply")
	dialog.ok_button_text = I18N.t("Review selected area")
	enabled.button_pressed = true
	streaming.button_pressed = true
	city.button_pressed = true
	changed()
	ui.import_dialog.hide()
	if source_path.text == "": source_dialog.popup_centered_ratio(0.7)
	else: dialog.popup_centered(Vector2i(840,680))

func finish_selection() -> void:
	if not guided:
		ui.import_dialog.popup_centered(Vector2i(760,550))
		return
	if error() != "" or source_path.text == "":
		ui._status(I18N.diagnostic(error()))
		dialog.popup_centered(Vector2i(840,680))
		return
	ui._start_import(source_path.text,ui.IMPORT_LAYER.OSM_LICENSE)
