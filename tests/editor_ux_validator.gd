extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
var ui: Control
var checks := 0
var failures: Array[String] = []

func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message + " | " + ui.status_label.text)
func state() -> String:
	return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.dirty, ui.store.project_path])
func button(node: Node, title: String) -> Button:
	if node is Button and node.text == title: return node
	for child in node.get_children():
		var found := button(child, title)
		if found != null: return found
	return null
func click(target: Button) -> void:
	check(target != null and target.is_visible_in_tree() and not target.disabled, "button is available")
	if target == null: return
	await process_frame
	var point := target.get_global_rect().get_center()
	if target.get_window() != root: point += Vector2(target.get_window().position)
	for down in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.button_index = MOUSE_BUTTON_LEFT
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
		event.pressed = down
		root.push_input(event)
		await process_frame
func write(path: String, value: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
	file.close()
func finish() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "operation finishes within bounded wait")
	await process_frame
func capture(name: String) -> void:
	var directory := OS.get_environment("MAPEDITOR_UX_CAPTURE_DIR")
	if directory == "" or DisplayServer.get_name() == "headless": return
	DirAccess.make_dir_recursive_absolute(directory)
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(directory.path_join(name + ".png")) == OK, "capture " + name)
func run() -> void:
	root.size = Vector2i(1024, 720)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	ui.dialog.use_native_dialog = false
	await process_frame
	await process_frame
	if ui.cancel_button == null:
		quit(1)
		return
	check(ui.cancel_button.disabled, "idle cancellation disabled")
	await click(button(ui, "Road"))
	check(ui.tool_hint.text.contains("right-click") and ui.tool_hint.text.contains("Authoring settings"), "persistent tool discovery")
	await capture("workbench")
	var before := state()
	await click(button(ui, "New"))
	check(ui.unsaved_dialog.visible and state() == before, "New asks before replacing dirty document")
	await capture("unsaved")
	await click(ui.unsaved_dialog.get_cancel_button())
	check(not ui.unsaved_dialog.visible and ui.pending_document_action.is_empty() and state() == before, "Keep editing preserves document/history")
	ui._notification(Node.NOTIFICATION_WM_CLOSE_REQUEST)
	check(ui.unsaved_dialog.visible and ui.pending_document_action.action == "close", "Close uses same unsaved guard")
	await click(ui.unsaved_dialog.get_cancel_button())
	check(state() == before, "cancel Close preserves document")
	var original_id: String = ui.store.document.map_id
	var retained_path: String = ui.store.recovery_path()
	await click(button(ui, "New"))
	await click(ui.recovery_continue_button)
	check(ui.store.document.map_id != original_id and ui.store.undo_stack.is_empty(), "explicit recovery continuation creates new document")
	check(FileAccess.file_exists(retained_path), "explicit continuation retains recovery snapshot")
	# Save picker cancellation must consume no deferred replacement, including late callbacks.
	before = state()
	await click(button(ui, "New"))
	await click(ui.unsaved_dialog.get_ok_button())
	check(ui.dialog.visible and ui.dialog_action == "save_transition", "save before transition asks for project directory")
	ui.dialog.hide()
	ui.dialog.canceled.emit()
	var abandoned := ProjectSettings.globalize_path("user://abandoned-save")
	ui._path_selected(abandoned)
	check(state() == before and not DirAccess.dir_exists_absolute(abandoned), "cancel picker rejects late save/transition")
	# First export guides Save -> new filename; export never alters source or overwrites output.
	await click(button(ui, "Export .memap"))
	check(ui.dialog_action == "save_for_export", "first export enters save flow")
	var project := ProjectSettings.globalize_path("user://ux-project")
	ui.dialog.hide()
	ui._path_selected(project)
	await process_frame
	check(ui.dialog_action == "export" and ui.dialog.visible and not ui.store.dirty, "successful save continues export")
	var package := ProjectSettings.globalize_path("user://ux-export.memap")
	ui.dialog.hide()
	ui._path_selected(package)
	await finish()
	check(FileAccess.file_exists(package) and ui.export_report.visible, "first export publishes validated package/report")
	ui.export_report.hide()
	var digest := FileAccess.get_sha256(package)
	ui._start_package("export", package)
	check(not ui.busy and ui.validation_label.text.contains("E_EXPORT_EXISTS") and FileAccess.get_sha256(package) == digest, "existing output reports persistent recoverable error and retains bytes")
	check(ui.store.apply_command("Change seed", [{"field":"seed", "before":ui.store.document.seed,"after":17}]) == "", "dirty fixture")
	before = state()
	# Failed Save-and-continue retains edits, history and conflicting disk bytes.
	write(project.path_join("document.json"), "external writer")
	await click(button(ui, "New"))
	await click(ui.unsaved_dialog.get_ok_button())
	check(state() == before and ui.pending_document_action.is_empty() and ui.status_label.text.contains("Save As"), "save conflict blocks replacement and explains recovery")
	check(FileAccess.get_file_as_string(project.path_join("document.json")) == "external writer", "conflicting original remains untouched")
	var safe_project := ProjectSettings.globalize_path("user://safe-project")
	check(ui.store.save_project(safe_project) == "", "Save As recovers conflict")
	ui._document_changed()
	check(ui.store.apply_command("Another seed", [{"field":"seed", "before":17,"after":18}]) == "", "second dirty fixture")
	original_id = ui.store.document.map_id
	await click(button(ui, "New"))
	await click(ui.unsaved_dialog.get_ok_button())
	var reopened := STORE.new()
	check(reopened.open_project(safe_project) == "" and reopened.document.seed == 18 and ui.store.document.map_id != original_id, "Save and continue persists exact edits before replacement")
	# A deferred document action cannot consume a replacement document.
	ui._new()
	ui.store.new_document()
	before = state()
	await click(ui.recovery_continue_button)
	check(state() == before and ui.pending_document_action.is_empty(), "stale document action cannot replace current map")
	# Invalid Open after explicit recovery leaves current map and history intact.
	before = state()
	ui.dialog_action = "open"
	ui._path_selected(project)
	check(ui.unsaved_dialog.visible and state() == before, "Open asks after choosing target")
	await click(ui.recovery_continue_button)
	check(state() == before and ui.status_label.text.contains("Current document retained"), "invalid target preserves document")
	# Import failure -> visible retry with retained settings -> review/discard/adopt.
	var source := ProjectSettings.globalize_path("user://source.geojson")
	write(source, "invalid JSON")
	ui.import_license.text = "MIT"
	ui.import_accuracy.text = "synthetic"
	ui._start_import(source, "MIT")
	await finish()
	check(state() == before and ui.retry_import_button.visible and ui.validation_label.text.contains("Import stopped"), "failure retains document and exposes retry")
	await click(ui.retry_import_button)
	check(ui.import_dialog.visible and ui.import_license.text == "MIT" and ui.import_accuracy.text == "synthetic", "retry reopens preserved settings")
	write(source, '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[30,10],[30,30],[10,30],[10,10]]]}}]}')
	var source_hash := FileAccess.get_sha256(source)
	await click(button(ui.import_dialog, "Import / retry last source"))
	await finish()
	check(ui.pending_import != null and state() == before and ui.validation_label.text.contains("review"), "retry prepares without adopting")
	await capture("import-review")
	await click(ui.import_review.get_cancel_button())
	check(ui.pending_import == null and state() == before and ui.validation_label.text.contains("discarded"), "Discard is non-destructive and explicit")
	ui._start_import(source, "MIT")
	await finish()
	await click(ui.import_review.get_ok_button())
	await finish()
	check(ui.store.document.buildings.size() == 1 and ui.store.undo_stack.size() == 1, "Adopt is one Undo command")
	await click(button(ui, "Undo"))
	check(ui.store.document.buildings.is_empty() and FileAccess.get_sha256(source) == source_hash, "Undo adoption preserves source")
	ui._start_import(source, "MIT")
	await process_frame
	await click(ui.cancel_button)
	await finish()
	check(ui.pending_import == null and ui.store.document.buildings.is_empty(), "cancel prevents late adoption")
	ui._set_tool("Select")
	await capture("retry")
	check(ui.right_dock.get_global_rect().end.x <= ui.size.x and ui.status_label.get_global_rect().end.y <= ui.size.y, "controls and feedback fit minimum window")
	check(ui.tool_hint.get_global_rect().end.x <= ui.canvas.get_global_rect().end.x, "tool help wraps within canvas")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("editor_ux_validator: %s (%d assertions)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)
