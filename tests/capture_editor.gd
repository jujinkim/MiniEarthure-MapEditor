extends SceneTree
func _initialize() -> void:
	_run.call_deferred()
func _run() -> void:
	var scene: PackedScene = load("res://main.tscn")
	var ui := scene.instantiate()
	root.add_child(ui)
	await process_frame
	var failure: String = ui.store.open_project(ProjectSettings.globalize_path("res://addons/mapkit/examples/minimal"))
	if failure != "":
		push_error(failure)
		quit(1)
		return
	ui._preview()
	for _i in range(300):
		await process_frame
		if not ui.busy:
			break
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var error := image.save_png("/tmp/miniearthure-mapeditor.png")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	quit(error)
