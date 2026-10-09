extends SceneTree
const RECOVERY_FIXTURE := preload("res://tests/recovery_fixture.gd")
## Deterministic input/worker ownership checks; no manual or OS acceptance claim.
const EDITOR := preload("res://scripts/editor_main.gd")
const STORE := preload("res://scripts/document_store.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
const FIXTURE := preload("res://tests/track_edit_benchmark.gd")
var ui: Control
var checks := 0

func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)

func settle() -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while ui.store.track_edit_busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.store.track_edit_busy, "worker finishes within bounded test deadline")

func state() -> String:
	return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.dirty])

func pointer(position: Vector2, pressed := false) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = pressed
	event.position = position
	return event

func run() -> void:
	ui = EDITOR.new()
	root.add_child(ui)
	await process_frame
	var bench: Node = ui.track_workbench
	var p: Node = bench.placement
	var source := FIXTURE.fixture(ui.store, 10, true)
	source.actions = [{"id":"jump", "kind":"jump_panel", "piece":"p-0", "sample":1, "height_cm":200, "panel_width_percent":50, "panel_alignment":"center", "landing":null}]
	source.attachments = [{"kind":"fixed_obstacle", "piece":"p-0", "path":"main", "station_cm":400, "side":1}]
	check(ui.store.edit_track(source) == "", "fixture with attached action, obstacle and supports")
	source = ui.store.track_source()
	ui.store.undo_stack.clear()
	ui.store.history_bytes = 0
	var original := state()
	var meshes := PREVIEW.mesh_builds
	var preparations := PREVIEW.preparations
	var view_id: int = bench.view.get_instance_id()
	for index in [2, 0, 1, 0]: bench.select_piece(index)
	check(PREVIEW.mesh_builds == meshes and PREVIEW.preparations == preparations and bench.view.get_instance_id() == view_id, "selection builds no meshes or full preview")
	var origin := PREVIEW.point(source.instances[0].position_cm)
	var grab := origin + Vector3(1.25, 0, 0.5)
	var builds: int = p.geometry_builds
	p.begin_move(0, grab)
	check(not p.preview_at(grab) and not p.commit_move() and state() == original, "stationary click does not snap, edit or create history")
	var self_exit := PREVIEW.point(ui.store.document.assembled_track.pieces[0].path.back().position_cm)
	check(p.preview_at(grab + self_exit - origin) and p.candidate.snap == -1, "entry near its own exit excludes self")
	var other_exit := PREVIEW.point(ui.store.document.assembled_track.pieces[3].path.back().position_cm)
	check(p.preview_at(grab + other_exit - origin + Vector3(0.2,0,0)) and p.candidate.snap == 3, "real-time snap uses another exit within three metres")
	var ghost_id: int = p.ghost.get_instance_id()
	var guides_id: int = p.guides.get_instance_id()
	var guide_mesh: int = p.guides.mesh.get_instance_id()
	check(p.preview_at(grab + Vector3(30, 0, 0)) and p.candidate.snap == -1, "leaving three metre radius releases snap")
	check(p.candidate.item.position_cm == [3000.0,300.0,0.0], "grab offset and elevation retained")
	check(p.ghost.get_instance_id() == ghost_id and p.guides.get_instance_id() == guides_id and p.guides.mesh.get_instance_id() == guide_mesh, "drag reuses ghost, guide node and guide mesh")
	var action_found := false
	var obstacle_found := false
	for id: String in bench.view.get_meta("objects"):
		var node: Node3D = bench.view.get_meta("objects")[id]
		if id.begins_with("action-jump"): action_found = true; check(not node.visible, "attached action original hidden")
		if id.begins_with("track-obstacle-0"): obstacle_found = true; check(not node.visible, "obstacle original hidden")
		if id.begins_with("assembled-support-"): check(node.visible, "supports remain until final recomputation")
	check(action_found and obstacle_found and p.hidden_nodes.size() == p.ghost.get_child_count(), "ghost includes owned road, action and obstacle")
	check(PREVIEW.mesh_builds == meshes and PREVIEW.preparations == preparations and p.geometry_builds == builds, "drag calls no full compilation, preview generation or mesh builds")
	bench.cancel_interaction()
	check(state() == original, "cancelled preview retains exact document/history")
	for node: Node3D in bench.view.get_meta("objects").values(): check(node.visible, "cancel restores originals")
	# Only the final motion in a frame is solved; release independently samples its
	# latest position, even before the queued motion has had a process tick.
	ui.preview_camera.frame(origin, 100)
	var camera: Camera3D = ui.preview_camera.camera
	p.begin_move(0, grab)
	var updates: int = p.pointer_updates
	for step in 8:
		var motion := InputEventMouseMotion.new()
		motion.position = camera.unproject_position(grab + Vector3(10 + step,0,0))
		motion.button_mask = MOUSE_BUTTON_MASK_LEFT
		p.input(motion)
	check(p.pointer_updates == updates, "motion events coalesce until frame")
	p._process(0)
	check(p.pointer_updates == updates + 1, "one latest motion processed per frame")
	var position_before: Vector3 = camera.position
	ui.canvas.zoom = 2.5
	var zoom_before: float = ui.canvas.zoom
	var view_before: Variant = ui.canvas.get("pan")
	p.input(pointer(camera.unproject_position(grab + Vector3(23,0,0))))
	check(ui.store.track_edit_busy and ui.store.track_source().instances[0].position_cm[0] == 2300 and ui.store.undo_stack.size() == 1, "release publishes draft and one history command immediately")
	check(ui.commands.reason("edit.delete") == "" and ui.commands.reason("file.save") == "" and ui.commands.reason("file.export_map") == "", "automatic preparation leaves edits and explicit file commands available")
	check(not ui.operation_dim.visible, "automatic preparation has no dim")
	bench.select_piece(4)
	check(ui.commands.reason("view.frame") == "" and bench.selected == 4, "camera and selection remain enabled during worker")
	await settle()
	check(bench.source.instances[0].position_cm == [2300.0,300.0,0.0] and ui.store.undo_stack.size() == 1, "latest release applied once with one Undo")
	var command: Dictionary = ui.store.undo_stack[0].duplicate(true)
	command.erase("bytes")
	check(ui.store.history_bytes == JSON.stringify(command).to_utf8_buffer().size() and ui.store.history_bytes <= ui.store.HISTORY_BYTES, "track memento uses shared serialized Undo budget")
	check(bench.selected == 4, "selection made during worker is retained")
	check(camera.position == position_before and ui.canvas.zoom == zoom_before and ui.canvas.get("pan") == view_before, "content map ID edit retains camera and plan navigation")
	check(ui.store.document.assembled_track.authoring.original_seed == source.original_seed, "seed provenance retained")
	var after := state()
	ui.store.poll_track_edit()
	check(state() == after, "completed response cannot install twice")
	ui._history(false)
	await settle()
	check(bench.source == source and ui.store.redo_stack.size() == 1, "worker Undo restores source and whole derived document")
	ui._history(true)
	await settle()
	check(bench.source.instances[0].position_cm[0] == 2300 and ui.store.undo_stack.size() == 1, "worker Redo restores exactly one command")
	var before_snap: Dictionary = bench.source.duplicate(true)
	origin = PREVIEW.point(before_snap.instances[0].position_cm)
	p.begin_move(0, origin)
	p.preview_at(other_exit + Vector3(0.1,0,0))
	check(p.candidate.snap == 3 and p.commit_move(), "release snapped move to worker")
	p.cancel()
	await settle()
	check(bench.source.connections.size() == before_snap.connections.size() + 1 and bench.source.connections.has({"from":"p-3", "to":"p-0"}), "snapped move adds one explicit connection")
	check(bench.source.paths == before_snap.paths and bench.source.instances.slice(1) == before_snap.instances.slice(1), "move does not rewrite routes or move neighbouring pieces")
	ui._history(false)
	await settle()
	# Failures and cancelled/stale calculations preserve admitted drafts/history.
	var valid_source: Dictionary = bench.source.duplicate(true)
	for scenario in ["failure", "cancel", "epoch", "request"]:
		var next: Dictionary = valid_source.duplicate(true)
		next.instances[0].position_cm[0] += 111
		if scenario == "failure": next.instances[0].width_cm = 999
		var before: Dictionary = ui.store.document.duplicate(true)
		check(ui.store.start_track_edit(next) == "", "admit " + scenario)
		var admitted := state()
		var job: RefCounted = ui.store.track_edit_job
		if scenario == "cancel": ui.store.cancel_track_edit()
		elif scenario == "epoch": ui.store.command_epoch += 1
		elif scenario == "request": ui.store.track_request_id += 1
		await settle()
		check(state() == admitted and ui.store.document == before and ui.store.track_source() == next and job.consumed, scenario + " retains draft/history and consumes result")
		check(ui.store.start_track_edit(valid_source) == "", "resume validation after " + scenario)
		await settle()
	# Snapshot does not alias a mutable caller, and changed preview nodes only.
	var next: Dictionary = bench.source.duplicate(true)
	next.instances[0].position_cm[0] += 50
	var wanted: int = int(next.instances[0].position_cm[0])
	var untouched: Node3D = bench.view.get_meta("objects")["assembled-road-9"]
	check(ui.store.start_track_edit(next) == "", "immutable request admitted")
	next.instances[0].position_cm[0] = 99999
	await settle()
	check(bench.source.instances[0].position_cm[0] == wanted, "worker input isolated from caller mutations")
	check(bench.view.get_meta("objects")["assembled-road-9"] == untouched, "unchanged preview object reused after commit")
	var cached: Dictionary = ui.store.track_preview_cache
	var cache_bytes := var_to_bytes(cached)
	var reused := PREVIEW.prepare(ui.store.document, ui.store.bridge, cached)
	var fresh := PREVIEW.prepare(ui.store.document, ui.store.bridge)
	check(var_to_bytes(reused) == var_to_bytes(fresh) and var_to_bytes(cached) == cache_bytes, "reused geometry equals fresh geometry and leaves prior preparation immutable")
	# All gesture cancellation routes restore hidden originals and reject release.
	for scenario in ["escape", "focus", "view", "popup"]:
		var before := state()
		origin = PREVIEW.point(bench.source.instances[0].position_cm)
		p.begin_move(0, origin)
		p.preview_at(origin + Vector3(10,0,0))
		match scenario:
			"escape": ui.commands.execute_id("edit.cancel_interaction")
			"focus": ui._notification(Node.NOTIFICATION_APPLICATION_FOCUS_OUT)
			"view": ui._set_view_mode("split")
			"popup": ui.commands.open(); ui.commands.hide()
		check(p.moving_index == -1 and not p.commit_move() and state() == before, scenario + " cancels uncommitted drag")
	var path := ProjectSettings.globalize_path("user://async-track-project")
	check(ui.store.save_project(path) == "" and RECOVERY_FIXTURE.write(ui.store) == "", "worker-edited document saves and creates recovery")
	var reopened := STORE.new()
	var recovered := STORE.new()
	check(reopened.open_project(path) == "" and reopened.document.assembled_track == ui.store.document.assembled_track and reopened.document.get("courses", []) == ui.store.document.get("courses", []), "save/reopen retains compiled shapes, supports and courses")
	check(recovered.recover(RECOVERY_FIXTURE.path(ui.store)) == "" and recovered._signature(recovered.document) == ui.store._signature(ui.store.document), "worker-edited recovery round trip")
	# Opening a different document invalidates the complete job identity.
	check(ui.store.start_track_edit(bench.source) == "", "request before session replacement")
	ui.store.new_track()
	var replacement := state()
	await settle()
	check(state() == replacement and ui.store.undo_stack.is_empty(), "old session result cannot replace new document")
	check(ui.store.start_track_edit(source) == "", "active request before editor shutdown")
	ui.queue_free()
	await process_frame
	print("track_edit_validator: PASS ", checks)
	quit()
