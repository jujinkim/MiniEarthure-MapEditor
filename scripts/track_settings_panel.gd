extends VBoxContainer
const I18N := preload("./locale_text.gd")
signal requested(settings: Dictionary)
signal cancelled
var seed_input: LineEdit
var circuit: CheckButton
var length: OptionButton
var selections := {}
var _defaults := {}
var _length_options := {}
var note: Label
var catalogue_ready := false
var generate: Button
var busy:=false
var progress:Control
var progress_label:Label
const RING:=preload("res://addons/mapkit/godot/work_progress.gd")

func _load_catalogue() -> Dictionary:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	return JSON.parse_string(bridge.track_catalogue()).data

func _ready() -> void:
	var catalogue := _load_catalogue()
	if not catalogue.get("selection_ids") is Array:
		note = Label.new()
		note.text = I18N.t("The track module does not match this screen. Close the application and restart with the current build.")
		note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		add_child(note)
		return
	catalogue_ready = true
	_defaults = catalogue.defaults
	_length_options = catalogue.length_options
	var toggle := Button.new()
	toggle.text = I18N.t("Seed Track generation")
	add_child(toggle)
	var form := VBoxContainer.new()
	add_child(form)
	form.hide()
	toggle.pressed.connect(func(): form.visible = not form.visible)
	seed_input = LineEdit.new()
	seed_input.placeholder_text = I18N.t("Seed")
	seed_input.text = str(randi())
	form.add_child(seed_input)
	var random_seed := Button.new()
	random_seed.text = I18N.t("New seed")
	random_seed.pressed.connect(func(): seed_input.text = str(randi()))
	form.add_child(random_seed)
	circuit = CheckButton.new()
	circuit.text = I18N.t("Circuit")
	circuit.button_pressed = _defaults.circuit
	form.add_child(circuit)
	length = OptionButton.new()
	_refresh_length(str(_defaults.length))
	circuit.toggled.connect(func(_value: bool): _refresh_length(selected_length()))
	form.add_child(length)
	var grid := GridContainer.new()
	grid.columns = 2
	form.add_child(grid)
	var labels := {"driving":"Driving", "gimmick":"Gimmick", "action":"Action"}
	for id: String in catalogue.selection_ids:
		var check := CheckBox.new()
		check.text = I18N.t(labels.get(id,id))
		check.button_pressed = id in _defaults.categories
		grid.add_child(check)
		selections[id] = check
		check.toggled.connect(func(_value: bool): _update_enabled())
	note = Label.new()
	note.text = I18N.t("The seed chooses types, widths and directions from enabled categories. Not every type is guaranteed. Length sets the lap count, sprint size and circuit scale; it is not a time target.")
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	form.add_child(note)
	progress=RING.new();form.add_child(progress);progress.hide()
	progress_label=Label.new();form.add_child(progress_label);progress_label.hide()
	generate = Button.new()
	generate.text = I18N.t("Generate / regenerate")
	generate.pressed.connect(func():
		if busy: return
		if not seed_input.text.is_valid_int() or int(seed_input.text)<0 or int(seed_input.text)>9007199254740991:
			note.text = I18N.t("Seed must be an integer from 0 to 9007199254740991.")
			return
		requested.emit(settings()))
	form.add_child(generate)
	_update_enabled()
	var cancel := Button.new()
	cancel.text = I18N.t("Cancel generation")
	cancel.pressed.connect(func(): cancelled.emit())
	form.add_child(cancel)

func settings() -> Dictionary:
	if not catalogue_ready: return {}
	var enabled: Array = []
	for id: String in selections:
		if selections[id].button_pressed: enabled.append(id)
	return {"seed":int(seed_input.text),"circuit":circuit.button_pressed,"length":selected_length(),
		"difficulty":_defaults.difficulty,"time_minutes":seed_defaults().get("time_minutes",_defaults.time_minutes),"categories":enabled}

func seed_defaults() -> Dictionary:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var result: Dictionary = JSON.parse_string(bridge.track_seed_defaults(int(seed_input.text)))
	return result.get("data",{})

func restore(value: Dictionary) -> void:
	if not catalogue_ready: return
	seed_input.text = str(int(value.seed))
	circuit.button_pressed = value.circuit
	_refresh_length(str(value.length))
	for id: String in selections: selections[id].button_pressed = id in value.categories
	_update_enabled()

const LENGTH_LABELS := {"short":"Short", "medium":"Medium", "long":"Long"}

func selected_length() -> String:
	return str(length.get_item_metadata(length.selected)) if length.selected >= 0 else str(_defaults.length)

func _refresh_length(id: String) -> void:
	length.clear()
	var choices: Array = _length_options["circuit" if circuit.button_pressed else "sprint"]
	for item: Dictionary in choices:
		var label := I18N.t(LENGTH_LABELS.get(str(item.length), str(item.length)))
		if circuit.button_pressed: label += I18N.t(" · up to %d laps") % int(item.max_laps)
		else: label += I18N.t(" · %d pieces") % int(item.pieces)
		length.add_item(label)
		length.set_item_metadata(length.item_count - 1, str(item.length))
	for i in length.item_count:
		if str(length.get_item_metadata(i)) == id: length.select(i); return
	length.select(0)

func show_result(assembly: Dictionary, summary: Dictionary = {}) -> void:
	var routes: Array = assembly.get("routes", [])
	var count: int = 0 if routes.is_empty() else (routes[0].get("pieces", []) as Array).size()
	note.text = I18N.t("Generated · %.1f m · estimated %.1f s · %d pieces") % [float(assembly.length_cm)/100.0, float(assembly.estimated_msec)/1000.0, count]
	for shortcut: Dictionary in routes.slice(1):
		note.text += I18N.t(" · shortcut %.1f s") % (float(shortcut.estimated_msec)/1000.0)
	if not summary.is_empty():
		var pieces: Dictionary = summary.pieces
		var gimmicks: Dictionary = summary.gimmicks
		note.text += "\n" + I18N.t("Pieces %d/%d types · Gimmicks %d/%d types") % [int(pieces.used), int(pieces.total), int(gimmicks.used), int(gimmicks.total)]

func _update_enabled() -> void:
	if not is_instance_valid(generate): return
	generate.disabled = true
	for check: CheckBox in selections.values():
		if check.button_pressed and not busy: generate.disabled = false

func set_busy(value:bool) -> void:
	busy=value
	if is_instance_valid(progress): progress.visible=value;progress_label.visible=value
	_update_enabled()
func update_progress(value:Dictionary) -> void:
	progress.set_progress(value)
	progress_label.text=I18N.t(RING.stage_key(str(value.get("stage","preparing"))))
