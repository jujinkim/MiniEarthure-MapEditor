extends AcceptDialog
## Read-only view over the current candidate; no deep copy or full serialization.
const TEXT := preload("./import_review_text.gd")
const PAGE_ITEMS := 24
const PAGE_CHARS := 4096
const SCAN_BATCH := 128
var valid: Callable
var current: Variant
var parents: Array = []
var page_keys: Array = []
var revision := 0
var scanning := false
var location: Label
var rows: ItemList
var content: TextEdit
var page: SpinBox
var previous: Button
var next: Button
var up: Button
var open_value: Button
var open_key: Button
var copy_text: Button
var exact_page := ""

func _ready() -> void:
	title = "Exact import details"
	ok_button_text = "Back to review"
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(640, 380)
	add_child(box)
	location = Label.new()
	location.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	location.custom_minimum_size = Vector2(620, 70)
	box.add_child(location)
	var nav := HBoxContainer.new()
	box.add_child(nav)
	up = _button(nav, "Up", go_up)
	previous = _button(nav, "Previous", func(): show_page(int(page.value) - 2))
	page = SpinBox.new()
	page.min_value = 1
	page.step = 1
	page.custom_minimum_size.x = 120
	nav.add_child(page)
	_button(nav, "Go to page", func(): show_page(int(page.value) - 1))
	next = _button(nav, "Next", func(): show_page(int(page.value)))
	rows = ItemList.new()
	rows.auto_height = false
	rows.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rows.custom_minimum_size.y = 260
	rows.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	rows.item_activated.connect(func(index): descend(index))
	rows.item_selected.connect(func(_index): open_value.disabled = false; open_key.disabled = current is not Dictionary)
	box.add_child(rows)
	content = TextEdit.new()
	content.editable = false
	content.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.custom_minimum_size.y = 260
	box.add_child(content)
	var actions := HBoxContainer.new()
	box.add_child(actions)
	open_value = _button(actions, "Open value", func():
		if not rows.get_selected_items().is_empty(): descend(rows.get_selected_items()[0]))
	open_key = _button(actions, "Read full field name", func():
		if not rows.get_selected_items().is_empty(): descend(rows.get_selected_items()[0], true))
	copy_text = _button(actions, "Copy exact text page", func():
		if _live(revision) and current is String: DisplayServer.clipboard_set(exact_page))
	confirmed.connect(clear)
	canceled.connect(clear)

func _button(parent: Control, label: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = label
	button.pressed.connect(action)
	parent.add_child(button)
	return button

func open(value: Dictionary, guard: Callable) -> void:
	clear()
	valid = guard
	current = value
	show_page(0)
	if _live(revision): popup_centered(Vector2i(760, 510))

func clear() -> void:
	revision += 1
	scanning = false
	current = null
	parents.clear()
	page_keys.clear()
	exact_page = ""
	valid = Callable()
	if rows != null: rows.clear()
	if content != null: content.text = ""
	hide()

func _live(token: int) -> bool:
	if token != revision: return false
	if not valid.is_valid() or not valid.call():
		clear()
		return false
	return true

func show_page(number: int) -> void:
	revision += 1
	var token := revision
	if not _live(token): return
	page_keys.clear()
	rows.clear()
	content.text = ""
	exact_page = ""
	open_value.disabled = true
	open_key.disabled = true
	copy_text.disabled = current is not String
	var container: bool = current is Dictionary or current is Array
	var count: int = current.size() if container else current.length() if current is String else JSON.stringify(current).length()
	var width := PAGE_ITEMS if container else PAGE_CHARS
	var pages := maxi(1, ceili(float(count) / width))
	number = clampi(number, 0, pages - 1)
	page.max_value = pages
	page.set_value_no_signal(number + 1)
	previous.disabled = number == 0
	next.disabled = number + 1 == pages
	up.disabled = parents.is_empty()
	rows.visible = container
	content.visible = not container
	var label := "ImportLayer" if parents.is_empty() else str(parents.back().label).substr(0, 100)
	var start := number * width
	location.text = "%s · depth %d · page %d / %d\n%d %s; showing %d–%d. Read-only captured candidate." % [label, parents.size(), number + 1, pages, count, "entries" if container else "characters", mini(start + 1, count), mini(start + width, count)]
	scanning = true
	if current is Dictionary:
		# Dictionary has no indexed key access. Scan without keys()/full indexing,
		# yielding even while skipping earlier pages; cancellation releases old refs.
		var offset := 0
		var source: Dictionary = current
		for key: String in source:
			if offset >= start: page_keys.append(key)
			offset += 1
			if page_keys.size() == PAGE_ITEMS: break
			if offset % SCAN_BATCH == 0:
				await get_tree().process_frame
				if not _live(token): return
	elif current is Array:
		for index in range(start, mini(start + width, count)): page_keys.append(index)
	else:
		if current is String:
			# TextEdit normalizes CR/CRLF. Quote only this bounded chunk so every
			# control character remains represented and Copy returns original text.
			exact_page = current.substr(start, PAGE_CHARS)
			content.text = JSON.stringify(exact_page)
			location.text += "\nText is JSON-quoted; Copy exact text page keeps original whitespace."
		else: content.text = JSON.stringify(current)
	if not _live(token): return
	for key in page_keys:
		rows.add_item(TEXT.preview(key, 80) + "  →  " + TEXT.preview(current[key], 160))
	scanning = false

func descend(index: int, field_name: bool = false) -> void:
	if not _live(revision) or scanning or index < 0 or index >= page_keys.size(): return
	var key: Variant = page_keys[index]
	parents.append({"value":current, "page":int(page.value) - 1, "label":TEXT.preview(key, 80)})
	current = key if field_name else current[key]
	show_page(0)

func go_up() -> void:
	if not _live(revision) or parents.is_empty(): return
	var parent: Dictionary = parents.pop_back()
	current = parent.value
	show_page(parent.page)
