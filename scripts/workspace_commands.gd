extends PopupPanel
## All command surfaces resolve the same stable ID, context and availability.
signal settings_changed
signal opening_popup
const STYLE := preload("./workbench_style.gd")
var commands: Array[Dictionary] = []
var query: LineEdit
var results: ItemList
var context_source: Callable
var blocked_source: Callable
var availability_source: Callable
var bindings: Dictionary = {}
var favorites: Dictionary = {}
var buttons: Array[Dictionary] = []
var menus_by_group: Dictionary = {}
var settings_path := "user://workbench.cfg"
var settings_dialog: Window
const DEFAULT_FAVORITES := {
	"track": ["track.piece.straight", "track.piece.gentle90", "track.piece.hairpin", "track.piece.slope_up", "track.piece.free_curve", "track.piece.cylinder", "track.piece.loop", "track.piece.jump", "track.action.jump_panel"],
	"roam": ["tool.select", "tool.road", "tool.building", "tool.terrain", "tool.water", "tool.forest", "tool.place", "tool.repeat", "tool.surface_area"]
}

func _ready() -> void:
	favorites = DEFAULT_FAVORITES.duplicate(true)
	var column := VBoxContainer.new()
	add_child(column)
	query = LineEdit.new()
	query.placeholder_text = "Search commands · Enter to run · Escape to close"
	column.add_child(query)
	results = ItemList.new()
	results.custom_minimum_size = Vector2(560, 280)
	column.add_child(results)
	query.text_changed.connect(_filter)
	query.text_submitted.connect(func(_text: String):
		var selected := results.get_selected_items()
		if not selected.is_empty(): _run(selected[0]))
	query.gui_input.connect(func(event: InputEvent):
		if event is InputEventKey and event.pressed and event.keycode in [KEY_UP, KEY_DOWN]:
			if results.item_count > 0:
				var selected := results.get_selected_items()
				var index := selected[0] if not selected.is_empty() else 0
				results.select(clampi(index + (1 if event.keycode == KEY_DOWN else -1), 0, results.item_count - 1))
				results.ensure_current_is_visible()
			query.accept_event())
	results.item_activated.connect(_run)

static func key(value: String) -> int:
	var code := 0
	for part: String in value.replace("Ctrl/Cmd", "Primary").split("+"):
		match part:
			"Primary": code |= KEY_MASK_META if OS.get_name() == "macOS" else KEY_MASK_CTRL
			"Ctrl": code |= KEY_MASK_CTRL
			"Cmd", "Meta": code |= KEY_MASK_META
			"Shift": code |= KEY_MASK_SHIFT
			"Alt": code |= KEY_MASK_ALT
			_: code |= OS.find_keycode_from_string(part)
	return code

static func event_key(event: InputEventKey) -> int:
	var code := int(event.physical_keycode if event.physical_keycode != 0 else event.keycode)
	if event.ctrl_pressed: code |= KEY_MASK_CTRL
	if event.meta_pressed: code |= KEY_MASK_META
	if event.shift_pressed: code |= KEY_MASK_SHIFT
	if event.alt_pressed: code |= KEY_MASK_ALT
	return code

static func key_text(code: int) -> String:
	return OS.get_keycode_string(code).replace("Meta", "Cmd")

func register(group: String, label: String, action: Callable, shortcut := "", options: Dictionary = {}) -> String:
	var id: String = options.get("id", group.to_lower() + "." + label.to_snake_case().replace("…", ""))
	assert(index_of(id) < 0, "Duplicate command ID: " + id)
	var defaults: Array = []
	if shortcut != "": defaults.append(key(shortcut))
	for extra: String in options.get("keys", []): defaults.append(key(extra))
	commands.append({"id":id, "group":group, "label":label, "action":action,
		"description":options.get("description", label), "icon":options.get("icon", STYLE.icon_name(label)),
		"context":options.get("context", "global"), "enabled":options.get("enabled", Callable()),
		"reason":options.get("reason", "This command is unavailable in the current state."),
		"defaults":defaults, "shortcut":shortcut, "menu":options.get("menu", true)})
	return id

func index_of(id: String) -> int:
	for i in commands.size():
		if commands[i].id == id: return i
	return -1

func current_context() -> String:
	return context_source.call() if context_source.is_valid() else "roam"

func reason(id: String) -> String:
	if availability_source.is_valid():
		var unavailable: String = availability_source.call(id)
		if unavailable != "": return unavailable
	var index := index_of(id)
	if index < 0: return "Command is unavailable."
	var command := commands[index]
	if command.context != "global" and command.context != current_context():
		return "Available in %s mode." % ("track" if command.context == "track" else "free roam")
	if command.enabled.is_valid() and not command.enabled.call(): return command.reason
	return ""

func keys_for(id: String, custom: Variant = null) -> Array:
	if custom == null: custom = bindings
	var index := index_of(id)
	return custom.get(id, commands[index].defaults) if index >= 0 else []

func shortcut_text(id: String) -> String:
	var labels: PackedStringArray = []
	for code in keys_for(id): labels.append(key_text(int(code)))
	return " / ".join(labels)

func tooltip(id: String) -> String:
	var command := commands[index_of(id)]
	var result: String = command.label + "\n" + command.description
	var shortcut := shortcut_text(id)
	if shortcut != "": result += "\n" + shortcut
	var why := reason(id)
	if why != "": result += "\n" + why
	return result

func button(parent: Node, id: String, tile := false) -> Button:
	var command := commands[index_of(id)]
	var result := STYLE.button(parent, command.label, execute_id.bind(id), "", command.icon, tile)
	result.set_meta("command_id", id)
	buttons.append({"control":weakref(result), "id":id})
	# Adding a control does not change command availability. Updating the entire
	# palette for every inspector button made one selection quadratic in controls.
	result.disabled = reason(id) != ""
	result.tooltip_text = tooltip(id)
	return result

func refresh_buttons() -> void:
	var alive: Array[Dictionary] = []
	for entry in buttons:
		var control: Button = entry.control.get_ref()
		if control == null or control.is_queued_for_deletion(): continue
		control.disabled = reason(entry.id) != ""
		control.tooltip_text = tooltip(entry.id)
		alive.append(entry)
	buttons = alive

func menus(parent: Control) -> void:
	for group in ["File", "Edit", "View", "Create", "Validate"]:
		var menu := MenuButton.new()
		menu.text = group
		menu.custom_minimum_size.y = 28
		parent.add_child(menu)
		var popup := menu.get_popup()
		menus_by_group[group] = popup
		popup.about_to_popup.connect(func(): opening_popup.emit(); _fill_menu(group))
		popup.id_pressed.connect(execute)

func _fill_menu(group: String) -> void:
	var popup: PopupMenu = menus_by_group[group]
	popup.clear()
	for i in commands.size():
		var command := commands[i]
		if command.group != group or not command.menu: continue
		var shortcut := shortcut_text(command.id)
		popup.add_icon_item(STYLE.icon(command.icon), command.label + ("    " + shortcut if shortcut != "" else ""), i)
		popup.set_item_disabled(popup.item_count - 1, reason(command.id) != "")
		popup.set_item_tooltip(popup.item_count - 1, tooltip(command.id))

func execute(index: int) -> bool:
	if index < 0 or index >= commands.size(): return false
	return execute_id(commands[index].id)

func execute_id(id: String) -> bool:
	if reason(id) != "": return false
	hide()
	commands[index_of(id)].action.call()
	refresh_buttons()
	return true

func handle_key(event: InputEventKey) -> bool:
	if not event.pressed or event.echo: return false
	if blocked_source.is_valid() and blocked_source.call(): return false
	var code := event_key(event)
	for command in commands:
		if code in keys_for(command.id) and reason(command.id) == "": return execute_id(command.id)
	return false

func conflicts(custom: Dictionary) -> PackedStringArray:
	var issues: PackedStringArray = []
	for i in commands.size():
		var a := commands[i]
		for j in range(i + 1, commands.size()):
			var b := commands[j]
			if a.context != b.context and a.context != "global" and b.context != "global": continue
			for code in keys_for(a.id, custom):
				if code in keys_for(b.id, custom): issues.append("%s: %s / %s" % [key_text(code), a.label, b.label])
	return issues

func save_bindings(custom: Dictionary) -> String:
	var issues := conflicts(custom)
	if not issues.is_empty(): return "Resolve shortcut conflicts before saving:\n" + "\n".join(issues)
	var old := bindings
	bindings = custom.duplicate(true)
	var failure := save_settings()
	if failure != "": bindings = old
	else: settings_changed.emit(); refresh_buttons()
	return failure

func save_settings() -> String:
	var config := ConfigFile.new()
	config.load(settings_path)
	config.set_value("commands", "bindings", bindings)
	config.set_value("commands", "favorites", favorites)
	var result := config.save(settings_path)
	return "" if result == OK else "Could not save workbench settings: " + error_string(result)

func load_settings() -> void:
	var config := ConfigFile.new()
	config.load(settings_path)
	var saved: Variant = config.get_value("commands", "bindings", {})
	bindings.clear()
	if saved is Dictionary:
		for id: String in saved:
			if index_of(id) < 0 or not saved[id] is Array: continue
			if saved[id].all(func(code): return code is int and code > 0): bindings[id] = saved[id].duplicate()
	if not conflicts(bindings).is_empty(): bindings.clear()
	favorites = DEFAULT_FAVORITES.duplicate(true)
	var slots: Variant = config.get_value("commands", "favorites", {})
	if slots is Dictionary:
		for mode: String in favorites:
			if not slots.get(mode) is Array or slots[mode].size() != 9: continue
			for i in 9:
				var id: String = str(slots[mode][i])
				if favorite_allowed(mode, id): favorites[mode][i] = id
	settings_changed.emit()
	refresh_buttons()

func favorite_allowed(mode: String, id: String) -> bool:
	var i := index_of(id)
	return i >= 0 and (commands[i].context == mode or id == "tool.select") and (id.begins_with("tool.") or id.begins_with("track.piece.") or id.begins_with("track.action.") or id.begins_with("track.obstacle."))

func assign_favorite(mode: String, slot: int, id: String) -> String:
	if slot < 0 or slot >= 9 or not favorite_allowed(mode, id): return "Invalid favorite assignment."
	var old: String = favorites[mode][slot]
	favorites[mode][slot] = id
	var failure := save_settings()
	if failure != "": favorites[mode][slot] = old
	else: settings_changed.emit()
	return failure

func run_favorite(slot: int) -> void:
	execute_id(favorites[current_context()][slot])

func open() -> void:
	opening_popup.emit()
	query.text = ""
	_filter("")
	popup_centered(Vector2i(580, 340))
	query.grab_focus()

func open_settings() -> void:
	opening_popup.emit()
	if not is_instance_valid(settings_dialog):
		settings_dialog = preload("./shortcut_settings.gd").new()
		settings_dialog.registry = self
		get_parent().add_child(settings_dialog)
	settings_dialog.open()

func _filter(value: String) -> void:
	results.clear()
	for index in commands.size():
		var command := commands[index]
		if command.context != "global" and command.context != current_context(): continue
		var label := "%s / %s  %s" % [command.group, command.label, shortcut_text(command.id)]
		if value.is_empty() or value.to_lower() in (label + " " + command.description + " " + command.id).to_lower():
			results.add_item(label, STYLE.icon(command.icon))
			results.set_item_metadata(results.item_count - 1, index)
			results.set_item_tooltip(results.item_count - 1, tooltip(command.id))
			results.set_item_disabled(results.item_count - 1, reason(command.id) != "")
	if results.item_count > 0: results.select(0)

func _run(index: int) -> void:
	if index >= 0 and index < results.item_count: execute(int(results.get_item_metadata(index)))
