extends SceneTree
## Track and city modes: one document, purpose-focused tool groups and panels.
var failed := false

func check(ok: bool, message: String) -> void:
	if not ok:
		failed = true
		push_error(message)

func _initialize() -> void: run.call_deferred()

func visible_groups(ui: Control) -> Array:
	var groups: Array = []
	for button: Button in ui.workspace_tabs.get_children():
		if button.visible: groups.append(str(button.get_meta("workspace_group")))
	return groups

func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	for _i in 4: await process_frame
	check(ui.editor_mode == "track" and visible_groups(ui) == ["roads", "gimmicks", "course"], "track mode groups: " + str(visible_groups(ui)))
	check(ui.selection_label.text.begins_with("TRACK MODE"), "track header: " + ui.selection_label.text)
	ui.set_editor_mode("city")
	await process_frame
	check(ui.editor_mode == "city" and ui.tool_group == "city" and ui.tool_workspace == "landscape", "city mode opens Map & data on the plan")
	check(visible_groups(ui) == ["city", "roads", "draw", "scenery", "parts", "course"], "city mode groups: " + str(visible_groups(ui)))
	check(ui.city_panel.visible and not ui.parts_panel.visible and not ui.simple_palette.visible and not ui.author_panel.visible and not ui.roam_palette.visible, "Map & data shows only the city panel")
	check(ui.city_panel.summary.text.contains("0 roads") and ui.selection_label.text.begins_with("CITY MODE"), "city summary and header: " + ui.city_panel.summary.text)
	ui.show_tool_group("draw")
	await process_frame
	check(ui.advanced_visible and ui.roam_palette.visible and ui.author_panel.visible and not ui.city_panel.visible, "Draw shows the full plan toolset")
	ui.show_tool_group("scenery")
	await process_frame
	check(not ui.advanced_visible and ui.simple_palette.visible and not ui.roam_palette.visible, "Scenery stays focused")
	ui.show_tool_group("parts")
	await process_frame
	check(ui.editor_mode == "city" and ui.parts_panel.visible and not ui.simple_palette.visible and not ui.roam_palette.visible and not ui.city_panel.visible, "Parts shows only the parts panel")
	ui.show_tool_group("roads")
	await process_frame
	check(ui.editor_mode == "city" and ui.tool_workspace == "track" and ui.selection_label.text.begins_with("CITY MODE"), "city roads edit in 3D within city mode: " + ui.selection_label.text)
	ui.set_editor_mode("track")
	await process_frame
	check(ui.editor_mode == "track" and ui.tool_group == "roads" and ui.selection_label.text.begins_with("TRACK MODE"), "track mode restores its group")
	ui.show_tool_group("gimmicks")
	ui.set_editor_mode("city")
	check(ui.tool_group == "roads", "city mode restores its last group")
	ui.set_editor_mode("track")
	check(ui.tool_group == "gimmicks", "track mode restores its last group")
	ui.open_advanced()
	ui.set_editor_mode("city")
	ui.show_tool_group("scenery")
	ui.open_advanced()
	check(ui.tool_group == "draw" and ui.author_panel.visible, "Advanced tools in city mode open Draw")
	# Opening a document picks its mode; editing and history stay shared.
	var MAIN := preload("res://scripts/editor_main.gd")
	check(MAIN.document_mode({"assembled_track":{}}) == "track", "assembled track is a track map")
	check(MAIN.document_mode({"play_area":[[[0,0],[1,0],[1,1]]]}) == "city", "play area is a city map")
	check(MAIN.document_mode({"attributions":[{"notice":"{\"adapter\":\"osm-extract-v1\"}"}], "assembled_track":{}}) == "city", "OSM import is a city map")
	check(MAIN.document_mode({"roads":[{}]}) == "city" and MAIN.document_mode({}) == "track", "plan roads are city, empty is track")
	ui.store.new_track(false)
	var path := ProjectSettings.globalize_path("user://editor-mode-check/track")
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	check(ui.store.save_project(path) == "", "save track fixture")
	ui.set_editor_mode("city")
	ui.store.dirty = false
	ui.pending_document_action = {"action":"open", "path":path, "session":ui.store.session_id}
	ui._continue_document_action()
	check(ui.editor_mode == "track" and ui.tool_group == "gimmicks", "opening a track project switches to track mode")
	ui.start_panel.show()
	var labels: Array = []
	var stack: Array = [ui.start_panel]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		if node is Label: labels.append(node.text)
		stack.append_array(node.get_children())
	check(labels.has("Track mode") and labels.has("City mode"), "start screen offers both modes: " + str(labels))
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("editor_mode_validator: ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)
