extends Control
const TEST_DRIVE := preload("./test_drive_launcher.gd")
var test_drive_launcher := TEST_DRIVE.new()
var drive_dialog: ConfirmationDialog
var client_dialog: FileDialog
var client_path: LineEdit
var drive_x: SpinBox
var drive_y: SpinBox
var drive_surface: OptionButton
var drive_request: Dictionary = {}
var last_drive_result: Dictionary = {}
const AUTHOR_PANEL := preload("./authoring_panel.gd")
var author_panel: AcceptDialog
const STORE := preload("./document_store.gd")
const CANVAS := preload("./map_canvas.gd")
const RENDERER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
var store := STORE.new()
var canvas: Control
var status_label: Label
var project_label: Label
var properties: VBoxContainer
const EDIT := preload("./workbench_edit.gd")
const LAYERS := preload("./workbench_layers.gd")
var layers: VBoxContainer
var left_dock: VBoxContainer
var right_dock: VSplitContainer
var outer_split: HSplitContainer
var center_split: HSplitContainer
var validation_label: Label
var selection_label: Label
var apply_button: Button
var property_changes := {}
var property_records: Array[Dictionary] = []
var tool_buttons := {}
var snap_toggle: CheckButton
var snap_size: SpinBox
var view_settings := ConfigFile.new()
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
var displayed_map_id := ""

func _ready() -> void:
	get_tree().auto_accept_quit = false
	get_window().min_size = Vector2i(1024, 720)
	_build_ui()
	store.changed.connect(_document_changed)
	store.new_document()
	_restore_workbench.call_deferred()
	var timer := Timer.new()
	timer.wait_time = 15
	timer.timeout.connect(_autosave)
	add_child(timer)
	timer.start()
	if DirAccess.dir_exists_absolute(ProjectSettings.globalize_path("user://recovery")):
		_status("Recovery snapshots are available. Use Recover to inspect one; saved projects stay unchanged.")

func _autosave() -> void:
	if store.dirty:
		var failure := store.autosave()
		if failure != "":
			_status(failure)

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		var failure := store.autosave() if store.dirty else ""
		if failure != "":
			_status("Cannot close safely: " + failure)
			return
		get_tree().quit()

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
	ui_theme.set_stylebox("panel", "Tree", panel)
	ui_theme.set_stylebox("selected", "Tree", active)
	ui_theme.set_stylebox("selected_focus", "Tree", active)
	ui_theme.set_color("font_color", "Tree", Color("e1e3e6"))
	ui_theme.set_icon("unchecked", "Tree", _checkbox_icon(false))
	ui_theme.set_icon("checked", "Tree", _checkbox_icon(true))
	var focus_style := StyleBoxFlat.new()
	focus_style.bg_color = Color(0, 0, 0, 0)
	focus_style.border_color = Color("ffe14c")
	focus_style.set_border_width_all(1)
	for control in ["Button", "Tree", "LineEdit"]:
		ui_theme.set_stylebox("focus", control, focus_style)
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
	var bar := HFlowContainer.new()
	column.add_child(bar)
	for entry in [["New", _new], ["Open", _choose.bind("open")], ["Save", _save], ["Save As", _choose.bind("save")], ["Recover", _choose.bind("recover")], ["Undo", _history.bind(false)], ["Redo", _history.bind(true)], ["Validate", _validate], ["Import GeoJSON", _import_geojson], ["Export .memap", _export], ["Test Drive", _test_drive]]:
		_button(bar, entry[0], entry[1])
	project_label = Label.new()
	project_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	column.add_child(project_label)
	outer_split = HSplitContainer.new()
	var split := outer_split
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(split)
	canvas = CANVAS.new()
	canvas.store = store
	canvas.custom_minimum_size = Vector2(300, 280)
	canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	canvas.status.connect(_status)
	canvas.selection_changed.connect(_selection)
	left_dock = VBoxContainer.new()
	var left := left_dock
	left.custom_minimum_size.x = 245
	split.add_child(left)
	_label(left, "TOOLS")
	var tool_scroll := ScrollContainer.new()
	tool_scroll.custom_minimum_size.y = 72
	tool_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tool_scroll.size_flags_stretch_ratio = 0.65
	tool_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left.add_child(tool_scroll)
	var tool_controls := VBoxContainer.new()
	tool_controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tool_scroll.add_child(tool_controls)
	var tools := HFlowContainer.new()
	tool_controls.add_child(tools)
	var group := ButtonGroup.new()
	for name in ["Select", "Road", "Building", "Forest", "Orchard", "Terrain", "Place", "Repeat", "Entrance", "Exclusion"]:
		var tool_button := _button(tools, name, _set_tool.bind(name))
		tool_button.toggle_mode = true
		tool_button.button_group = group
		tool_button.button_pressed = name == "Select"
		tool_buttons[name] = tool_button
	author_panel = AUTHOR_PANEL.new()
	author_panel.editor = self
	add_child(author_panel)
	_button(left, "Authoring settings…", func(): author_panel.open())
	var edits := HBoxContainer.new()
	left.add_child(edits)
	_button(edits, "Duplicate", func(): canvas.duplicate_selection())
	_button(edits, "Delete", func(): canvas.delete_selection())
	var snap := HBoxContainer.new()
	left.add_child(snap)
	snap_toggle = CheckButton.new()
	snap_toggle.text = "Snap (m)"
	snap_toggle.button_pressed = true
	snap_toggle.toggled.connect(func(value):
		canvas.cancel_interaction()
		canvas.snap_enabled = value
	)
	snap.add_child(snap_toggle)
	snap_size = SpinBox.new()
	snap_size.min_value = 0.01
	snap_size.max_value = 100
	snap_size.step = 0.01
	snap_size.value = 1
	snap_size.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	snap_size.value_changed.connect(func(value):
		canvas.cancel_interaction()
		canvas.snap_cm = round(value * 100)
	)
	snap.add_child(snap_size)
	layers = LAYERS.new()
	layers.canvas = canvas
	layers.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layers.state_changed.connect(_save_workbench)
	left.add_child(layers)
	center_split = HSplitContainer.new()
	center_split.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.add_child(center_split)
	var center := VBoxContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center_split.add_child(center)
	selection_label = Label.new()
	selection_label.text = "2D MAP  ·  Select  ·  0 selected"
	center.add_child(selection_label)
	canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.add_child(canvas)
	_label(center, "Wheel: zoom · Middle drag: pan · Shift: toggle · Empty drag: box")
	right_dock = VSplitContainer.new()
	right_dock.custom_minimum_size.x = 300
	center_split.add_child(right_dock)
	var property_dock := VBoxContainer.new()
	property_dock.custom_minimum_size.y = 140
	property_dock.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_dock.add_child(property_dock)
	_label(property_dock, "PROPERTIES")
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	property_dock.add_child(scroll)
	properties = VBoxContainer.new()
	properties.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(properties)
	apply_button = _button(property_dock, "Apply properties", _apply_properties)
	var preview_dock := VBoxContainer.new()
	preview_dock.custom_minimum_size.y = 160
	preview_dock.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_dock.add_child(preview_dock)
	var controls := HBoxContainer.new()
	preview_dock.add_child(controls)
	_label(controls, "Cell")
	preview_x = SpinBox.new()
	preview_y = SpinBox.new()
	for spin in [preview_x, preview_y]:
		spin.min_value = 0
		spin.max_value = 127
		controls.add_child(spin)
	_button(controls, "3D Preview", _preview)
	var preview_hint := Label.new()
	preview_hint.text = "Full cell preview · 2D layer filters do not change export"
	preview_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	preview_hint.add_theme_font_size_override("font_size", 12)
	preview_dock.add_child(preview_hint)
	var preview_container := SubViewportContainer.new()
	preview_container.stretch = true
	preview_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	preview_container.custom_minimum_size = Vector2(280, 100)
	preview_dock.add_child(preview_container)
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
	var view_bar := HBoxContainer.new()
	column.add_child(view_bar)
	_button(view_bar, "Tools / layers", func(): left_dock.visible = not left_dock.visible)
	_button(view_bar, "Properties / 3D", func(): right_dock.visible = not right_dock.visible)
	_button(view_bar, "Fit map (F)", func(): canvas.fit_map())
	_button(view_bar, "Reset panels", _reset_panels)
	validation_label = Label.new()
	validation_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	validation_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	view_bar.add_child(validation_label)
	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size.y = 48
	status_label.text = "V Select · R Road · B Building · G Forest · O Orchard · Ctrl/Cmd+A/D/Z/Y/S · Delete · Escape cancels"
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
	_build_test_drive_dialog()

func _checkbox_icon(checked: bool) -> Texture2D:
	var icon := Image.new()
	var tick := '<path d="M4 8l3 3 5-6" fill="none" stroke="#ffe14c" stroke-width="2"/>' if checked else ""
	icon.load_svg_from_string('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect x="1" y="1" width="14" height="14" rx="2" fill="#15181e" stroke="#b8bcc5"/>' + tick + '</svg>')
	return ImageTexture.create_from_image(icon)

func _button(parent: Node, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func _label(parent: Node, text: String) -> void:
	var label := Label.new()
	label.text = text
	if parent is VBoxContainer:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
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
	if action in ["open", "save", "save_for_drive"]:
		dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	else:
		dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE if action == "export" else FileDialog.FILE_MODE_OPEN_FILE
		dialog.filters = PackedStringArray(["*.memap ; Map package"] if action == "export" else ["*.json ; Recovery snapshot"])
		if action == "import":
			dialog.filters = PackedStringArray(["*.geojson,*.json ; Local-metre GeoJSON"])
		if action == "recover":
			dialog.filters = PackedStringArray(["* ; Recovery, previous or pending document"])
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
		"save_for_drive":
			failure = store.save_project(path)
			if failure == "":
				_document_changed()
				_test_drive()
				return
		"recover":
			if store.dirty:
				failure = store.autosave()
			if failure == "":
				failure = store.recover(path)
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
	validation_label.text = "Valid document · Files/seams checked on export" if result.ok else store.reason(result)
	_status(validation_label.text)

func _selection(ids: Array) -> void:
	selected_record = {}
	selected_field = ""
	property_records.clear()
	property_changes.clear()
	for entry in EDIT.entries(store.document):
		if (entry.key in ids or str(entry.record.id) in ids) and canvas.available(entry, true):
			property_records.append(entry.duplicate(true))
	for child in properties.get_children():
		properties.remove_child(child)
		child.queue_free()
	if layers != null: layers.sync_selection()
	selection_label.text = "2D MAP  ·  %s  ·  %d selected" % [canvas.tool, property_records.size()]
	apply_button.disabled = property_records.is_empty()
	if property_records.is_empty():
		_label(properties, "Select objects on the map or in layers.")
		_label(properties, "Shift toggles; drag empty space to box-select.")
		return
	selected_field = property_records[0].field
	selected_record = property_records[0].record.duplicate(true)
	var title := Label.new()
	title.text = str(selected_record.id) if property_records.size() == 1 else "%d objects selected" % property_records.size()
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	properties.add_child(title)
	_number_property("Move X (m)", 0, -100000, 100000, func(v): property_changes.move_x = int(round(v * 100)))
	_number_property("Move Y (m)", 0, -100000, 100000, func(v): property_changes.move_y = int(round(v * 100)))
	for entry in property_records:
		if entry.field != selected_field:
			_label(properties, "Mixed types · translation only")
			return
	if property_records.size() > 1:
		_label(properties, "Only changed fields apply to all selected objects.")
	match selected_field:
		"buildings":
			_number_property("Height (m)", float(selected_record.height_cm) / 100.0, 0.1, 1000.0, func(v): property_changes.height_cm = int(round(v * 100)))
			_choice_property("Use", ["residential", "commercial", "industrial", "public"], str(selected_record.usage), func(v): property_changes.usage = v)
			_choice_property("Material", ["concrete", "brick", "wood"], str(selected_record.material), func(v): property_changes.material = v)
			_choice_property("Roof", ["flat", "gable"], str(selected_record.roof), func(v): property_changes.roof = v)
			_number_property("Base (m)", float(selected_record.base_cm) / 100.0, -10000.0, 10000.0, func(v): property_changes.base_cm = int(round(v * 100)))
		"roads":
			_number_property("All widths (m)", float(selected_record.widths_cm[0]) / 100.0, 0.2, 100.0, func(v): property_changes.width_cm = int(round(v * 100)))
			_choice_property("All surfaces", ["asphalt", "concrete", "dirt", "gravel", "grass"], str(selected_record.surfaces[0]), func(v): property_changes.surface = v)
			_label(properties, "Structure: " + str(selected_record.kind))
			_label(properties, "Moving endpoints also moves incident road ends.")
		"zones":
			_number_property("Spacing (m)", float(selected_record.spacing_cm) / 100.0, 2.0, 200.0, func(v): property_changes.spacing_cm = int(round(v * 100)))
			_number_property("Density (%)", float(selected_record.density_per_mille) / 10.0, 0.0, 100.0, func(v): property_changes.density_per_mille = int(round(v * 10)))
			_choice_property("Planting", ["forest", "orchard"], str(selected_record.kind), func(v): property_changes.kind = v)
		"placements":
			_label(properties, "Asset: " + str(selected_record.asset_id))
			_choice_property("Rotation", ["0", "90", "180", "270"], str(int(selected_record.quarter_turns) * 90), func(v): property_changes.quarter_turns = int(v) / 90)
		"repetitions":
			_label(properties, "Asset: " + str(selected_record.asset_id))
			_number_property("Spacing (m)", float(selected_record.spacing_cm) / 100.0, 0.01, 1000.0, func(v): property_changes.spacing_cm = int(round(v * 100)))
		"nodes":
			_label(properties, "Shared road endpoint · level " + str(selected_record.level))

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
	canvas.cancel_interaction()
	if property_records.is_empty(): return
	var delta := Vector2(property_changes.get("move_x", 0), property_changes.get("move_y", 0))
	var plan := EDIT.plan(store.document, canvas.selected, "move", delta)
	var patches: Array = plan.patches
	for entry in property_records:
		if not canvas.available(entry, true):
			_status("Selection is hidden or locked.")
			return
		var after: Dictionary = entry.record.duplicate(true)
		var existing := -1
		for i in range(patches.size()):
			if EDIT.key(patches[i].field, patches[i].id) == entry.key:
				after = patches[i].after
				existing = i
		for key: String in property_changes:
			if key in ["move_x", "move_y"]: continue
			if key == "width_cm": after.widths_cm.fill(property_changes[key])
			elif key == "surface": after.surfaces.fill(property_changes[key])
			else: after[key] = property_changes[key]
		if existing >= 0: patches[existing].after = after
		elif after != entry.record: patches.append(EDIT.patch(entry.field, entry.record, after))
	for entry in EDIT.entries(store.document):
		if entry.key in plan.affected and not canvas.available(entry, true):
			_status("Movement affects a hidden or locked layer: " + entry.key)
			return
	var failure: String = canvas.author.apply("Edit selection properties", patches, selected_field == "roads")
	_status(failure if failure != "" else "Properties updated.")
	if failure == "": _selection(canvas.selected)

func _document_changed() -> void:
	generation += 1
	canvas.cancel_interaction()
	var map_id := str(store.document.get("map_id", ""))
	if displayed_map_id != map_id:
		canvas.selected.clear()
		canvas.layer_state = view_settings.get_value("layers", map_id, {}).duplicate(true)
		canvas.fit_map()
	displayed_map_id = map_id
	canvas.normalize_selection()
	layers.refresh()
	_selection(canvas.selected)
	validation_label.text = "Document valid · Preview needs refresh"
	var bounds: Dictionary = store.document.bounds
	preview_x.max_value = ceili(float(bounds.max[0] - bounds.min[0]) / store.document.cell_size_cm) - 1
	preview_y.max_value = ceili(float(bounds.max[1] - bounds.min[1]) / store.document.cell_size_cm) - 1
	project_label.text = (store.project_path if store.project_path != "" else "Unsaved project") + ("  • modified" if store.dirty else "")
	canvas.queue_redraw()

func _set_tool(name: String) -> void:
	canvas.tool = name
	tool_buttons[name].button_pressed = true
	_selection(canvas.selected)
	canvas.queue_redraw()

func _reset_panels() -> void:
	left_dock.show()
	right_dock.show()
	outer_split.split_offset = 0
	center_split.split_offset = int(size.x * 0.35)
	right_dock.split_offset = 0

func _restore_workbench() -> void:
	view_settings.load("user://workbench.cfg")
	left_dock.visible = bool(view_settings.get_value("panels", "left_visible", true))
	right_dock.visible = bool(view_settings.get_value("panels", "right_visible", true))
	outer_split.split_offset = int(view_settings.get_value("panels", "left", 0))
	center_split.split_offset = int(view_settings.get_value("panels", "right", int(size.x * 0.35)))
	right_dock.split_offset = int(view_settings.get_value("panels", "vertical", 0))
	snap_toggle.button_pressed = bool(view_settings.get_value("snap", "enabled", true))
	snap_size.value = clampf(float(view_settings.get_value("snap", "metres", 1.0)), 0.01, 100.0)
	canvas.layer_state = view_settings.get_value("layers", displayed_map_id, {}).duplicate(true)
	layers.refresh()

func _save_workbench() -> void:
	if canvas == null or left_dock == null: return
	view_settings.set_value("panels", "left_visible", left_dock.visible)
	view_settings.set_value("panels", "right_visible", right_dock.visible)
	view_settings.set_value("panels", "left", outer_split.split_offset)
	view_settings.set_value("panels", "right", center_split.split_offset)
	view_settings.set_value("panels", "vertical", right_dock.split_offset)
	view_settings.set_value("snap", "enabled", canvas.snap_enabled)
	view_settings.set_value("snap", "metres", canvas.snap_cm / 100.0)
	if displayed_map_id != "": view_settings.set_value("layers", displayed_map_id, canvas.layer_state)
	var failure := view_settings.save("user://workbench.cfg")
	if failure != OK: _status("Workbench settings could not be saved: " + error_string(failure))

func _preview() -> void:
	if busy:
		_status("Preview or export already running.")
		return
	if not store.document.heightmaps.is_empty() or not store.document.assets.is_empty():
		_status("Asset/heightmap preview requires a saved project.")
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
	var test_request := drive_request.duplicate(true)
	var x := int(preview_x.value)
	var y := int(preview_y.value)
	var import_script := ProjectSettings.globalize_path("user://importers/geojson.py")
	if operation == "import":
		var source_code := FileAccess.get_file_as_string("res://scripts/importers/geojson.py")
		var failure := store.files.write(import_script, source_code, store.files.digest(import_script))
		if failure != "" or source_code == "":
			busy = false
			_status(failure if failure != "" else "GeoJSON importer is missing.")
			return
	var import_output := ProjectSettings.globalize_path("user://import-" + Crypto.new().generate_random_bytes(8).hex_encode() + ".json")
	var err := worker.start(func():
		if operation == "test_drive":
			return {"operation": operation, "result": TEST_DRIVE.prepare(source, destination, test_request.document, test_request.x_cm, test_request.y_cm, test_request.surface)}
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
				var prepared: Dictionary = bridge.generate_chunk_packed(x, y)
				if prepared.ok: prepared = bridge.with_presentation(prepared.data)
				return {"operation": operation, "result": prepared}
		else:
			return {"operation": operation, "result": bridge.preview_document_packed(source, x, y)}
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
		if output.operation == "test_drive":
			last_drive_result = result
		_status(store.reason(result))
		return
	if output.operation == "test_drive":
		if generation != worker_generation:
			last_drive_result = TEST_DRIVE.error("E_DOCUMENT_CHANGED", "Document changed during packaging; snapshot retained. Start test drive again.")
			_status(store.reason(last_drive_result))
			return
		last_drive_result = test_drive_launcher.launch(drive_request.client, result.data.path, drive_request.x_cm, drive_request.y_cm, drive_request.surface)
		_status("Client launched (PID %d). Close Client to end the test. Snapshot: %s" % [last_drive_result.data.pid, result.data.path] if last_drive_result.ok else store.reason(last_drive_result))
		return
	if output.operation == "import":
		if generation != worker_generation:
			_status("Document changed during import; retry to add the new layer.")
			return
		var layer: Dictionary = result.data
		var source := str(layer.source) + "#" + str(layer.layer_id)
		var patches: Array = layer.patches
		var attribution := {"source": source, "license": layer.license, "notice": "Local-metre GeoJSON import; " + "; ".join(layer.warnings)}
		patches.append({"field": "attributions", "id": store.record_id("attributions", attribution), "before": null, "after": attribution})
		var failure := store.apply_command("Import " + str(layer.source), patches)
		_status(failure if failure != "" else "Imported new layer. " + " · ".join(layer.warnings))
		return
	if output.operation == "export":
		_status("Exported %d bytes  ·  user assets %d expanded bytes  ·  %s" % [result.data.package_bytes, result.data.user_asset_bytes, result.data.world_content_hash.left(12)])
		return
	if generation != worker_generation:
		_status("Document changed during preview; generate again.")
		return
	var staged := Node3D.new()
	preview_world.add_child(staged)
	var render_job := RENDERER.begin(result.data.chunk, staged)
	while not RENDERER.advance(render_job): pass
	if not render_job.error.is_empty():
		staged.queue_free()
		_status(store.reason({"ok": false, "error": render_job.error}))
		return
	for child in preview_world.get_children():
		if child != staged and child.name != "PreviewCamera" and child is not DirectionalLight3D:
			child.queue_free()
	var bounds: Dictionary = store.document.bounds
	var cell_size := float(store.document.cell_size_cm)
	var center := RENDERER.scene_position([bounds.min[0] + (preview_x.value + 0.5) * cell_size, 0, bounds.min[1] + (preview_y.value + 0.5) * cell_size])
	var camera: Camera3D = preview_world.get_node("PreviewCamera")
	camera.position = center + Vector3(35, 55, 45) * cell_size / 51200.0
	camera.look_at(center)
	validation_label.text = "Preview ready · cell %d / %d" % [preview_x.value, preview_y.value]
	_status(validation_label.text)

func _unhandled_key_input(event: InputEvent) -> void:
	if event is not InputEventKey or not event.pressed or event.echo: return
	var focus := get_viewport().gui_get_focus_owner()
	if focus is LineEdit or focus is TextEdit or author_panel.visible: return
	var handled := true
	if event.ctrl_pressed or event.meta_pressed:
		match event.keycode:
			KEY_S: _save()
			KEY_Z: _history(event.shift_pressed)
			KEY_Y: _history(true)
			KEY_D: canvas.duplicate_selection()
			KEY_A: canvas.select_all()
			_: handled = false
	else:
		match event.keycode:
			KEY_ESCAPE: canvas.cancel_interaction()
			KEY_DELETE, KEY_BACKSPACE:
				if not canvas.draft.is_empty():
					canvas.draft.pop_back()
					canvas.queue_redraw()
				else: canvas.delete_selection()
			KEY_V: _set_tool("Select")
			KEY_R: _set_tool("Road")
			KEY_B: _set_tool("Building")
			KEY_G: _set_tool("Forest")
			KEY_O: _set_tool("Orchard")
			KEY_F: canvas.fit_map()
			_: handled = false
	if handled: get_viewport().set_input_as_handled()

func _history(forward: bool) -> void:
	canvas.cancel_interaction()
	var failure := store.redo() if forward else store.undo()
	if failure != "":
		_status(failure)

func _status(text: String) -> void:
	if busy and text.begins_with("x "): return
	if validation_label != null and text.contains("E_"):
		validation_label.text = "Edit/operation rejected · " + text
	status_label.text = text

func _exit_tree() -> void:
	_save_workbench()
	if worker.is_started():
		worker.wait_to_finish()
	if store.dirty:
		store.autosave()


func _build_test_drive_dialog() -> void:
	drive_dialog = ConfirmationDialog.new()
	drive_dialog.title = "Test Drive"
	drive_dialog.ok_button_text = "Save, Package and Launch"
	drive_dialog.theme = theme
	var layout := VBoxContainer.new()
	layout.custom_minimum_size = Vector2(650, 270)
	drive_dialog.add_child(layout)
	_label(layout, "Saves the current project and opens a separate snapshot in installed Client.")
	var path_row := HBoxContainer.new()
	layout.add_child(path_row)
	client_path = LineEdit.new()
	client_path.placeholder_text = "Installed MiniEarthure Client executable"
	client_path.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	path_row.add_child(client_path)
	_button(path_row, "Browse", func(): client_dialog.popup_centered_ratio(0.8))
	var coordinates := HBoxContainer.new()
	layout.add_child(coordinates)
	_label(coordinates, "x (m)")
	drive_x = SpinBox.new()
	coordinates.add_child(drive_x)
	_label(coordinates, "y (m)")
	drive_y = SpinBox.new()
	coordinates.add_child(drive_y)
	for spin in [drive_x, drive_y]:
		spin.step = 0.01
		spin.custom_minimum_size.x = 160
	_label(layout, "Surface (validated at the chosen position before launch)")
	drive_surface = OptionButton.new()
	layout.add_child(drive_surface)
	drive_dialog.confirmed.connect(_launch_test_drive)
	add_child(drive_dialog)
	client_dialog = FileDialog.new()
	client_dialog.access = FileDialog.ACCESS_FILESYSTEM
	client_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	client_dialog.use_native_dialog = true
	if OS.get_name() == "Windows":
		client_dialog.filters = PackedStringArray(["*.exe ; MiniEarthure Client"])
	client_dialog.file_selected.connect(func(path: String): client_path.text = path)
	add_child(client_dialog)
	var settings := ConfigFile.new()
	if settings.load("user://editor_tools.cfg") == OK:
		client_path.text = str(settings.get_value("test_drive", "client_executable", ""))


func _test_drive() -> void:
	if busy:
		_status("Wait for the current operation before starting test drive.")
		return
	if store.project_path == "":
		_status("Choose a project directory before test drive.")
		_choose("save_for_drive")
		return
	var bounds: Dictionary = store.document.bounds
	drive_x.min_value = float(bounds.min[0]) / 100
	drive_x.max_value = float(bounds.max[0]) / 100
	drive_y.min_value = float(bounds.min[1]) / 100
	drive_y.max_value = float(bounds.max[1]) / 100
	drive_x.value = (drive_x.min_value + drive_x.max_value) * 0.5
	drive_y.value = (drive_y.min_value + drive_y.max_value) * 0.5
	drive_surface.clear()
	drive_surface.add_item("Terrain")
	drive_surface.set_item_metadata(0, "terrain")
	for road: Dictionary in store.document.roads:
		drive_surface.add_item(str(road.id) + " · " + str(road.kind))
		drive_surface.set_item_metadata(drive_surface.item_count - 1, road.id)
		if selected_field == "roads" and selected_record.get("id") == road.id:
			drive_surface.select(drive_surface.item_count - 1)
			drive_x.value = float(road.points[0][0] + road.points[1][0]) / 200
			drive_y.value = float(road.points[0][2] + road.points[1][2]) / 200
	drive_dialog.popup_centered()


func _launch_test_drive() -> void:
	last_drive_result = {}
	if busy:
		_status("Another operation is running.")
		return
	var checked := TEST_DRIVE.check_client(client_path.text)
	if not checked.ok:
		last_drive_result = checked
		_status(store.reason(checked))
		return
	var failure := store.save_project(store.project_path)
	if failure != "":
		_status(failure)
		return
	_document_changed()
	var validation: Dictionary = JSON.parse_string(store.bridge.validate_document(JSON.stringify(store.document)))
	if not validation.ok:
		_status(store.reason(validation))
		return
	var directory := ProjectSettings.globalize_path("user://test-drives")
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK:
		_status(error_string(error))
		return
	var snapshot := directory.path_join(Crypto.new().generate_random_bytes(16).hex_encode() + ".memap")
	drive_request = {"client": client_path.text, "x_cm": roundi(drive_x.value * 100),
		"y_cm": roundi(drive_y.value * 100), "surface": drive_surface.get_selected_metadata(),
		"document": validation.data.canonical}
	var settings := ConfigFile.new()
	settings.load("user://editor_tools.cfg")
	settings.set_value("test_drive", "client_executable", client_path.text)
	error = settings.save("user://editor_tools.cfg")
	if error != OK:
		_status("Cannot save Client tool setting: " + error_string(error))
		return
	_start_worker("test_drive", store.project_path, snapshot)
	_status("Validating and packaging test-drive snapshot…")
