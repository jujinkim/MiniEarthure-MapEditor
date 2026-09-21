extends "./preview_export_validator.gd"

func run() -> void:
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	ui.preview_enabled = false
	ui.preview_due = 0
	var canonical: String = ui.store.bridge.canonical_document()
	var epoch: int = ui.store.command_epoch
	check(ui.author_panel is PanelContainer and ui.author_panel.visible, "authoring settings are a persistent dock")
	check(ui.preview_dock.get_parent() == ui.canvas.get_parent(), "2D and 3D share the central workspace")
	for window_size in [Vector2i(1024,720), Vector2i(1440,900), Vector2i(1920,1080)]:
		root.size = window_size
		for mode in ["2d", "3d", "split"]:
			ui._set_view_mode(mode)
			await process_frame
			await process_frame
			check(ui.canvas.visible == (mode != "3d") and ui.preview_dock.visible == (mode != "2d"), "view visibility " + mode)
			print("layout ", window_size, " ", mode, " ui=", ui.size, " right=", ui.right_dock.get_global_rect(), " status=", ui.status_label.get_global_rect(), " outer_min=", ui.outer_split.get_combined_minimum_size(), " author_min=", ui.author_panel.get_combined_minimum_size())
			check(ui.right_dock.get_global_rect().end.x <= ui.size.x + 1 and ui.status_label.get_global_rect().end.y <= ui.size.y + 1, "workspace fits " + str(window_size) + " " + mode)
	ui._set_view_mode("3d")
	ui.workspace_views.split_offset = 12
	ui._save_workbench()
	ui._set_view_mode("2d")
	ui._restore_workbench()
	check(ui.view_mode == "3d", "view mode persists independently")
	ui.commands._filter("restore")
	check(ui.commands.results.item_count == 1, "search finds package restoration")
	ui.commands._filter("no-such-command")
	check(ui.commands.results.item_count == 0, "empty search result is safe")
	ui.commands._filter("Create / Road")
	check(ui.commands.results.item_count == 1, "search selects one tool command")
	ui.commands._run(0)
	check(ui.canvas.tool == "Road", "command invokes existing tool")
	var input := LineEdit.new()
	ui.add_child(input)
	input.grab_focus()
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_B
	ui._unhandled_key_input(event)
	check(ui.canvas.tool == "Road", "text entry does not switch tools")
	input.release_focus()
	ui._unhandled_key_input(event)
	check(ui.canvas.tool == "Building", "docked settings do not block canvas shortcuts")
	var camera: Camera3D = ui.preview_camera.camera
	ui.preview_camera.frame(Vector3.ZERO, 40)
	var original_position := camera.position
	var orbit := InputEventMouseMotion.new()
	orbit.button_mask = MOUSE_BUTTON_MASK_RIGHT
	orbit.relative = Vector2(30, 20)
	check(ui.preview_camera.input(orbit) and camera.position != original_position, "3D orbit changes camera")
	check(is_equal_approx(camera.position.distance_to(ui.preview_camera.target), 40), "orbit keeps target distance")
	orbit.button_mask = MOUSE_BUTTON_MASK_MIDDLE
	check(ui.preview_camera.input(orbit) and ui.preview_camera.target != Vector3.ZERO, "3D pan changes view target")
	var zoom := InputEventMouseButton.new()
	zoom.pressed = true
	zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	check(ui.preview_camera.input(zoom) and ui.preview_camera.distance < 40, "3D zoom bounded view state")
	check(ui.store.bridge.canonical_document() == canonical and ui.store.command_epoch == epoch, "workspace changes never modify document or history")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("workspace_commands_validator: PASS (", checks, " checks)")
	quit(0)
