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
	ui._open_overture()
	check(ui.overture_dialog.get_ok_button().disabled,"empty area cannot proceed")
	ui.overture_release.text = "2026-02-30.0"
	check(ui._overture_error().contains("calendar"),"invalid calendar rejected locally")
	ui.overture_release.text = "2099-13-01.0"
	check(ui._overture_error().contains("calendar"),"invalid month rejected without engine diagnostics")
	ui.overture_release.text = "2024-02-29.0"
	var bounds := [9.0,55.0,9.001,55.001]
	for i in range(4): ui.overture_bbox[i].value = bounds[i]
	ui.overture_area.toggle_fit()
	check(ui._overture_error() == "","valid leap date and bounded area")
	ui.overture_bbox[2].value = 9.1
	check(ui.overture_dialog.get_ok_button().disabled,"oversize blocked before worker")
	ui.overture_bbox[2].value = 8.0
	check(ui._overture_error().contains("west"),"reversed or crossing box rejected")
	ui.overture_bbox[2].value = 9.001
	await process_frame
	var area: Control = ui.overture_area
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = area.size*Vector2(0.8,0.8)
	area._gui_input(press)
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.position = area.size*Vector2(0.2,0.2)
	area._gui_input(release)
	var selected: Array = ui._overture_plan().bbox
	check(selected[0] < selected[2] and selected[1] < selected[3],"reverse drag normalizes W/S/E/N")
	check(selected != bounds and area.bounds == selected,"drag updates numeric fields and diagram")
	ui.overture_dialog.hide()
	ui._review_overture()
	check(not ui.overture_reviewed.is_empty() and not ui.busy,"review precedes download")
	check(ui.overture_review.dialog_text.contains("not a crop") and ui.overture_review.dialog_text.contains("unknown"),"whole footprints and unknown costs disclosed")
	var revision: int = ui.overture_revision
	ui.overture_bbox[0].value += 0.000001
	ui.overture_bbox[0].value -= 0.000001
	check(ui.overture_revision > revision and ui.overture_reviewed.is_empty(),"changed then restored selection invalidates review")
	ui._download_overture()
	check(not ui.busy and ui.import_job == null,"stale review cannot spawn")
	ui._review_overture()
	ui.overture_review.hide()
	ui.overture_review.canceled.emit()
	check(ui.overture_reviewed.is_empty() and ui.overture_dialog.visible,"cancel returns to editable selection")
	check(ui.store.document == before and ui.pending_import == null,"selection and cancellation preserve document")
	check(ui.import_origin_lon.value == 0 and ui.import_origin_lat.value == 0,"selection never silently changes origins")
	if DisplayServer.get_name() != "headless":
		await process_frame
		check(ui.overture_dialog.size.x <= 1024 and ui.overture_dialog.size.y <= 720,"wizard fits 1024x720")
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture) == OK,"area screenshot")
	ui.queue_free()
	await process_frame
	print("area_selection_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
