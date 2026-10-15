extends SceneTree
## Standalone initial application screen only; no detailed interaction acceptance.
func _initialize() -> void: run.call_deferred()
func check_icons(node: Node) -> int:
	var count := 0
	if node is Button and node.has_meta("action_label") and node.expand_icon and node.is_visible_in_tree():
		assert(node.icon != null and not node.icon.get_image().is_invisible(), str(node.get_meta("action_label")))
		count += 1
	for child in node.get_children(): count += check_icons(child)
	return count
func run() -> void:
	var entry: Node = load("res://scripts/editor_entry.tscn").instantiate()
	root.add_child(entry)
	var editor: Node = entry.get_child(0)
	for _i in 4: await process_frame
	for button: Button in editor.workspace_tabs.get_children():
		assert(button.visible and not button.text.is_empty(),"all four tool groups have visible labels")
	var palette: VBoxContainer = editor.track_workbench.palette_tools
	assert(palette.tabs.get_tab_title(palette.tabs.current_tab) == "Driving")
	var visible_tools := 0
	var grind_tool := false
	for tile: Dictionary in palette.tiles:
		if tile.button.is_visible_in_tree(): visible_tools += 1
		if tile.id == "track.grind_line": grind_tool = true
	assert(visible_tools > 0 and grind_tool, "Driving tools are visible; the Grind Line remains in the Gimmick tab")
	assert(editor.store.document.recipe_version == 1)
	assert(is_instance_valid(editor.canvas) and not editor.canvas.visible)
	assert(editor.start_panel.visible and editor.import_dialog == null and editor.generation_panel == null, "entry choices and lazy advanced tools")
	assert(check_icons(editor) > 20, "Initial controls contain visible artwork")
	var capture := OS.get_environment("MINIEARTHURE_INITIAL_SCREEN_CAPTURE")
	if not capture.is_empty():
		await RenderingServer.frame_post_draw
		assert(root.get_texture().get_image().save_png(capture) == OK)
	entry.queue_free()
	for _i in 3: await process_frame
	print("initial_screen_validator: PASS")
	quit()
