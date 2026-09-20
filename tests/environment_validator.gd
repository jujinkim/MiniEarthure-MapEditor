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
	panel._apply()
	check(ui.store.document.recipe_version==1 and ui.store.document.has("environment"),"current v1 environment profile")
	var accepted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and not ui.store.document.has("environment"),"undo restores legacy profile absence")
	check(ui.store.redo()=="" and ui.store.document.environment==accepted.environment,"redo restores profile")
	ui.author_panel.open()
	panel=ui.author_panel.environment_panel
	panel.regions.text="[{}]"
	panel._apply()
	check(ui.store.document.environment==accepted.environment,"invalid region cannot mutate source")
	ui.queue_free()
	for frame in 6: await process_frame
	print("environment_editor_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
