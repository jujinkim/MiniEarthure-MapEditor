extends Control
const STORE := preload("./document_store.gd")
const CANVAS := preload("./map_canvas.gd")
const RENDERER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
var store := STORE.new()
var canvas: Control
var status_label: Label
var project_label: Label
var properties: VBoxContainer
var pending_record: Dictionary = {}
var layers: ItemList
var viewport: SubViewport
var preview_world: Node3D
var preview_x: SpinBox
var preview_y: SpinBox
var dialog: FileDialog
var dialog_action := ""
var busy := false
var worker := Thread.new()
var generation := 0
var worker_generation := 0
var import_dialog: ConfirmationDialog
var import_license: LineEdit
var selected_field := ""
var selected_record: Dictionary = {}

func _ready() -> void:
	_build_ui()
	store.changed.connect(_document_changed)
	store.new_document()
	var timer := Timer.new()
	timer.wait_time = 15
	timer.timeout.connect(func():
		if store.dirty:
			var failure := store.autosave()
			if failure != "":
				_status(failure)
	)
	add_child(timer)
	timer.start()

func _build_ui() -> void:
	var ui_theme := Theme.new()
	ui_theme.default_font_size = 16
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color(0.08, 0.1, 0.13, 0.94)
	panel.set_corner_radius_all(7)
	panel.content_margin_left = 12
	panel.content_margin_right = 12
	panel.content_margin_top = 8
	panel.content_margin_bottom = 8
	ui_theme.set_stylebox("panel", "PanelContainer", panel)
	var button := panel.duplicate()
	button.bg_color = Color("292f39")
	ui_theme.set_stylebox("normal", "Button", button)
	var active := panel.duplicate()
	active.bg_color = Color("766727")
	active.border_color = Color("ffe14c")
	active.set_border_width_all(1)
	ui_theme.set_stylebox("hover", "Button", active)
	ui_theme.set_stylebox("pressed", "Button", active)
	theme = ui_theme
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	var title := Label.new()
	title.text = "MINIEARTHURE   /   MAP EDITOR"
	title.add_theme_color_override("font_color", Color("ffe14c"))
	title.add_theme_font_size_override("font_size", 24)
	column.add_child(title)
	var bar := HBoxContainer.new()
	column.add_child(bar)
	for entry in [["New", _new], ["Open", _choose.bind("open")], ["Save", _save], ["Recover", _choose.bind("recover")], ["Undo", store.undo], ["Redo", store.redo], ["Validate", _validate], ["Import GeoJSON", _import_geojson], ["Export .memap", _export]]:
		_button(bar, entry[0], entry[1])
	project_label = Label.new()
	column.add_child(project_label)
	var split := HSplitContainer.new()
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(split)
	var left := VBoxContainer.new()
	left.custom_minimum_size.x = 170
	split.add_child(left)
	_label(left, "TOOLS")
	var group := ButtonGroup.new()
	for name in ["Select", "Road", "Building", "Forest", "Orchard"]:
		var tool_button := _button(left, name, func():
			canvas.tool = name
			canvas.draft.clear()
			canvas.queue_redraw()
		)
		tool_button.toggle_mode = true
		tool_button.button_group = group
		tool_button.button_pressed = name == "Select"
	_button(left, "Duplicate", func(): canvas.duplicate_selection())
	_label(left, "OBJECTS")
	layers = ItemList.new()
	layers.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layers.item_selected.connect(func(index):
		canvas.selected.assign([layers.get_item_text(index)])
		_selection(canvas.selected)
		canvas.queue_redraw()
	)
	left.add_child(layers)
	var center_split := HSplitContainer.new()
	center_split.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.add_child(center_split)
	canvas = CANVAS.new()
	canvas.store = store
	canvas.custom_minimum_size = Vector2(480, 420)
	canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	canvas.status.connect(_status)
	canvas.selection_changed.connect(_selection)
	center_split.add_child(canvas)
	var right := VBoxContainer.new()
	right.custom_minimum_size.x = 340
	center_split.add_child(right)
	_label(right, "PROPERTIES")
	properties = VBoxContainer.new()
	properties.custom_minimum_size.y = 230
	properties.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(properties)
	_button(right, "Apply properties", _apply_properties)
	var controls := HBoxContainer.new()
	right.add_child(controls)
	_label(controls, "Cell")
	preview_x = SpinBox.new()
	preview_y = SpinBox.new()
	for spin in [preview_x, preview_y]:
		spin.max_value = 127
		controls.add_child(spin)
	_button(controls, "3D Preview", _preview)
	var preview_container := SubViewportContainer.new()
	preview_container.stretch = true
	preview_container.custom_minimum_size = Vector2(340, 250)
	right.add_child(preview_container)
	viewport = SubViewport.new()
	viewport.size = Vector2i(680, 500)
	viewport.own_world_3d = true
	preview_container.add_child(viewport)
	preview_world = Node3D.new()
	viewport.add_child(preview_world)
	var camera := Camera3D.new()
	camera.name = "PreviewCamera"
	camera.far = 2000
	preview_world.add_child(camera)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -25, 0)
	preview_world.add_child(sun)
	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size.y = 48
	status_label.text = "Click vertices; right-click to finish. Shift-select. Drag polygons to move. Wheel zoom; middle-drag pan."
	column.add_child(status_label)
	dialog = FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.dir_selected.connect(_path_selected)
	dialog.file_selected.connect(_path_selected)
	add_child(dialog)
	import_dialog = ConfirmationDialog.new()
	import_dialog.title = "Import local-metre GeoJSON"
	import_dialog.dialog_text = "Coordinates must be local x/y metres. Geographic longitude/latitude is unsupported.\nA new layer is added; source files remain unchanged. Python 3 must be installed."
	import_license = LineEdit.new()
	import_license.placeholder_text = "Source license (required)"
	import_license.custom_minimum_size = Vector2(540, 40)
	import_dialog.add_child(import_license)
	import_dialog.get_ok_button().disabled = true
	import_license.text_changed.connect(func(value): import_dialog.get_ok_button().disabled = value.strip_edges() == "")
	import_dialog.confirmed.connect(func(): _choose("import"))
	add_child(import_dialog)

func _button(parent: Node, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _label(parent: Node, text: String) -> void:
	var label := Label.new()
	label.text = text
	parent.add_child(label)

func _new() -> void:
	if store.dirty:
		var failure := store.autosave()
		if failure != "":
			_status(failure)
			return
	store.new_document()
	_status("New map. Previous unsaved map retained in recovery snapshots.")

func _choose(action: String) -> void:
	dialog_action = action
	dialog.filters = PackedStringArray()
	if action in ["open", "save"]:
		dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	else:
		dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE if action == "export" else FileDialog.FILE_MODE_OPEN_FILE
		dialog.filters = PackedStringArray(["*.memap ; Map package"] if action == "export" else ["*.json ; Recovery snapshot"])
		if action == "import":
			dialog.filters = PackedStringArray(["*.geojson,*.json ; Local-metre GeoJSON"])
		if action == "recover":
			dialog.current_dir = ProjectSettings.globalize_path("user://recovery")
	dialog.popup_centered_ratio(0.8)

func _path_selected(path: String) -> void:
	var failure := ""
	match dialog_action:
		"import":
			_start_worker("import", path, import_license.text.strip_edges())
			return
		"open":
			if store.dirty:
				failure = store.autosave()
			if failure == "":
				failure = store.open_project(path)
		"save": failure = store.save_project(path)
		"recover": failure = store.recover(path)
		"export":
			if busy:
				_status("Wait for the current preview or export.")
				return
			failure = store.save_project(store.project_path)
			if failure == "":
				_start_worker("export", store.project_path, path)
				return
	_status(failure if failure != "" else "Ready: " + path)
	_document_changed()

func _save() -> void:
	if busy:
		_status("Wait for the active operation before saving.")
		return
	if store.project_path == "":
		_choose("save")
	else:
		var failure := store.save_project(store.project_path)
		_status(failure if failure != "" else "Project saved.")
		_document_changed()

func _import_geojson() -> void:
	if not busy:
		import_dialog.popup_centered(Vector2i(700, 180))

func _export() -> void:
	if store.project_path == "":
		_status("Save the project to a directory before exporting.")
		return
	_choose("export")

func _validate() -> void:
	var result: Dictionary = JSON.parse_string(store.bridge.validate_document(JSON.stringify(store.document)))
	_status("Document valid. Export also verifies files and terrain seams." if result.ok else store.reason(result))

func _selection(ids: Array) -> void:
	selected_record = {}
	selected_field = ""
	if ids.size() == 1:
		for field in ["roads", "buildings", "zones", "placements"]:
			for record: Dictionary in store.document[field]:
				if str(record.id) == str(ids[0]):
					selected_record = record.duplicate(true)
					selected_field = field
	for child in properties.get_children():
		child.queue_free()
	pending_record = selected_record.duplicate(true)
	if selected_record.is_empty():
		_label(properties, "Select one object.")
		return
	_label(properties, str(selected_record.id))
	match selected_field:
		"buildings":
			_number_property("Height (m)", float(selected_record.height_cm) / 100.0, 0.1, 1000.0, func(v): pending_record.height_cm = int(round(v * 100)))
			_number_property("Base elevation (m)", float(selected_record.base_cm) / 100.0, -10000.0, 10000.0, func(v): pending_record.base_cm = int(round(v * 100)))
		"roads":
			_number_property("Width (m)", float(selected_record.widths_cm[0]) / 100.0, 0.2, 100.0, func(v):
				for i in range(pending_record.widths_cm.size()):
					pending_record.widths_cm[i] = int(round(v * 100))
			)
			_choice_property("Surface", ["asphalt", "concrete", "dirt", "gravel", "grass"], str(selected_record.surfaces[0]), func(v):
				for i in range(pending_record.surfaces.size()):
					pending_record.surfaces[i] = v
			)
			_label(properties, "Structure: " + str(selected_record.kind))
		"zones":
			_number_property("Spacing (m)", float(selected_record.spacing_cm) / 100.0, 2.0, 200.0, func(v): pending_record.spacing_cm = int(round(v * 100)))
			_number_property("Density (%)", float(selected_record.density_per_mille) / 10.0, 0.0, 100.0, func(v): pending_record.density_per_mille = int(round(v * 10)))
			_choice_property("Planting", ["forest", "orchard"], str(selected_record.kind), func(v): pending_record.kind = v)

func _number_property(label: String, value: float, minimum: float, maximum: float, change: Callable) -> void:
	var row := HBoxContainer.new()
	properties.add_child(row)
	_label(row, label)
	var spin := SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = 0.1
	spin.value = value
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spin.value_changed.connect(change)
	row.add_child(spin)

func _choice_property(label: String, values: Array, current: String, change: Callable) -> void:
	var row := HBoxContainer.new()
	properties.add_child(row)
	_label(row, label)
	var select := OptionButton.new()
	for value: String in values:
		select.add_item(value.capitalize())
	select.selected = values.find(current)
	select.item_selected.connect(func(index): change.call(values[index]))
	row.add_child(select)

func _apply_properties() -> void:
	if selected_record.is_empty():
		return
	var failure := store.apply_command("Edit properties", [{"field": selected_field, "id": selected_record.id, "before": selected_record, "after": pending_record}])
	_status(failure if failure != "" else "Properties updated.")
	_selection(canvas.selected)

func _document_changed() -> void:
	generation += 1
	canvas.queue_redraw()
	layers.clear()
	for field in ["roads", "buildings", "zones", "placements"]:
		for record: Dictionary in store.document.get(field, []):
			layers.add_item(str(record.id))
	project_label.text = (store.project_path if store.project_path != "" else "Unsaved project") + ("  • modified" if store.dirty else "")

func _preview() -> void:
	if busy:
		_status("Preview or export already running.")
		return
	if not store.document.heightmaps.is_empty():
		_status("Heightmap preview requires a saved project.")
		if store.project_path == "":
			return
		var failure := store.save_project(store.project_path)
		if failure != "":
			_status(failure)
			return
		_start_worker("project", store.project_path, "")
	else:
		_start_worker("document", JSON.stringify(store.document), "")

func _start_worker(operation: String, source: String, destination: String) -> void:
	if busy:
		_status("Another operation is running.")
		return
	busy = true
	worker_generation = generation
	var x := int(preview_x.value)
	var y := int(preview_y.value)
	var import_script := ProjectSettings.globalize_path("user://importers/geojson.py")
	if operation == "import":
		var source_code := FileAccess.get_file_as_string("res://scripts/importers/geojson.py")
		var failure := store._atomic_write(import_script, source_code)
		if failure != "" or source_code == "":
			busy = false
			_status(failure if failure != "" else "GeoJSON importer is missing.")
			return
	var import_output := ProjectSettings.globalize_path("user://import-" + Crypto.new().generate_random_bytes(8).hex_encode() + ".json")
	var err := worker.start(func():
		if operation == "import":
			var log: Array = []
			var exit_code := OS.execute("python3", [import_script, source, import_output, "--coordinates", "local-metres", "--license", destination], log, true)
			var result := {"ok": false, "error": {"code": "E_IMPORT", "message": "\n".join(log)}}
			if exit_code == 0 and FileAccess.file_exists(import_output):
				result = {"ok": true, "data": JSON.parse_string(FileAccess.get_file_as_string(import_output))}
				DirAccess.remove_absolute(import_output)
			return {"operation": operation, "result": result}
		var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
		var text := ""
		if operation == "export":
			text = bridge.export_project(source, destination)
		elif operation == "project":
			text = bridge.open_project(source)
			if JSON.parse_string(text).ok:
				text = bridge.generate_chunk(x, y)
		else:
			text = bridge.preview_document(source, x, y)
		return {"operation": operation, "result": JSON.parse_string(text)}
	)
	if err != OK:
		busy = false
		_status(error_string(err))
	else:
		_status("Importing local GeoJSON…" if operation == "import" else ("Exporting package…" if operation == "export" else "Generating preview cell…"))

func _process(_delta: float) -> void:
	if not busy or worker.is_alive():
		return
	var output: Dictionary = worker.wait_to_finish()
	busy = false
	var result: Dictionary = output.result
	if not result.ok:
		_status(store.reason(result))
		return
	if output.operation == "import":
		if generation != worker_generation:
			_status("Document changed during import; retry to add the new layer.")
			return
		var layer: Dictionary = result.data
		var source := str(layer.source) + "#" + str(layer.layer_id)
		var patches: Array = layer.patches
		patches.append({"field": "attributions", "id": source, "before": null, "after": {"source": source, "license": layer.license, "notice": "Local-metre GeoJSON import; " + "; ".join(layer.warnings)}})
		var failure := store.apply_command("Import " + str(layer.source), patches)
		_status(failure if failure != "" else "Imported new layer. " + " · ".join(layer.warnings))
		return
	if output.operation == "export":
		_status("Exported %d bytes  ·  user assets %d expanded bytes  ·  %s" % [result.data.package_bytes, result.data.user_asset_bytes, result.data.world_content_hash.left(12)])
		return
	if generation != worker_generation:
		_status("Document changed during preview; generate again.")
		return
	for child in preview_world.get_children():
		if child.name != "PreviewCamera" and child is not DirectionalLight3D:
			child.queue_free()
	RENDERER.attach(result.data.chunk, preview_world)
	var bounds: Dictionary = store.document.bounds
	var cell_size := float(store.document.cell_size_cm)
	var center := RENDERER.scene_position([bounds.min[0] + (preview_x.value + 0.5) * cell_size, 0, bounds.min[1] + (preview_y.value + 0.5) * cell_size])
	var camera: Camera3D = preview_world.get_node("PreviewCamera")
	camera.position = center + Vector3(35, 55, 45) * cell_size / 51200.0
	camera.look_at(center)
	_status("Preview ready  ·  " + str(result.data.generated_sha256))

func _unhandled_key_input(event: InputEvent) -> void:
	if event is not InputEventKey or not event.pressed or event.echo:
		return
	if event.ctrl_pressed:
		match event.keycode:
			KEY_S: _save()
			KEY_Z:
				if event.shift_pressed:
					store.redo()
				else:
					store.undo()
			KEY_Y: store.redo()
			KEY_D: canvas.duplicate_selection()
	elif event.keycode == KEY_ESCAPE:
		canvas.draft.clear()
		canvas.queue_redraw()

func _status(text: String) -> void:
	status_label.text = text

func _exit_tree() -> void:
	if worker.is_started():
		worker.wait_to_finish()
	if store.dirty:
		store.autosave()
