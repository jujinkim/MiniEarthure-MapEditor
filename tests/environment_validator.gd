extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
var failed := false
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	if not value: failed=true; push_error(message)
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.environment_panel
	check(panel != null,"public environment authoring panel")
	var original: Dictionary=ui.store.document.duplicate(true)
	panel.fields.architecture = func(): return "cycladic"
	panel.fields.climate = func(): return "mediterranean"
	panel.fields.settlement = func(): return "village"
	panel.fields.terrain = func(): return "coast"
	panel.regions.text = '[{"id":"canal","concept":"metropolis","architecture":"venetian","terrain":"canal","polygon":[[0,0],[1000,0],[1000,1000]]}]'
	panel._apply()
	check(ui.store.document.recipe_version==1 and ui.store.document.has("environment"),"current v1 environment profile")
	check(ui.store.document.environment.architecture == "cycladic" and ui.store.document.environment.terrain == "coast", "catalogue axes adopted")
	var accepted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store._signature(ui.store.document) == ui.store._signature(original),"undo restores the current original document")
	check(ui.store.redo()=="" and ui.store.document.environment==accepted.environment,"redo restores profile")
	ui.author_panel.open()
	panel=ui.author_panel.environment_panel
	panel.regions.text="[{}]"
	panel._apply()
	check(ui.store.document.environment==accepted.environment,"invalid region cannot mutate source")
	var before_style: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.apply_command("Ground appearance", [{"field":"ground_style_id","before":null,"after":"ground/rock"}]) == "", "ground style is a document value")
	check(ui.store.document.ground_style_id == "ground/rock", "ground style retained")
	check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before_style), "ground style undo restores omission")
	check(ui.store.apply_command("Invalid ground appearance", [{"field":"ground_style_id","before":null,"after":"building/modern/office/glass"}]) != "", "cross-domain style rejected")
	check(ui.store._signature(ui.store.document) == ui.store._signature(before_style), "invalid style leaves source intact")
	ui.queue_free()
	for frame in 6: await process_frame
	print("environment_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
