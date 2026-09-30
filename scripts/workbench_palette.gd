extends VBoxContainer
## Stable favorite IDs are independent of palette filtering and sorting.
const STYLE := preload("./workbench_style.gd")
var registry: PopupPanel
var mode := "roam"
var entries: Array[Dictionary] = []
var favorites_row: HBoxContainer
var search: LineEdit
var tabs: TabContainer
var tiles: Array[Dictionary] = []
var popup: PopupMenu
var assigning := ""

func build(commands: PopupPanel, context: String, items: Array[Dictionary]) -> void:
	STYLE.outline(self)
	registry = commands
	mode = context
	entries = items
	var favorite_title := Label.new()
	favorite_title.text = "FAVORITES · 1–9"
	favorite_title.add_theme_color_override("font_color", STYLE.BLUE)
	add_child(favorite_title)
	var favorites_scroll := ScrollContainer.new()
	favorites_scroll.custom_minimum_size.y = 64
	favorites_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(favorites_scroll)
	STYLE.outline(favorites_scroll)
	favorites_row = HBoxContainer.new()
	favorites_scroll.add_child(favorites_row)
	var row := HBoxContainer.new()
	add_child(row)
	search = LineEdit.new()
	search.placeholder_text = "Search palette"
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(search)
	search.text_changed.connect(_filter)
	var sort_button := CheckButton.new()
	sort_button.text = "A–Z"
	sort_button.tooltip_text = "Sort palette by name. Favorite slot numbers stay fixed."
	row.add_child(sort_button)
	sort_button.toggled.connect(func(value: bool): _build_tiles(value))
	tabs = TabContainer.new()
	tabs.custom_minimum_size.y = 108
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(tabs)
	popup = PopupMenu.new()
	add_child(popup)
	for i in 9: popup.add_item("Assign to favorite %d" % (i + 1), i)
	popup.id_pressed.connect(func(slot: int):
		var failure: String = registry.assign_favorite(mode, slot, assigning)
		if failure != "": registry.get_parent()._status(failure))
	registry.settings_changed.connect(refresh_favorites)
	_build_tiles(false)
	refresh_favorites()

func _build_tiles(alphabetical: bool) -> void:
	for child in tabs.get_children(): tabs.remove_child(child); child.queue_free()
	tiles.clear()
	var ordered := entries.duplicate()
	if alphabetical: ordered.sort_custom(func(a, b): return registry.commands[registry.index_of(a.id)].label.naturalnocasecmp_to(registry.commands[registry.index_of(b.id)].label) < 0)
	var groups := {}
	var sections := {}
	for entry in ordered:
		if not groups.has(entry.group):
			var scroll := ScrollContainer.new()
			scroll.name = entry.group
			scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
			tabs.add_child(scroll)
			var column := VBoxContainer.new()
			column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			scroll.add_child(column)
			groups[entry.group] = column
		var section: String = entry.group + "/" + entry.get("section", "Tools")
		if not sections.has(section):
			var label := Label.new()
			label.text = entry.get("section", "Tools")
			groups[entry.group].add_child(label)
			var flow := HFlowContainer.new()
			groups[entry.group].add_child(flow)
			sections[section] = flow
		var b: Button = registry.button(sections[section], entry.id, true)
		b.toggle_mode = true
		_context(b, entry.id)
		var badge := _badge(b, "")
		tiles.append({"button":b, "badge":badge, "id":entry.id})
	var group_order: Array = ["Driving", "Gimmick", "Action"] if mode == "track" else ["Free roam"]
	for i in group_order.size():
		if groups.has(group_order[i]): tabs.move_child(groups[group_order[i]].get_parent(), i)
	tabs.current_tab = 0
	_filter(search.text)
	if is_instance_valid(favorites_row): refresh_favorites()

func _context(button: Button, id: String) -> void:
	button.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
			registry.opening_popup.emit()
			assigning = id
			popup.position = Vector2i(get_global_mouse_position())
			popup.popup()
			button.accept_event())

func _badge(button: Button, text: String) -> Label:
	var badge := Label.new()
	badge.text = text
	badge.add_theme_font_size_override("font_size", 10)
	badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	button.add_child(badge)
	badge.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	badge.offset_left = -48
	badge.offset_right = -2
	badge.offset_top = 0
	badge.offset_bottom = 15
	badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	badge.add_theme_color_override("font_color", STYLE.INK)
	return badge

func refresh_favorites() -> void:
	for child in favorites_row.get_children(): favorites_row.remove_child(child); child.queue_free()
	for i in 9:
		var id: String = registry.favorites.get(mode, registry.DEFAULT_FAVORITES[mode])[i]
		if registry.index_of(id) < 0: continue
		var b: Button = registry.button(favorites_row, id, true)
		_badge(b, str(i + 1))
		_context(b, id)
		b.tooltip_text += "\nFavorite %d" % (i + 1)
	for tile in tiles:
		var slots: PackedStringArray = []
		for i in 9:
			if registry.favorites[mode][i] == tile.id: slots.append(str(i + 1))
		tile.badge.text = ",".join(slots) if not slots.is_empty() else registry.shortcut_text(tile.id)

func select_tool(id: String) -> void:
	for tile in tiles: tile.button.set_pressed_no_signal(tile.id == id)

func _filter(value: String) -> void:
	for tile in tiles:
		var command: Dictionary = registry.commands[registry.index_of(tile.id)]
		tile.button.visible = value.is_empty() or value.to_lower() in (command.label + " " + command.id).to_lower()
