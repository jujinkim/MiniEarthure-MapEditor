extends SceneTree
## Every public preset reaches a cached native preview without editing the map.
func _initialize() -> void: run.call_deferred()
func check(value: bool, message := "Palette entry check failed") -> void:
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var original: String = JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty])
	var bench: Node = ui.track_workbench
	for entry: Dictionary in bench.catalogue.entries:
		check(ui.commands.execute_id("track.piece." + entry.id))
		check(bench.placement.preview_at(Vector3.ZERO), "Preview rejected: " + entry.id + ": " + bench.placement.hint)
		check(bench.placement.ghost.get_child_count() > 0 or (entry.id == "flight_curve" and bench.placement.guides.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size() > 12), "Empty shared geometry: " + entry.id)
		check(JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty]) == original)
		await process_frame
	bench.add_piece("straight")
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit())
	for kind: String in bench.catalogue.obstacle_kinds:
		bench.add_obstacle(kind)
		check(bench.placement.preview_attachment(0, 2), "Obstacle preview rejected: " + kind)
		await process_frame
	for kind: String in ["jump_panel", "acceleration_panel", "boost_chain", "air_ring"]:
		bench.add_action(kind)
		check(bench.placement.preview_attachment(0, 2), "Action preview rejected: " + kind)
		var sample: Dictionary = ui.store.document.assembled_track.pieces[0].path[2]
		ui.preview_camera.frame(bench.PREVIEW.point(sample.position_cm), 35)
		var point: Vector2 = ui.preview_camera.camera.unproject_position(bench.PREVIEW.point(sample.position_cm))
		var hit: Dictionary = bench.placement._surface_at(point)
		check(hit.piece == 0 and hit.sample == 2, "Surface ray resolves native road sample: " + str(hit) + " point=" + str(point) + " sample=" + str(sample.position_cm) + " camera=" + str(ui.preview_camera.camera.position))
		await process_frame
	bench.cancel_interaction()
	var previous: String = JSON.stringify([ui.store.document, ui.store.undo_stack])
	ui.commands.execute_id("track.piece.straight")
	var event := InputEventMouseButton.new()
	event.position = ui.preview_camera.camera.unproject_position(Vector3(20, 0, 0))
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	check(bench.input(event))
	check(bench.source.instances.size() == 2 and JSON.stringify([ui.store.document, ui.store.undo_stack]) != previous)
	event.pressed = false
	bench.input(event)
	event.pressed = true
	event.double_click = true
	bench.input(event)
	check(bench.source.instances.size() == 2, "Release/double-click cannot replay a candidate")
	check(bench.placement.cache.size() <= 24)
	ui.store.dirty = false
	ui.queue_free()
	for _i in 3: await process_frame
	print("palette_entry_validator: PASS (all 70 pieces, attachments and pointer commit)")
	quit()
