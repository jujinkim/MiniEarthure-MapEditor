extends VBoxContainer
## City mode → Parts: ready-made city parts placed on the plan. Choosing a part
## arms plan placement (a ghost follows the pointer); a click places it as one
## validated Undo. Rotation is free: the angle field, Q/E 15° steps, Shift+wheel
## 1° steps, or alignment to the nearest road. "My parts" is the user library.
const I18N := preload("./locale_text.gd")
const STYLE := preload("./workbench_style.gd")
const PARTS := preload("./city_parts.gd")
const UNITS := preload("./import_units.gd")
const TOOL := "Part"
var ui: Control
var builtin_list: ItemList
var user_list: ItemList
var angle: SpinBox
var replace: CheckBox
var hint: Label
var builtins: Array = []
var user_parts: Array = []
## The armed part (parsed v1 dictionary), empty when placement is off.
var active: Dictionary = {}
var name_dialog: ConfirmationDialog
var name_field: LineEdit
var name_action := Callable()
var delete_dialog: ConfirmationDialog
## The user part Rename… and Delete act on: the last My parts entry clicked.
## Kept apart from the list highlight, which editing cancellation may clear.
var chosen_user: Dictionary = {}
var pending_delete: Dictionary = {}
var preview_key := ""
var preview: Dictionary = {}

func build(owner_ui: Control) -> void:
	ui = owner_ui
	add_theme_constant_override("separation", 6)
	_heading("Built-in parts")
	builtin_list = _list()
	builtin_list.item_clicked.connect(_builtin_clicked)
	_heading("My parts")
	user_list = _list()
	user_list.item_clicked.connect(_user_clicked)
	STYLE.button(self, "Rename…", _rename, "", "settings")
	STYLE.button(self, "Delete", _confirm_delete, "", "delete")
	var row := HBoxContainer.new()
	add_child(row)
	ui._label(row, "Angle (°)")
	angle = SpinBox.new()
	angle.min_value = -180.0
	angle.max_value = 180.0
	angle.step = 0.1
	angle.allow_greater = true
	angle.allow_lesser = true
	angle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	angle.value_changed.connect(func(_value: float): ui.canvas.queue_redraw())
	row.add_child(angle)
	STYLE.button(self, "Align to road", align, "", "snap")
	replace = CheckBox.new()
	replace.text = I18N.t("Replace objects under the part")
	replace.button_pressed = true
	add_child(replace)
	STYLE.button(self, "Save selection as part…", _save_selection, "", "save")
	hint = ui._label(self, "Choose a part, then click the plan.")
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	name_dialog = ConfirmationDialog.new()
	name_dialog.title = I18N.t("Part name")
	name_field = LineEdit.new()
	name_field.max_length = 128
	name_dialog.add_child(name_field)
	name_dialog.register_text_enter(name_field)
	name_dialog.confirmed.connect(func(): if name_action.is_valid(): name_action.call(name_field.text.strip_edges()))
	ui.add_child(name_dialog)
	delete_dialog = ConfirmationDialog.new()
	delete_dialog.confirmed.connect(_delete)
	ui.add_child(delete_dialog)
	refresh()

func _builtin_clicked(index: int, _at: Vector2, button: int) -> void:
	if button == MOUSE_BUTTON_LEFT: activate(builtins[index].part)

func _user_clicked(index: int, _at: Vector2, button: int) -> void:
	if button != MOUSE_BUTTON_LEFT: return
	chosen_user = user_parts[index]
	activate(chosen_user.part)
	user_list.select(index)

func _heading(text: String) -> void:
	var label: Label = ui._label(self, text)
	label.add_theme_color_override("font_color", STYLE.BLUE)

func _list() -> ItemList:
	var list := ItemList.new()
	list.custom_minimum_size.y = 150
	list.auto_height = false
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(list)
	return list

## Reloads both libraries; unreadable user files are reported, not hidden.
func refresh() -> void:
	builtins = PARTS.list(PARTS.BUILTIN_DIR).parts
	var library := PARTS.list(PARTS.user_dir())
	user_parts = library.parts
	builtin_list.clear()
	for entry: Dictionary in builtins: builtin_list.add_item(I18N.t(str(entry.part.name)))
	user_list.clear()
	chosen_user = {}
	for entry: Dictionary in user_parts:
		user_list.add_item(str(entry.part.name))
		user_list.set_item_tooltip(user_list.item_count - 1, str(entry.path))
	if not library.errors.is_empty(): ui._status(", ".join(library.errors))

func _denominator() -> int:
	var scale := UNITS.osm_scale(ui.store.document)
	return maxi(1, int(scale.get("denominator", 1)))

## Arms plan placement of `part`; the plan view opens when it is hidden.
func activate(part: Dictionary) -> void:
	# Opening the plan cancels editing, so it comes before arming the part.
	if not ui.canvas.visible: ui._set_view_mode("split")
	ui._cancel_editing()
	active = part
	preview_key = ""
	ui.canvas.tool = TOOL
	ui.canvas.grab_focus()
	ui._selection(ui.canvas.selected)
	hint.text = I18N.t(ui._tool_help(TOOL))

func cancel() -> void:
	active = {}
	if ui != null and ui.canvas != null and ui.canvas.tool == TOOL: ui.canvas.tool = "Select"
	if is_instance_valid(builtin_list): builtin_list.deselect_all()

func rotate_by(degrees: float) -> void:
	angle.value = wrapf(angle.value + degrees, -180.0, 180.0)

## Ground height under the part origin: the terrain when the map has any,
## otherwise the map's base height.
func _ground(point: Vector2) -> int:
	var document: Dictionary = ui.store.document
	if not document.get("heightmaps", []).is_empty():
		var result: Variant = JSON.parse_string(ui.store.working_snapshot().height(point))
		if result is Dictionary and result.get("ok", false): return int(result.data.height)
	return int(document.get("terrain_base_cm", 0))

func place(point: Vector2) -> void:
	if active.is_empty(): return
	var plan := PARTS.plan_place(ui.store.document, active, point, angle.value, {"replace": replace.button_pressed, "ground_cm": _ground(point)})
	if plan.has("error"):
		ui._status(plan.error)
		return
	var failure: String = ui.canvas.author.apply("Place city part", plan.patches, true)
	if failure != "":
		ui._status(I18N.diagnostic(failure))
		return
	ui.canvas.set_selection(plan.selection)
	ui._status(I18N.t("Part placed: %d of %d mouths joined.") % [int(plan.joined), int(plan.mouths)])

## Turns the part so a mouth (or, without mouths, its axes) follows the road
## nearest the pointer, choosing the closest such angle to the current one.
func align() -> void:
	if active.is_empty():
		ui._status(I18N.t("Choose a part, then click the plan."))
		return
	var cursor: Vector2 = ui.canvas.brush_cursor
	var best := INF
	var direction := 0.0
	for road: Dictionary in ui.store.document.get("roads", []):
		for i in range(road.points.size() - 1):
			var a := Vector2(road.points[i][0], road.points[i][2])
			var b := Vector2(road.points[i + 1][0], road.points[i + 1][2])
			var distance := cursor.distance_to(Geometry2D.get_closest_point_to_segment(cursor, a, b))
			if distance < best and a != b:
				best = distance
				direction = rad_to_deg((b - a).angle())
	if best > 10000.0 / _denominator():
		ui._status(I18N.t("No road near the cursor to align with."))
		return
	var headings: Array = active.mouths.map(func(m: Dictionary) -> float: return float(m.heading_deg))
	var step := 180.0 if not headings.is_empty() else 90.0
	if headings.is_empty(): headings = [0.0]
	var chosen := angle.value
	var change := INF
	for heading: float in headings:
		for k in range(4):
			var candidate := wrapf(direction - heading + k * step, -180.0, 180.0)
			var delta := absf(wrapf(candidate - angle.value, -180.0, 180.0))
			if delta < change:
				change = delta
				chosen = candidate
	angle.value = snappedf(chosen, 0.1)

## The ghost: footprint, roads and buildings at the pointer.
func draw_preview(canvas: Control, cursor: Vector2) -> void:
	if active.is_empty() or not Rect2(Vector2.ZERO, canvas.size).has_point(canvas.get_local_mouse_position()): return
	var key := str([active.id, active.name, angle.value, _denominator()])
	if key != preview_key:
		preview_key = key
		preview = PARTS.transform(active, Vector2.ZERO, angle.value, _denominator(), 0, "")
	if preview.has("error"): return
	var to_screen := func(p: Array) -> Vector2: return canvas.screen([float(p[0]) + cursor.x, float(p[1]) + cursor.y])
	var outline := PackedVector2Array()
	for p: Array in preview.footprint: outline.append(to_screen.call(p))
	var color := Color("c76035")
	if not Geometry2D.triangulate_polygon(outline).is_empty(): canvas.draw_colored_polygon(outline, Color(color, 0.12))
	outline.append(outline[0])
	canvas.draw_polyline(outline, color, 2.0, true)
	for building: Dictionary in preview.records.buildings:
		var ring := PackedVector2Array()
		for p: Array in building.footprint: ring.append(to_screen.call(p))
		ring.append(ring[0])
		canvas.draw_polyline(ring, Color("4e4825"), 1.5, true)
	for road: Dictionary in preview.records.roads:
		for i in range(road.points.size() - 1):
			var a: Vector2 = to_screen.call([road.points[i][0], road.points[i][2]])
			var b: Vector2 = to_screen.call([road.points[i + 1][0], road.points[i + 1][2]])
			canvas.draw_line(a, b, Color("4e4825"), maxf(2.0, float(road.widths_cm[i]) * canvas._scale()), true)

func _save_selection() -> void:
	var captured := PARTS.capture(ui.store.document, ui.canvas.selected, "-")
	if captured.has("error"):
		ui._status(captured.error)
		return
	name_field.text = ""
	name_action = func(text: String):
		if text == "": return
		var part: Dictionary = captured.part
		part.name = text
		var saved := PARTS.save_user(part)
		if saved.has("error"):
			ui._status(saved.error)
			return
		refresh()
		ui._status(I18N.t("Saved part %s.") % text)
	name_dialog.popup_centered(Vector2i(420, 120))
	name_field.grab_focus()

func _rename() -> void:
	var entry := chosen_user
	if entry.is_empty():
		ui._status(I18N.t("Choose a part, then click the plan."))
		return
	name_field.text = str(entry.part.name)
	name_action = func(text: String):
		if text == "": return
		var failure := PARTS.rename_user(entry.path, text)
		if failure != "": ui._status(failure)
		cancel()
		refresh()
	name_dialog.popup_centered(Vector2i(420, 120))
	name_field.grab_focus()

func _confirm_delete() -> void:
	var entry := chosen_user
	if entry.is_empty():
		ui._status(I18N.t("Choose a part, then click the plan."))
		return
	pending_delete = entry
	delete_dialog.dialog_text = I18N.t("Delete part %s?") % str(entry.part.name)
	delete_dialog.popup_centered()

func _delete() -> void:
	var entry := pending_delete
	pending_delete = {}
	if entry.is_empty(): return
	var failure := PARTS.delete_user(entry.path)
	if failure != "": ui._status(failure)
	cancel()
	refresh()
