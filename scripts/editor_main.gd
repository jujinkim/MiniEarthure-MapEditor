extends Control
const PACKAGE_WORK := preload("./package_work.gd")
const PAYLOAD_FILES := preload("./authoring_files.gd")
const REPORT := preload("./export_report.gd")
const ATTACH_USEC := 8000
const CACHE_CELLS := 4
const CACHE_BYTES := 256 * 1024 * 1024
var package_work: RefCounted
var package_operation := ""
var package_destination := ""
var package_cell := Vector2i.ZERO
var render_job := {}
var render_staged: Node3D
var render_data := {}
var render_batch_estimate := 1000
var preview_cache := {}
var cache_clock := 0
var preview_due := 0
var preview_enabled := false
var preview_stats := {"generated": 0, "reused": 0, "attachment_frames": 0, "max_batch_usec": 0, "max_frame_usec": 0}
var export_report: AcceptDialog
var last_export_report := {}
var full_generation: CheckButton
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
const DEM_PANEL := preload("./dem_panel.gd")
var dem_panel: ConfirmationDialog
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
var unsaved_dialog: ConfirmationDialog
var recovery_continue_button: Button
var pending_document_action := {}
var tool_hint: Label
var cancel_button: Button
var retry_import_button: Button
var worker := Thread.new()
var generation := 0
var worker_generation := 0
var import_dialog: ConfirmationDialog
var import_license: LineEdit
var import_accuracy: LineEdit
const IMPORT_LAYER := preload("./import_layer.gd")
var import_identity := ""
var pending_import: RefCounted
var import_review: ConfirmationDialog
var import_summary: TextEdit
var import_review_generation := 0
const IMPORT_JOB := preload("./import_job.gd")
var import_job: RefCounted
var import_python: LineEdit
var last_import_source := ""
var import_progress: ProgressBar
var import_coordinate_mode: OptionButton
var import_source_format: OptionButton
var import_origin_lon: SpinBox
var import_origin_lat: SpinBox
var import_origin_x: SpinBox
var import_origin_y: SpinBox
var import_coordinates_request := {}
const DOWNLOAD_JOB := preload("./download_job.gd")
var download_dialog: ConfirmationDialog
var download_url: LineEdit
var download_summary: TextEdit
var download_plan := {}
var download_revision := 0
var download_request_revision := -1
var osm_crop_button: Button
var osm_panel: RefCounted
var osm_import_revision := -1
var acquisition_mode := ""
var download_sources := {}
var overture_dialog: ConfirmationDialog
var overture_release: LineEdit
var overture_bbox: Array[SpinBox] = []
var overture_requested := {}
var overture_area: Control
var overture_area_status: Label
var overture_review: ConfirmationDialog
var overture_reviewed := {}
var overture_revision := 0
var overture_request_revision := -1

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
		_request_document_action("close")

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
	ui_theme.set_color("font_readonly_color", "TextEdit", Color("e1e3e6"))
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
	for entry in [["New", _new], ["Open", _choose.bind("open")], ["Save", _save], ["Save As", _choose.bind("save")], ["Recover", _choose.bind("recover")], ["Undo", _history.bind(false)], ["Redo", _history.bind(true)], ["Validate", _validate], ["Import vector", _import_geojson], ["Export .memap", _export], ["Test Drive", _test_drive]]:
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
		tool_button.tooltip_text = _tool_help(name)
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
	tool_hint = Label.new()
	tool_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tool_hint.add_theme_font_size_override("font_size", 12)
	center.add_child(tool_hint)
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
	preview_x.value_changed.connect(_preview_cell_changed)
	preview_y.value_changed.connect(_preview_cell_changed)
	var preview_hint := Label.new()
	preview_hint.text = "Affected cells refresh automatically · 2D filters do not change export"
	preview_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	preview_hint.add_theme_font_size_override("font_size", 12)
	preview_dock.add_child(preview_hint)
	full_generation = CheckButton.new()
	full_generation.text = "Full 3D check on Validate / Export"
	full_generation.add_theme_font_size_override("font_size", 12)
	preview_dock.add_child(full_generation)
	export_report = REPORT.new()
	export_report.theme = theme
	add_child(export_report)
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
	var view_bar := HFlowContainer.new()
	column.add_child(view_bar)
	cancel_button = _button(view_bar, "Cancel operation", _cancel_operation)
	cancel_button.disabled = true
	retry_import_button = _button(view_bar, "Retry import…", _import_geojson)
	retry_import_button.hide()
	_button(view_bar, "Tools / layers", func(): left_dock.visible = not left_dock.visible)
	_button(view_bar, "Properties / 3D", func(): right_dock.visible = not right_dock.visible)
	_button(view_bar, "Fit map (F)", func(): canvas.fit_map())
	_button(view_bar, "Reset panels", _reset_panels)
	validation_label = Label.new()
	validation_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	validation_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(validation_label)
	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size.y = 48
	status_label.text = "V Select · R Road · B Building · G Forest · O Orchard · Ctrl/Cmd+A/D/Z/Y/S · Delete · Escape cancels"
	column.add_child(status_label)
	import_progress = ProgressBar.new()
	import_progress.visible = false
	column.add_child(import_progress)
	dialog = FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.canceled.connect(func():
		if dialog_action == "save_transition": pending_document_action.clear()
	)
	dialog.dir_selected.connect(_path_selected)
	dialog.file_selected.connect(_path_selected)
	add_child(dialog)
	unsaved_dialog = ConfirmationDialog.new()
	unsaved_dialog.title = "Unsaved changes"
	unsaved_dialog.ok_button_text = "Save and continue"
	unsaved_dialog.cancel_button_text = "Keep editing"
	recovery_continue_button = unsaved_dialog.add_button("Keep recovery and continue", false, "recovery")
	unsaved_dialog.confirmed.connect(_save_before_document_action)
	unsaved_dialog.custom_action.connect(func(action):
		if action == "recovery":
			unsaved_dialog.hide()
			_continue_document_action()
	)
	unsaved_dialog.canceled.connect(func(): pending_document_action.clear())
	add_child(unsaved_dialog)
	import_dialog = ConfirmationDialog.new()
	import_dialog.title = "Import vector source"
	import_dialog.ok_button_text = "Choose source…"
	import_license = LineEdit.new()
	import_license.placeholder_text = "Source license (required)"
	import_license.custom_minimum_size = Vector2(540, 40)
	var import_fields := VBoxContainer.new()
	import_fields.custom_minimum_size.x = 700
	import_dialog.add_child(import_fields)
	_label(import_fields, "Select a local source up to 32 MiB; review before adopting.\nWGS84 needs pyproj 3.7.2; OSM also needs osmium 4.3.1 in the selected Python.")
	import_fields.get_child(0).custom_minimum_size.x = 700
	import_source_format = OptionButton.new()
	for format_title in ["GeoJSON", "OSM PBF extract (.osm.pbf)", "OSM XML extract (.osm)", "Overture building area snapshot (.overture.json)"]: import_source_format.add_item(format_title)
	import_fields.add_child(import_source_format)
	_button(import_fields, "Download Geofabrik region…", _open_download)
	osm_crop_button = _button(import_fields, "OSM crop area…", func(): osm_panel.open())
	_button(import_fields, "Download Overture building area…", _open_overture)
	_button(import_fields, "Import Copernicus DEM…", func(): dem_panel.open())
	import_fields.add_child(import_license)
	import_accuracy = LineEdit.new()
	import_accuracy.placeholder_text = "Source accuracy / resolution (unknown if omitted)"
	import_fields.add_child(import_accuracy)
	import_python = LineEdit.new()
	import_python.placeholder_text = "Python 3 executable (name or absolute path)"
	var settings := ConfigFile.new()
	settings.load("user://editor_tools.cfg")
	import_python.text = str(settings.get_value("import", "python", "python" if OS.get_name() == "Windows" else "python3"))
	import_fields.add_child(import_python)
	import_coordinate_mode = OptionButton.new()
	import_coordinate_mode.add_item("Local x/y metres (explicit extension)")
	import_coordinate_mode.add_item("WGS84 longitude/latitude → local map (UTM)")
	import_fields.add_child(import_coordinate_mode)
	var geographic := GridContainer.new()
	geographic.columns = 2
	import_fields.add_child(geographic)
	import_origin_lon = _import_number(geographic, "Origin longitude (degrees)", -180, 180, 0, 0.000001)
	import_origin_lat = _import_number(geographic, "Origin latitude (degrees)", -80, 84, 0, 0.000001)
	import_origin_x = _import_number(geographic, "Origin maps to local x (m)", -100000, 100000, 512, 0.01)
	import_origin_y = _import_number(geographic, "Origin maps to local y (m)", -100000, 100000, 512, 0.01)
	geographic.visible = false
	import_coordinate_mode.item_selected.connect(func(index): geographic.visible = index == 1)
	import_source_format.item_selected.connect(func(index):
		import_license.editable = index == 0
		import_coordinate_mode.disabled = index != 0
		if index != 0:
			import_license.text = IMPORT_LAYER.OVERTURE_LICENSE if index == 3 else IMPORT_LAYER.OSM_LICENSE
			import_coordinate_mode.select(1)
			geographic.visible = true
		elif import_license.text in [IMPORT_LAYER.OSM_LICENSE, IMPORT_LAYER.OVERTURE_LICENSE]:
			import_license.text = ""
		import_dialog.get_ok_button().disabled = import_license.text.strip_edges() == ""
	)

	_button(import_fields, "Import / retry last source", func():
		import_dialog.hide()
		if last_import_source == "": _status("Choose a source file first.")
		else: _start_import(last_import_source, import_license.text.strip_edges())
	)
	import_dialog.get_ok_button().disabled = true
	import_license.text_changed.connect(func(value): import_dialog.get_ok_button().disabled = value.strip_edges() == "")
	import_dialog.confirmed.connect(func(): _choose("import"))
	add_child(import_dialog)
	import_review = ConfirmationDialog.new()
	import_review.title = "Review imported layer"
	import_review.ok_button_text = "Adopt new layer"
	import_review.cancel_button_text = "Discard"
	import_summary = TextEdit.new()
	import_summary.editable = false
	import_summary.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	import_summary.custom_minimum_size = Vector2(640, 340)
	import_review.add_child(import_summary)
	import_review.confirmed.connect(_adopt_import)
	import_review.canceled.connect(func():
		_discard_import()
		validation_label.text = "Import discarded · document unchanged"
		_status("Imported layer discarded. Use Retry import to prepare it again.")
	)
	add_child(import_review)
	_setup_download()
	_setup_overture()
	dem_panel = DEM_PANEL.new()
	dem_panel.editor = self
	add_child(dem_panel)
	_build_test_drive_dialog()

func _import_number(parent: Control, title: String, minimum: float, maximum: float, initial: float, step_size: float) -> SpinBox:
	_label(parent, title)
	var value := SpinBox.new()
	value.min_value = minimum
	value.max_value = maximum
	value.step = step_size
	value.value = initial
	value.custom_minimum_size.x = 220
	parent.add_child(value)
	return value

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

func _label(parent: Node, text: String) -> Label:
	var label := Label.new()
	label.text = text
	if parent is VBoxContainer:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(label)
	return label

func _new() -> void:
	_request_document_action("new")

func _request_document_action(action: String, path: String = "") -> void:
	canvas.cancel_interaction()
	if store.dirty:
		var failure := store.autosave()
		if failure != "":
			_status(("Cannot close safely: " if action == "close" else "Cannot leave document: ") + failure)
			return
	pending_document_action = {"action": action, "path": path, "map_id": str(store.document.map_id)}
	if not store.dirty:
		_continue_document_action()
		return
	unsaved_dialog.dialog_text = "Save changes before %s?\nA recovery snapshot retains committed changes and file references.\nKeep original imported files available. Keep editing cancels this action." % {"new":"creating a new map", "open":"opening another project", "recover":"recovering another document", "close":"closing the editor"}[action]
	unsaved_dialog.popup_centered(Vector2i(700, 200))
	unsaved_dialog.get_cancel_button().grab_focus()

func _save_before_document_action() -> void:
	if pending_document_action.is_empty(): return
	if pending_document_action.map_id != str(store.document.map_id):
		pending_document_action.clear()
		_status("Document changed; request the action again.")
		return
	if busy:
		_status("Cancel the active operation or wait, then try again. Your document stays open.")
		pending_document_action.clear()
		return
	if store.project_path == "":
		_choose("save_transition")
		return
	var failure := store.save_project(store.project_path)
	if failure != "":
		pending_document_action.clear()
		_status(failure + " Use Save As to a new directory, then try again.")
		return
	_document_changed()
	_continue_document_action()

func _continue_document_action() -> void:
	if pending_document_action.is_empty(): return
	var request := pending_document_action.duplicate()
	pending_document_action.clear()
	if request.map_id != str(store.document.map_id):
		_status("Document changed; request the action again.")
		return
	# Recheck retention at consumption, including edits since the prompt opened.
	var failure := store.autosave() if store.dirty else ""
	if failure != "":
		_status("Cannot leave document: " + failure)
		return
	match request.action:
		"new":
			store.new_document()
			_status("New map. Previous unsaved changes remain in Recover.")
		"open": failure = store.open_project(request.path)
		"recover": failure = store.recover(request.path)
		"close": get_tree().quit()
	if failure != "": _status(failure + " Current document retained. Use Recover to inspect a backup.")
	elif request.action in ["open", "recover"]: _status("Ready: " + request.path)

func _choose(action: String) -> void:
	dialog_action = action
	dialog.filters = PackedStringArray()
	dialog.title = {"open":"Open project directory", "save":"Save project to directory", "save_transition":"Save before continuing", "save_for_export":"Save project before export", "save_for_drive":"Save project before test drive", "export":"Export package — choose a new filename", "recover":"Recover a document", "import":"Choose source to review"}.get(action, "Choose file")
	if action in ["open", "save", "save_for_drive", "save_transition", "save_for_export"]:
		dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	else:
		dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE if action == "export" else FileDialog.FILE_MODE_OPEN_FILE
		dialog.filters = PackedStringArray(["*.memap ; Map package"] if action == "export" else ["*.json ; Recovery snapshot"])
		if action == "import":
			dialog.filters = PackedStringArray(["*.geojson,*.json ; GeoJSON (explicit coordinates)"])
			if import_source_format.selected == 1: dialog.filters = PackedStringArray(["*.osm.pbf,*.pbf ; OSM PBF snapshot"])
			if import_source_format.selected == 3: dialog.filters = PackedStringArray(["*.overture.json ; Overture building snapshot"])
			if import_source_format.selected == 2: dialog.filters = PackedStringArray(["*.osm ; OSM XML snapshot"])
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
		"open", "recover":
			_request_document_action(dialog_action, path)
			return
		"save": failure = store.save_project(path)
		"save_transition", "save_for_export":
			if dialog_action == "save_transition" and (pending_document_action.is_empty() or pending_document_action.map_id != str(store.document.map_id)):
				pending_document_action.clear()
				_status("Document changed or action cancelled; choose Save again.")
				return
			failure = store.save_project(path)
			if failure == "":
				_document_changed()
				if dialog_action == "save_transition": _continue_document_action()
				else: _choose.call_deferred("export")
			else:
				pending_document_action.clear()
				_status(failure + " Choose Save As to a new directory and try again.")
			return
		"save_for_drive":
			failure = store.save_project(path)
			if failure == "":
				_document_changed()
				_test_drive()
				return
		"export":
			if busy:
				_status("Wait for the current preview or export.")
				return
			_start_package("export", path)
			return
	_status(failure if failure != "" else "Ready: " + path)
	if failure == "": _document_changed()

func _save() -> void:
	if busy:
		_status("Wait for the active operation before saving.")
		return
	if store.project_path == "":
		_choose("save")
	else:
		var failure := store.save_project(store.project_path)
		_status(failure if failure != "" else "Project saved.")
		if failure == "": _document_changed()

func _import_geojson() -> void:
	if not busy:
		import_dialog.get_ok_button().disabled = not IMPORT_LAYER._text(import_license.text.strip_edges())
		import_dialog.popup_centered(Vector2i(760, 520))

func _export() -> void:
	if busy:
		_status("Cancel the active operation or wait before exporting.")
		return
	if store.project_path == "":
		_choose("save_for_export")
		return
	_choose("export")

func _validate() -> void:
	_start_package("report")

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
	tool_hint.text = _tool_help(canvas.tool)
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
	if import_job != null: import_job.cancel()
	_discard_import()
	generation += 1
	if package_work != null: package_work.cancel()
	_cancel_attachment()
	if preview_enabled: preview_due = Time.get_ticks_msec() + 150
	canvas.cancel_interaction()
	var map_id := str(store.document.get("map_id", ""))
	if displayed_map_id != map_id:
		_clear_preview_cache()
		preview_enabled = false
		preview_due = 0
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

func _tool_help(name: String) -> String:
	var hints := {
		"Select":"V · Click to select; Shift toggles. Drag empty space to box-select. Edit in Properties, then Apply.",
		"Road":"R · Click at least two points; right-click to finish. Set width, surface and structure in Authoring settings.",
		"Building":"B · Click at least three corners; right-click to finish. Select the building to edit height and material.",
		"Forest":"G · Click at least three corners; right-click to finish. Select the zone to edit density and spacing.",
		"Orchard":"O · Click at least three corners; right-click to finish. Select the zone to edit density and spacing.",
		"Terrain":"Drag to paint terrain. Choose brush, radius and strength in Authoring settings; release commits one Undo step.",
		"Place":"Click to place the asset chosen in Authoring settings. Select it to change rotation.",
		"Repeat":"Click a path; right-click to finish. Choose asset and spacing in Authoring settings.",
		"Entrance":"Select one building first, then draw an entrance polygon; right-click to finish.",
		"Exclusion":"Select one forest/orchard zone first, then draw an exclusion polygon; right-click to finish."
	}
	return str(hints.get(name, "")) + "\nEscape cancels · Wheel zooms · Middle drag pans"

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
	preview_enabled = true
	preview_due = 0
	_start_package("preview")

func _preview_cell_changed(_value: float) -> void:
	if preview_enabled:
		generation += 1
		if package_work != null: package_work.cancel()
		_cancel_attachment()
		preview_due = Time.get_ticks_msec() + 150

func _start_package(operation: String, destination: String = "") -> void:
	if busy:
		_status("Another operation is running; cancel it or wait.")
		return
	if store.has_gesture():
		_status("Finish or cancel the current gesture first.")
		return
	if operation == "export" and FileAccess.file_exists(destination):
		_operation_status("Export failed · E_EXPORT_EXISTS", "Choose a new package filename; existing files are preserved.")
		return
	package_work = PACKAGE_WORK.new()
	package_operation = operation
	package_destination = destination
	package_cell = Vector2i(int(preview_x.value), int(preview_y.value))
	worker_generation = generation
	var document: Dictionary = store.document.duplicate(true)
	var source: String = store.project_path
	var cached: Dictionary = preview_cache.get(package_cell, {}).duplicate()
	cached.erase("root")
	var cell := package_cell
	var full := full_generation.button_pressed
	var task: RefCounted = package_work
	busy = true
	var err := worker.start(func(): return {"operation": "package", "result": task.run(document, source, operation, cell, cached, full)})
	if err != OK:
		busy = false
		package_work = null
		_status(error_string(err))

func _cancel_operation() -> void:
	if import_job != null: import_job.cancel()
	_discard_import()
	generation += 1
	preview_due = 0
	if package_work != null: package_work.cancel()
	_cancel_attachment()
	_status("Operation cancelled; previous preview and original files retained.")

func _cancel_attachment() -> void:
	if render_job.is_empty(): return
	RENDERER.cancel(render_job)
	render_job = {}
	if is_instance_valid(render_staged): render_staged.queue_free()
	render_staged = null
	render_data = {}
	busy = false

func _clear_preview_cache() -> void:
	for entry: Dictionary in preview_cache.values():
		if is_instance_valid(entry.root): entry.root.queue_free()
	preview_cache.clear()

func _show_cached(cell: Vector2i) -> void:
	cache_clock += 1
	preview_cache[cell].used = cache_clock
	for key: Vector2i in preview_cache: preview_cache[key].root.visible = key == cell
	var bounds: Dictionary = store.document.bounds
	var cell_size := float(store.document.cell_size_cm)
	var center := RENDERER.scene_position([bounds.min[0] + (cell.x + 0.5) * cell_size, 0, bounds.min[1] + (cell.y + 0.5) * cell_size])
	var camera: Camera3D = preview_world.get_node("PreviewCamera")
	camera.position = center + Vector3(35, 55, 45) * cell_size / 51200.0
	camera.look_at(center)
	validation_label.text = "Preview ready · cell %d / %d" % [cell.x, cell.y]
	_status(validation_label.text)

func _package_finished(result: Dictionary) -> void:
	var stale: bool = generation != worker_generation or package_work.stopped()
	package_work = null
	if stale:
		if result.ok and result.data.has("scratch"): PAYLOAD_FILES.remove_scratch(result.data.scratch)
		_status("Operation cancelled or document changed; prior preview and files retained.")
		return
	if not result.ok:
		_operation_status(package_operation.capitalize() + " failed · Prior preview and original files retained", store.reason(result))
		return
	if package_operation != "preview":
		last_export_report = result.data
		if package_operation == "export":
			var failure := _publish_package(result.data.path, package_destination)
			PAYLOAD_FILES.remove_scratch(result.data.scratch)
			if failure != "":
				_operation_status("Export failed · Choose a new filename and retry", failure)
				return
			last_export_report.path = package_destination
		_status("Exported validated package: " + package_destination if package_operation == "export" else "Validated immutable snapshot; capacity report ready.")
		validation_label.text = "Validated · %d bytes · base goal %s" % [result.data.package_bytes, "met" if result.data.base_target_met else "exceeded"]
		export_report.show_report(result.data)
		return
	if result.data.get("reused", false):
		preview_stats.reused += 1
		_show_cached(package_cell)
		return
	preview_stats.generated += 1
	render_data = result.data
	render_batch_estimate = 1000
	render_staged = Node3D.new()
	render_staged.visible = false
	preview_world.add_child(render_staged)
	render_job = RENDERER.begin(result.data.chunk, render_staged)
	busy = true

func _publish_package(source: String, destination: String) -> String:
	if FileAccess.file_exists(destination): return "E_EXPORT_EXISTS: Existing package preserved; choose a new filename."
	var pending := destination + ".pending-" + Crypto.new().generate_random_bytes(8).hex_encode()
	var err := DirAccess.copy_absolute(source, pending)
	if err != OK: return "E_EXPORT_IO: " + error_string(err)
	if FileAccess.get_sha256(source) != FileAccess.get_sha256(pending):
		return "E_EXPORT_IO: Copy verification failed; pending file retained."
	if FileAccess.file_exists(destination): return "E_EXPORT_EXISTS: Destination appeared; pending copy retained."
	err = DirAccess.rename_absolute(pending, destination)
	return "" if err == OK else "E_EXPORT_IO: Pending copy retained: " + error_string(err)

func _advance_attachment() -> void:
	if generation != worker_generation:
		_cancel_attachment()
		return
	var started := Time.get_ticks_usec()
	preview_stats.attachment_frames += 1
	while not render_job.is_empty():
		var batch := Time.get_ticks_usec()
		var done := RENDERER.advance(render_job)
		var batch_usec := Time.get_ticks_usec() - batch
		render_batch_estimate = maxi(render_batch_estimate, batch_usec)
		preview_stats.max_batch_usec = maxi(preview_stats.max_batch_usec, batch_usec)
		if done:
			if not render_job.error.is_empty():
				var failure := store.reason({"ok": false, "error": render_job.error})
				_cancel_attachment()
				_status(failure)
				return
			# Publish once; keep the old root visible throughout candidate attachment.
			if preview_cache.has(package_cell): preview_cache[package_cell].root.queue_free()
			preview_cache[package_cell] = {"root": render_staged, "signature": render_data.signature, "charge": render_data.charge, "used": cache_clock + 1}
			render_job = {}
			render_staged = null
			render_data = {}
			_trim_preview_cache(package_cell)
			_show_cached(package_cell)
			busy = false
			break
		if Time.get_ticks_usec() - started + render_batch_estimate >= ATTACH_USEC: break
	preview_stats.max_frame_usec = maxi(preview_stats.max_frame_usec, Time.get_ticks_usec() - started)

func _trim_preview_cache(keep: Vector2i) -> void:
	while true:
		var charge := 0
		var oldest := keep
		for cell: Vector2i in preview_cache:
			charge += int(preview_cache[cell].charge)
			if cell != keep and (oldest == keep or preview_cache[cell].used < preview_cache[oldest].used): oldest = cell
		if preview_cache.size() <= CACHE_CELLS and charge <= CACHE_BYTES: return
		if oldest == keep: return
		preview_cache[oldest].root.queue_free()
		preview_cache.erase(oldest)

func _start_import(source: String, license_name: String) -> void:
	if busy:
		_status("Another operation is running; wait for cancellation to finish.")
		return
	_discard_import()
	if not IMPORT_LAYER._text(license_name):
		_status("A source license is required.")
		return
	last_import_source = source
	var settings := ConfigFile.new()
	settings.load("user://editor_tools.cfg")
	settings.set_value("import", "python", import_python.text.strip_edges())
	settings.save("user://editor_tools.cfg")
	import_identity = Crypto.new().generate_random_bytes(16).hex_encode()
	var job := IMPORT_JOB.new()
	var accuracy := import_accuracy.text.strip_edges() if not import_accuracy.text.strip_edges().is_empty() else "unknown"
	import_coordinates_request = {"mode":"local-metres"} if import_coordinate_mode.selected == 0 else {"mode":"wgs84-utm", "origin":[import_origin_lon.value,import_origin_lat.value], "local_origin_m":[import_origin_x.value,import_origin_y.value]}
	var input_format: String = ["geojson", "pbf", "osm", "overture"][import_source_format.selected]
	osm_import_revision = osm_panel.revision
	if input_format in ["osm", "pbf"] and osm_panel.enabled.button_pressed:
		if osm_panel.error() != "":
			_status(osm_panel.error())
			return
		import_coordinates_request.osm_bbox = osm_panel.bbox()
	import_coordinates_request.adapter = "overture-buildings-v1" if input_format == "overture" else ("geojson-v2" if input_format == "geojson" else "osm-extract-v1")
	if input_format != "geojson": license_name = IMPORT_LAYER.OVERTURE_LICENSE if input_format == "overture" else IMPORT_LAYER.OSM_LICENSE
	var failure := job.start(source, license_name, accuracy, import_python.text.strip_edges(), import_identity, import_coordinates_request, input_format, str(download_sources.get(source, "")))
	if failure != "":
		_operation_status("Import failed · Use Retry import to adjust settings", "E_IMPORT: " + failure)
		return
	import_job = job
	worker_generation = generation
	busy = true
	import_progress.value = 0
	import_progress.visible = true
	_status("Starting import · %d source bytes · maximum 32 MiB. Cancel stops the child; Retry last source starts a new layer." % job.progress.total)

func _start_worker(operation: String, source: String, destination: String) -> void:
	if operation == "import":
		_start_import(source, destination)
		return
	if busy:
		_status("Another operation is running.")
		return
	busy = true
	worker_generation = generation
	var test_request := drive_request.duplicate(true)
	var err := worker.start(func():
		if operation == "test_drive":
			return {"operation": operation, "result": TEST_DRIVE.prepare(source, destination, test_request.document, test_request.x_cm, test_request.y_cm, test_request.surface)}
		return {"operation": operation, "result": TEST_DRIVE.error("E_STATE", "Unsupported worker operation.")}
	)
	if err != OK:
		busy = false
		_status(error_string(err))
	else: _status("Preparing test drive…")

func _process(_delta: float) -> void:
	cancel_button.disabled = not busy and pending_import == null
	cancel_button.tooltip_text = "Cancel the running operation; keep prior preview and original files." if busy else "No running operation."
	retry_import_button.visible = last_import_source != "" and not busy and pending_import == null
	if import_job != null:
		import_job.poll()
		var progress: Dictionary = import_job.progress
		if not progress.is_empty():
			import_progress.value = 100.0 * float(progress.completed) / maxf(1.0, float(progress.total))
			validation_label.text = "%s %s · %d / %d %s" % ["Overture captured snapshot" if acquisition_mode == "overture" else "DEM" if acquisition_mode.begins_with("dem") else "Import", progress.stage, progress.completed, progress.total, progress.unit]
		if import_job.done:
			var result: Dictionary = import_job.result
			import_job = null
			busy = false
			import_progress.visible = false
			if acquisition_mode != "": _finish_acquisition(result)
			else: _finish_import(result)
		return
	if not render_job.is_empty():
		_advance_attachment()
		return
	if not busy:
		if preview_due > 0 and Time.get_ticks_msec() >= preview_due: _preview()
		return
	if worker.is_alive():
		if package_work != null: validation_label.text = package_work.status()
		return
	var output: Dictionary = worker.wait_to_finish()
	busy = false
	var result: Dictionary = output.result
	if output.operation == "package":
		_package_finished(result)
		return
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
func _finish_import(result: Dictionary) -> void:
	if osm_import_revision != osm_panel.revision:
		_status("OSM crop selection changed during import; retry. Original source retained.")
		return
	if not result.ok:
		_operation_status("Import stopped · Use Retry import to review settings", store.reason(result))
		return
	if generation != worker_generation:
		_status("Document changed during import; retry to add the new layer.")
		return
	var layer := IMPORT_LAYER.new()
	var failure := layer.load_value(result.data, import_identity, import_coordinates_request)
	if failure == "": failure = layer.validate_for(store)
	if failure != "":
		_status("E_IMPORT: " + failure)
		return
	pending_import = layer
	import_review_generation = generation
	validation_label.text = "Import ready for review · document unchanged until Adopt"
	import_summary.text = layer.summary()
	import_review.popup_centered(Vector2i(760, 460))
	_status("Import prepared. Review and adopt the new layer, or discard it.")
	return

func _discard_import() -> void:
	pending_import = null
	if import_review != null: import_review.hide()

func _adopt_import() -> void:
	if pending_import == null or generation != import_review_generation:
		_discard_import()
		_status("E_IMPORT_STALE: Document changed; import again.")
		return
	var candidate: RefCounted = pending_import
	_discard_import()
	var failure: String = candidate.adopt(store)
	_status(failure if failure != "" else "Imported new layer. Undo removes only this adoption.")

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

func _operation_status(summary: String, details: String) -> void:
	_status(details)
	validation_label.text = summary

func _status(text: String) -> void:
	if busy and text.begins_with("x "): return
	if validation_label != null and text.contains("E_"):
		validation_label.text = "Edit/operation rejected · " + text
	status_label.text = text

func _exit_tree() -> void:
	if import_job != null: import_job.shutdown()
	_save_workbench()
	if package_work != null: package_work.cancel()
	_cancel_attachment()
	if worker.is_started():
		var output: Variant = worker.wait_to_finish()
		if output is Dictionary and output.operation == "package" and output.result.ok and output.result.data.has("scratch"):
			PAYLOAD_FILES.remove_scratch(output.result.data.scratch)
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

func _setup_download() -> void:
	osm_panel = preload("./osm_area_panel.gd").new()
	osm_panel.setup(self)
	download_dialog = ConfirmationDialog.new()
	download_dialog.title = "OSM region download · Geofabrik"
	download_dialog.ok_button_text = "Download reviewed region"
	var fields := VBoxContainer.new()
	fields.custom_minimum_size = Vector2(700, 350)
	download_dialog.add_child(fields)
	_label(fields, "Select a region or paste its public Geofabrik PBF URL. Download is the whole region.\nOptional OSM crop applies later on import; the 32 MiB source limit still applies.")
	download_url = LineEdit.new()
	download_url.placeholder_text = "https://download.geofabrik.de/europe/monaco-latest.osm.pbf"
	fields.add_child(download_url)
	download_url.text_changed.connect(func(_text):
		download_revision += 1
		download_plan.clear()
		download_dialog.get_ok_button().disabled = true
		download_summary.text = "URL changed. Check region and size again."
	)
	osm_panel.setup_catalog(fields)
	_button(fields, "Check region and size", func(): _begin_acquisition({"mode":"probe", "url":download_url.text.strip_edges()}))
	download_summary = TextEdit.new()
	download_summary.editable = false
	download_summary.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	download_summary.custom_minimum_size = Vector2(680, 140)
	fields.add_child(download_summary)
	download_dialog.get_ok_button().disabled = true
	download_dialog.confirmed.connect(func():
		if download_plan.is_empty() or download_plan.requested_url != download_url.text.strip_edges(): return
		var folder := ProjectSettings.globalize_path("user://import-sources")
		var error := DirAccess.make_dir_recursive_absolute(folder)
		if error != OK:
			_status("Cannot create download source folder: " + error_string(error))
			return
		var destination := folder.path_join(Crypto.new().generate_random_bytes(16).hex_encode() + ".osm.pbf")
		_begin_acquisition({"mode":"download", "plan":download_plan.duplicate(true), "destination":destination})
	)
	download_dialog.canceled.connect(func():
		if acquisition_mode != "" and import_job != null: import_job.cancel()
	)
	add_child(download_dialog)

func _open_download() -> void:
	if busy: return
	import_dialog.hide()
	download_dialog.popup_centered(Vector2i(760, 460))

func _begin_acquisition(request: Dictionary) -> void:
	if busy: return
	_discard_import()
	if request.mode in ["probe", "download", "catalog"]: download_request_revision = download_revision
	if request.mode == "probe": download_plan.clear()
	download_dialog.get_ok_button().disabled = true
	var job := _new_download_job()
	var failure: String = job.start_acquisition(request, import_python.text.strip_edges(), Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "":
		_status("E_DOWNLOAD: " + failure)
		return
	acquisition_mode = request.mode
	import_job = job
	worker_generation = generation
	busy = true
	import_progress.visible = true
	download_summary.text = "Checking provider…" if request.mode == "probe" else "Downloading. Cancel stops this request; retry starts from zero."

func _finish_acquisition(result: Dictionary) -> void:
	var mode := acquisition_mode
	acquisition_mode = ""
	if mode.begins_with("dem"):
		dem_panel.finish(mode,result)
		return
	if not result.ok:
		download_summary.text = str(result.error.message)
		_status("E_DOWNLOAD: " + str(result.error.message))
		return
	if generation != worker_generation:
		_status("Document changed; download result will not start an import. Complete source files are retained.")
		return
	if mode == "overture":
		if overture_request_revision != overture_revision or overture_requested != _overture_plan():
			_status("Area changed; completed source retained without selecting it. Retry the new area.")
			return
		last_import_source = str(result.data.path)
		import_source_format.select(3)
		import_source_format.item_selected.emit(3)
		_status("Overture snapshot retained: " + last_import_source + ". Set origins, then Import / retry last source.")
		import_dialog.popup_centered(Vector2i(760, 550))
		return
	if mode in ["probe", "download", "catalog"] and download_request_revision != download_revision:
		_status("Region selection changed; completed sources retained without selection. Check again.")
		return
	if mode == "catalog":
		osm_panel.load_catalog(result.data)
		return
	if mode == "probe":
		if result.data.requested_url != download_url.text.strip_edges(): return
		download_plan = result.data
		var expected := "%d bytes" % int(download_plan.bytes) if download_plan.bytes != null else "unknown (progress shows bytes against the 32 MiB cap)"
		download_summary.text = "Region: %s\nProvider: Geofabrik\n%s\nExpected transfer: %s; hard limit 32 MiB.\nModified: %s\n%s\n\nWhole provider polygon, buffered borders and complete crossing ways may extend beyond it. No automatic clipping or terrain accuracy guarantee.\nCompleted source + receipt are retained in import-sources. Partial downloads are discarded; retry is a fresh request. Then set WGS84 origins and review the imported layer." % [download_plan.region, download_plan.url, expected, download_plan.modified, download_plan.license]
		download_dialog.get_ok_button().disabled = download_plan.etag == "" and download_plan.modified == ""
	else:
		var source: String = result.data.path
		download_sources[source] = "Geofabrik " + str(result.data.url)
		last_import_source = source
		import_source_format.select(1)
		import_source_format.item_selected.emit(1)
		_status("Download retained: " + source + ". Set origins, then Retry last source to review/import.")
		import_dialog.popup_centered(Vector2i(760, 550))

func _new_download_job() -> RefCounted:
	return DOWNLOAD_JOB.new()

func _setup_overture() -> void:
	overture_dialog = ConfirmationDialog.new()
	overture_dialog.title = "Overture · building area review"
	overture_dialog.ok_button_text = "Review selected area"
	var fields := VBoxContainer.new()
	fields.custom_minimum_size.x = 700
	overture_dialog.add_child(fields)
	_label(fields, "Buildings only · overturemaps 1.0.2 in the selected Python.
Explicit release; W/S/E/N area ≤ 0.02° per side. Crossing footprints stay whole.
Expected transfer / count: unknown. Snapshot cap 32 MiB / 20,000 features.
Network bytes and native reader memory can exceed snapshot size. Deadline 120s.
Progress reports captured snapshot bytes against the cap, not network completion.")
	overture_release = LineEdit.new()
	overture_release.placeholder_text = "Dated release, e.g. 2026-08-19.0 (never latest)"
	fields.add_child(overture_release)
	var grid := GridContainer.new()
	grid.columns = 4
	fields.add_child(grid)
	for item in [["West longitude",-180,180], ["South latitude",-80,84], ["East longitude",-180,180], ["North latitude",-80,84]]:
		overture_bbox.append(_import_number(grid, item[0], item[1], item[2], 0, 0.000001))
	overture_area = preload("./area_selector.gd").new()
	fields.add_child(overture_area)
	overture_area.bounds_selected.connect(func(bounds: Array):
		for i in range(4): overture_bbox[i].value = bounds[i]
	)
	var actions := HBoxContainer.new()
	fields.add_child(actions)
	_button(actions, "Fit coordinates", func(): overture_area.toggle_fit())
	_button(actions, "Area at import origin", func():
		var origin_bounds := [import_origin_lon.value, import_origin_lat.value, minf(180,import_origin_lon.value+0.001), minf(84,import_origin_lat.value+0.001)]
		for i in range(4): overture_bbox[i].value = origin_bounds[i]
		overture_area.toggle_fit()
	)
	overture_area_status = _label(fields, "")
	for field in overture_bbox: field.value_changed.connect(func(_value): _overture_changed())
	overture_release.text_changed.connect(func(_value): _overture_changed())
	_label(fields, "ODbL · © OpenStreetMap contributors, Overture Maps Foundation.
Source notices: https://docs.overturemaps.org/attribution/#buildings
Complete multipart/courtyard footprints are retained (recipe 5 for courtyards).
Vertical/underground parts reject; base/material/roof/use may be estimates.
Completed snapshots stay in import-sources even if conversion fails.
Cancel removes only this request's partial. Retry starts a fresh request.")
	for child in fields.get_children():
		if child is Label: child.custom_minimum_size.x = 700
	overture_dialog.confirmed.connect(_review_overture)
	overture_review = ConfirmationDialog.new()
	overture_review.title = "Confirm Overture area and source"
	overture_review.ok_button_text = "Download reviewed area"
	overture_review.confirmed.connect(_download_overture)
	overture_review.canceled.connect(func():
		overture_reviewed.clear()
		_open_overture()
	)
	add_child(overture_review)
	overture_dialog.canceled.connect(func():
		if acquisition_mode == "overture" and import_job != null: import_job.cancel()
	)
	add_child(overture_dialog)
	_overture_changed()

func _open_overture() -> void:
	if busy: return
	import_dialog.hide()
	overture_dialog.popup_centered(Vector2i(760, 560))

func _overture_plan() -> Dictionary:
	var bounds: Array = []
	for field in overture_bbox: bounds.append(field.value)
	return {"provider":"Overture", "release":overture_release.text.strip_edges(), "bbox":bounds, "theme":"buildings", "type":"building", "license":IMPORT_LAYER.OVERTURE_LICENSE}

func _download_overture() -> void:
	if busy: return
	if overture_reviewed.is_empty() or overture_reviewed != _overture_plan() or _overture_error() != "":
		_status("Area changed or has not been reviewed. Review the current selection first.")
		return
	overture_requested = overture_reviewed.duplicate(true)
	overture_request_revision = overture_revision
	overture_reviewed.clear()
	var folder := ProjectSettings.globalize_path("user://import-sources")
	var error := DirAccess.make_dir_recursive_absolute(folder)
	if error != OK:
		_status("Cannot create source folder: " + error_string(error))
		return
	var destination := folder.path_join(Crypto.new().generate_random_bytes(16).hex_encode() + ".overture.json")
	_begin_acquisition({"mode":"overture", "provider":"Overture", "plan":overture_requested.duplicate(true), "destination":destination})

func _overture_error() -> String:
	var query := _overture_plan()
	var b: Array = query.bbox
	var pattern := RegEx.new()
	pattern.compile("^20[0-9]{2}-[0-9]{2}-[0-9]{2}\\.[0-9]+$")
	if pattern.search(query.release) == null: return "Enter an explicit dated release (YYYY-MM-DD.N)."
	var date: PackedStringArray = query.release.substr(0,10).split("-")
	var year := int(date[0])
	var month := int(date[1])
	var day := int(date[2])
	var days := [31,29 if year%4 == 0 and (year%100 != 0 or year%400 == 0) else 28,31,30,31,30,31,31,30,31,30,31]
	if month < 1 or month > 12 or day < 1 or day > days[month-1]: return "Release date is not a calendar date."
	if b[0] >= b[2] or b[1] >= b[3]: return "Choose west < east and south < north; no dateline crossing."
	if b[2]-b[0] > 0.02 or b[3]-b[1] > 0.02: return "Area exceeds 0.02 degrees per side. Select a smaller area."
	return ""

func _overture_changed() -> void:
	overture_revision += 1
	overture_reviewed.clear()
	overture_review.hide()
	overture_area.set_bounds(_overture_plan().bbox)
	var error := _overture_error()
	overture_dialog.get_ok_button().disabled = error != ""
	overture_area_status.text = error if error != "" else "Valid query envelope · crossing buildings stay whole; origin is chosen separately on import."

func _review_overture() -> void:
	if busy: return
	var error := _overture_error()
	if error != "":
		_status(error)
		_open_overture()
		return
	import_dialog.hide()
	overture_dialog.hide()
	overture_reviewed = _overture_plan().duplicate(true)
	var b: Array = overture_reviewed.bbox
	overture_review.dialog_text = "Release: %s · buildings only\nW %.6f / S %.6f / E %.6f / N %.6f\n\nQuery envelope, not a crop. All returned footprint parts stay whole.\nTransfer/count unknown; captured snapshot ≤32 MiB / 20,000 features.\nNetwork bytes and reader memory may exceed that cap. Deadline 120s.\nODbL · OpenStreetMap contributors / Overture Maps Foundation.\n\nDownload preserves a new source; it does not adopt or change the map.\nNext: set explicit geographic/local origins, import, review and adopt.\nCancel stops this request; completed sources remain; retry starts fresh." % [overture_reviewed.release,b[0],b[1],b[2],b[3]]
	overture_review.popup_centered(Vector2i(740,360))
