extends Control
const I18N := preload("./locale_text.gd")
const PACKAGE_WORK := preload("./package_work.gd")
const PAYLOAD_FILES := preload("./authoring_files.gd")
const REPORT := preload("./export_report.gd")
const ATTACH_USEC := 8000
const CACHE_CELLS := 4
const CACHE_BYTES := 256 * 1024 * 1024
var package_work: RefCounted
var density_panel: VBoxContainer
var density_deferred_package := {}
var package_started_usec := 0
var package_operation := ""
var regional_grouping: SpinBox
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
var preview_camera := preload("./preview_camera.gd").new()
var framed_cell := Vector2i(-1, -1)
var preview_stats := {"generated": 0, "reused": 0, "attachment_frames": 0, "max_batch_usec": 0, "max_frame_usec": 0}
var export_report: AcceptDialog
var last_export_report := {}
var track_workbench: Node
var new_map_dialog: ConfirmationDialog
var new_free_roam: CheckBox
var track_job: Node
var track_dialog: AcceptDialog
var track_panel: Control
var track_epoch := -1
var track_request := -1
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
var author_panel: PanelContainer
const DEM_PANEL := preload("./dem_panel.gd")
var dem_panel: ConfirmationDialog
const STORE := preload("./document_store.gd")
const CANVAS := preload("./map_canvas.gd")
const GIMMICK_GEOMETRY := preload("res://addons/mapkit/godot/gimmick_geometry.gd")
const RENDERER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
var store := STORE.new()
var canvas: Control
var status_label: Label
var project_label: Label
var commands: PopupPanel
var workspace_views: HSplitContainer
var preview_dock: VBoxContainer
var view_mode := "split"
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
var environment_preview := preload("./environment_preview.gd").new()
var environment_renderer: Node3D
var preview_resources := preload("res://addons/mapkit/godot/render_resource_cache.gd").new()
var preview_world: Node3D
var preview_x: SpinBox
var preview_y: SpinBox
var dialog: FileDialog
var dialog_action := ""
var busy := false:
	set(value):
		busy = value
		store.set_external_lock(value)
		if is_instance_valid(operation_dim): _sync_operation_ui()
var operation_dim: ColorRect
var operation_label: Label
var applying_row: HBoxContainer
var applying_spinner: Control
var operation_spinner: Control
var file_continuation := ""
var generation_lock := false
var file_dialog_lock := false

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
var import_details: AcceptDialog
var import_summary: TextEdit
var import_review_generation := 0
var import_review_controls: Array = []
const IMPORT_JOB := preload("./import_job.gd")
const TERRAIN_NATIVE_JOB := preload("./terrain_native_job.gd")
const HEIGHTMAP_NATIVE_JOB := preload("./heightmap_native_job.gd")
const ASSET_NATIVE_JOB := preload("./asset_native_job.gd")
const DEM_NATIVE_JOB := preload("./dem_native_job.gd")
const IMPORT_NATIVE_JOB := preload("./import_native_job.gd")
var import_job: RefCounted
var import_selection_signature := ""
var import_controls_revision := 0
var native_request_identity := ""
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
const DEM_JOB := preload("./dem_job.gd")
var osm_crop_button: Button
var osm_panel: RefCounted
var osm_import_revision := -1
var vertical_panel: RefCounted
var vertical_import_revision := -1
var dem_mode := ""

const IMPORT_RECOVERY := preload("./import_recovery_panel.gd")
var import_recovery: AcceptDialog

var selected_field := ""
var selected_record: Dictionary = {}
var displayed_map_id := ""
var displayed_session := -1

const WORKBENCH_STYLE := preload("./workbench_style.gd")
var roam_palette: VBoxContainer

func _ready() -> void:
	get_tree().auto_accept_quit = false
	get_window().min_size = Vector2i(1024, 720)
	_build_ui()
	track_workbench=preload("./track_workbench.gd").new()
	add_child(track_workbench)
	track_workbench.build(self)
	commands.settings_changed.connect(func():
		snap_toggle.tooltip_text = commands.tooltip("edit.toggle_snap")
		track_workbench.snap.tooltip_text = commands.tooltip("edit.toggle_snap"))
	commands.load_settings()
	commands.opening_popup.connect(_cancel_editing)
	get_tree().node_added.connect(_watch_ui_node)
	_decorate_ui(self)
	_build_operation_ui()
	store.lock_changed.connect(_sync_operation_ui)
	store.file_operation_finished.connect(_file_finished)
	store.autosave_finished.connect(func(failure: String):
		if failure != "": _status(I18N.diagnostic(failure)))
	store.changed.connect(_document_changed)
	store.new_track()
	_restore_workbench.call_deferred()
	var timer := Timer.new()
	timer.wait_time = 15
	timer.timeout.connect(_autosave)
	add_child(timer)
	timer.start()
	if DirAccess.dir_exists_absolute(ProjectSettings.globalize_path("user://recovery")):
		_status(I18N.t("Recovery snapshots are available. Use Recover to inspect one; saved projects stay unchanged."))

func _autosave() -> void:
	if store.dirty: store.start_autosave()

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT or what == NOTIFICATION_WM_WINDOW_FOCUS_OUT: _cancel_editing()
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_request_document_action("close")

func _build_ui() -> void:
	theme = WORKBENCH_STYLE.create_theme()
	RenderingServer.set_default_clear_color(WORKBENCH_STYLE.PANEL)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 4 if side == "top" else 8)
	add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	var title_row := HBoxContainer.new()
	title_row.name = "MenuRow"
	column.add_child(title_row)
	WORKBENCH_STYLE.outline(title_row)
	commands = preload("./workspace_commands.gd").new()
	add_child(commands)
	_register_commands()
	commands.menus(title_row)
	var title := Label.new()
	title.text = I18N.t("MAP EDITOR")
	title.add_theme_color_override("font_color", WORKBENCH_STYLE.BLUE)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(title)
	var bar := HBoxContainer.new()
	column.add_child(bar)
	var toolbar_groups := {}
	for group in [["File", ["file.new", "file.open", "file.save", "file.export_map"]], ["Edit", ["edit.undo", "edit.redo", "edit.duplicate", "edit.delete"]], ["Create", ["create.seed_track"]], ["Inspect", ["validate.validate", "view.commands", "edit.shortcuts"]]]:
		var group_row := HBoxContainer.new()
		bar.add_child(group_row)
		toolbar_groups[group[0]] = group_row
		WORKBENCH_STYLE.outline(group_row)
		_label(group_row, group[0])
		for id: String in group[1]: commands.button(group_row, id)
	regional_grouping = SpinBox.new()
	regional_grouping.min_value = 1
	regional_grouping.max_value = 128
	regional_grouping.value = 8
	regional_grouping.prefix = I18N.t("Regional cells ")
	regional_grouping.tooltip_text = I18N.t("Storage grouping only. Execution cell size and map quality stay unchanged.")
	var import_work_button := Button.new()
	WORKBENCH_STYLE.decorate(import_work_button, "Import work", "Inspect leftover import work.", "import")
	import_work_button.tooltip_text = I18N.t("Inspect leftover local import work without changing files.")
	toolbar_groups["Inspect"].add_child(import_work_button)
	import_recovery = IMPORT_RECOVERY.new()
	import_recovery.banner = import_work_button
	add_child(import_recovery)
	import_work_button.pressed.connect(import_recovery.show_report)
	project_label = Label.new()
	project_label.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	project_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	column.add_child(project_label)
	WORKBENCH_STYLE.outline(project_label)
	outer_split = HSplitContainer.new()
	var split := outer_split
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(split)
	canvas = CANVAS.new()
	canvas.store = store
	canvas.custom_minimum_size = Vector2(100, 100)
	canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	canvas.status.connect(_status)
	canvas.terrain_requested.connect(_start_terrain)
	canvas.selection_changed.connect(_selection)
	left_dock = VBoxContainer.new()
	var left := left_dock
	left.custom_minimum_size.x = 245
	split.add_child(left)
	roam_palette = preload("./workbench_palette.gd").new()
	roam_palette.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left.add_child(roam_palette)
	var tool_entries: Array[Dictionary] = []
	for name in ["Select", "Road", "Surface area", "Water", "Island", "Building", "Cylinder wall", "Forest", "Orchard", "Terrain", "Place", "Repeat", "Entrance", "Exclusion"]:
		tool_entries.append({"id":"tool." + name.to_snake_case(), "group":"Free roam", "section":"Drawing tools"})
	roam_palette.build(commands, "roam", tool_entries)
	for tile in roam_palette.tiles: tool_buttons[commands.commands[commands.index_of(tile.id)].label] = tile.button
	author_panel = AUTHOR_PANEL.new()
	author_panel.editor = self
	author_panel.hide()
	var edits := HBoxContainer.new()
	left.add_child(edits)
	WORKBENCH_STYLE.outline(edits)
	_button(edits, "Authoring settings…", func(): author_panel.open())
	commands.button(edits, "edit.duplicate")
	commands.button(edits, "edit.delete")
	var snap := HBoxContainer.new()
	left.add_child(snap)
	WORKBENCH_STYLE.outline(snap)
	snap_toggle = CheckButton.new()
	snap_toggle.text = I18N.t("Snap (m)")
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
	WORKBENCH_STYLE.outline(center)
	selection_label = Label.new()
	selection_label.add_theme_color_override("font_color", WORKBENCH_STYLE.BLUE)
	selection_label.text = I18N.t("2D MAP  ·  Select  ·  0 selected")
	center.add_child(selection_label)
	canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var view_modes := HBoxContainer.new()
	center.add_child(view_modes)
	for mode in ["2d", "3d", "split"]:
		commands.button(view_modes, "view." + mode)
	workspace_views = HSplitContainer.new()
	workspace_views.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.add_child(workspace_views)
	workspace_views.add_child(canvas)
	WORKBENCH_STYLE.outline(canvas)
	tool_hint = Label.new()
	tool_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tool_hint.max_lines_visible = 2
	tool_hint.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	tool_hint.add_theme_font_size_override("font_size", 12)
	center.add_child(tool_hint)
	right_dock = VSplitContainer.new()
	right_dock.custom_minimum_size.x = 248
	center_split.add_child(right_dock)
	var property_dock := VBoxContainer.new()
	property_dock.custom_minimum_size.y = 140
	property_dock.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right_dock.add_child(property_dock)
	WORKBENCH_STYLE.outline(property_dock)
	_label(property_dock, "PROPERTIES").add_theme_color_override("font_color", WORKBENCH_STYLE.BLUE)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	property_dock.add_child(scroll)
	properties = VBoxContainer.new()
	properties.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(properties)
	apply_button = _button(property_dock, "Apply properties", _apply_properties)
	preview_dock = VBoxContainer.new()
	preview_dock.custom_minimum_size = Vector2(200, 160)
	preview_dock.size_flags_vertical = Control.SIZE_EXPAND_FILL
	workspace_views.add_child(preview_dock)
	WORKBENCH_STYLE.outline(preview_dock)
	var controls := HFlowContainer.new()
	preview_dock.add_child(controls)
	_label(controls, "Cell")
	preview_x = SpinBox.new()
	preview_y = SpinBox.new()
	for spin in [preview_x, preview_y]:
		spin.min_value = 0
		spin.max_value = 127
		controls.add_child(spin)
	_button(controls, "3D Preview", _preview)
	_button(controls, "Frame selection", _frame_selection)
	preview_x.value_changed.connect(_preview_cell_changed)
	preview_y.value_changed.connect(_preview_cell_changed)
	var preview_hint := Label.new()
	preview_hint.text = I18N.t("Orbit / pan / zoom")
	preview_hint.tooltip_text = I18N.t("Right drag: orbit · Middle drag: pan · Wheel: zoom · Refresh loads only the selected cell")
	preview_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	preview_hint.add_theme_font_size_override("font_size", 12)
	preview_dock.add_child(preview_hint)
	full_generation = CheckButton.new()
	full_generation.text = I18N.t("Full 3D check on Validate / Export")
	full_generation.add_theme_font_size_override("font_size", 12)
	property_dock.add_child(full_generation)
	property_dock.add_child(regional_grouping)
	right_dock.add_child(author_panel)
	export_report = REPORT.new()
	export_report.theme = theme
	add_child(export_report)
	var preview_container := SubViewportContainer.new()
	preview_container.stretch = true
	preview_container.focus_mode = Control.FOCUS_ALL
	preview_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	preview_container.custom_minimum_size = Vector2(200, 100)
	preview_dock.add_child(preview_container)
	preview_container.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.pressed: preview_container.grab_focus()
		if track_workbench != null and track_workbench.input(event):
			preview_container.accept_event()
		elif author_panel != null and author_panel.gimmick_panel != null and author_panel.gimmick_panel.surface_input(event):
			preview_container.accept_event()
		elif preview_camera.input(event): preview_container.accept_event())
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
	preview_camera.camera = camera
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -25, 0)
	preview_world.add_child(sun)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	preview_world.add_child(world_environment)
	environment_renderer = preload("res://addons/mapkit/godot/environment_renderer.gd").new()
	environment_renderer.configure(world_environment.environment,sun,true)
	preview_world.add_child(environment_renderer)
	var time := preload("./time_of_day_picker.gd").new()
	time.value = 12
	controls.add_child(time)
	time.value_changed.connect(func(value: float): environment_preview.seconds = value*3600.0)
	var weather := OptionButton.new()
	for value in [I18N.t("Clear"),I18N.t("Cloudy"),I18N.t("Rain"),I18N.t("Snow")]: weather.add_item(value)
	controls.add_child(weather)
	weather.item_selected.connect(func(index: int):
		environment_preview.weather = ["clear","cloudy","rain","snow"][index]
		environment_preview.previous_weather = environment_preview.weather
		environment_preview.wet = 2 if index == 2 else 0
		environment_preview.snow = 2 if index == 3 else 0)
	var output_tabs := TabContainer.new()
	output_tabs.custom_minimum_size.y = 128
	column.add_child(output_tabs)
	var activity := VBoxContainer.new()
	activity.name = "Activity"
	output_tabs.add_child(activity)
	var view_bar := HFlowContainer.new()
	activity.add_child(view_bar)
	WORKBENCH_STYLE.outline(view_bar)
	cancel_button = _button(view_bar, "Cancel operation", _cancel_operation)
	cancel_button.disabled = true
	retry_import_button = _button(view_bar, "Retry import…", _import_geojson)
	retry_import_button.hide()
	_button(view_bar, "Tools / layers", func(): left_dock.visible = not left_dock.visible)
	_button(view_bar, "Properties / 3D", func(): right_dock.visible = not right_dock.visible)
	_button(view_bar, "Frame selection", _frame_current)
	_button(view_bar, "Reset panels", _reset_panels)
	validation_label = Label.new()
	validation_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	validation_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	activity.add_child(validation_label)
	density_panel = preload("./chunk_density_panel.gd").new()
	density_panel.name = "Problems"
	output_tabs.add_child(density_panel)
	density_panel.configure(store, canvas)
	density_panel.busy_source = func(): return busy
	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size.y = 20
	status_label.text = I18N.t("Choose a tool. Search commands or open Shortcuts for keyboard controls.")
	activity.add_child(status_label)
	import_progress = ProgressBar.new()
	import_progress.visible = false
	activity.add_child(import_progress)
	dialog = FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.canceled.connect(func():
		_release_file_dialog_lock()
		if dialog_action == "save_transition": pending_document_action.clear()
	)
	dialog.dir_selected.connect(_path_selected)
	dialog.file_selected.connect(_path_selected)
	add_child(dialog)
	unsaved_dialog = ConfirmationDialog.new()
	unsaved_dialog.title = I18N.t("Unsaved changes")
	unsaved_dialog.ok_button_text = I18N.t("Save and continue")
	unsaved_dialog.cancel_button_text = I18N.t("Keep editing")
	recovery_continue_button = unsaved_dialog.add_button(I18N.t("Keep recovery and continue"), false, "recovery")
	unsaved_dialog.confirmed.connect(_save_before_document_action)
	unsaved_dialog.custom_action.connect(func(action):
		if action == "recovery":
			unsaved_dialog.hide()
			_continue_document_action()
	)
	unsaved_dialog.canceled.connect(func(): pending_document_action.clear())
	add_child(unsaved_dialog)
	import_dialog = ConfirmationDialog.new()
	import_dialog.title = I18N.t("Import vector source")
	import_dialog.ok_button_text = I18N.t("Choose source…")
	import_license = LineEdit.new()
	import_license.placeholder_text = I18N.t("Source license (required)")
	import_license.custom_minimum_size = Vector2(540, 40)
	var import_fields := VBoxContainer.new()
	import_fields.custom_minimum_size.x = 700
	import_dialog.add_child(import_fields)
	_label(import_fields, "Local sources up to 32 MiB; PBF streaming in OSM crop supports up to 2 GiB.\nWGS84 needs pyproj 3.7.2; OSM also needs osmium 4.3.1 in the selected Python.")
	import_fields.get_child(0).custom_minimum_size.x = 700
	import_source_format = OptionButton.new()
	for format_title in [I18N.t("GeoJSON"), I18N.t("OSM PBF extract (.osm.pbf)"), I18N.t("OSM XML extract (.osm)"), I18N.t("Overture building area snapshot (.overture.json)"), I18N.t("Overture transportation snapshot (.overture-roads.json)"), I18N.t("Overture land cover snapshot (.overture-land-cover.json)")]: import_source_format.add_item(format_title)
	import_fields.add_child(import_source_format)
	osm_crop_button = _button(import_fields, "OSM crop area…", func(): osm_panel.open())
	vertical_panel = preload("./vertical_panel.gd").new()
	vertical_panel.setup(self)
	_button(import_fields, "OSM height reference…", func(): vertical_panel.open())
	_button(import_fields, "Import Copernicus DEM…", func(): dem_panel.open())
	import_fields.add_child(import_license)
	import_accuracy = LineEdit.new()
	import_accuracy.placeholder_text = I18N.t("Source accuracy / resolution (unknown if omitted)")
	import_fields.add_child(import_accuracy)
	import_python = LineEdit.new()
	import_python.placeholder_text = I18N.t("Python 3 executable (name or absolute path)")
	var settings := ConfigFile.new()
	settings.load("user://editor_tools.cfg")
	import_python.text = str(settings.get_value("import", "python", "python" if OS.get_name() == "Windows" else "python3"))
	import_fields.add_child(import_python)
	import_coordinate_mode = OptionButton.new()
	import_coordinate_mode.add_item(I18N.t("Local x/y metres (explicit extension)"))
	import_coordinate_mode.add_item(I18N.t("WGS84 longitude/latitude → local map (UTM)"))
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
			import_license.text = IMPORT_LAYER.OVERTURE_LAND_COVER_LICENSE if index == 5 else IMPORT_LAYER.OVERTURE_TRANSPORTATION_LICENSE if index == 4 else IMPORT_LAYER.OVERTURE_LICENSE if index == 3 else IMPORT_LAYER.OSM_LICENSE
			import_coordinate_mode.select(1)
			geographic.visible = true
		elif import_license.text in [IMPORT_LAYER.OSM_LICENSE, IMPORT_LAYER.OVERTURE_LICENSE, IMPORT_LAYER.OVERTURE_TRANSPORTATION_LICENSE, IMPORT_LAYER.OVERTURE_LAND_COVER_LICENSE]:
			import_license.text = ""
		import_dialog.get_ok_button().disabled = import_license.text.strip_edges() == ""
	)

	_button(import_fields, "Import / retry last source", func():
		import_dialog.hide()
		if last_import_source == "": _status(I18N.t("Choose a source file first."))
		else: _start_import(last_import_source, import_license.text.strip_edges())
	)
	import_dialog.get_ok_button().disabled = true
	import_license.text_changed.connect(func(value): import_dialog.get_ok_button().disabled = value.strip_edges() == "")
	import_dialog.confirmed.connect(func(): _choose("import"))
	add_child(import_dialog)
	import_review = ConfirmationDialog.new()
	import_review.title = I18N.t("Review imported layer")
	import_review.ok_button_text = I18N.t("Adopt new layer")
	import_review.cancel_button_text = I18N.t("Discard")
	var review_fields := VBoxContainer.new()
	import_review.add_child(review_fields)
	import_summary = TextEdit.new()
	import_summary.editable = false
	import_summary.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	import_summary.custom_minimum_size = Vector2(640, 340)
	import_summary.size_flags_vertical = Control.SIZE_EXPAND_FILL
	review_fields.add_child(import_summary)
	_button(review_fields, "Browse exact details", _open_import_details)
	import_review.confirmed.connect(_adopt_import)
	import_review.canceled.connect(func():
		_discard_import()
		validation_label.text = I18N.t("Import discarded · document unchanged")
		_status(I18N.t("Imported layer discarded. Use Retry import to prepare it again."))
	)
	add_child(import_review)
	import_details = preload("./import_review_browser.gd").new()
	# Nest under the review so closing detail returns to its modal owner.
	import_review.add_child(import_details)
	for control in [import_source_format, import_coordinate_mode]:
		control.item_selected.connect(func(_index): _import_controls_changed())
	for control in [import_origin_lon, import_origin_lat, import_origin_x, import_origin_y]:
		control.value_changed.connect(func(_value): _import_controls_changed())
	osm_panel = preload("./osm_area_panel.gd").new()
	osm_panel.setup(self)
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

func _button(parent: Node, text: String, action: Callable) -> Button:
	for command: Dictionary in commands.commands:
		if command.action == action: return commands.button(parent, command.id)
	return WORKBENCH_STYLE.button(parent, text, action)

func _label(parent: Node, text: String) -> Label:
	var label := Label.new()
	label.text = I18N.t(text)
	if parent is VBoxContainer:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(label)
	return label

func _new() -> void:
	_cancel_editing()
	if not is_instance_valid(new_map_dialog):
		new_map_dialog=ConfirmationDialog.new()
		new_map_dialog.title=I18N.t("New Map")
		add_child(new_map_dialog)
		new_free_roam=CheckBox.new()
		new_free_roam.text=I18N.t("Free roam map (default: track assembly)")
		new_map_dialog.add_child(new_free_roam)
		new_map_dialog.confirmed.connect(func(): _request_document_action("new"))
	new_free_roam.button_pressed=false
	new_map_dialog.popup_centered(Vector2i(400,160))

func _request_document_action(action: String, path: String = "") -> void:
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	_cancel_editing()
	canvas.cancel_interaction()
	if store.dirty:
		var failure := store.autosave()
		if failure != "":
			_status((I18N.t("Cannot close safely: ") if action == "close" else I18N.t("Cannot leave document: ")) + I18N.diagnostic(failure))
			return
	pending_document_action = {"action": action, "path": path, "session": store.session_id}
	if not store.dirty:
		_continue_document_action()
		return
	unsaved_dialog.dialog_text = I18N.t("Save changes before %s?\nA recovery snapshot retains committed changes and file references.\nKeep original imported files available. Keep editing cancels this action.") % {"new":I18N.t("creating a new map"), "open":I18N.t("opening another project"), "recover":I18N.t("recovering another document"), "close":I18N.t("closing the editor")}[action]
	unsaved_dialog.popup_centered(Vector2i(700, 200))
	unsaved_dialog.get_cancel_button().grab_focus()

func _save_before_document_action() -> void:
	if pending_document_action.is_empty(): return
	if pending_document_action.session != store.session_id:
		pending_document_action.clear()
		_status(I18N.t("Document changed; request the action again."))
		return
	if busy:
		_status(I18N.t("Cancel the active operation or wait, then try again. Your document stays open."))
		pending_document_action.clear()
		return
	if store.project_path == "":
		_choose("save_transition")
		return
	_start_save(store.project_path, "save_transition")

func _continue_document_action() -> void:
	if store.editing_locked(): return
	if pending_document_action.is_empty(): return
	var request := pending_document_action.duplicate()
	pending_document_action.clear()
	if request.session != store.session_id:
		_status(I18N.t("Document changed; request the action again."))
		return
	# Recheck retention at consumption, including edits since the prompt opened.
	var failure := store.autosave() if store.dirty else ""
	if failure != "":
		_status(I18N.t("Cannot leave document: ") + I18N.diagnostic(failure))
		return
	match request.action:
		"new":
			store.new_track(new_free_roam.button_pressed if is_instance_valid(new_free_roam) else false)
			_status(I18N.t("New map. Previous unsaved changes remain in Recover."))
		"open": failure = store.open_project(request.path)
		"recover": failure = store.recover(request.path)
		"close": get_tree().quit()
	if failure != "": _status(I18N.diagnostic(failure) + I18N.t(" Current document retained. Use Recover to inspect a backup."))
	elif request.action in ["open", "recover"]: _status(I18N.t("Ready: ") + request.path)

func _choose(action: String) -> void:
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	_cancel_editing()
	dialog_action = action
	if action in ["save", "save_transition", "save_for_export", "save_for_drive", "export"]:
		file_dialog_lock = true
		store.set_external_lock(true)
	dialog.filters = PackedStringArray()
	dialog.title = {"open":I18N.t("Open project directory"), "save":I18N.t("Save project to directory"), "save_transition":I18N.t("Save before continuing"), "save_for_export":I18N.t("Save project before export"), "save_for_drive":I18N.t("Save project before test drive"), "export":I18N.t("Export package — choose a new filename"), "recover":I18N.t("Recover a document"), "import":I18N.t("Choose source to review")}.get(action, I18N.t("Choose file"))
	if action in ["open", "save", "save_for_drive", "save_transition", "save_for_export"]:
		dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
	else:
		dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE if action == "export" else FileDialog.FILE_MODE_OPEN_FILE
		dialog.filters = I18N.filters(["*.memap ; Map package", "*.mkregions ; Indexed regional map"] if action == "export" else ["*.json ; Recovery snapshot"])
		if action == "import":
			dialog.filters = I18N.filters(["*.geojson,*.json ; GeoJSON (explicit coordinates)"])
			if import_source_format.selected == 1: dialog.filters = I18N.filters(["*.osm.pbf,*.pbf ; OSM PBF snapshot"])
			if import_source_format.selected == 3: dialog.filters = I18N.filters(["*.overture.json ; Overture building snapshot"])
			if import_source_format.selected == 5: dialog.filters = I18N.filters(["*.overture-land-cover.json ; Overture land cover snapshot"])
			if import_source_format.selected == 4: dialog.filters = I18N.filters(["*.overture-roads.json ; Overture transportation snapshot"])
			if import_source_format.selected == 2: dialog.filters = I18N.filters(["*.osm ; OSM XML snapshot"])
		if action == "reopen_package":
			dialog.title = I18N.t("Restore package into a new adjacent .source directory")
			dialog.filters = I18N.filters(["*.memap ; Map package", "*.mkregions ; Indexed regional map"])
		if action == "recover":
			dialog.filters = I18N.filters(["* ; Recovery, previous or pending document"])
			dialog.current_dir = ProjectSettings.globalize_path("user://recovery")
	dialog.popup_centered_ratio(0.8)

func _release_file_dialog_lock() -> void:
	if not file_dialog_lock: return
	file_dialog_lock = false
	store.set_external_lock(busy or generation_lock)

func _path_selected(path: String) -> void:
	_release_file_dialog_lock()
	var failure := ""
	match dialog_action:
		"reopen_package":
			if busy: return
			var destination := path + ".source"
			if DirAccess.dir_exists_absolute(destination):
				_status(I18N.t("Destination already exists: ") + destination + I18N.t(". Open it as a project or choose a different package copy."))
				return
			package_work = PACKAGE_WORK.new()
			var task: RefCounted = package_work
			worker_generation = generation
			busy = true
			var error := worker.start(func(): return {"operation":"reopen_package","result":task.reopen_package(path,destination)})
			if error != OK:
				busy = false
				package_work = null
				_status(I18N.diagnostic(error_string(error)))
			return
		"import":
			_start_worker("import", path, import_license.text.strip_edges())
			return
		"open", "recover":
			_request_document_action(dialog_action, path)
			return
		"save", "save_transition", "save_for_export", "save_for_drive":
			if dialog_action == "save_transition" and (pending_document_action.is_empty() or pending_document_action.session != store.session_id):
				pending_document_action.clear()
				_status(I18N.t("Document changed or action cancelled; choose Save again."))
				return
			_start_save(path, dialog_action)
			return
		"export":
			if busy:
				_status(I18N.t("Wait for the current preview or export."))
				return
			_start_package("export", path)
			return
	_status(I18N.diagnostic(failure) if failure != "" else I18N.t("Ready: ") + path)
	if failure == "": _document_changed()

func _save() -> void:
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	if busy:
		_status(I18N.t("Wait for the active operation before saving."))
		return
	if store.project_path == "":
		_choose("save")
	else:
		_start_save(store.project_path)

func _import_geojson() -> void:
	_cancel_editing()
	if not busy:
		import_dialog.get_ok_button().disabled = not IMPORT_LAYER._text(import_license.text.strip_edges())
		import_dialog.popup_centered(Vector2i(760, 520))

func _export() -> void:
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	if busy:
		_status(I18N.t("Cancel the active operation or wait before exporting."))
		return
	if store.project_path == "":
		_choose("save_for_export")
		return
	_choose("export")

func _validate() -> void:
	if track_workbench != null and track_workbench.active:
		store.retry_track_edit()
		track_workbench.refresh()
		_status(track_workbench.report.text)
		return
	_start_package("report")

func _selection(ids: Array) -> void:
	if commands != null: commands.refresh_buttons()
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
	tool_hint.text = I18N.t(canvas.tool) + " · " + I18N.t(_tool_help(canvas.tool))
	tool_hint.text += I18N.t("\nCancel: ") + commands.shortcut_text("edit.cancel_interaction")
	tool_hint.tooltip_text = tool_hint.text
	selection_label.text = I18N.t("2D MAP  ·  %s  ·  %d selected") % [I18N.t(canvas.tool), property_records.size()]
	apply_button.disabled = property_records.is_empty()
	if property_records.is_empty():
		var free_roam := CheckBox.new()
		free_roam.text = I18N.t("Free roam map")
		free_roam.tooltip_text = I18N.t("Show results after finishing, then return to free roam.")
		free_roam.button_pressed = store.document.free_roam
		free_roam.toggled.connect(func(value: bool):
			var failure: String = store.set_free_roam(value)
			if failure != "": _status(I18N.diagnostic(failure)))
		properties.add_child(free_roam)
		_label(properties, "Select objects on the map or in layers.")
		_label(properties, "Shift toggles; drag empty space to box-select.")
		return
	selected_field = property_records[0].field
	selected_record = property_records[0].record.duplicate(true)
	var title := Label.new()
	title.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	title.text = str(selected_record.id) if property_records.size() == 1 else I18N.t("%d objects selected") % property_records.size()
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
			_label(properties, I18N.t("Structure: ") + I18N.builtin(str(selected_record.kind)))
			_label(properties, "Moving endpoints also moves incident road ends.")
		"zones":
			_number_property("Spacing (m)", float(selected_record.spacing_cm) / 100.0, 2.0, 200.0, func(v): property_changes.spacing_cm = int(round(v * 100)))
			_number_property("Density (%)", float(selected_record.density_per_mille) / 10.0, 0.0, 100.0, func(v): property_changes.density_per_mille = int(round(v * 10)))
			_choice_property("Planting", ["forest", "orchard"], str(selected_record.kind), func(v): property_changes.kind = v)
		"placements":
			_label(properties, I18N.t("Asset: ") + str(selected_record.asset_id))
			_choice_property("Rotation", ["0", "90", "180", "270"], str(int(selected_record.quarter_turns) * 90), func(v): property_changes.quarter_turns = int(v) / 90)
			_number_property("Yaw offset (millidegrees)", selected_record.get("yaw_offset_mdeg", 0), -360000, 360000, func(v): property_changes.yaw_offset_mdeg = int(v))
		"repetitions":
			_label(properties, I18N.t("Asset: ") + str(selected_record.asset_id))
			_number_property("Spacing (m)", float(selected_record.spacing_cm) / 100.0, 0.01, 1000.0, func(v): property_changes.spacing_cm = int(round(v * 100)))
		"nodes":
			_label(properties, I18N.t("Shared road endpoint · level ") + str(selected_record.level))

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
		select.add_item(I18N.builtin(value))
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
			_status(I18N.t("Selection is hidden or locked."))
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
			_status(I18N.t("Movement affects a hidden or locked layer: ") + entry.key)
			return
	var failure: String = canvas.author.apply("Edit selection properties", patches, selected_field == "roads")
	_status(I18N.diagnostic(failure) if failure != "" else I18N.t("Properties updated."))
	if failure == "": _selection(canvas.selected)

func _document_changed() -> void:
	if track_workbench != null: track_workbench.cancel_interaction(false)
	if not density_deferred_package.is_empty():
		density_deferred_package.clear()
		busy = false
	if import_job != null: import_job.cancel()
	native_request_identity = ""
	_discard_import()
	generation += 1
	if package_work != null: package_work.cancel()
	_cancel_attachment()
	if preview_enabled: preview_due = Time.get_ticks_msec() + 150
	canvas.cancel_interaction()
	var map_id := str(store.document.get("map_id", ""))
	if displayed_session != store.session_id:
		_clear_preview_cache()
		preview_enabled = false
		preview_due = 0
		canvas.selected.clear()
		canvas.layer_state = view_settings.get_value("layers", map_id, {}).duplicate(true)
		canvas.fit_map()
	displayed_map_id = map_id
	displayed_session = store.session_id
	canvas.normalize_selection()
	layers.refresh()
	_selection(canvas.selected)
	validation_label.text = I18N.t("Document valid · Preview needs refresh")
	var bounds: Dictionary = store.document.bounds
	preview_x.max_value = ceili(float(bounds.max[0] - bounds.min[0]) / store.document.cell_size_cm) - 1
	preview_y.max_value = ceili(float(bounds.max[1] - bounds.min[1]) / store.document.cell_size_cm) - 1
	project_label.text = (store.project_path if store.project_path != "" else I18N.t("Unsaved project")) + (I18N.t("  • modified") if store.dirty else "")
	canvas.queue_redraw()
	if track_workbench != null: track_workbench.refresh()
	commands.refresh_buttons()

func _tool_help(name: String) -> String:
	var hints := {
		"Select":"Click to select; Shift toggles. Drag empty space to box-select. Edit in Properties, then Apply.",
		"Road":"Click at least two points; right-click to finish. Set width, surface and structure in Authoring settings.",
		"Building":"Click at least three corners; right-click to finish. Select the building to edit height and material.",
		"Water":"Draw a non-solid water polygon; right-click finishes. Set surface, bottom and flow in Authoring settings.",
		"Island":"Select a water body, then draw a dry island; right-click finishes.",
		"Cylinder wall":"Click the centre to place a solid round wall. Set radius and height in Authoring settings; select it to resize.",
		"Forest":"Click at least three corners; right-click to finish. Select the zone to edit density and spacing.",
		"Orchard":"Click at least three corners; right-click to finish. Select the zone to edit density and spacing.",
		"Terrain":"Drag to paint terrain. Choose brush, radius and strength in Authoring settings; release commits one Undo step.",
		"Place":"Click to place the asset chosen in Authoring settings. Select it to change rotation.",
		"Repeat":"Click a path; right-click to finish. Choose asset and spacing in Authoring settings.",
		"Entrance":"Select one building first, then draw an entrance polygon; right-click to finish.",
		"Exclusion":"Select one forest/orchard zone first, then draw an exclusion polygon; right-click to finish."
	}
	return str(hints.get(name, "")) + "\nWheel zooms · Middle drag pans"

func _set_tool(name: String) -> void:
	_cancel_editing()
	if not store.document.get("free_roam", false):
		if track_workbench != null: track_workbench.show_hint()
		return
	canvas.tool = name
	roam_palette.select_tool("tool." + name.to_snake_case())
	_selection(canvas.selected)
	canvas.queue_redraw()

func _has_selection() -> bool:
	if not store.document.get("free_roam", false):
		return track_workbench != null and track_workbench.selected >= 0
	return canvas != null and not canvas.selected.is_empty()

func _duplicate_current() -> void:
	_cancel_editing()
	if store.document.get("free_roam", false): canvas.duplicate_selection()
	else: track_workbench.duplicate_piece()

func _can_delete() -> bool:
	return _has_selection() or (store.document.get("free_roam", false) and not canvas.draft.is_empty())

func _delete_current() -> void:
	if store.document.get("free_roam", false) and not canvas.draft.is_empty():
		canvas.draft.pop_back()
		canvas.queue_redraw()
		return
	_cancel_editing()
	if store.document.get("free_roam", false): canvas.delete_selection()
	else: track_workbench.delete_piece()

func _frame_current() -> void:
	if store.document.get("free_roam", false): canvas.fit_map()
	else: track_workbench.frame_selection()

func _toggle_snap() -> void:
	if store.document.get("free_roam", false): snap_toggle.button_pressed = not snap_toggle.button_pressed
	else:
		track_workbench.snap.button_pressed = not track_workbench.snap.button_pressed
		track_workbench.placement.invalidate_candidate()

func _cancel_editing() -> void:
	if canvas != null: canvas.cancel_interaction()
	if track_workbench != null: track_workbench.cancel_interaction()

func _register_commands() -> void:
	commands.context_source = func(): return "roam" if store.document.get("free_roam", false) else "track"
	commands.blocked_source = _shortcuts_blocked
	commands.availability_source = func(_id: String):
		return store.EDIT_BUSY if store.editing_locked() else ""

	for entry in [["New", _new], ["Open", _choose.bind("open")], ["Restore package", _choose.bind("reopen_package")], ["Save", _save], ["Save As", _choose.bind("save")], ["Recover", _choose.bind("recover")], ["Import vector", _import_geojson], ["Export map", _export]]:
		commands.register("File", entry[0], entry[1], "Primary+S" if entry[0] == "Save" else "")
	commands.register("Edit", "Undo", _history.bind(false), "Primary+Z", {"enabled":func(): return not store.undo_stack.is_empty(), "reason":"No committed edit to undo."})
	commands.register("Edit", "Redo", _history.bind(true), "Primary+Shift+Z", {"keys":["Primary+Y"], "enabled":func(): return not store.redo_stack.is_empty(), "reason":"No edit to redo."})
	commands.register("Edit", "Duplicate", _duplicate_current, "Primary+D", {"enabled":_has_selection, "reason":"Select an object in the current mode first."})
	commands.register("Edit", "Delete", _delete_current, "Delete", {"keys":["Backspace"], "enabled":_can_delete, "reason":"Select an object in the current mode first."})
	commands.register("Edit", "Select all", func(): canvas.select_all(), "Primary+A", {"context":"roam"})
	commands.register("Edit", "Cancel interaction", _cancel_editing, "Escape", {"menu":false, "icon":"cancel"})
	commands.register("Edit", "Toggle snap", _toggle_snap, "S", {"icon":"snap"})
	commands.register("Edit", "Shortcuts", commands.open_settings, "", {"icon":"keyboard"})
	commands.register("View", "Commands…", commands.open, "Primary+P", {"id":"view.commands", "icon":"search"})
	commands.register("View", "Frame selection", _frame_current, "F", {"id":"view.frame", "icon":"frame", "description":"Frame the selected track piece, or fit the free roam map."})
	commands.register("View", "Frame selection in 3D", _frame_selection, "", {"context":"roam", "icon":"frame"})
	commands.register("View", "Tools / layers", func(): left_dock.visible = not left_dock.visible)
	commands.register("View", "Properties", func(): right_dock.visible = not right_dock.visible)
	commands.register("View", "Reset panels", _reset_panels)
	for mode in ["2d", "3d", "split"]:
		commands.register("View", mode.to_upper(), _set_view_mode.bind(mode), "", {"id":"view." + mode, "icon":mode})
	for tool in ["Select", "Road", "Surface area", "Water", "Island", "Building", "Cylinder wall", "Forest", "Orchard", "Terrain", "Place", "Repeat", "Entrance", "Exclusion"]:
		var shortcut: String = {"Select":"V", "Road":"R", "Building":"B", "Forest":"G", "Orchard":"O"}.get(tool, "")
		commands.register("Create", tool, _set_tool.bind(tool), shortcut, {"id":"tool." + tool.to_snake_case(), "context":"global" if tool == "Select" else "roam", "description":"Select in the active workspace: track pieces in 3D, or free roam objects on the plan." if tool == "Select" else _tool_help(tool), "menu":false})
	commands.register("Create", "Authoring settings…", func(): author_panel.open(), "", {"context":"roam"})
	commands.register("Create", "Seed Track", _open_track_generator, "", {"id":"create.seed_track", "icon":"generate"})
	commands.register("Validate", "Validate", _validate)
	commands.register("Validate", "3D Preview", _preview, "", {"context":"roam", "icon":"3d"})
	commands.register("Validate", "Test Drive", _test_drive)
	for slot in 9:
		commands.register("Favorites", "Favorite %d" % (slot + 1), commands.run_favorite.bind(slot), str(slot + 1), {"id":"favorite.%d" % (slot + 1), "menu":false})

func _popup_open(node: Node) -> bool:
	for child in node.get_children():
		if child is Window and child.visible: return true
		if _popup_open(child): return true
	return false

func _shortcuts_blocked() -> bool:
	var focus := get_viewport().gui_get_focus_owner()
	return store.editing_locked() or focus is LineEdit or focus is TextEdit or (DisplayServer.has_feature(DisplayServer.FEATURE_IME) and not DisplayServer.ime_get_text().is_empty()) or _popup_open(self)

func _watch_ui_node(node: Node) -> void:
	if is_ancestor_of(node): _decorate_ui_id.call_deferred(node.get_instance_id())

func _decorate_ui_id(id: int) -> void:
	var node := instance_from_id(id)
	if node is Node: _decorate_ui(node)

func _decorate_ui(node: Node) -> void:
	if not is_instance_valid(node) or node.is_queued_for_deletion(): return
	if node is Window:
		node.theme = theme
		if not node.visibility_changed.is_connected(_window_visibility_changed): node.visibility_changed.connect(_window_visibility_changed)
	if node is Button and not node is OptionButton and not node is MenuButton and not node is CheckBox and not node is CheckButton and not node is ColorPickerButton and not node.has_meta("action_label"):
		var owner_node := node.get_parent()
		var dialog_control := false
		while owner_node != null:
			if owner_node is AcceptDialog and (node == owner_node.get_ok_button() or (owner_node is ConfirmationDialog and node == owner_node.get_cancel_button()) or node == recovery_continue_button): dialog_control = true
			if owner_node is FileDialog: dialog_control = true
			owner_node = owner_node.get_parent()
		if not dialog_control and node.text != "": WORKBENCH_STYLE.decorate(node, node.text, node.tooltip_text)
	for child in node.get_children(): _decorate_ui(child)

func _window_visibility_changed() -> void:
	if _popup_open(self): _cancel_editing()

func _set_view_mode(mode: String) -> void:
	_cancel_editing()
	view_mode = mode if mode in ["2d", "3d", "split"] else "split"
	canvas.visible = view_mode != "3d"
	preview_dock.visible = view_mode != "2d"
	canvas.cancel_interaction()

func _reset_panels() -> void:
	left_dock.show()
	right_dock.show()
	outer_split.split_offset = 0
	center_split.split_offset = int(size.x * 0.35)
	right_dock.split_offset = 0
	workspace_views.split_offset = 0
	_set_view_mode("split")

func _restore_workbench() -> void:
	view_settings.load("user://workbench.cfg")
	_set_view_mode(str(view_settings.get_value("views", "mode", "split")))
	workspace_views.split_offset = int(view_settings.get_value("views", "split", 0))
	left_dock.visible = bool(view_settings.get_value("panels", "left_visible", true))
	right_dock.visible = bool(view_settings.get_value("panels", "right_visible", true))
	outer_split.split_offset = int(view_settings.get_value("panels", "left", 0))
	center_split.split_offset = int(view_settings.get_value("panels", "right", int(size.x * 0.35)))
	right_dock.split_offset = int(view_settings.get_value("panels", "vertical", 0))
	snap_toggle.button_pressed = bool(view_settings.get_value("snap", "enabled", true))
	snap_size.value = clampf(float(view_settings.get_value("snap", "metres", 1.0)), 0.01, 100.0)
	author_panel.visible = store.document.get("free_roam",false) and bool(view_settings.get_value("panels", "authoring_visible", true))
	if author_panel.visible and author_panel.tabs.get_tab_count() == 0: author_panel.open()
	canvas.layer_state = view_settings.get_value("layers", displayed_map_id, {}).duplicate(true)
	layers.refresh()
	if not store.document.get("free_roam",false):
		_set_view_mode("split")
		workspace_views.move_child(preview_dock,0)
		preview_dock.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		preview_dock.size_flags_stretch_ratio=3.0
		canvas.size_flags_stretch_ratio=1.0
		workspace_views.split_offset=300
		track_workbench.refresh()

func _save_workbench() -> void:
	if canvas == null or left_dock == null: return
	view_settings.load("user://workbench.cfg")
	view_settings.set_value("views", "mode", view_mode)
	view_settings.set_value("views", "split", workspace_views.split_offset)
	view_settings.set_value("panels", "left_visible", left_dock.visible)
	view_settings.set_value("panels", "right_visible", right_dock.visible)
	view_settings.set_value("panels", "left", outer_split.split_offset)
	view_settings.set_value("panels", "right", center_split.split_offset)
	view_settings.set_value("panels", "vertical", right_dock.split_offset)
	view_settings.set_value("panels", "authoring_visible", author_panel.visible)
	view_settings.set_value("snap", "enabled", canvas.snap_enabled)
	view_settings.set_value("snap", "metres", canvas.snap_cm / 100.0)
	if displayed_map_id != "": view_settings.set_value("layers", displayed_map_id, canvas.layer_state)
	var failure := view_settings.save("user://workbench.cfg")
	if failure != OK: _status(I18N.t("Workbench settings could not be saved: ") + error_string(failure))

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
	if operation == "export":
		if store.editing_locked(): _status(store.EDIT_BUSY); return
		_cancel_editing()
		var failure := store.start_file_operation("export", destination, {"full":full_generation.button_pressed, "regional_side_cells":int(regional_grouping.value) if destination.get_extension().to_lower() == "mkregions" else 0})
		if failure != "": _status(I18N.diagnostic(failure))
		return
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	if busy:
		_status(I18N.t("Another operation is running; cancel it or wait."))
		return
	_cancel_editing()
	if density_panel.task != null:
		density_panel.cancel()
		density_deferred_package = {"operation":operation,"destination":destination}
		busy = true
		return
	if operation == "export" and FileAccess.file_exists(destination):
		_operation_status(I18N.t("Export failed · E_EXPORT_EXISTS"), I18N.t("Choose a new package filename; existing files are preserved."))
		return
	package_work = PACKAGE_WORK.new()
	package_work.regional_side_cells = int(regional_grouping.value) if destination.get_extension().to_lower() == "mkregions" else 0
	package_operation = operation
	package_started_usec = Time.get_ticks_usec()
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
		_status(I18N.diagnostic(error_string(err)))

func _cancel_operation() -> void:
	if file_dialog_lock:
		dialog.hide()
		_release_file_dialog_lock()
		pending_document_action.clear()
		return
	if generation_lock:
		_cancel_track_generation()
		return
	if not store.file_request.is_empty():
		store.cancel_file_operation()
		_status(I18N.t("Stopping operation… Waiting for publication result."))
		return
	store.cancel_track_edit()
	if density_panel != null: density_panel.cancel()
	if not density_deferred_package.is_empty():
		density_deferred_package.clear()
		busy = false
	if import_job != null: import_job.cancel()
	native_request_identity = ""
	_discard_import()
	generation += 1
	preview_due = 0
	if package_work != null: package_work.cancel()
	_cancel_attachment()
	_status(I18N.t("Operation cancelled; previous preview and original files retained."))

func _cancel_attachment() -> void:
	if render_job.is_empty(): return
	RENDERER.cancel(render_job)
	render_job = {}
	if is_instance_valid(render_staged): render_staged.queue_free()
	render_staged = null
	render_data = {}
	busy = false

func _clear_preview_cache() -> void:
	if is_instance_valid(preview_world):
		var stage := preview_world.get_node_or_null("ToyTrackStage")
		if stage != null:
			preview_world.remove_child(stage)
			stage.queue_free()
	for entry: Dictionary in preview_cache.values():
		if is_instance_valid(entry.root): entry.root.queue_free()
	preview_cache.clear()
	framed_cell = Vector2i(-1, -1)

func _frame_selection() -> void:
	if property_records.is_empty():
		_status(I18N.t("Select an object in the map or tree before framing it."))
		return
	var points: Array[Vector2] = []
	var height := 0.0
	for entry in property_records:
		points.append_array(EDIT.points(entry.field, entry.record))
		if entry.field == "placements": height = float(entry.record.position[1])
		elif entry.field == "buildings": height = float(entry.record.base_cm)
	if points.is_empty(): return
	var bounds := Rect2(points[0], Vector2.ZERO)
	for point in points: bounds = bounds.expand(point)
	var center := bounds.get_center()
	var origin: Array = store.document.bounds.min
	var cell := Vector2i(floori((center.x - origin[0]) / store.document.cell_size_cm), floori((center.y - origin[1]) / store.document.cell_size_cm))
	preview_x.value = cell.x
	preview_y.value = cell.y
	framed_cell = cell
	preview_camera.frame(RENDERER.scene_position([center.x, height, center.y]), maxf(8, bounds.size.length() / 100.0))
	_set_view_mode("split" if view_mode == "2d" else view_mode)
	preview_enabled = true
	preview_due = Time.get_ticks_msec() + 150

func _show_cached(cell: Vector2i) -> void:
	if store.document.get("assembled_track") is Dictionary and not preview_world.has_node("ToyTrackStage"):
		var b: Dictionary = store.document.bounds
		preview_world.add_child(preload("res://addons/mapkit/godot/track_stage.gd").create(PackedInt64Array([b.min[0],b.min[1],b.max[0],b.max[1]]), store.document.assembled_track))
	cache_clock += 1
	preview_cache[cell].used = cache_clock
	for key: Vector2i in preview_cache: preview_cache[key].root.visible = key == cell
	var bounds: Dictionary = store.document.bounds
	var cell_size := float(store.document.cell_size_cm)
	var center := RENDERER.scene_position([bounds.min[0] + (cell.x + 0.5) * cell_size, 0, bounds.min[1] + (cell.y + 0.5) * cell_size])
	if framed_cell != cell:
		preview_camera.frame(center, Vector3(35, 55, 45).length() * cell_size / 51200.0)
		framed_cell = cell
	validation_label.text = I18N.t("Preview ready · cell %d / %d") % [cell.x, cell.y]
	_status(validation_label.text)

func _package_finished(result: Dictionary) -> void:
	var stale: bool = generation != worker_generation or package_work.stopped()
	package_work = null
	if stale:
		if result.ok and result.data.has("scratch"): PAYLOAD_FILES.remove_scratch(result.data.scratch)
		_status(I18N.t("Operation cancelled or document changed; prior preview and files retained."))
		return
	if not result.ok:
		_operation_status(I18N.t(package_operation.capitalize()) + I18N.t(" failed · Prior preview and original files retained"), I18N.result(result))
		return
	if package_operation != "preview":
		result.data.preview_delays = density_panel.measured_delays.duplicate(true)
		last_export_report = result.data
		if package_operation == "export":
			var failure := _publish_package(result.data.path, package_destination)
			PAYLOAD_FILES.remove_scratch(result.data.scratch)
			if failure != "":
				_operation_status(I18N.t("Export failed · Choose a new filename and retry"), I18N.diagnostic(failure))
				return
			last_export_report.path = package_destination
		_status(I18N.t("Exported validated package: ") + package_destination if package_operation == "export" else I18N.t("Validated immutable snapshot; capacity report ready."))
		validation_label.text = I18N.t("Validated · %d bytes · base goal %s") % [result.data.package_bytes, "met" if result.data.base_target_met else "exceeded"]
		export_report.show_report(result.data)
		return
	if result.data.get("reused", false):
		preview_stats.reused += 1
		_show_cached(package_cell)
		return
	preview_stats.generated += 1
	render_data = result.data
	render_data.gimmicks = JSON.parse_string(result.data.chunk.gimmicks_json) if result.data.chunk.has("gimmicks_json") else result.data.chunk.get("gimmicks",[])
	render_data.gimmick_index = 0
	render_batch_estimate = 1000
	render_staged = Node3D.new()
	render_staged.visible = false
	preview_world.add_child(render_staged)
	render_job = RENDERER.begin(result.data.chunk, render_staged, Callable(), 0, preview_resources)
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
		if done and render_job.error.is_empty() and render_data.gimmick_index < render_data.gimmicks.size():
			var definition: Dictionary = render_data.gimmicks[render_data.gimmick_index]
			var visual := GIMMICK_GEOMETRY.visual(definition)
			visual.transform = GIMMICK_GEOMETRY.pose(definition,0)
			visual.set_meta("gimmick_id",definition.id)
			render_staged.add_child(visual)
			render_data.gimmick_index += 1
			done = false
		var batch_usec := Time.get_ticks_usec() - batch
		render_batch_estimate = maxi(render_batch_estimate, batch_usec)
		preview_stats.max_batch_usec = maxi(preview_stats.max_batch_usec, batch_usec)
		if done:
			if not render_job.error.is_empty():
				var failure := store.reason({"ok": false, "error": render_job.error})
				_cancel_attachment()
				_status(I18N.diagnostic(failure))
				return
			# Publish once; keep the old root visible throughout candidate attachment.
			if preview_cache.has(package_cell): preview_cache[package_cell].root.queue_free()
			preview_cache[package_cell] = {"root": render_staged, "signature": render_data.signature, "charge": render_data.charge, "used": cache_clock + 1}
			density_panel.record_preview(package_cell,render_data.signature,(Time.get_ticks_usec()-package_started_usec)/1000000.0)
			RENDERER.dispose(render_job)
			preview_resources.trim()
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
		_status(I18N.t("Another operation is running; wait for cancellation to finish."))
		return
	_discard_import()
	if not IMPORT_LAYER._text(license_name):
		_status(I18N.t("A source license is required."))
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
	var input_format: String = ["geojson", "pbf", "osm", "overture", "overture-transportation", "overture-land-cover"][import_source_format.selected]
	osm_import_revision = osm_panel.revision
	vertical_import_revision = vertical_panel.revision
	if input_format in ["osm", "pbf"]:
		var vertical: Dictionary = vertical_panel.capture()
		if vertical.has("error"):
			_status(I18N.t("E_IMPORT: ") + I18N.diagnostic(vertical.error))
			return
		import_coordinates_request.vertical = vertical
		var supplement: Dictionary = vertical_panel.capture_supplement()
		if supplement.has("error"):
			_status(I18N.t("E_IMPORT: ") + I18N.diagnostic(supplement.error))
			return
		import_coordinates_request.merge(supplement)
	if osm_panel.streaming.button_pressed:
		if input_format != "pbf" or osm_panel.error() != "":
			_status(I18N.t("PBF streaming requires PBF input and an enabled valid crop area."))
			return
		import_coordinates_request.osm_stream = true
	if input_format in ["osm", "pbf"] and osm_panel.enabled.button_pressed:
		if osm_panel.error() != "":
			_status(I18N.diagnostic(osm_panel.error()))
			return
		import_coordinates_request.osm_bbox = osm_panel.bbox()
	import_coordinates_request.adapter = "overture-land-cover-v1" if input_format == "overture-land-cover" else "overture-transportation-v1" if input_format == "overture-transportation" else "overture-buildings-v1" if input_format == "overture" else ("geojson-v1" if input_format == "geojson" else "osm-extract-v1")
	if input_format != "geojson": license_name = IMPORT_LAYER.OVERTURE_LAND_COVER_LICENSE if input_format == "overture-land-cover" else IMPORT_LAYER.OVERTURE_TRANSPORTATION_LICENSE if input_format == "overture-transportation" else IMPORT_LAYER.OVERTURE_LICENSE if input_format == "overture" else IMPORT_LAYER.OSM_LICENSE
	var failure := job.start(source, license_name, accuracy, import_python.text.strip_edges(), import_identity, import_coordinates_request, input_format, "")
	if failure != "":
		_operation_status(I18N.t("Import failed · Use Retry import to adjust settings"), I18N.t("E_IMPORT: ") + I18N.diagnostic(failure))
		return
	import_job = job
	import_selection_signature = _import_selection_signature()
	worker_generation = generation
	busy = true
	import_progress.value = 0
	import_progress.visible = true
	_status(I18N.t("Starting import · %d source bytes · %ds deadline. Cancel stops the child; Retry last source starts a new layer.") % [job.progress.total, job.timeout_seconds])

func _start_worker(operation: String, source: String, destination: String) -> void:
	if operation == "import":
		_start_import(source, destination)
		return
	if busy:
		_status(I18N.t("Another operation is running."))
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
		_status(I18N.diagnostic(error_string(err)))
	else: _status(I18N.t("Preparing test drive…"))

func _terrain_selection() -> String:
	return JSON.stringify([canvas.interaction_revision, canvas.authoring_revision, canvas.tool, canvas.author.options, canvas.layer_state]).sha256_text()

func _start_terrain(request: Dictionary) -> void:
	if busy:
		_status(I18N.t("Finish the running operation before painting terrain."))
		return
	if not canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true):
		_status(I18N.t("Show and unlock terrain before painting."))
		return
	var job := TERRAIN_NATIVE_JOB.new()
	job.editor_generation = generation
	var failure := job.start_terrain(store, request, _terrain_selection(), Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "":
		_status(I18N.diagnostic(failure))
		return
	import_job = job
	worker_generation = generation
	busy = true
	import_progress.visible = true
	_status(I18N.t("Preparing terrain stroke · 120s deadline · Cancel preserves the map."))

func _finish_terrain(job: RefCounted, result: Dictionary) -> void:
	if job.editor_generation != generation or not job.matches(store, _terrain_selection()):
		_status(I18N.t("Terrain stroke cancelled or stale; nothing was changed."))
		return
	if not result.get("ok", false) or not result.get("data", {}).get("ok", false):
		_status(I18N.result(result.get("data", result)))
		return
	var failure: String = job.commit(store)
	_status(I18N.diagnostic(failure) if failure != "" else I18N.t("Terrain stroke applied. Undo: ") + commands.shortcut_text("edit.undo"))

func _process(_delta: float) -> void:
	if generation_lock and not track_job.busy():
		generation_lock = false
		store.set_external_lock(busy)
	store.poll_track_edit()
	store.poll_file_operation()
	store.poll_autosave()
	_sync_operation_ui()
	if track_workbench != null and track_workbench.placement.tool != "" and _popup_open(self): _cancel_editing()
	if not density_deferred_package.is_empty() and density_panel.task == null:
		var pending := density_deferred_package
		density_deferred_package = {}
		busy = false
		_start_package(pending.operation,pending.destination)
	cancel_button.disabled = not busy and pending_import == null and not store.track_edit_busy and store.file_request.is_empty()
	cancel_button.tooltip_text = I18N.t("Cancel the running operation; keep prior preview and original files.") if busy or store.track_edit_busy else I18N.t("No running operation.")
	retry_import_button.visible = last_import_source != "" and not busy and pending_import == null
	if import_job != null:
		if import_job is TERRAIN_NATIVE_JOB:
			if generation != worker_generation or not import_job.matches(store, _terrain_selection()): import_job.cancel()
		elif import_job is ASSET_NATIVE_JOB:
			if generation != worker_generation or import_job.document_epoch != store.command_epoch or import_job.selection_signature != author_panel.asset_selection(): import_job.cancel()
			author_panel.asset_progress(import_job.progress)
		elif import_job is HEIGHTMAP_NATIVE_JOB:
			if generation != worker_generation or import_job.document_epoch != store.command_epoch or import_job.selection_signature != author_panel.heightmap_selection(): import_job.cancel()
			author_panel.heightmap_progress(import_job.progress)
		elif import_job is DEM_NATIVE_JOB:
			if generation != worker_generation or import_job.document_epoch != store.command_epoch or import_job.selection_signature != dem_panel.native_selection(): import_job.cancel()
		elif import_job is IMPORT_NATIVE_JOB and (generation != worker_generation or import_job.document_epoch != store.command_epoch or import_job.selection_signature != _import_selection_signature()): import_job.cancel()
		import_job.poll()
		var progress: Dictionary = import_job.progress
		if not progress.is_empty():
			import_progress.value = 100.0 * float(progress.completed) / maxf(1.0, float(progress.total))
			validation_label.text = "%s %s · %d / %d %s" % [I18N.t("Terrain") if import_job is TERRAIN_NATIVE_JOB else I18N.t("DEM") if dem_mode.begins_with("dem") else I18N.t("Import"), I18N.builtin(progress.stage), progress.completed, progress.total, I18N.builtin(progress.unit)]
		if import_job.done:
			var completed: RefCounted = import_job
			var result: Dictionary = import_job.result
			import_job = null
			busy = false
			import_progress.visible = false
			if completed is TERRAIN_NATIVE_JOB: _finish_terrain(completed, result)
			elif completed is ASSET_NATIVE_JOB: author_panel.finish_asset(completed, result)
			elif completed is HEIGHTMAP_NATIVE_JOB: author_panel.finish_heightmap(completed, result)
			elif completed is DEM_NATIVE_JOB: dem_panel.finish_native(completed, result)
			elif completed is IMPORT_NATIVE_JOB: _finish_native_import(completed, result)
			elif dem_mode != "": _finish_dem(result)
			else: _finish_import(result)
		return
	if not render_job.is_empty():
		_advance_attachment()
		return
	if not busy:
		if preview_due > 0 and Time.get_ticks_msec() >= preview_due: _preview()
		return
	if worker.is_alive():
		if package_work != null: validation_label.text = I18N.display(package_work.status())
		return
	var output: Dictionary = worker.wait_to_finish()
	busy = false
	var result: Dictionary = output.result
	if output.operation == "reopen_package":
		var stale: bool = generation != worker_generation or package_work.stopped()
		package_work = null
		if not result.ok: _status(I18N.result(result))
		elif stale: _status(I18N.t("Reopen cancelled; restored project retained at ") + str(result.data.path))
		else: _request_document_action("open", result.data.path)
		return
	if output.operation == "package":
		_package_finished(result)
		return
	if not result.ok:
		if output.operation == "test_drive":
			last_drive_result = result
		_status(I18N.result(result))
		return
	if output.operation == "test_drive":
		if generation != worker_generation:
			last_drive_result = TEST_DRIVE.error("E_DOCUMENT_CHANGED", "Document changed during packaging; snapshot retained. Start test drive again.")
			_status(I18N.result(last_drive_result))
			return
		last_drive_result = test_drive_launcher.launch(drive_request.client, result.data.path, drive_request.x_cm, drive_request.y_cm, drive_request.surface)
		_status(I18N.t("Client launched (PID %d). Close Client to end the test. Snapshot: %s") % [last_drive_result.data.pid, result.data.path] if last_drive_result.ok else I18N.result(last_drive_result))
		return
func _finish_import(result: Dictionary) -> void:
	if import_selection_signature != _import_selection_signature():
		_status(I18N.t("Import selection changed; retry. Original source retained."))
		return
	if vertical_import_revision != vertical_panel.revision:
		_status(I18N.t("Height reference changed during import; retry. Original source retained."))
		return
	if osm_import_revision != osm_panel.revision:
		_status(I18N.t("OSM crop selection changed during import; retry. Original source retained."))
		return
	if not result.ok:
		_operation_status(I18N.t("Import stopped · Use Retry import to review settings"), I18N.result(result))
		return
	if generation != worker_generation:
		_status(I18N.t("Document changed during import; retry to add the new layer."))
		return
	var layer := IMPORT_LAYER.new()
	var failure := layer.load_value(result.data, import_identity, import_coordinates_request)
	if failure != "":
		_status(I18N.t("E_IMPORT: ") + I18N.diagnostic(failure))
		return
	_start_native_import(layer, false)

func _import_controls_changed() -> void:
	import_controls_revision += 1
	if import_job != null: import_job.cancel()
	_discard_import()

func _import_selection_signature() -> String:
	return JSON.stringify([import_controls_revision, import_source_format.selected, import_coordinate_mode.selected,
		import_origin_lon.value, import_origin_lat.value, import_origin_x.value, import_origin_y.value,
		osm_panel.revision, vertical_panel.revision, import_coordinates_request, import_identity, last_import_source])

func _start_native_import(layer: RefCounted, adopting: bool) -> void:
	if busy:
		_status(I18N.t("Another operation is running; wait for it to finish."))
		return
	var job := IMPORT_NATIVE_JOB.new()
	job.editor_generation = generation
	var failure := job.start_validation(store, layer, adopting, _import_selection_signature(), last_import_source, Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "":
		_operation_status(I18N.t("Native import validation stopped · Retry import"), I18N.t("E_IMPORT_NATIVE: ") + I18N.diagnostic(failure))
		return
	import_job = job
	native_request_identity = job.identity
	worker_generation = generation
	busy = true
	import_progress.visible = true
	import_progress.value = 0
	_status(I18N.t("Checking %s before %s · 120s deadline · Cancel retains the current map.") % [I18N.t("structural surfaces") if layer.has_structures() else I18N.t("import candidate"), "adoption" if adopting else "review"])

func _finish_native_import(job: RefCounted, result: Dictionary) -> void:
	if native_request_identity != job.identity or generation != job.editor_generation or not job.done or not job.exited or not job.matches(store, _import_selection_signature()):
		_status(I18N.t("E_IMPORT_STALE: Document or import selection changed; import again."))
		return
	native_request_identity = ""
	if not result.get("ok", false):
		_operation_status(I18N.t("Native import validation stopped · Retry import"), I18N.result(result))
		return
	var checked: Variant = result.get("data")
	if checked is not Dictionary or checked.get("request") != job.identity or checked.get("ok") is not bool:
		_status(I18N.t("E_IMPORT_NATIVE: Invalid validation result; import again."))
		return
	if not checked.ok:
		if checked.get("error") is not Dictionary or checked.error.get("code") != "E_IMPORT_NATIVE" or checked.error.get("message") is not String:
			_status(I18N.t("E_IMPORT_NATIVE: Invalid validation failure; import again."))
			return
		_operation_status(I18N.t("Native import validation rejected · Prior map retained"), I18N.result(checked))
		return
	if not IMPORT_LAYER._hex(checked.get("payloads"), 64):
		_status(I18N.t("E_IMPORT_NATIVE: Missing validation snapshot identity."))
		return
	if job.adopting:
		# The owned child prepared the canonical document and exact Undo command.
		# Commit once against its unchanged document/history epoch.
		var failure: String = job.commit(store)
		_status(I18N.diagnostic(failure) if failure != "" else I18N.t("Imported new layer. Undo removes only this adoption."))
	else:
		job.layer.native_payload_digest = checked.payloads
		_review_import(job.layer)

func _review_import(layer: RefCounted) -> void:
	import_details.clear()
	pending_import = layer
	import_review_generation = generation
	import_review_controls = _review_controls()
	validation_label.text = I18N.t("Import ready for review · document unchanged until Adopt")
	import_summary.text = layer.summary()
	import_review.popup_centered(Vector2i(760, 460))
	_status(I18N.t("Import prepared. Review and adopt the new layer, or discard it."))
	return

func _import_review_current() -> bool:
	# Detail-page guards compare only bounded UI identities. The full immutable
	# request signature remains checked on entry and again by adoption/native work.
	return pending_import != null and generation == import_review_generation and import_review_controls == _review_controls()

func _review_controls() -> Array:
	return [import_controls_revision, import_source_format.selected, import_coordinate_mode.selected,
		import_origin_lon.value, import_origin_lat.value, import_origin_x.value, import_origin_y.value,
		osm_panel.revision, vertical_panel.revision, import_identity, last_import_source]

func _open_import_details() -> void:
	if not _import_review_current() or import_selection_signature != _import_selection_signature():
		_discard_import()
		_status(I18N.t("E_IMPORT_STALE: Document or import selection changed; import again."))
		return
	import_details.open(pending_import.value, _import_review_current)

func _discard_import() -> void:
	if import_details != null: import_details.clear()
	if import_summary != null: import_summary.text = ""
	import_review_controls.clear()
	pending_import = null
	if import_review != null: import_review.hide()

func _adopt_import() -> void:
	if pending_import == null or generation != import_review_generation or import_selection_signature != _import_selection_signature():
		_discard_import()
		_status(I18N.t("E_IMPORT_STALE: Document changed; import again."))
		return
	var candidate: RefCounted = pending_import
	_discard_import()
	_start_native_import(candidate, true)

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and commands.handle_key(event): get_viewport().set_input_as_handled()

func _history(forward: bool) -> void:
	_cancel_editing()
	var failure := store.start_track_history(forward) if store.document.has("assembled_track") else store.redo() if forward else store.undo()
	if failure != "":
		_status(I18N.diagnostic(failure))

func _operation_status(summary: String, details: String) -> void:
	_status(details)
	validation_label.text = summary

func _status(text: String) -> void:
	if busy and text.begins_with("x "): return
	if validation_label != null and text.contains("E_"):
		validation_label.text = I18N.t("Edit/operation rejected · ") + text
	status_label.text = I18N.display(text)

func _exit_tree() -> void:
	store.shutdown_track_edit()
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
	drive_dialog.title = I18N.t("Test Drive")
	drive_dialog.ok_button_text = I18N.t("Save, Package and Launch")
	drive_dialog.theme = theme
	var layout := VBoxContainer.new()
	layout.custom_minimum_size = Vector2(650, 270)
	drive_dialog.add_child(layout)
	_label(layout, "Saves the current project and opens a separate snapshot in installed Client.")
	var path_row := HBoxContainer.new()
	layout.add_child(path_row)
	client_path = LineEdit.new()
	client_path.placeholder_text = I18N.t("Installed MiniEarthure Client executable")
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
		client_dialog.filters = I18N.filters(["*.exe ; MiniEarthure Client"])
	client_dialog.file_selected.connect(func(path: String): client_path.text = path)
	add_child(client_dialog)
	var settings := ConfigFile.new()
	if settings.load("user://editor_tools.cfg") == OK:
		client_path.text = str(settings.get_value("test_drive", "client_executable", ""))


func _test_drive() -> void:
	_cancel_editing()
	if busy:
		_status(I18N.t("Wait for the current operation before starting test drive."))
		return
	if store.project_path == "":
		_status(I18N.t("Choose a project directory before test drive."))
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
	drive_surface.add_item(I18N.t("Terrain"))
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
	if store.editing_locked():
		_status(I18N.t("Another operation is running."))
		return
	var checked := TEST_DRIVE.check_client(client_path.text)
	if not checked.ok:
		last_drive_result = checked
		_status(I18N.result(checked))
		return
	_start_save(store.project_path, "launch_drive")

func _prepare_test_drive() -> void:
	var directory := ProjectSettings.globalize_path("user://test-drives")
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK:
		_status(I18N.diagnostic(error_string(error)))
		return
	var snapshot := directory.path_join(Crypto.new().generate_random_bytes(16).hex_encode() + ".memap")
	drive_request = {"client": client_path.text, "x_cm": roundi(drive_x.value * 100),
		"y_cm": roundi(drive_y.value * 100), "surface": drive_surface.get_selected_metadata(),
		"document": store._saved_canonical}
	var settings := ConfigFile.new()
	settings.load("user://editor_tools.cfg")
	settings.set_value("test_drive", "client_executable", client_path.text)
	error = settings.save("user://editor_tools.cfg")
	if error != OK:
		_status(I18N.t("Cannot save Client tool setting: ") + error_string(error))
		return
	_start_worker("test_drive", store.project_path, snapshot)
	_status(I18N.t("Validating and packaging test-drive snapshot…"))

func _begin_dem(request: Dictionary) -> void:
	if busy: return
	_discard_import()
	var job := DEM_JOB.new()
	var failure: String = job.start_local(request, import_python.text.strip_edges(), Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "":
		_status(I18N.t("E_DEM: ") + I18N.diagnostic(failure))
		return
	dem_mode = request.mode
	import_job = job
	worker_generation = generation
	busy = true
	import_progress.visible = true

func _finish_dem(result: Dictionary) -> void:
	var mode := dem_mode
	dem_mode = ""
	dem_panel.finish(mode, result)

func _physics_process(delta: float) -> void:
	if not is_instance_valid(environment_renderer): return
	environment_preview.elapsed += delta
	environment_preview.profile = store.document.get("environment",{})
	for key in ["sunrise_minutes","sunset_minutes","latitude_mdeg","longitude_mdeg","utc_offset_minutes"]:
		if environment_preview.profile.has(key): environment_preview.config[key] = environment_preview.profile[key]
	environment_renderer.update_environment(environment_preview,preview_world.get_node("PreviewCamera").global_position,[],preview_resources)
	environment_renderer.update_dynamic_lights(preview_world.get_node("PreviewCamera").global_position,[])

func _open_track_generator() -> void:
	_cancel_editing()
	if not is_instance_valid(track_job):
		track_job = preload("res://addons/mapkit/godot/track_job.gd").new()
		add_child(track_job)
		track_job.progressed.connect(func(request:int,value:Dictionary):
			if request==track_request and track_epoch==store.command_epoch: track_panel.update_progress(value))
		track_job.completed.connect(func(request: int, result: Dictionary):
			if request!=track_request: return
			track_request=-1
			generation_lock = false
			store.set_external_lock(busy)
			track_panel.set_busy(false)
			if track_epoch != store.command_epoch: return
			if not result.ok: _status(I18N.error(result.error)); track_panel.note.text=I18N.error(result.error); return
			var failure: String = store.open_generated(result.data.document,result.data.get("preview",{}))
			if failure != "": _status(I18N.diagnostic(failure)); return
			_clear_preview_cache()
			track_panel.show_result(result.data.document.assembled_track)
			_status(track_panel.note.text)
			track_dialog.hide()
			track_workbench.refresh())
	if not is_instance_valid(track_dialog):
		track_dialog = AcceptDialog.new()
		track_dialog.title = I18N.t("Seed Track")
		add_child(track_dialog)
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size = Vector2(460,520)
		track_dialog.add_child(scroll)
		var panel := preload("./track_settings_panel.gd").new()
		track_panel = panel
		panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		scroll.add_child(panel)
		panel.requested.connect(func(settings: Dictionary):
			if store.editing_locked() or track_request>=0: _status(I18N.t("Finish or cancel the current operation first.")); return
			track_panel.set_busy(true)
			track_panel.progress.reduce_motion=bool(view_settings.get_value("accessibility","reduce_ui_motion",false))
			track_panel.update_progress({"stage":"preparing"})
			track_epoch = store.command_epoch
			generation_lock = true
			store.set_external_lock(true)
			var directory := ProjectSettings.globalize_path("user://generated-tracks")
			DirAccess.make_dir_recursive_absolute(directory)
			track_request=track_job.begin(settings,directory.path_join(Crypto.new().generate_random_bytes(12).hex_encode()+".memap"),true)
			_status(I18N.t("Assembling track…")))
		panel.cancelled.connect(func(): _cancel_track_generation(); _status(I18N.t("Generation cancelled. Current document retained.")))
		track_dialog.canceled.connect(_cancel_track_generation)
		track_dialog.confirmed.connect(_cancel_track_generation)
		if store.document.get("assembled_track") is Dictionary:
			track_panel.restore(store.document.assembled_track.settings)
	track_dialog.popup_centered(Vector2i(500,600))

func _cancel_track_generation() -> void:
	track_request=-1
	track_job.cancel()
	track_panel.set_busy(false)

func _build_operation_ui() -> void:
	applying_row = HBoxContainer.new()
	status_label.get_parent().add_child(applying_row)
	applying_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	applying_spinner = preload("res://addons/mapkit/godot/work_progress.gd").new()
	applying_spinner.diameter = 28
	applying_spinner.show_text = false
	applying_row.add_child(applying_spinner)
	_label(applying_row, "Applying changes")
	operation_dim = ColorRect.new()
	operation_dim.color = Color(0, 0, 0, 0.55)
	operation_dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	operation_dim.mouse_filter = Control.MOUSE_FILTER_STOP
	operation_dim.z_index = 100
	add_child(operation_dim)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	operation_dim.add_child(center)
	var box := VBoxContainer.new()
	center.add_child(box)
	operation_spinner = preload("res://addons/mapkit/godot/work_progress.gd").new()
	box.add_child(operation_spinner)
	operation_label = _label(box, "Working…")
	var stop := Button.new()
	stop.text = I18N.t("Cancel")
	stop.pressed.connect(_cancel_operation)
	box.add_child(stop)
	_sync_operation_ui()

func _sync_operation_ui() -> void:
	if not is_instance_valid(operation_dim): return
	var locked := store.editing_locked()
	if locked and not operation_dim.visible:
		var focus := get_viewport().gui_get_focus_owner()
		if focus != null: focus.release_focus()
	if operation_dim.visible != locked: commands.refresh_buttons()
	operation_dim.visible = locked
	applying_row.visible = store.applying_visible() and not locked
	var reduced := bool(view_settings.get_value("accessibility", "reduce_ui_motion", false))
	applying_spinner.reduce_motion = reduced
	operation_spinner.reduce_motion = reduced
	operation_label.text = I18N.t("Saving map" if store.file_request.get("operation", "") == "save" else "Working…")

func _draft_status_changed() -> void:
	canvas.queue_redraw()
	project_label.text = (store.project_path if store.project_path != "" else I18N.t("Unsaved project")) + (I18N.t("  • modified") if store.dirty else "")
	commands.refresh_buttons()

func _start_save(path: String, continuation := "save") -> void:
	if store.editing_locked(): _status(store.EDIT_BUSY); return
	_cancel_editing()
	file_continuation = continuation
	var failure := store.start_file_operation("save", path)
	if failure != "":
		file_continuation = ""
		_status(I18N.diagnostic(failure))

func _file_finished(result: Dictionary) -> void:
	_draft_status_changed()
	var continuation := file_continuation
	file_continuation = ""
	if not result.ok:
		pending_document_action.clear()
		_status(I18N.diagnostic(str(result.error)))
		return
	if result.request.operation == "export":
		last_export_report = result.data
		_status(I18N.t("Exported validated package: ") + str(result.data.path))
		export_report.show_report(result.data)
		return
	_status(I18N.t("Project saved."))
	match continuation:
		"save_transition": _continue_document_action()
		"save_for_export": _choose.call_deferred("export")
		"save_for_drive": _test_drive()
		"launch_drive": _prepare_test_drive()
