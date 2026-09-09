extends SceneTree
const EDIT := preload("res://scripts/workbench_edit.gd")
var failures: Array[String] = []
var checks := 0
var ui: Control

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures.append(message)
		push_error(message)
		print("E01 failure state: selection=", ui.canvas.selected, " status=", ui.status_label.text, " history=", ui.store.undo_stack.size(), " buildings=", ui.store.document.buildings)
		quit(1)

func _initialize() -> void:
	run.call_deferred()

func equal(value: Variant, expected: Variant) -> bool:
	return value == JSON.parse_string(JSON.stringify(expected))

func state() -> String:
	return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.history_bytes, ui.store.dirty])

func record(field: String, id: String) -> Dictionary:
	for item: Dictionary in ui.store.document.get(field, []):
		if str(item.id) == id: return item
	return {}

func button(node: Node, title: String) -> Button:
	if node is Button and node.text == title: return node
	for child in node.get_children():
		var found := button(child, title)
		if found != null: return found
	return null

func pointer(p: Vector2, down: bool, shift: bool = false) -> void:
	var event := InputEventMouseButton.new()
	event.position = p
	event.global_position = p
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
	event.pressed = down
	event.shift_pressed = shift
	root.push_input(event)
	await process_frame

func click(p: Vector2, shift: bool = false) -> void:
	await pointer(p, true, shift)
	await pointer(p, false, shift)

func click_button(title: String) -> void:
	var target := button(ui, title)
	check(target != null and target.is_visible_in_tree(), "button available: " + title)
	if target != null: await click(target.get_global_rect().get_center())

func motion(p: Vector2, delta: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = p
	event.global_position = p
	event.relative = delta
	event.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(event)
	await process_frame

func key(code: Key, command: bool = false, shift: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	event.ctrl_pressed = command and OS.get_name() != "macOS"
	event.meta_pressed = command and OS.get_name() == "macOS"
	event.shift_pressed = shift
	root.push_input(event)
	await process_frame
	event.pressed = false
	root.push_input(event)
	await process_frame

func map_point(p: Array) -> Vector2:
	return ui.canvas.global_position + ui.canvas.screen(p)

func type_text(value: String) -> void:
	for i in range(value.length()):
		var event := InputEventKey.new()
		event.unicode = value.unicode_at(i)
		event.keycode = value.unicode_at(i)
		event.pressed = true
		root.push_input(event)
		await process_frame
		event.pressed = false
		root.push_input(event)
		await process_frame

func run() -> void:
	root.size = Vector2i(1440, 900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	var patches: Array = [{"field":"recipe_version", "before":1, "after":3}]
	for item in [
		["buildings", {"id":"house-a","footprint":[[8000,8000],[20000,8000],[20000,20000],[8000,20000]],"base_cm":0,"height_cm":1200,"usage":"residential","material":"concrete","roof":"flat","entrances":[[[10000,6000],[12000,6000],[12000,8000],[10000,8000]]]}],
		["buildings", {"id":"house-b","footprint":[[28000,8000],[40000,8000],[40000,20000],[28000,20000]],"base_cm":0,"height_cm":1800,"usage":"residential","material":"brick","roof":"flat"}],
		["nodes", {"id":"n-a","position":[10000,20,40000],"level":0}],
		["nodes", {"id":"n-b","position":[30000,20,40000],"level":0}],
		["nodes", {"id":"n-c","position":[60000,20,40000],"level":0}],
		["roads", {"id":"road-a","from":"n-a","to":"n-b","points":[[10000,20,40000],[30000,20,40000]],"widths_cm":[800],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}],
		["roads", {"id":"import-0123456789abcdef-1","from":"n-b","to":"n-c","points":[[30000,20,40000],[60000,20,40000]],"widths_cm":[600],"surfaces":["gravel"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}],
		["zones", {"id":"grove","polygon":[[65000,60000],[90000,60000],[90000,90000],[65000,90000]],"kind":"forest","spacing_cm":800,"density_per_mille":100,"exclusions":[[[70000,70000],[72000,70000],[72000,72000],[70000,72000]]]}],
		["placements", {"id":"tree","asset_id":"builtin:tree","position":[50000,0,80000],"quarter_turns":0}],
		["repetitions", {"id":"fence","asset_id":"builtin:fence","points":[[10000,0,65000],[30000,0,65000]],"spacing_cm":500}]
	]: patches.append(EDIT.patch(item[0], null, item[1]))
	var fixture_error: String = ui.store.apply_command("Workbench synthetic fixture", patches)
	check(fixture_error == "", "native fixture accepted: " + fixture_error)
	if ui.store.document.buildings.is_empty():
		ui.store.dirty = false
		ui.free()
		quit(1)
		return
	await process_frame
	print("E01 initial geometry: ", record("buildings", "house-a"))
	print("E01 layout: root=", root.size, " ui=", ui.size, " canvas=", ui.canvas.get_global_rect(), " right=", ui.right_dock.get_global_rect())
	check(ui.canvas.get_global_rect().end.x <= ui.size.x and ui.canvas.size.x >= 300, "canvas fits native layout")
	check(ui.right_dock.get_global_rect().end.x <= ui.size.x, "properties/preview fit window")
	await click(map_point([14000,14000]))
	check(ui.canvas.selected == ["buildings/house-a"], "actual pointer selects building")
	await click(map_point([34000,14000]), true)
	check(ui.canvas.selected.size() == 2, "Shift adds second building")
	await click(map_point([34000,14000]), true)
	check(ui.canvas.selected == ["buildings/house-a"], "Shift toggles without duplicates")
	await click(map_point([34000,14000]), true)
	var count: int = ui.store.undo_stack.size()
	var start := map_point([14000,14000])
	var end := map_point([17000,16000])
	await pointer(start, true)
	await motion(end, end - start)
	check(equal(record("buildings", "house-a").footprint[0], [8000,8000]), "drag retains committed geometry until release")
	await pointer(end, false)
	check(equal(record("buildings", "house-a").footprint[0], [11000,10000]) and equal(record("buildings", "house-b").footprint[0], [31000,10000]), "drag moves the whole existing multiselection on grid")
	check(equal(record("buildings", "house-a").entrances[0][0], [13000,8000]), "building entrance translates with footprint")
	check(ui.store.undo_stack.size() == count + 1, "whole multiselection drag is one command")
	await key(KEY_Z, true)
	check(equal(record("buildings", "house-a").footprint[0], [8000,8000]), "actual shortcut undoes movement")
	await key(KEY_D, true)
	check(ui.store.document.buildings.size() == 4 and ui.canvas.selected.size() == 2, "actual duplicate selects new copies")
	await key(KEY_DELETE)
	check(ui.store.document.buildings.size() == 2, "actual delete removes selected copies")
	await key(KEY_Z, true)
	check(ui.store.document.buildings.size() == 4, "deleted selection undo restores records")
	ui._history(false)
	await process_frame
	# Box selection uses real routing and only includes completely enclosed shapes.
	start = map_point([5000,5000])
	end = map_point([43000,23000])
	await pointer(start, true)
	await motion(end, end - start)
	await pointer(end, false)
	check(ui.canvas.selected.size() == 2, "empty-space box selects both buildings")
	# Apply only the changed common property to a heterogeneous-valued group.
	var height_spin: SpinBox
	for row in ui.properties.get_children():
		if row is HBoxContainer and row.get_child(0).text == "Height (m)": height_spin = row.get_child(1)
	check(height_spin != null, "multi-object property panel has height")
	if height_spin != null:
		ui.properties.get_parent().ensure_control_visible(height_spin)
		await process_frame
		await click(height_spin.get_line_edit().get_global_rect().get_center())
		await key(KEY_A, true)
		await type_text("22")
		await key(KEY_ENTER)
		print("E01 numeric input: text=", height_spin.get_line_edit().text, " value=", height_spin.value, " changed=", ui.property_changes)
		check(height_spin.value == 22 and ui.property_changes.get("height_cm", 0) == 2200, "visible numeric input submits property change")
		await click_button("Apply properties")
	check(record("buildings", "house-a").height_cm == 2200 and record("buildings", "house-b").height_cm == 2200, "entered multi-property applies to both")
	check(record("buildings", "house-b").material == "brick", "unmodified heterogeneous property is retained")
	ui._history(false)
	await process_frame
	# A text field owns editing shortcuts; typing must never delete map objects.
	await click(ui.layers.search.get_global_rect().get_center())
	var before := state()
	await key(KEY_A, true)
	await key(KEY_DELETE)
	await key(KEY_B)
	check(state() == before and ui.canvas.tool == "Select", "text-input shortcuts do not modify map or active tool")
	ui.layers.search.text = ""
	ui.layers.refresh()
	ui.canvas.grab_focus()
	# Shared graph updates and locked dependency failure use the same live command route.
	await click(map_point([20000,40000]))
	check(ui.canvas.selected == ["roads/road-a"], "pointer selects road segment")
	ui.canvas._move_selection(Vector2(1000,2000), false)
	check(equal(record("nodes", "n-b").position, [31000,20,42000]), "shared node moves once")
	check(equal(record("roads", "import-0123456789abcdef-1").points[0], [31000,20,42000]) and equal(record("roads", "import-0123456789abcdef-1").points[1], [60000,20,40000]), "unselected incident road follows shared endpoint only")
	ui._history(false)
	ui.canvas.set_layer_state("import/0123456789abcdef", {"locked":true})
	before = state()
	ui.canvas._move_selection(Vector2(1000,2000), false)
	check(state() == before and ui.status_label.text.contains("locked"), "locked incident road rejects the whole edit/history")
	ui.canvas.set_layer_state("import/0123456789abcdef", {})
	ui.canvas.set_selection(["roads/road-a", "roads/import-0123456789abcdef-1"])
	ui.canvas.duplicate_selection()
	check(ui.store.document.nodes.size() == 6 and ui.store.document.roads.size() == 4, "duplicate graph remaps three shared nodes, not four")
	var copied: Array = []
	for road: Dictionary in ui.store.document.roads:
		if EDIT.key("roads", str(road.id)) in ui.canvas.selected: copied.append(road)
	check(copied.size() == 2 and (copied[0].from == copied[1].to or copied[0].to == copied[1].from), "copied roads retain shared connection and separate original graph")
	ui._history(false)
	ui.canvas.set_selection(["nodes/n-b"])
	before = state()
	ui.canvas.delete_selection()
	check(state() == before and ui.status_label.text.contains("unselected road"), "referenced node cannot be deleted alone")
	ui.canvas.set_selection(["roads/road-a"])
	ui.canvas.delete_selection()
	check(record("nodes", "n-a").is_empty() and not record("nodes", "n-b").is_empty(), "road delete removes only its unused endpoint")
	ui._history(false)
	ui.canvas.set_selection(["roads/road-a"])
	before = state()
	ui.canvas._move_selection(Vector2(-1000000,0), false)
	check(state() == before, "native bounds failure preserves graph, undo and dirty state")
	# All vector domains use the same command and preserve embedded rings.
	ui.canvas.set_selection(["zones/grove", "placements/tree", "repetitions/fence"])
	ui.canvas._move_selection(Vector2(100,200), false)
	check(equal(record("zones", "grove").exclusions[0][0], [70100,70200]), "zone exclusions move with polygon")
	check(equal(record("placements", "tree").position, [50100,0,80200]) and equal(record("repetitions", "fence").points[0], [10100,0,65200]), "placement and repetition preserve elevation")
	ui._history(false)
	await layer_and_panel_checks()
	var directory := OS.get_user_data_dir().path_join("workbench-project")
	check(ui.store.save_project(directory) == "", "workbench edits save")
	var saved: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.autosave() == "", "workbench autosave")
	var recovery: String = ui.store.recovery_path()
	check(ui.store.open_project(directory) == "" and ui.store.document == saved, "save/reopen preserves the document independently of view state")
	check(ui.store.recover(recovery) == "", "workbench recovery opens")
	await click_button("Validate")
	check(ui.validation_label.text.begins_with("Valid document"), "validation has persistent dedicated status")
	await click_button("3D Preview")
	for _i in range(600):
		await process_frame
		if not ui.busy: break
	check(not ui.busy and ui.validation_label.text.begins_with("Preview ready"), "same public MapKit worker preview attaches")
	ui.canvas.set_selection(["buildings/house-a", "buildings/house-b"])
	for window_size in [Vector2i(1024,720), Vector2i(1280,800)]:
		root.size = window_size
		for _frame in range(3): await process_frame
		check(ui.right_dock.get_global_rect().end.x <= ui.size.x and ui.status_label.get_global_rect().end.y <= ui.size.y, "docks/status fit resized window " + str(window_size))
	var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
	if capture != "" and DisplayServer.get_name() != "headless":
		ui.canvas.set_selection(["buildings/house-a", "buildings/house-b"])
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(capture) == OK, "rendered workbench capture")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("workbench_validator: %s (%d assertions)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)

func layer_and_panel_checks() -> void:
	ui.layers.refresh()
	await process_frame
	var tree: Tree = ui.layers.tree
	var layer: TreeItem = tree.get_root().get_first_child()
	while layer != null and layer.get_metadata(0) != "buildings": layer = layer.get_next()
	check(layer != null, "typed layer row exists")
	check(tree.get_item_area_rect(layer, 2).end.x <= tree.size.x, "Lock column remains accessible without horizontal scrolling")
	var before := state()
	if layer != null:
		var p := tree.global_position + tree.get_item_area_rect(layer, 1).get_center()
		await click(p)
		check(not ui.canvas.layer_state.get("buildings", {}).get("visible", true), "actual layer Show checkbox hides category")
		check(ui.canvas._hit(Vector2(14000,14000)) == "", "hidden objects are not pickable")
		# Refresh replaces TreeItems; reacquire the row.
		layer = tree.get_root().get_first_child()
		while layer != null and layer.get_metadata(0) != "buildings": layer = layer.get_next()
		await click(tree.global_position + tree.get_item_area_rect(layer, 1).get_center())
		layer = tree.get_root().get_first_child()
		while layer != null and layer.get_metadata(0) != "buildings": layer = layer.get_next()
		await click(tree.global_position + tree.get_item_area_rect(layer, 2).get_center())
		check(ui.canvas.layer_state.get("buildings", {}).get("locked", false), "actual Lock checkbox locks category")
		check(ui.canvas._hit(Vector2(14000,14000)) == "", "locked objects are not pickable")
		ui._set_tool("Building")
		ui.canvas.draft.assign([Vector2(1000,1000),Vector2(2000,1000),Vector2(2000,2000)])
		ui.canvas.finish_shape()
		check(state() == before, "layer state does not dirty document and locked layer rejects creation")
	ui.canvas.cancel_interaction()
	ui.canvas.set_layer_state("buildings", {})
	ui._set_tool("Select")
	ui.layers.refresh()
	await process_frame
	var row: TreeItem = ui.layers.rows["buildings/house-a"]
	await click(tree.global_position + tree.get_item_area_rect(row, 0).get_center())
	check(ui.canvas.selected == ["buildings/house-a"], "actual object-tree selection reaches canvas and properties")
	var other: TreeItem = ui.layers.rows["buildings/house-b"]
	await click(tree.global_position + tree.get_item_area_rect(other, 0).get_center(), true)
	check(ui.canvas.selected.size() == 2, "actual tree Shift selection publishes the final group")
	layer = tree.get_root().get_first_child()
	while layer != null and layer.get_metadata(0) != "buildings": layer = layer.get_next()
	await click(tree.global_position + tree.get_item_area_rect(layer, 0).get_center())
	check(ui.layers.active_layer == "buildings" and ui.canvas.selected.size() == 2, "layer heading selects its editable objects")
	var slider: HSlider = ui.layers.opacity_control
	await click(slider.global_position + Vector2(slider.size.x * 0.5, slider.size.y * 0.5))
	check(float(ui.canvas.layer_state.get("buildings", {}).get("opacity", 1.0)) < 0.8, "actual opacity slider updates the selected layer")
	ui.canvas.set_layer_state("buildings", {})
	ui.layers.refresh()
	await process_frame
	# Move the visible native split handle, then persist/restore view-only settings.
	var split: HSplitContainer = ui.outer_split
	var original: int = split.split_offset
	var handle := Vector2(ui.left_dock.get_global_rect().end.x + 5, ui.left_dock.global_position.y + 30)
	await pointer(handle, true)
	await motion(handle + Vector2(30,0), Vector2(30,0))
	await pointer(handle + Vector2(30,0), false)
	check(split.split_offset != original, "actual split handle adjusts panel width")
	ui.snap_size.value = 2.5
	ui.snap_toggle.button_pressed = false
	ui._save_workbench()
	var offset: int = split.split_offset
	split.split_offset = 0
	ui.snap_size.value = 1
	ui.snap_toggle.button_pressed = true
	ui._restore_workbench()
	check(split.split_offset == offset and ui.canvas.snap_cm == 250 and not ui.canvas.snap_enabled, "view settings restore without entering document/history")
	check(state() == before, "panel/snap preferences are separate from map source")
	await click_button("Tools / layers")
	check(not ui.left_dock.visible, "dock toggle collapses tools/layers")
	await click_button("Tools / layers")
	await click_button("Properties / 3D")
	check(not ui.right_dock.visible, "dock toggle collapses properties/preview")
	await click_button("Properties / 3D")
	ui.snap_toggle.button_pressed = true
	ui.snap_size.value = 1
	ui._reset_panels()
	await process_frame
	var probe: Vector2 = ui.canvas.screen([1234,5678])
	check(ui.canvas.world(probe) == Vector2(1200,5700), "grid rounds to configured centimetres")
	check(ui.canvas._snap_vertex(Vector2(10005,40005)) == Vector2(10000,40000), "endpoint snap uses existing exact vertex")
	ui.canvas.grab_focus()
	await key(KEY_R)
	check(ui.canvas.tool == "Road" and ui.tool_buttons.Road.button_pressed, "tool shortcut and toolbar stay synchronized")
	await key(KEY_V)
	var start := map_point([14000,14000])
	await pointer(start, true)
	await motion(start + Vector2(20,0), Vector2(20,0))
	await key(KEY_ESCAPE)
	await pointer(start + Vector2(20,0), false)
	check(state() == before and not ui.store.has_gesture(), "routed Escape rejects late drag release")
