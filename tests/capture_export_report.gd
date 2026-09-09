extends SceneTree
func _initialize() -> void: run.call_deferred()
func run() -> void:
	root.size = Vector2i(1024,720)
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	ui.canvas.tool = "Building"
	ui.canvas.draft.assign([Vector2(10000,10000),Vector2(30000,10000),Vector2(30000,30000),Vector2(10000,30000)])
	ui.canvas.finish_shape()
	ui.canvas.tool = "Road"
	ui.canvas.draft.assign([Vector2(1000,40000),Vector2(60000,40000),Vector2(90000,90000)])
	ui.canvas.finish_shape()
	ui._validate()
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await create_timer(0.002).timeout
	assert(not ui.busy and ui.export_report.visible and ui.last_export_report.cell_count == 4)
	assert(ui.export_report.position.x >= 0 and ui.export_report.position.y >= 0)
	assert(ui.export_report.position.x + ui.export_report.size.x <= root.size.x)
	assert(ui.export_report.position.y + ui.export_report.size.y <= root.size.y)
	assert(ui.export_report.summary.text.contains("Compressed package"))
	var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
	assert(capture != "" and DisplayServer.get_name() != "headless")
	await process_frame
	await RenderingServer.frame_post_draw
	assert(root.get_texture().get_image().save_png(capture) == OK)
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("capture_export_report: PASS")
	quit(0)
