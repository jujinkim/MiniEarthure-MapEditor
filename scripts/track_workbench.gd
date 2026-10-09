extends Node
const I18N := preload("./locale_text.gd")
## Commands edit public authoring source; the native compiler owns every derived frame.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var editor: Control
var palette: VBoxContainer
var properties: VBoxContainer
var report: Label
var selection: ItemList
var catalogue: Dictionary
var source: Dictionary={}
var selected := -1
var route_index := 0
var snap: CheckButton
var road_tools: RefCounted
var active := false
var view: Node3D
var controls: Array[SpinBox]=[]
var port_widths: Array[SpinBox]=[]
var width: OptionButton
var target: OptionButton
var sample_input: SpinBox
var action_height: SpinBox
var landing_target: OptionButton
var landing_sample: SpinBox
var updating := false
var selection_serial := 0
var interaction_serial := 0
var apply_context: Dictionary = {}
var drawn_epoch := -1
var display_document: Dictionary = {}
var final_preview_due := false

const STYLE := preload("./workbench_style.gd")
var palette_tools: VBoxContainer
var placement: Node
var route_list: ItemList
var section_open := {"Transform":true, "Connections":false, "Routes & Checkpoints":false, "Actions":false}

func build(owner: Control) -> void:
	editor = owner
	editor.store.draft_changed.connect(func(context: Dictionary):
		apply_context = context
		refresh()
		editor._draft_status_changed())
	editor.store.validated_changed.connect(func():
		final_preview_due = true
		editor._draft_status_changed())
	editor.store.track_edit_finished.connect(func(failure: String):
		if failure != "":
			editor._status(I18N.diagnostic(failure))
			if properties.get_meta("placement_tool", "") != placement.tool: _properties()
		elif not editor.store.editing_locked(): editor._status(I18N.t("Track edit complete · Draft saved in document history."))
		editor.commands.refresh_buttons())
	catalogue = JSON.parse_string(editor.store.bridge.track_catalogue()).data
	road_tools = preload("./road_workbench.gd").new()
	road_tools.bench = self
	placement = preload("./track_placement.gd").new()
	placement.bench = self
	add_child(placement)
	var entries: Array[Dictionary] = []
	editor.commands.register("Track", "Grind Line", open_grind_lines, "", {"id":"track.grind_line", "context":"track", "icon":"free_curve", "description":"Author independent straight or curved grind lines and their endpoint connections.", "menu":false})
	entries.append({"id":"track.grind_line","group":"Gimmick","section":"Grind lines"})
	for entry: Dictionary in catalogue.entries:
		var id: String = "track.piece." + entry.id
		editor.commands.register("Track", piece_name(entry.id), add_piece.bind(entry.id), "", {"id":id, "context":"track", "description":"Preview this road piece; click in 3D to place. Repeat with the same tool.", "icon":"piece_" + entry.id, "menu":false})
		entries.append({"id":id, "group":str(entry.category).capitalize(), "section":"Road pieces"})
	for kind: String in catalogue.obstacle_kinds:
		var id := "track.obstacle." + kind
		editor.commands.register("Track", piece_name(kind) + " obstacle", add_obstacle.bind(kind), "", {"id":id, "context":"track", "icon":"obstacle", "description":"Point at a road surface, then click to attach an obstacle.", "menu":false})
		entries.append({"id":id, "group":"Gimmick", "section":"Road attachments"})
	for kind: String in ["jump_panel", "acceleration_panel", "boost_chain", "air_ring"]:
		var id := "track.action." + kind
		editor.commands.register("Track", "Attached " + piece_name(kind), add_action.bind(kind), "", {"id":id, "context":"track", "icon":kind, "description":"Point at a road surface, then click to attach an action.", "menu":false})
		entries.append({"id":id, "group":"Action", "section":"Road attachments"})
	for entry in [["Left", -15.0, "Q"], ["Right", 15.0, "E"]]:
		editor.commands.register("Track", "Rotate preview " + entry[0], placement.rotate_by.bind(entry[1]), entry[2], {"id":"track.rotate_" + str(entry[0]).to_lower(), "context":"track", "enabled":func(): return placement.tool != "" and placement.kind == "piece", "reason":"Choose a road piece to preview first.", "icon":"rotate_" + str(entry[0]).to_lower()})
	for entry in [
		["apply_transform", "Apply transform and widths", apply_properties, "check", func(): return selected >= 0],
		["snap_connection", "Snap entry to target exit", snap_to_target, "snap", func(): return selected >= 0 and is_instance_valid(target) and target.item_count > 0],
		["connect_curve", "Connect exit to target entry", connect_curve, "connect", func(): return selected >= 0 and is_instance_valid(target) and target.item_count > 0],
		["route_add", "Append selected piece", _route_add, "plus", func(): return selected >= 0],
		["route_remove", "Remove route item", _route_remove, "minus", func(): return _route_can_move(0)],
		["route_up", "Move route item up", _route_move.bind(-1), "up", func(): return _route_can_move(-1)],
		["route_down", "Move route item down", _route_move.bind(1), "down", func(): return _route_can_move(1)],
		["checkpoint_start", "Set start checkpoint", checkpoint.bind(true), "flag", func(): return selected >= 0],
		["checkpoint_append", "Add finish / common checkpoint", checkpoint.bind(false), "flag", func(): return selected >= 0],
		["route_new", "Add alternative route", _route_new, "plus", func(): return true],
		["shortcut_example", "Zigzag + jump shortcut", _shortcut_example, "route", func(): return true]]:
		editor.commands.register("Track", entry[1], entry[2], "", {"id":"track." + entry[0], "icon":entry[3], "context":"track", "enabled":entry[4], "reason":"Select an eligible piece, connection target or route item first."})
	palette = VBoxContainer.new()
	palette.size_flags_vertical = Control.SIZE_EXPAND_FILL
	editor.left_dock.add_child(palette)
	palette_tools = preload("./workbench_palette.gd").new()
	palette_tools.size_flags_vertical = Control.SIZE_EXPAND_FILL
	palette_tools.size_flags_stretch_ratio = 3.0
	palette.add_child(palette_tools)
	palette_tools.build(editor.commands, "track", entries)
	var actions := HBoxContainer.new()
	palette.add_child(actions)
	STYLE.outline(actions)
	editor.commands.button(actions, "tool.select")
	editor.commands.button(actions, "view.frame")
	editor.commands.button(actions, "edit.duplicate")
	editor.commands.button(actions, "edit.delete")
	_button(actions, "Zigzag + jump shortcut", _shortcut_example)
	selection = ItemList.new()
	selection.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	selection.custom_minimum_size.y = 60
	selection.size_flags_vertical = Control.SIZE_EXPAND_FILL
	selection.size_flags_stretch_ratio = 0.6
	palette.add_child(selection)
	selection.item_selected.connect(select_piece)
	road_tools.build(palette)
	snap = CheckButton.new()
	snap.text = I18N.t("Port snap")
	snap.tooltip_text = I18N.t("Snap entry to a nearby exit within 3 m · S")
	snap.button_pressed = true
	snap.toggled.connect(func(_on: bool): placement.invalidate_candidate())
	palette.add_child(snap)
	STYLE.outline(snap)
	properties = VBoxContainer.new()
	properties.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor.properties.get_parent().add_child(properties)
	report = editor.validation_label
	report.max_lines_visible = 2

static func piece_name(id: String) -> String:
	return {"gentle90":"Gentle 90°", "gentle45":"Gentle 45°", "gentle90_left":"Gentle 90° left", "gentle45_left":"Gentle 45° left", "hairpin":"Hairpin", "slope_up":"Slope Up"}.get(id, id.replace("_", " ").capitalize())

func show_hint() -> void:
	if not active: return
	if placement.tool != "":
		editor.tool_hint.text = I18N.t(piece_name(placement.tool)) + " · " + I18N.display(placement.hint)
		editor.tool_hint.text += I18N.t(" · Cancel: ") + editor.commands.shortcut_text("edit.cancel_interaction")
	else:
		editor.tool_hint.text = I18N.t("Select · Click a piece; drag to move · Choose a palette tool to preview · Right drag orbits · Wheel zooms")
	editor.tool_hint.tooltip_text = editor.tool_hint.text

func select_piece(index: int) -> void:
	cancel_interaction(false)
	selection_serial += 1
	interaction_serial += 1
	selected = index
	road_tools.selected = ""
	road_tools.clear_guides()
	if selected >= 0: selection.select(selected)
	else: selection.deselect_all()
	_properties()
	PREVIEW.select(view, selected)
	editor.commands.refresh_buttons()

func cancel_interaction(rebuild_properties := true) -> void:
	if rebuild_properties: interaction_serial += 1
	var had_preview: bool = placement != null and placement.tool != "" and placement.moving_index < 0
	if placement != null: placement.cancel()
	if palette_tools != null: palette_tools.select_tool("")
	if rebuild_properties and had_preview and is_instance_valid(properties) and not source.is_empty(): _properties()
	show_hint()

func refresh() -> void:
	if updating: return
	active=editor.tool_workspace == "track"
	editor.canvas.navigation_only = active
	palette.visible=active
	properties.visible=active
	report.visible=true
	editor.author_panel.visible=not active
	editor.full_generation.visible=not active
	editor.regional_grouping.visible=not active
	editor.preview_dock.get_child(0).visible=not active or not editor.store.document.get("heightmaps",[]).is_empty()
	if active:
		editor.selection_label.text=I18N.t("ROADS & TRACKS · 3D + navigation plan")
		show_hint()
		editor.status_label.text=I18N.t("Choose a piece to preview, or generate a Seed Track.") if source.get("instances",[]).is_empty() else I18N.t("Draft can be saved · Free roam needs safe geometry; races also need a valid course.")
	for child in editor.left_dock.get_children():
		if child!=palette and child!=editor.workspace_tabs: child.visible=not active
	editor.properties.visible=not active
	editor.apply_button.visible=not active
	if not active:
		road_tools.refresh()
		if editor.author_panel.tabs.get_tab_count() == 0: editor.author_panel.open()
		if editor.store.document.has("assembled_track") or not editor.store.document.get("roads",[]).is_empty(): _draw()
		elif is_instance_valid(view): view.queue_free()
		return
	var selected_id: String = str(source.instances[selected].id) if selected >= 0 and selected < source.get("instances", []).size() else ""
	source=editor.store.track_source()
	road_tools.refresh()
	if apply_context.get("selection_serial", -1) != selection_serial and selected_id != "":
		selected = -1
		for i in source.instances.size():
			if source.instances[i].id == selected_id: selected = i; break
	var route_item: int = int(apply_context.get("route_item", -1))
	if not apply_context.is_empty():
		if apply_context.get("selection_serial", -1) == selection_serial:
			selected = int(apply_context.get("selected", selected))
			if apply_context.has("repeat") and apply_context.get("interaction_serial", -1) == interaction_serial: placement.resume_tool(apply_context.repeat)
		apply_context = {}
	selection.clear()
	for i: Dictionary in source.instances: selection.add_item(i.id+" · "+I18N.t(piece_name(i.preset)))
	selected=mini(selected,source.instances.size()-1)
	if selected>=0: selection.select(selected)
	_properties()
	if route_item >= 0 and route_item < route_list.item_count: route_list.select(route_item)
	var a: Dictionary=editor.store.document.get("assembled_track",{})
	var issues: Array=[] if editor.store.draft_pending() else a.get("issues",[])
	report.text=I18N.t("Connections & courses: ")+(I18N.t("Geometry ready · Manual courses need player completion") if issues.is_empty() and not a.is_empty() else " / ".join(issues.map(func(issue): return I18N.diagnostic(str(issue)))))
	if editor.store.draft_pending(): report.text = I18N.t("Draft geometry · Connections and supports are being prepared.")
	_draw()

func _button(parent: Node, text: String, callback: Callable) -> Button:
	for command: Dictionary in editor.commands.commands:
		if command.action == callback: return editor.commands.button(parent, command.id)
	return STYLE.button(parent, text, callback)

func _spin(parent: Node, label: String, value: float, low := -100000.0, high := 100000.0, step := 0.01) -> SpinBox:
	var s:=SpinBox.new()
	s.prefix=I18N.t(label)+" "
	s.min_value=low
	s.max_value=high
	s.step=step
	s.value=value
	parent.add_child(s)
	return s

func _section(title: String) -> VBoxContainer:
	var header := Button.new()
	header.text = ("▼ " if section_open[title] else "▶ ") + I18N.t(title)
	header.set_meta("action_label", title)
	header.custom_minimum_size.y = 40
	header.alignment = HORIZONTAL_ALIGNMENT_LEFT
	properties.add_child(header)
	var content := VBoxContainer.new()
	content.visible = section_open[title]
	properties.add_child(content)
	STYLE.outline(content)
	header.pressed.connect(func():
		section_open[title] = not section_open[title]
		content.visible = section_open[title]
		header.text = ("▼ " if section_open[title] else "▶ ") + I18N.t(title))
	return content

func _selected_button(parent: Node, label: String, callback: Callable, enabled := true, reason := "Select a track piece first.") -> Button:
	var button := _button(parent, label, callback)
	button.disabled = selected < 0 or not enabled
	if button.disabled: button.tooltip_text += "\n" + reason
	return button

func _properties() -> void:
	properties.set_meta("placement_tool", placement.tool)
	for child in properties.get_children(): child.queue_free(); properties.remove_child(child)
	controls.clear()
	port_widths.clear()
	if source.is_empty(): return
	if road_tools.selected != "":
		road_tools.properties(properties)
		if placement.tool != "" and placement.moving_index < 0: placement.build_controls(properties)
		return
	var policy := CheckButton.new()
	policy.text = I18N.t("Free roam map")
	policy.button_pressed = editor.store.document.get("free_roam",false)
	properties.add_child(policy)
	policy.toggled.connect(func(value: bool):
		cancel_interaction()
		var failure: String = editor.store.set_free_roam(value)
		if failure != "": editor._status(I18N.diagnostic(failure)))
	if placement.tool != "" and placement.moving_index < 0:
		placement.build_controls(properties)
	var transform := _section("Transform")
	var connections := _section("Connections")
	var routes_box := _section("Routes & Checkpoints")
	var actions_box := _section("Actions")
	var circuit := CheckButton.new()
	circuit.text = I18N.t("Circuit")
	circuit.button_pressed = source.settings.circuit
	routes_box.add_child(circuit)
	circuit.toggled.connect(func(value: bool): var next := source.duplicate(true); next.settings.circuit = value; _commit(next))
	var routes := OptionButton.new()
	for path: Dictionary in source.paths: routes.add_item(path.id)
	route_index = clampi(route_index, 0, maxi(0, source.paths.size() - 1))
	if routes.item_count > 0: routes.select(route_index)
	routes.item_selected.connect(func(index: int): route_index = index; _properties())
	routes_box.add_child(routes)
	var route_actions := HBoxContainer.new()
	routes_box.add_child(route_actions)
	_button(route_actions, "Add alternative route", _route_new)
	_selected_button(route_actions, "Append selected piece", _route_add)
	_button(route_actions, "Remove route item", _route_remove)
	STYLE.button(route_actions, "Move route item up", _route_move.bind(-1), "", "up")
	STYLE.button(route_actions, "Move route item down", _route_move.bind(1), "", "down")
	route_list = ItemList.new()
	route_list.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	route_list.custom_minimum_size.y = 96
	routes_box.add_child(route_list)
	if not source.paths.is_empty():
		for id: String in source.paths[route_index].pieces: route_list.add_item(id)
	var sync_route := func():
		var chosen := route_list.get_selected_items()
		var at := -1 if chosen.is_empty() else chosen[0]
		for j in range(2, 5):
			var button: Button = route_actions.get_child(j)
			button.disabled = at < 0 or (j == 3 and at == 0) or (j == 4 and at == route_list.item_count - 1)
			if button.disabled: button.tooltip_text = str(button.get_meta("action_label")) + I18N.t("\nSelect an eligible route list item.")
	route_list.item_selected.connect(func(_i: int): sync_route.call(); editor.commands.refresh_buttons())
	sync_route.call()
	for n in source.checkpoints.size():
		var cp: Dictionary = source.checkpoints[n]
		var row := HBoxContainer.new()
		routes_box.add_child(row)
		editor._label(row, I18N.t("CP %d · %s / %d") % [n, cp.piece, int(cp.sample)])
		_button(row, "Delete checkpoint", func(): var next := source.duplicate(true); next.checkpoints.remove_at(n); _commit(next))
	for n in source.actions.size():
		var row := HBoxContainer.new()
		actions_box.add_child(row)
		var label: Label = editor._label(row, str(source.actions[n].id))
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		_button(row, "Delete action", func(): var next := source.duplicate(true); next.actions.remove_at(n); _commit(next))
		if source.actions[n].kind in ["jump_panel", "acceleration_panel", "boost_chain"]:
			panel_controls(actions_box, int(source.actions[n].panel_width_percent), str(source.actions[n].panel_alignment), func(width: int, alignment: String): set_panel_layout(n, width, alignment))
	if selected < 0:
		for section in [transform, connections, actions_box]: editor._label(section, "Select a piece to edit its properties.")
		return
	var item: Dictionary = source.instances[selected]
	road_tools.terrain_policy_control(transform, str(source.get("terrain_policies",{}).get(item.id,"auto_fit" if item.preset in ["straight","gentle45","gentle90","gentle45_left","gentle90_left","free_curve","slope_up","slope_down"] else "preserve")), func(value: String): var next := source.duplicate(true); next.get_or_add("terrain_policies",{})[item.id]=value; _commit(next))
	for j in 3: controls.append(_spin(transform, ["X (m)", "Height (m)", "Z (m)"][j], float(item.position_cm[j]) / 100.0))
	for j in 3: controls.append(_spin(transform, ["Pitch X°", "Yaw Y°", "Roll Z°"][j], float(item.rotation_mdeg[j]) / 1000.0, -360.0, 360.0, 0.1))
	width = OptionButton.new()
	var minimum_port := 2.0
	for entry: Dictionary in catalogue.entries:
		if entry.id != item.preset: continue
		minimum_port = float(entry.min_port_width_cm) / 100.0
		for w in entry.widths_cm:
			width.add_item(I18N.t("Width %dm") % (float(w) / 100.0), int(w))
			if int(w) == int(item.width_cm): width.select(width.item_count - 1)
	transform.add_child(width)
	port_widths.append(_spin(transform, "Entry width (m)", float(item.entry_width_cm) / 100.0, minimum_port, 12.0))
	port_widths.append(_spin(transform, "Exit width (m)", float(item.exit_width_cm) / 100.0, minimum_port, 12.0))
	_button(transform, "Apply transform and widths", apply_properties)
	if item.preset in ["free_curve", "flight_curve"]:
		for n in item.control_points.size():
			for j in 3: controls.append(_spin(transform, I18N.t("Point %d %s") % [n, ["X", "Y", "Z"][j]], float(item.control_points[n][j]) / 100.0))
		_button(transform, "Apply curve points", apply_properties)
	target = OptionButton.new()
	target.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	for i in source.instances.size():
		if i != selected: target.add_item(source.instances[i].id, i)
	connections.add_child(target)
	var road_ports: Array=road_tools.ports()
	if not road_ports.is_empty():
		var road_target:=OptionButton.new()
		for port: Dictionary in road_ports:road_target.add_item(str(port.road)+I18N.t(" · start" if port.start else " · end"))
		connections.add_child(road_target)
		_button(connections,"Snap entry to road port",func():road_tools.connect_track(road_ports[road_target.selected],false))
		_button(connections,"Connect curve from road port",func():road_tools.connect_track(road_ports[road_target.selected],true))
	for link: Dictionary in source.get("road_connections",[]):
		if link.instance==item.id:
			editor._label(connections,I18N.t("Road port · ")+str(link.road))
			_button(connections,"Detach road port",func():var next:=source.duplicate(true);next.road_connections=next.road_connections.filter(func(c):return c.instance!=item.id);_commit(next))
	_selected_button(connections, "Snap entry to target exit", snap_to_target, target.item_count > 0, I18N.t("Add another piece to connect."))
	_selected_button(connections, "Connect exit to target entry", connect_curve, target.item_count > 0, I18N.t("Add another piece to connect."))
	var piece: Dictionary = editor.store.track_pieces()[selected]
	sample_input = _spin(routes_box, "Path sample", 0, 0, maxi(0, piece.path.size() - 1), 1)
	var cp_actions := HBoxContainer.new()
	routes_box.add_child(cp_actions)
	_button(cp_actions, "Set start checkpoint", checkpoint.bind(true))
	_button(cp_actions, "Add finish / common checkpoint", checkpoint.bind(false))
	action_height = _spin(actions_box, "Jump height (m)", 2.0, 0.5, 10.0, 0.1)
	landing_target = OptionButton.new()
	landing_target.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	landing_target.add_item(I18N.t("Continuous road jump"), -2)
	for i in source.instances.size(): landing_target.add_item(I18N.t("Landing · ") + source.instances[i].id, i)
	actions_box.add_child(landing_target)
	landing_sample = _spin(actions_box, "Landing sample", 0, 0, 1024, 1)
	var action_row := HBoxContainer.new()
	actions_box.add_child(action_row)
	for kind: String in ["jump_panel", "acceleration_panel", "boost_chain", "air_ring"]:
		editor.commands.button(action_row, "track.action." + kind)

func panel_controls(parent: Node, width: int, alignment: String, changed: Callable) -> void:
	var row := HBoxContainer.new()
	parent.add_child(row)
	var widths := OptionButton.new()
	widths.tooltip_text = I18N.t("Panel width")
	for value: int in [25,50,75,100]:
		widths.add_item(str(value) + "%", value)
		if value == width: widths.select(widths.item_count-1)
	row.add_child(widths)
	var alignments := OptionButton.new()
	alignments.tooltip_text = I18N.t("Panel alignment")
	var values := ["left", "center", "right"]
	for value: String in values:
		alignments.add_item(I18N.t(value.capitalize()))
		if value == alignment: alignments.select(alignments.item_count-1)
	row.add_child(alignments)
	widths.item_selected.connect(func(_i: int): changed.call(widths.get_selected_id(), values[alignments.selected]))
	alignments.item_selected.connect(func(_i: int): changed.call(widths.get_selected_id(), values[alignments.selected]))

func set_panel_layout(index: int, width: int, alignment: String) -> bool:
	if index < 0 or index >= source.actions.size() or width not in [25,50,75,100] or alignment not in ["left","center","right"]: return false
	var next := source.duplicate(true)
	next.actions[index].panel_width_percent = width
	next.actions[index].panel_alignment = alignment
	return _commit(next)

func _shortcut_example() -> void:
	cancel_interaction()
	var result: Dictionary = JSON.parse_string(editor.store.bridge.track_shortcut_source())
	_commit(result.data)

func _route_new() -> void:
	var next := source.duplicate(true)
	next.paths.append({"id":"Alternative %d" % next.paths.size(), "pieces":[]})
	route_index = next.paths.size() - 1
	_commit(next)

func _route_can_move(delta: int) -> bool:
	if not is_instance_valid(route_list): return false
	var chosen := route_list.get_selected_items()
	return not chosen.is_empty() and chosen[0] + delta >= 0 and chosen[0] + delta < route_list.item_count

func _route_add() -> void:
	if selected < 0: return
	var next := source.duplicate(true)
	if next.paths.is_empty(): next.paths = [{"id":"base", "pieces":[]}]
	var id: String = next.instances[selected].id
	if not next.paths[route_index].pieces.has(id): next.paths[route_index].pieces.append(id)
	_commit(next)

func _route_remove() -> void:
	var chosen := route_list.get_selected_items()
	if chosen.is_empty(): return
	var next := source.duplicate(true)
	next.paths[route_index].pieces.remove_at(chosen[0])
	_commit(next)

func _route_move(delta: int) -> void:
	var chosen := route_list.get_selected_items()
	if chosen.is_empty(): return
	var at: int = chosen[0]
	var next := source.duplicate(true)
	var path: Array = next.paths[route_index].pieces
	if at + delta < 0 or at + delta >= path.size(): return
	var id: String = path[at]
	path.remove_at(at)
	path.insert(at + delta, id)
	_commit(next, -2, {"route_item":at + delta})

func _commit(next: Dictionary, next_selection := -2, extra: Dictionary = {}) -> bool:
	if editor.busy or editor.store.editing_locked(): editor._status(I18N.t("Wait for the current operation.")); return false
	var context := {"selection_serial":selection_serial, "interaction_serial":interaction_serial, "selected":selected if next_selection == -2 else next_selection}
	context.merge(extra)
	placement.cancel()
	var failure: String = editor.store.start_track_edit(next, editor.store.command_epoch, context)
	if failure != "": editor._status(I18N.diagnostic(failure)); return false
	editor._status(I18N.t("Draft updated · Continue editing while changes are applied."))
	editor.commands.refresh_buttons()
	return true

func add_piece(preset: String) -> void:
	placement.activate("piece", preset)

func apply_properties() -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var item: Dictionary=next.instances[selected]
	for j in 3: item.position_cm[j]=roundi(controls[j].value*100.0)
	for j in 3: item.rotation_mdeg[j]=roundi(controls[j+3].value*1000.0)
	item.width_cm=width.get_selected_id()
	item.entry_width_cm=roundi(port_widths[0].value*100.0)
	item.exit_width_cm=roundi(port_widths[1].value*100.0)
	for n in item.control_points.size():
		for j in 3: item.control_points[n][j]=roundi(controls[6+n*3+j].value*100.0)
	_commit(next)

func duplicate_piece() -> void:
	if road_tools.selected != "": road_tools.duplicate_road(); return
	if selected<0: return
	var next:=source.duplicate(true)
	var item: Dictionary=next.instances[selected].duplicate(true)
	item.id="p-"+Crypto.new().generate_random_bytes(4).hex_encode()
	item.position_cm[0]+=int(item.width_cm)+200
	next.instances.append(item)
	_commit(next, next.instances.size()-1)

func delete_piece() -> void:
	if road_tools.selected != "": road_tools.delete_road(); return
	if selected<0: return
	var next:=source.duplicate(true)
	var id: String=next.instances[selected].id
	next.instances.remove_at(selected)
	next.get_or_add("terrain_policies",{}).erase(id)
	next.road_connections=next.get("road_connections",[]).filter(func(c):return c.instance!=id)
	next.connections=next.connections.filter(func(c): return c.from!=id and c.to!=id)
	next.checkpoints=next.checkpoints.filter(func(c): return c.piece!=id)
	next.attachments=next.attachments.filter(func(c): return c.piece!=id)
	next.actions=next.actions.filter(func(c): return c.piece!=id and (c.landing==null or c.landing.piece!=id))
	for path: Dictionary in next.paths: path.pieces.erase(id)
	_commit(next, -1)

func snap_to_target() -> void:
	if selected<0 or target.item_count==0: return
	var next:=source.duplicate(true)
	var other: Dictionary=next.instances[target.get_selected_id()]
	var result: Dictionary=JSON.parse_string(editor.store.bridge.snap_track_instance(JSON.stringify(next.instances[selected]),JSON.stringify(other)))
	if not result.ok: editor._status(I18N.error(result.error)); return
	next.instances[selected]=result.data
	next.connections.append({"from":other.id,"to":result.data.id})
	_commit(next)

func connect_curve() -> void:
	if selected<0 or target.item_count==0: return
	var next:=source.duplicate(true)
	var other:=target.get_selected_id()
	var pieces: Array = editor.store.track_pieces()
	if pieces[selected].path.is_empty() or pieces[other].path.is_empty(): return
	var a: Dictionary=pieces[selected].path.back()
	var b: Dictionary=pieces[other].path[0]
	var reach:=maxf(400.0,PREVIEW.point(a.position_cm).distance_to(PREVIEW.point(b.position_cm))*50.0)
	var p1: Array=[]
	var p2: Array=[]
	for j in 3:
		p1.append(roundi(float(a.position_cm[j])+float(a.forward[j])*reach/1000000.0))
		p2.append(roundi(float(b.position_cm[j])-float(b.forward[j])*reach/1000000.0))
	var id: String="c-"+Crypto.new().generate_random_bytes(4).hex_encode()
	next.instances.append({"id":id,"preset":"free_curve","position_cm":[0,0,0],"rotation_mdeg":[0,0,0],"width_cm":400,"entry_width_cm":int(a.lateral_cm)*2,"exit_width_cm":int(b.lateral_cm)*2,"control_points":[a.position_cm,p1,p2,b.position_cm]})
	next.connections=next.connections.filter(func(c): return not (c.from==next.instances[selected].id and c.to==next.instances[other].id))
	next.connections.append({"from":next.instances[selected].id,"to":id})
	next.connections.append({"from":id,"to":next.instances[other].id})
	if not next.paths.is_empty():
		var path: Array=next.paths[route_index].pieces
		var at:=path.find(next.instances[selected].id)
		path.insert(at+1,id)
		if not path.has(next.instances[other].id): path.insert(at+2,next.instances[other].id)
	_commit(next, next.instances.size()-1)

func checkpoint(start: bool) -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var cp: Dictionary={"piece":next.instances[selected].id,"sample":int(sample_input.value)}
	var pieces:Array=editor.store.track_pieces()
	var checkpoints:Array=[]
	for existing:Dictionary in source.checkpoints:
		var index:int=source.instances.find(source.instances.filter(func(item):return item.id==existing.piece)[0])
		var gate:Dictionary=JSON.parse_string(editor.store.bridge.track_checkpoint(JSON.stringify(pieces[index].path[int(existing.sample)])))
		if not gate.ok:return
		checkpoints.append(gate.data)
	var gate:Dictionary=JSON.parse_string(editor.store.bridge.track_checkpoint(JSON.stringify(pieces[selected].path[int(sample_input.value)])))
	if not gate.ok:return
	var allowed:Dictionary=JSON.parse_string(editor.store.bridge.checkpoint_edit_allowed(JSON.stringify(checkpoints),JSON.stringify(gate.data),0 if start and not checkpoints.is_empty() else -1))
	if not allowed.ok or not allowed.data:
		report.text=I18N.t("Checkpoint overlaps an existing checkpoint; change rejected.")
		return
	if start:
		if next.checkpoints.is_empty(): next.checkpoints.append(cp)
		else: next.checkpoints[0]=cp
	else: next.checkpoints.append(cp)
	_commit(next)

func add_action(kind: String) -> void:
	placement.activate("action", kind)

func _process(_delta: float) -> void:
	if road_tools != null: road_tools.poll()
	if not final_preview_due or editor.store.draft_pending(): return
	var focus := editor.get_viewport().gui_get_focus_owner()
	if placement.moving_index >= 0 or focus is LineEdit or focus is TextEdit or editor.store.has_gesture(): return
	final_preview_due = false
	drawn_epoch = -1
	_draw()
	var issues: Array = editor.store.document.get("assembled_track", {}).get("issues", [])
	report.text = I18N.t("Geometry ready · Manual courses need player completion") if issues.is_empty() else " / ".join(issues.map(func(issue): return I18N.diagnostic(str(issue))))

func _draw() -> void:
	if editor.store.draft_pending() and is_instance_valid(view):
		PREVIEW.apply_draft(view, source, editor.store.track_pieces(), display_document, selected)
		return
	if drawn_epoch == editor.store.command_epoch and is_instance_valid(view):
		PREVIEW.select(view, selected)
		return
	drawn_epoch = editor.store.command_epoch
	var a: Dictionary=editor.store.document.get("assembled_track",{})
	if a.is_empty() and editor.store.document.get("roads",[]).is_empty():
		if is_instance_valid(view): view.queue_free()
		view = null
		display_document = {}
		return
	var prepared: Dictionary = editor.store.prepared_track_preview
	if prepared.is_empty():
		PREVIEW.preparations += 1
		prepared = PREVIEW.prepare(editor.store.document, editor.store.bridge, editor.store.track_preview_cache)
	display_document = editor.store.document.duplicate(true)
	editor.store.track_preview_cache = prepared
	editor.store.prepared_track_preview = {}
	if is_instance_valid(view):
		PREVIEW.apply(view, prepared, selected)
		return
	view = Node3D.new()
	PREVIEW.apply(view, prepared, selected)
	# View-only grid supplies orientation for an empty draft; it is not map geometry.
	var mesh:=ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	mesh.surface_set_color(Color("35434a"))
	for station in range(-50,51,5):
		mesh.surface_add_vertex(Vector3(station,-0.05,-50)); mesh.surface_add_vertex(Vector3(station,-0.05,50))
		mesh.surface_add_vertex(Vector3(-50,-0.05,station)); mesh.surface_add_vertex(Vector3(50,-0.05,station))
	mesh.surface_end()
	var grid:=MeshInstance3D.new()
	var assembly: Dictionary=editor.store.document.assembled_track if editor.store.document.get("assembled_track") is Dictionary else {}
	grid.visible=not (assembly.get("authoring") is Dictionary and assembly.authoring.get("terrain_integration",false)) and editor.store.document.get("roads",[]).is_empty()
	grid.mesh=mesh
	var material:=StandardMaterial3D.new()
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo=true
	grid.material_override=material
	view.add_child(grid)
	editor.preview_world.add_child(view)
	if editor.preview_camera.camera.position==Vector3.ZERO: editor.preview_camera.frame(Vector3.ZERO,80.0)

func input(event: InputEvent) -> bool:
	if not active or editor.store.editing_locked() or editor.busy or editor._popup_open(editor): return false
	if placement.tool != "": return placement.input(event)
	var camera: Camera3D = editor.preview_camera.camera
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var nearest := 18.0
		var index := -1
		var pieces: Array = editor.store.track_pieces()
		for i in pieces.size():
			for p: Dictionary in pieces[i].path:
				var point := PREVIEW.point(p.position_cm)
				if camera.is_position_behind(point): continue
				var d := camera.unproject_position(point).distance_to(event.position)
				if d < nearest: nearest = d; index = i
		var road_hit: Dictionary=road_tools.raycast(event.position,true)
		if road_hit.get("road","")!="" and index<0:
			road_tools.select(road_hit.road);return true
		select_piece(index)
		if selected >= 0 and not editor.store.editing_locked() and not editor.busy:
			var start: Variant = _plane_point(event.position, float(source.instances[selected].position_cm[1])*0.01)
			if start != null: placement.begin_move(selected, start)
		return true
	return false

func _plane_point(point: Vector2, height: float) -> Variant:
	var camera: Camera3D=editor.preview_camera.camera
	return Plane(Vector3.UP,height).intersects_ray(camera.project_ray_origin(point),camera.project_ray_normal(point))

func add_obstacle(kind: String) -> void:
	placement.activate("obstacle", kind)

func frame_selection() -> void:
	if road_tools.selected != "" and road_tools.paths.has(road_tools.selected):
		var point: Vector3=PREVIEW.point(road_tools.design.control_points[road_tools.point_index])
		editor.preview_camera.frame(point,48);road_tools.focus_point(point);return
	if selected<0:
		if not road_tools.paths.is_empty():road_tools.select(road_tools.paths.keys()[0])
		else:editor.preview_camera.frame(Vector3.ZERO,80.0)
		return
	var piece: Dictionary=editor.store.track_pieces()[selected]
	var center:=Vector3.ZERO
	for point: Dictionary in piece.path: center+=PREVIEW.point(point.position_cm)
	if piece.path.is_empty(): return
	center/=piece.path.size()
	var radius:=8.0
	for point: Dictionary in piece.path: radius=maxf(radius,center.distance_to(PREVIEW.point(point.position_cm))*2.0)
	editor.preview_camera.frame(center,radius)

func open_grind_lines() -> void:
	cancel_interaction()
	var panel := preload("./grind_line_panel.gd").new()
	add_child(panel)
	panel.open(self)

func _exit_tree() -> void:
	if road_tools != null: road_tools.shutdown()
