extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	root.size = Vector2i(1024,720)
	var before: Dictionary = ui.store.document.duplicate(true)
	ui.osm_panel.open()
	ui.osm_panel.enabled.button_pressed = true
	check(ui.osm_panel.error() != "", "empty crop rejected")
	var bounds := [9.0,55.0,9.001,55.001]
	for i in range(4): ui.osm_panel.fields[i].value = bounds[i]
	ui.osm_panel.area.toggle_fit()
	check(ui.osm_panel.error() == "","bounded local crop")
	ui.osm_panel.fields[2].value = 9.1
	check(ui.osm_panel.error() != "","oversize blocked before worker")
	ui.osm_panel.fields[2].value = 8.0
	check(ui.osm_panel.error().contains("west"),"reversed or crossing box rejected")
	ui.osm_panel.fields[2].value = 9.001
	await process_frame
	var area: Control = ui.osm_panel.area
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = area.size*Vector2(0.8,0.8)
	area._gui_input(press)
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.position = area.size*Vector2(0.2,0.2)
	area._gui_input(release)
	var selected: Array = ui.osm_panel.bbox()
	check(selected[0] < selected[2] and selected[1] < selected[3],"reverse drag normalizes W/S/E/N")
	check(selected != bounds and area.bounds == selected,"drag updates numeric fields and diagram")
	var revision: int = ui.osm_panel.revision
	ui.osm_panel.fields[0].value += 0.000001
	ui.osm_panel.fields[0].value -= 0.000001
	check(ui.osm_panel.revision > revision, "changed then restored crop has a new revision")
	ui.osm_panel.dialog.hide()
	ui.osm_panel.dialog.canceled.emit()
	check(ui.import_dialog.visible and not ui.busy, "cancel returns to import without starting a worker")
	check(ui.store.document == before and ui.pending_import == null,"selection and cancellation preserve document")
	check(ui.import_origin_lon.value == 0 and ui.import_origin_lat.value == 0,"selection never silently changes origins")
	if DisplayServer.get_name() != "headless":
		await process_frame
		check(ui.osm_panel.dialog.size.x <= 1024 and ui.osm_panel.dialog.size.y <= 720,"wizard fits 1024x720")
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture) == OK,"area screenshot")
	ui.queue_free()
	await process_frame
	print("area_selection_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
