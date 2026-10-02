extends SceneTree
## Every public preset reaches a cached native preview without editing the map.
func _initialize() -> void: run.call_deferred()
func check(value: bool, message := "Palette entry check failed") -> void:
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)
func settle_edit(ui: Control, expected_count: int) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while ui.store.track_edit_busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.store.track_edit_busy and ui.track_workbench.source.instances.size() == expected_count,
		"Placement worker publishes exactly once: " + ui.status_label.text)
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
	# Wide approach supports ramp/quarterpipe clearances; rails need a corner.
	bench.add_piece("approach")
	bench.placement.width_cm = 800
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit())
	await settle_edit(ui, 1)
	bench.add_piece("curve")
	check(bench.placement.preview_at(Vector3(40, 0, 0)) and bench.placement.commit())
	await settle_edit(ui, 2)
	var path: Array = ui.store.document.assembled_track.pieces[0].path
	var corner: Array = ui.store.document.assembled_track.pieces[1].path
	var attachment_sample := path.size() / 2
	var placed: String = JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty])
	bench.add_obstacle("ramp_low")
	var unsafe_source: Dictionary = bench.source.duplicate(true)
	unsafe_source.attachments = [bench.placement._attachment(unsafe_source.instances[0], 0)]
	var unsafe_result: Dictionary = JSON.parse_string(ui.store.bridge.compile_track_source(JSON.stringify(unsafe_source)))
	check(unsafe_result.ok and unsafe_result.data.document.assembled_track.obstacles.is_empty()
		and unsafe_result.data.document.assembled_track.issues.any(func(issue: String): return issue.contains("obstacle no longer has safe clearance")),
		"unsafe attachment remains a non-executable draft without obstacle geometry: " + JSON.stringify(unsafe_result.get("error", {})))
	for kind: String in bench.catalogue.obstacle_kinds:
		bench.add_obstacle(kind)
		var target := 1 if kind == "grind_rail" else 0
		var sample := corner.size() / 2 if target == 1 else attachment_sample
		var accepted: bool = bench.placement.preview_attachment(target, sample)
		check(accepted, "Obstacle preview rejected: " + kind + ": " + bench.placement.hint)
		var objects: Dictionary = bench.placement.cache[bench.placement.ghost_key].node.get_meta("objects")
		check(objects.keys().any(func(id: String): return id.begins_with("track-obstacle-")), "Shared preview contains actual obstacle geometry: " + kind)
		check(JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty]) == placed, "Obstacle previews preserve document/history: " + kind)
		await process_frame
	for kind: String in ["jump_panel", "acceleration_panel", "boost_chain", "air_ring"]:
		bench.add_action(kind)
		var accepted: bool = bench.placement.preview_attachment(0, attachment_sample)
		check(accepted, "Action preview rejected: " + kind + ": " + bench.placement.hint)
		var sample: Dictionary = path[attachment_sample]
		ui.preview_camera.frame(bench.PREVIEW.point(sample.position_cm), 35)
		var point: Vector2 = ui.preview_camera.camera.unproject_position(bench.PREVIEW.point(sample.position_cm))
		var hit: Dictionary = bench.placement._surface_at(point)
		check(hit.piece == 0 and hit.sample == attachment_sample, "Surface ray resolves native road sample: " + str(hit) + " point=" + str(point) + " sample=" + str(sample.position_cm) + " camera=" + str(ui.preview_camera.camera.position))
		await process_frame
	bench.cancel_interaction()
	var previous: String = JSON.stringify([ui.store.document, ui.store.undo_stack])
	ui.commands.execute_id("track.piece.straight")
	var event := InputEventMouseButton.new()
	event.position = ui.preview_camera.camera.unproject_position(Vector3(20, 0, 0))
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	check(bench.input(event))
	await settle_edit(ui, 3)
	check(bench.source.instances.size() == 3 and JSON.stringify([ui.store.document, ui.store.undo_stack]) != previous)
	event.pressed = false
	bench.input(event)
	event.pressed = true
	event.double_click = true
	bench.input(event)
	check(not ui.store.track_edit_busy and bench.source.instances.size() == 3, "Release/double-click cannot replay a candidate")
	check(bench.placement.cache.size() <= 24)
	ui.store.dirty = false
	ui.queue_free()
	for _i in 3: await process_frame
	print("palette_entry_validator: PASS (all 70 pieces, attachments and pointer commit)")
	quit()
