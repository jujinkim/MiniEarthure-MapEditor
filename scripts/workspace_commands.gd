extends PopupPanel
## Menu and search share one command registry. No document state is kept here.
var commands: Array[Dictionary] = []
var query: LineEdit
var results: ItemList

func _ready() -> void:
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

func register(group: String, label: String, action: Callable, shortcut: String = "") -> void:
	commands.append({"group":group, "label":label, "action":action, "shortcut":shortcut})

func menus(parent: Control) -> void:
	for group in ["File", "Edit", "View", "Create", "Validate"]:
		var menu := MenuButton.new()
		menu.text = group
		parent.add_child(menu)
		var popup := menu.get_popup()
		for index in range(commands.size()):
			var command := commands[index]
			if command.group == group:
				popup.add_item(command.label + ("    " + command.shortcut if command.shortcut != "" else ""), index)
		popup.id_pressed.connect(execute)

func execute(index: int) -> void:
	if index < 0 or index >= commands.size(): return
	hide()
	commands[index].action.call()

func open() -> void:
	query.text = ""
	_filter("")
	popup_centered(Vector2i(580, 340))
	query.grab_focus()

func _filter(value: String) -> void:
	results.clear()
	for index in range(commands.size()):
		var command := commands[index]
		var label := "%s / %s  %s" % [command.group, command.label, command.shortcut]
		if value.to_lower() in label.to_lower():
			results.add_item(label)
			results.set_item_metadata(results.item_count - 1, index)
	if results.item_count > 0: results.select(0)

func _run(index: int) -> void:
	execute(int(results.get_item_metadata(index)))
