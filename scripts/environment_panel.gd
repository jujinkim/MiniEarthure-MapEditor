extends RefCounted
## Public environment authoring; commands retain ordinary undo/redo and validation.
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")
var panel: AcceptDialog
var fields := {}
var regions: TextEdit
var lights: TextEdit
var before: Variant
var epoch := 0

func setup(owner: AcceptDialog) -> void:
	panel = owner
	before = panel.editor.store.document.get("environment")
	epoch = panel.editor.store.command_epoch
	var value: Dictionary = before.duplicate(true) if before is Dictionary else PROFILE.defaults()
	var box: VBoxContainer = panel.page("Environment")
	panel.hint(box,"Map defaults and regional art direction. Uses the current generation rules. Time and weather preview controls do not change saved data.")
	_pick(box,"Map concept","concept",PROFILE.CONCEPTS,str(value.concept))
	_pick(box,"Architecture","architecture",["","modern","rural","adobe","timber","tropical"],str(value.get("architecture","")))
	_pick(box,"Climate","climate",["","temperate","polar","arid","tropical"],str(value.get("climate","")))
	_pick(box,"Settlement","settlement",["","urban","village","sparse","wilderness"],str(value.get("settlement","")))
	_number(box,"Latitude (degrees)","latitude_mdeg",-90,90,value.latitude_mdeg/1000.0,1000)
	_number(box,"Longitude (degrees)","longitude_mdeg",-180,180,value.longitude_mdeg/1000.0,1000)
	_number(box,"UTC offset (minutes)","utc_offset_minutes",-720,840,value.utc_offset_minutes)
	_number(box,"Sunrise (minutes after midnight)","sunrise_minutes",0,1439,value.sunrise_minutes)
	_number(box,"Sunset (minutes after midnight)","sunset_minutes",0,1439,value.sunset_minutes)
	panel.hint(box,'Regional overrides · ordered polygons in centimetres. Example: [{"id":"farm","concept":"countryside","polygon":[[0,0],[10000,0],[10000,10000]]}]. Architecture, climate and settlement may be overridden separately.')
	regions = _json(box,value.get("regions",[]))
	panel.hint(box,'Light bindings · explicit asset/material indices. Empty lists add no lights. Example: [{"asset_id":"lamp","window_materials":[],"bulb_materials":[1],"position_cm":[0,400,0],"range_cm":1400,"color":[255,216,158]}]. Building window materials use a stable nightly schedule.')
	lights = _json(box,value.get("lights",[]))
	var apply := Button.new()
	apply.text = "Apply environment design"
	box.add_child(apply)
	apply.pressed.connect(_apply)

func _pick(box: Node, title: String, key: String, values: Array, current: String) -> void:
	var row: HBoxContainer = panel.row(box,title)
	var picker := OptionButton.new()
	for value: String in values: picker.add_item("From concept" if value.is_empty() else value.capitalize())
	picker.select(maxi(0,values.find(current)))
	row.add_child(picker)
	fields[key] = func(): return values[picker.selected]

func _number(box: Node, title: String, key: String, minimum: float, maximum: float, current: float, factor := 1.0) -> void:
	var row: HBoxContainer = panel.row(box,title)
	var spin := SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = 0.001 if factor > 1.0 else 1.0
	spin.value = current
	row.add_child(spin)
	fields[key] = func(): return roundi(spin.value*factor)

func _json(box: Node, value: Array) -> TextEdit:
	var edit := TextEdit.new()
	edit.text = JSON.stringify(value,"  ")
	edit.custom_minimum_size = Vector2(0,140)
	box.add_child(edit)
	return edit

func _apply() -> void:
	var store: RefCounted = panel.editor.store
	if store.command_epoch != epoch:
		panel.feedback.text = "Document changed; reopen Environment before applying."
		return
	if regions.text.length() > 131072 or lights.text.length() > 131072:
		panel.feedback.text = "Environment metadata exceeds the editor budget."
		return
	var value := {"version":1,"regions":JSON.parse_string(regions.text),"lights":JSON.parse_string(lights.text)}
	for key: String in fields: value[key] = fields[key].call()
	if not value.regions is Array or not value.lights is Array:
		panel.feedback.text = "Regions and light bindings must be JSON arrays."
		return
	var patches := [{"field":"environment","before":before,"after":value}]
	var failure: String = store.apply_command("Environment design",patches)
	panel.feedback.text = "Environment saved in document · Undo is available" if failure.is_empty() else failure
	if failure.is_empty():
		before = store.document.environment.duplicate(true)
		epoch = store.command_epoch
