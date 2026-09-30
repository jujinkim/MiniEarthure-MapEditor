extends ConfirmationDialog
## Edits a private working copy; conflicts never reach persistent settings.
const STYLE := preload("./workbench_style.gd")
var registry: PopupPanel
var search: LineEdit
var list: ItemList
var feedback: Label
var pending: Dictionary = {}
var capturing := false
var selected_id := ""

func _ready() -> void:
	title = "Keyboard shortcuts"
	ok_button_text = "Save shortcuts"
	cancel_button_text = "Cancel"
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(680, 440)
	add_child(column)
	search = LineEdit.new()
	search.placeholder_text = "Search commands, keys or context"
	column.add_child(search)
	search.text_changed.connect(_filter)
	list = ItemList.new()
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.custom_minimum_size.y = 260
	column.add_child(list)
	list.item_selected.connect(func(i: int): selected_id = list.get_item_metadata(i); capturing = false)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	STYLE.button(actions, "Assign key", begin_capture, "Select a command, then press its new shortcut.", "keyboard")
	STYLE.button(actions, "Clear keys", func():
		if selected_id != "": pending[selected_id] = []; capturing = false; _filter(search.text), "", "delete")
	STYLE.button(actions, "Restore defaults", func(): pending.clear(); capturing = false; _filter(search.text), "Restore all default shortcuts.", "undo")
	feedback = Label.new()
	feedback.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	feedback.custom_minimum_size.y = 60
	column.add_child(feedback)
	confirmed.connect(func():
		var failure: String = registry.save_bindings(pending)
		if failure != "": feedback.text = failure; show())
	dialog_hide_on_ok = false
	confirmed.connect(func():
		if registry.conflicts(pending).is_empty() and registry.bindings == pending: hide())
	canceled.connect(func(): capturing = false)

func open() -> void:
	pending = registry.bindings.duplicate(true)
	capturing = false
	selected_id = ""
	search.text = ""
	_filter("")
	popup_centered(Vector2i(720, 520))
	search.grab_focus()

func _filter(value: String) -> void:
	list.clear()
	for command: Dictionary in registry.commands:
		var keys: PackedStringArray = []
		for code in registry.keys_for(command.id, pending): keys.append(registry.key_text(code))
		var label := "%s · %s    %s" % [command.context, command.label, " / ".join(keys)]
		if not value.is_empty() and value.to_lower() not in (label + " " + command.id).to_lower(): continue
		list.add_item(label)
		list.set_item_metadata(list.item_count - 1, command.id)
		if selected_id == command.id: list.select(list.item_count - 1)
	var issues: PackedStringArray = registry.conflicts(pending)
	get_ok_button().disabled = not issues.is_empty()
	feedback.text = "Select a command to assign or clear keys. Physical keys are used for tools." if issues.is_empty() else "Conflicts — save blocked:\n" + "\n".join(issues)

func begin_capture() -> void:
	if selected_id == "": feedback.text = "Select a command first."; return
	capturing = true
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null: focus.release_focus()
	feedback.text = "Press a shortcut · Escape cancels assignment"

func _input(event: InputEvent) -> void:
	if not visible or not capturing or not event is InputEventKey: return
	get_viewport().set_input_as_handled()
	if not event.pressed or event.echo: return
	if event.keycode == KEY_ESCAPE:
		capturing = false
		_filter(search.text)
		return
	if event.keycode in [KEY_SHIFT, KEY_CTRL, KEY_ALT, KEY_META, KEY_NONE]: return
	pending[selected_id] = [registry.event_key(event)]
	capturing = false
	_filter(search.text)
