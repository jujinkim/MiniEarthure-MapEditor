extends SceneTree
## Focused command / preference / preview state regressions, no OS interaction.
const EDITOR := preload("res://scripts/editor_main.gd")
const REGISTRY := preload("res://scripts/workspace_commands.gd")
var ui: Control
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)
func state() -> String:
	return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.dirty])
func key(code: int, primary := false, echo := false) -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = true
	event.physical_keycode = code
	event.echo = echo
	if OS.get_name() == "macOS": event.meta_pressed = primary
	else: event.ctrl_pressed = primary
	return event
func release_focus() -> void:
	var focus := root.gui_get_focus_owner()
	if focus != null: focus.release_focus()
func run() -> void:
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	for _i in 3: await process_frame
	var commands: PopupPanel = ui.commands
	var bench: Node = ui.track_workbench
	var placement: Node = bench.placement
	commands._filter("")
	check(commands.results.item_count > 20, "empty command query lists available commands")
	check(bench.palette_tools.tiles[0].button.visible, "empty palette query shows tiles")
	check(commands.conflicts({}).is_empty(), "defaults have no overlapping keys")
	for entry: Dictionary in bench.catalogue.entries:
		check(commands.index_of("track.piece." + entry.id) >= 0, "every catalogue piece is a command")
	check(commands.favorites.track[8] == "track.action.jump_panel", "slot nine is attached jump panel")
	var before := state()
	commands.execute_id("track.piece.straight")
	check(state() == before and placement.tool == "straight", "palette tool selection is view-only")
	check(placement.width_cm == 400, "default width prefers four metres after JSON numeric conversion")
	check(placement.preview_at(Vector3.ZERO) and state() == before, "ghost does not edit the map")
	var builds: int = placement.geometry_builds
	placement.preview_at(Vector3(2, 0, 0))
	check(placement.geometry_builds == builds, "mouse movement reuses compiled ghost geometry")
	var serial: int = placement.serial
	check(placement.commit(serial), "one placement commits")
	check(bench.source.instances.size() == 1 and ui.store.undo_stack.size() == 1, "one click is one command")
	check(placement.tool == "straight" and not placement.commit(serial), "same tool remains; consumed candidate cannot repeat")
	var end: Vector3 = bench.PREVIEW.point(ui.store.document.assembled_track.pieces[0].path.back().position_cm)
	check(placement.preview_at(end), "continuous preview uses current source")
	check(placement.candidate.snap == 0 and placement.commit(), "port snap uses current exit")
	check(bench.source.instances.size() == 2 and bench.source.connections.size() == 1 and ui.store.undo_stack.size() == 2, "continuous placement records one edge and one step")
	ui._history(false)
	check(bench.source.instances.size() == 1 and placement.tool == "", "Undo cancels preview and reverses only last placement")
	ui._history(true)
	check(bench.source.instances.size() == 2 and placement.tool == "", "Redo restores placement without restarting a tool")
	commands.execute_id("track.piece.gentle90")
	placement.preview_at(Vector3(40, 0, 0))
	before = state()
	serial = placement.serial
	placement.rotate_by(15)
	check(placement.yaw == 15 and state() == before and not placement.commit(serial), "rotation invalidates old candidate without editing")
	placement.preview_at(Vector3(40, 0, 0))
	placement.candidate.item.width_cm = 999
	var selected: int = bench.selected
	check(not placement.commit() and state() == before and bench.selected == selected, "failed native validation preserves map, selection and history")
	commands.execute_id("track.piece.straight")
	placement.preview_at(Vector3(40, 0, 0))
	serial = placement.serial
	ui._set_view_mode("2d")
	check(placement.tool == "" and not placement.commit(serial), "view change rejects late candidates")
	commands.execute_id("track.piece.straight")
	check(ui.view_mode == "split", "hidden 3D automatically opens split view")
	placement.preview_at(Vector3(40, 0, 0))
	ui.commands.open()
	check(placement.tool == "" and not placement.commit(), "opening command popup cancels placement")
	commands.hide()
	release_focus()
	commands.execute_id("track.piece.straight")
	placement.preview_at(Vector3(40, 0, 0))
	ui._notification(Node.NOTIFICATION_APPLICATION_FOCUS_OUT)
	check(placement.tool == "" and not placement.commit(), "focus loss cancels placement")
	commands.execute_id("track.action.jump_panel")
	before = state()
	check(not placement.preview_attachment(-1, 0) and not placement.commit() and state() == before, "attachment needs a surface")
	check(placement.preview_attachment(0, 2) and placement.commit(), "attached jump panel commits against target road")
	check(bench.source.actions.size() == 1 and bench.source.actions[0].landing == null, "continuous road action has no forced landing")
	ui._history(false)
	check(bench.source.actions.is_empty(), "attached action undoes atomically")
	# Button, search, slot and shortcut all select the same tool without an edit.
	before = state()
	for tile: Dictionary in bench.palette_tools.tiles:
		if tile.id == "track.piece.straight": tile.button.pressed.emit(); break
	check(placement.tool == "straight" and state() == before, "tile uses command registry")
	commands._filter("track.piece.hairpin")
	commands._run(0)
	check(placement.tool == "hairpin" and state() == before, "command search activates same preview")
	release_focus()
	check(commands.handle_key(key(KEY_1)) and placement.tool == "straight", "numeric favorite activates current-mode tool")
	check(not commands.handle_key(key(KEY_2, false, true)) and placement.tool == "straight", "key repeat is ignored")
	check(commands.handle_key(key(KEY_V)) and placement.tool == "", "V selects and cancels")
	commands.handle_key(key(KEY_1))
	check(commands.handle_key(key(KEY_ESCAPE)) and placement.tool == "", "Escape cancels")
	var config_before: String = ui.store._signature(ui.store.document)
	check(commands.assign_favorite("track", 0, "track.piece.loop") == "", "favorite assignment saves")
	bench.palette_tools.search.text = "curve"
	bench.palette_tools._filter("curve")
	bench.palette_tools._build_tiles(true)
	check(commands.favorites.track[0] == "track.piece.loop", "filter and sort preserve slot identity")
	commands.handle_key(key(KEY_1))
	check(placement.tool == "loop", "slot executes assigned stable ID")
	var custom := {"track.piece.loop":[REGISTRY.key("L")], "tool.road":[REGISTRY.key("L")], "edit.toggle_snap":[REGISTRY.key("H")]}
	check(commands.conflicts(custom).is_empty(), "exclusive contexts can reuse a physical key")
	check(commands.save_bindings(custom) == "", "custom keys persist")
	check(ui.snap_toggle.tooltip_text == commands.tooltip("edit.toggle_snap") and bench.snap.tooltip_text == ui.snap_toggle.tooltip_text, "both snap hints follow remapped keys")
	var conflict := custom.duplicate(true)
	conflict["track.piece.straight"] = [REGISTRY.key("L")]
	var settings_before := FileAccess.get_file_as_string(commands.settings_path)
	check(commands.save_bindings(conflict) != "" and FileAccess.get_file_as_string(commands.settings_path) == settings_before, "overlapping key conflict blocks persistence")
	ui._save_workbench()
	commands.bindings.clear()
	commands.favorites = commands.DEFAULT_FAVORITES.duplicate(true)
	commands.load_settings()
	check(commands.bindings == custom and commands.favorites.track[0] == "track.piece.loop", "settings reload and panel save retain bindings and favorites")
	check(ui.store._signature(ui.store.document) == config_before, "preferences are not document edits")
	commands.open_settings()
	check(commands.settings_dialog.list.item_count == commands.commands.size(), "empty settings query lists every command")
	check(commands.settings_dialog.get_ok_button().text == "Save shortcuts", "settings dialog retains text actions")
	commands.settings_dialog.pending = conflict
	commands.settings_dialog._filter("")
	check(commands.settings_dialog.get_ok_button().disabled, "settings UI shows conflict and blocks Save")
	commands.settings_dialog.selected_id = "track.piece.loop"
	commands.settings_dialog.begin_capture()
	before = state()
	check(not commands.handle_key(key(KEY_DELETE)) and state() == before, "key assignment blocks editor commands")
	commands.settings_dialog.hide()
	check(commands.save_bindings({}) == "" and commands.keys_for("track.piece.loop").is_empty(), "restore defaults clears custom key")
	commands.execute_id("tool.select")
	release_focus()
	for input in [LineEdit.new(), TextEdit.new(), SpinBox.new()]:
		ui.add_child(input)
		if input is SpinBox: input.get_line_edit().grab_focus()
		else: input.grab_focus()
		before = state()
		check(not commands.handle_key(key(KEY_DELETE)) and not commands.handle_key(key(KEY_D, true)) and state() == before, "text/number input protects map editing")
		input.queue_free()
		await process_frame
	release_focus()
	# In track mode, duplicate/delete never target a hidden free-roam selection.
	ui.canvas.selected.assign(["buildings:hidden"])
	bench.selected = -1
	commands.refresh_buttons()
	before = state()
	check(not commands.execute_id("edit.delete") and state() == before, "hidden roam selection cannot enable track deletion")
	bench.selected = 0
	check(commands.execute_id("edit.duplicate") and bench.source.instances.size() == 3, "track duplicate resolves current selection")
	check(commands.execute_id("edit.delete") and bench.source.instances.size() == 2, "track delete resolves current selection")
	bench.selected = 0
	bench._properties()
	bench.route_list.select(0)
	var route: Array = bench.source.paths[0].pieces.duplicate()
	bench._route_move(1)
	check(bench.source.paths[0].pieces == [route[1], route[0]], "route list reorders IDs atomically")
	ui._history(false)
	# Navigation-only plan cannot edit derived track roads.
	before = state()
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = Vector2(50, 50)
	ui.canvas._gui_input(click)
	check(state() == before and ui.canvas.navigation_only, "auxiliary track plan is navigation-only")
	# Same physical slot selects a different mode's command.
	check(ui.store.set_free_roam(true) == "", "switch to free roam")
	release_focus()
	commands.handle_key(key(KEY_2))
	check(ui.canvas.tool == "Road", "free-roam favorite two selects Road")
	var snap: bool = ui.canvas.snap_enabled
	commands.handle_key(key(KEY_S))
	check(ui.canvas.snap_enabled != snap, "S toggles current mode snap")
	check(not ui.canvas.navigation_only, "free roam keeps polygon and terrain editing")
	commands.handle_key(key(KEY_V))
	ui.canvas.zoom = 2
	commands.handle_key(key(KEY_F))
	check(ui.canvas.zoom == 1, "F fits the free roam plan through the shared command")
	for roam in [false, true]:
		ui.store.set_free_roam(roam)
		for window_size in [Vector2i(1024, 720), Vector2i(1440, 900), Vector2i(1920, 1080)]:
			root.size = window_size
			ui._reset_panels()
			for _i in 3: await process_frame
			print("layout ", window_size, " roam=", roam, " root=", ui.size, " right=", ui.right_dock.get_global_rect(), " footer=", ui.status_label.get_global_rect())
			check(ui.size == Vector2(window_size), "root fits requested window")
			check(ui.right_dock.get_global_rect().end.x <= window_size.x + 1 and ui.status_label.get_global_rect().end.y <= window_size.y + 1, "docks/footer fit requested window")
			check(ui.workspace_views.size.x >= 300 and ui.workspace_views.size.y >= 100, "workspace retains usable area")
	ui.store.dirty = false
	ui.queue_free()
	for _i in 3: await process_frame
	print("icon_workbench_validator: PASS (", checks, " checks)")
	quit()
