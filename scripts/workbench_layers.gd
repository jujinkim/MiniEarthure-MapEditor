extends VBoxContainer
signal state_changed
const EDIT := preload("./workbench_edit.gd")
var canvas: Control
var tree: Tree
var search: LineEdit
var opacity_control: HSlider
var active_layer := ""
var updating := false
var rows: Dictionary = {}
var collapsed: Dictionary = {}
var selection_queued := false
var pending_layer := ""

func _ready() -> void:
	search = LineEdit.new()
	search.placeholder_text = "Filter object ID…"
	search.text_changed.connect(func(_value): refresh())
	add_child(search)
	tree = Tree.new()
	tree.columns = 3
	tree.hide_root = true
	tree.select_mode = Tree.SELECT_MULTI
	tree.column_titles_visible = true
	tree.set_column_title(0, "Objects")
	tree.set_column_clip_content(0, true)
	tree.set_column_custom_minimum_width(0, 80)
	tree.set_column_title(1, "Show")
	tree.set_column_title(2, "Lock")
	for col in [1, 2]:
		tree.set_column_expand(col, false)
		tree.set_column_custom_minimum_width(col, 45)
	tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tree.custom_minimum_size.y = 110
	tree.multi_selected.connect(_selected)
	tree.item_edited.connect(_edited)
	tree.item_collapsed.connect(func(item):
		if not updating and item.get_metadata(0) is String:
			collapsed[item.get_metadata(0)] = item.collapsed
	)
	add_child(tree)
	var row := HBoxContainer.new()
	add_child(row)
	var label := Label.new()
	label.text = "Layer opacity"
	row.add_child(label)
	opacity_control = HSlider.new()
	opacity_control.min_value = 0.15
	opacity_control.max_value = 1.0
	opacity_control.step = 0.05
	opacity_control.value = 1.0
	opacity_control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	opacity_control.editable = false
	opacity_control.value_changed.connect(func(value):
		if updating or active_layer == "": return
		var state: Dictionary = canvas.layer_state.get(active_layer, {}).duplicate()
		state.opacity = value
		canvas.set_layer_state(active_layer, state)
		state_changed.emit()
	)
	row.add_child(opacity_control)
	var hint := Label.new()
	hint.text = "Show / lock affect 2D editing only.\nShift/Ctrl-click for multiple objects."
	hint.add_theme_font_size_override("font_size", 12)
	add_child(hint)

func _layer(parent: TreeItem, key: String, title: String, count: int) -> TreeItem:
	var item := tree.create_item(parent)
	item.set_text(0, "%s (%d)" % [title, count])
	item.set_metadata(0, key)
	item.collapsed = bool(collapsed.get(key, key.begins_with("import/")))
	var state: Dictionary = canvas.layer_state.get(key, {})
	for col in [1, 2]:
		item.set_cell_mode(col, TreeItem.CELL_MODE_CHECK)
		item.set_editable(col, true)
		item.set_selectable(col, false)
	item.set_checked(1, bool(state.get("visible", true)))
	item.set_checked(2, bool(state.get("locked", false)))
	item.set_tooltip_text(0, "Select layer to select its editable objects and adjust opacity.")
	return item

func refresh() -> void:
	if tree == null: return
	updating = true
	tree.clear()
	rows.clear()
	var root := tree.create_item()
	var entries := EDIT.entries(canvas.store.document)
	var imports := {}
	_layer(root, "heightmaps", "Terrain", canvas.store.document.heightmaps.size())
	for field: String in EDIT.FIELDS:
		var parent := _layer(root, field, field.capitalize(), canvas.store.document.get(field, []).size())
		for entry in entries:
			if entry.field != field: continue
			for key in canvas.layer_keys(entry):
				if key.begins_with("import/"): imports[key] = int(imports.get(key, 0)) + 1
			if not search.text.is_empty() and not str(entry.record.id).to_lower().contains(search.text.to_lower()): continue
			var item := tree.create_item(parent)
			item.set_text(0, str(entry.record.id))
			item.set_tooltip_text(0, entry.key)
			item.set_metadata(0, entry)
			item.set_selectable(0, canvas.available(entry, true))
			if not canvas.available(entry, true): item.set_custom_color(0, Color("7d8188"))
			for col in [1, 2]: item.set_selectable(col, false)
			rows[entry.key] = item
	for key: String in imports:
		_layer(root, key, "Import " + key.trim_prefix("import/").left(8), imports[key])
	updating = false
	sync_selection()

func sync_selection() -> void:
	updating = true
	if tree.get_root() != null:
		var layer := tree.get_root().get_first_child()
		while layer != null:
			layer.deselect(0)
			layer = layer.get_next()
	for key: String in rows:
		if key in canvas.selected: rows[key].select(0)
		else: rows[key].deselect(0)
	updating = false

func _selected(item: TreeItem, _column: int, selected: bool) -> void:
	if updating: return
	canvas.cancel_interaction()
	var metadata: Variant = item.get_metadata(0)
	if metadata is String and selected: pending_layer = metadata
	# Tree emits individual deselections before the final selection. Publishing or
	# synchronizing those partial snapshots would reselect old rows mid-dispatch.
	if not selection_queued:
		selection_queued = true
		_publish_selection.call_deferred()

func _publish_selection() -> void:
	selection_queued = false
	if pending_layer != "":
		active_layer = pending_layer
		pending_layer = ""
		updating = true
		opacity_control.editable = true
		opacity_control.value = float(canvas.layer_state.get(active_layer, {}).get("opacity", 1.0))
		updating = false
		var keys: Array[String] = []
		for entry in EDIT.entries(canvas.store.document):
			if active_layer in canvas.layer_keys(entry) and canvas.available(entry, true): keys.append(entry.key)
		canvas.set_selection(keys)
	else:
		var keys: Array[String] = []
		for key: String in rows:
			if rows[key].is_selected(0): keys.append(key)
		canvas.set_selection(keys)

func _edited() -> void:
	if updating: return
	var item := tree.get_edited()
	var key: String = item.get_metadata(0)
	var state: Dictionary = canvas.layer_state.get(key, {}).duplicate()
	state.visible = item.is_checked(1)
	state.locked = item.is_checked(2)
	canvas.set_layer_state(key, state)
	# Godot locks TreeItems while dispatching item_edited.
	refresh.call_deferred()
	state_changed.emit()
