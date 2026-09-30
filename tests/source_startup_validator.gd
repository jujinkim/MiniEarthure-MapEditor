extends SceneTree
## Exercise the real entry scene with no import scan or extension-list cache.
var checks := 0

func _initialize() -> void: run.call_deferred()

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)

func run() -> void:
	check(OS.get_user_data_dir().replace("\\", "/") == OS.get_environment("MAPEDITOR_STARTUP_USER"), "isolated user data")
	var mode := OS.get_environment("MAPEDITOR_STARTUP_MODE")
	check(ClassDB.class_exists(&"MapKitBridge") == (mode == "registered"), "fixture starts with the expected native registration")
	var entry: Node = load("res://scripts/editor_entry.tscn").instantiate()
	root.add_child(entry)
	for _i in 4: await process_frame
	if mode == "missing":
		check(entry.get_child_count() == 1 and entry.has_node("StartupError"), "native failure shows only the startup error")
		var details: TextEdit = entry.find_child("Diagnostics", true, false)
		check(details != null and details.text.contains("Cannot load") and details.text.contains(ProjectSettings.globalize_path("res://")), "copyable diagnostics identify the error and actual project")
		check(not DirAccess.dir_exists_absolute("user://recovery") and not FileAccess.file_exists("user://workbench.cfg"), "failed startup does not create a document or change preferences")
	else:
		var editor: Node = entry.get_child(0)
		check(editor.name == "MapEditor" and editor.track_workbench.active, "entry starts the track workspace")
		check(editor.track_workbench.palette.is_visible_in_tree() and not editor.roam_palette.is_visible_in_tree(), "track palette replaces Drawing tools")
		check(editor.selection_label.text.begins_with("TRACK WORKSPACE"), "track heading is visible")
		var startup := load("res://scripts/mapkit_startup.gd")
		var extensions := GDExtensionManager.get_loaded_extensions()
		check(startup.ensure_loaded() == "" and GDExtensionManager.get_loaded_extensions() == extensions, "already loaded native module is reused")
		# Use the actual asynchronous command and its adoption callback, with a
		# synthetic seed and generated package confined to this run's user data.
		if mode == "cold":
			editor._open_track_generator()
			check(editor.track_panel.catalogue_ready and not editor.track_panel.generate.disabled, "Seed Track controls initialize")
			var settings: Dictionary = editor.track_panel.settings()
			settings.seed = 42
			editor.track_panel.requested.emit(settings)
			var deadline := Time.get_ticks_msec() + 30000
			while editor.track_job.busy() and Time.get_ticks_msec() < deadline:
				await process_frame
			check(not editor.track_job.busy(), "bounded seed generation completes")
			check(not editor.track_workbench.source.get("instances", []).is_empty() and not editor.track_dialog.visible, "generated track is adopted and dialog closes")
			check(editor.store.document.assembled_track.settings.seed == 42, "generated document retains requested seed")
	entry.queue_free()
	for _i in 3: await process_frame
	print("source_startup_validator: PASS (%s, %d checks)" % [mode, checks])
	quit()
