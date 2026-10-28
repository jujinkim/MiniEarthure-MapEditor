extends Node
const I18N := preload("./locale_text.gd")
## Route the private worker before constructing any Editor UI or user session.
const STARTUP := preload("./mapkit_startup.gd")

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var worker := not args.is_empty() and args[0] == "--native-import-validation"
	var failure := STARTUP.ensure_loaded()
	if not failure.is_empty():
		printerr("MapEditor startup: " + failure)
		if worker: get_tree().quit(1)
		else: _show_startup_error(failure)
		return
	# Keep this dynamic: loading editor_main first constructs a document store
	# before the native class is registered in a source checkout without imports.
	var scene := "res://scripts/import_native_worker.tscn" if worker else "res://main.tscn"
	var editor: Node = load(scene).instantiate()
	add_child(editor)
	var recipe := args.find("--real-city-recipe")
	if not worker and recipe >= 0: _run_recipe.call_deferred(editor, args, recipe)

## Headless real-city build: `-- --real-city-recipe recipe.json [--report out.json]`
## runs the same steps as File → New real-city map, prints the report and quits
## with 0 on success.
func _run_recipe(editor: Control, args: PackedStringArray, at: int) -> void:
	var RECIPE := preload("./real_city_recipe.gd")
	var path := args[at + 1] if at + 1 < args.size() else ""
	var report_at := args.find("--report")
	var report_path := args[report_at + 1] if report_at >= 0 and report_at + 1 < args.size() else ""
	var parsed: Dictionary = RECIPE.parse(FileAccess.get_file_as_string(path), path.get_base_dir()) if FileAccess.file_exists(path) else {"ok":false, "error":"Recipe file not found: " + path}
	var report: Dictionary = parsed
	if parsed.ok:
		for i in 2: await get_tree().process_frame
		if is_instance_valid(editor.start_panel): editor.start_panel.hide()
		var runner: RefCounted = RECIPE.new(editor, func(text: String): print("REAL_CITY ", text))
		report = await runner.run(parsed.recipe)
		editor.store.dirty = false
	var text := JSON.stringify(report, "  ")
	print("REAL_CITY_REPORT ", text)
	if report_path != "":
		var file := FileAccess.open(report_path, FileAccess.WRITE)
		if file != null: file.store_string(text)
	get_tree().quit(0 if report.get("ok", false) else 1)

func _show_startup_error(failure: String) -> void:
	var panel := PanelContainer.new()
	panel.name = "StartupError"
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.theme = preload("./workbench_style.gd").create_theme()
	add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 20)
	panel.add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	var title := Label.new()
	title.text = I18N.t("MapEditor could not start")
	title.add_theme_font_size_override("font_size", 22)
	column.add_child(title)
	var explanation := Label.new()
	explanation.text = I18N.t("MapKit is unavailable or does not match this editor. Close Godot and rebuild MapKit for this project, then restart.")
	explanation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(explanation)
	var details := TextEdit.new()
	details.name = "Diagnostics"
	details.editable = false
	details.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	details.size_flags_vertical = Control.SIZE_EXPAND_FILL
	details.text = I18N.t("%s\n\nProject: %s\nEngine: %s\nGodot: %s\nExtension: %s") % [I18N.diagnostic(failure), ProjectSettings.globalize_path("res://"), OS.get_executable_path(), Engine.get_version_info().string, STARTUP.EXTENSION]
	column.add_child(details)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	var copy := Button.new()
	copy.text = I18N.t("Copy diagnostics")
	copy.pressed.connect(func(): DisplayServer.clipboard_set(details.text))
	actions.add_child(copy)
	var close := Button.new()
	close.text = I18N.t("Close")
	close.pressed.connect(func(): get_tree().quit(1))
	actions.add_child(close)
