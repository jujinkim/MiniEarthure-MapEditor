extends SceneTree
## Standalone initial application screen only; no detailed interaction acceptance.
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var editor: Node = load("res://main.tscn").instantiate()
	root.add_child(editor)
	await process_frame
	assert(editor.store.document.recipe_version == 1)
	assert(is_instance_valid(editor.canvas) and editor.canvas.visible)
	var capture := OS.get_environment("MINIEARTHURE_INITIAL_SCREEN_CAPTURE")
	if not capture.is_empty():
		await RenderingServer.frame_post_draw
		assert(root.get_texture().get_image().save_png(capture) == OK)
	editor.queue_free()
	for _i in 3: await process_frame
	print("initial_screen_validator: PASS")
	quit()
