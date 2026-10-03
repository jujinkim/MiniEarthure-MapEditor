extends SceneTree
const EDITOR := preload("res://scripts/editor_main.gd")
const STORE := preload("res://scripts/document_store.gd")
const JOB := preload("res://scripts/track_edit_job.gd")
const FILES := preload("res://scripts/document_files.gd")
const FIXTURE := preload("res://tests/track_edit_benchmark.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var checks := 0
var ui: Control

class HeldJob extends JOB:
	var held := true
	var snapshot: Dictionary
	func start(store: RefCounted, id: int, _operation: String, source: Dictionary, view_context: Dictionary) -> Error:
		store_id = store.get_instance_id()
		request_id = id
		session = store.session_id
		epoch = store.command_epoch
		revision = store.draft_revision
		context = view_context.duplicate(true)
		snapshot = {"document":store.document.duplicate(true), "source":source.duplicate(true), "operation":"edit", "project_path":store.project_path, "preview":store.track_preview_cache}
		return OK
	func is_alive() -> bool: return held
	func finish() -> Dictionary: return _prepare(snapshot)
	func shutdown() -> void: cancel()

class FailingFiles extends FILES:
	func _publish(_source: String, _destination: String) -> Error: return ERR_FILE_CANT_WRITE

class CancelAfterPublish extends FILES:
	var job: RefCounted
	func _publish(source: String, destination: String) -> Error:
		var result := super._publish(source, destination)
		if not destination.ends_with(".previous"): job.cancel()
		return result

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)

func _initialize() -> void: run.call_deferred()
func release(store: RefCounted) -> void:
	if store.track_edit_job != null:
		store.track_edit_job.held = false
		store.poll_track_edit()

func settle_file(store: RefCounted) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while store.editing_locked() and Time.get_ticks_msec() < deadline:
		release(store)
		store.poll_file_operation()
		await process_frame
	check(not store.editing_locked(), "file operation reaches an unlocked terminal state")

func run() -> void:
	ui = EDITOR.new()
	root.add_child(ui)
	await process_frame
	var store: RefCounted = ui.store
	var results: Array = []
	store.file_operation_finished.connect(func(result: Dictionary): results.append(result))
	var bench: Node = ui.track_workbench
	var p: Node = bench.placement
	check(store.edit_track(FIXTURE.fixture(store, 3, false)) == "", "small validated fixture")
	store.undo_stack.clear(); store.history_bytes = 0
	store.track_job_factory = func(): return HeldJob.new()
	var ticks := [0]
	store.clock = func(): return ticks[0]
	var base: Dictionary = store.document.duplicate(true)
	bench.select_piece(0)
	bench.snap.button_pressed = false
	var original_mesh: Mesh = bench.view.get_meta("objects")["assembled-road-0"].mesh
	p.begin_move(0, Vector3.ZERO)
	check(p.preview_at(Vector3(4,0,0)) and p.commit_move(), "move A accepted")
	p.cancel()
	var first: RefCounted = store.track_edit_job
	check(store.document == base and store.track_source().instances[0].position_cm[0] == 400, "validated document remains separate from draft")
	check(bench.view.get_meta("objects")["assembled-road-0"].mesh == original_mesh and bench.view.get_meta("objects")["assembled-road-0"].transform.origin.x == 4, "release retains transformed existing mesh")
	check(store.undo_stack.size() == 1 and not store.editing_locked() and not ui.operation_dim.visible, "one drag records one command without dim")
	ticks[0] = 499
	check(not store.applying_visible(), "indicator hidden before 500 ms")
	bench.select_piece(1)
	var next: Dictionary = store.track_source()
	next.instances[1].position_cm[0] += 600
	check(bench._commit(next), "edit B while A computes")
	next = store.track_source(); next.instances[0].position_cm[0] += 300
	check(bench._commit(next), "edit A again while first computation runs")
	check(store.track_edit_job == first and not first.token.is_cancelled() and store.pending_track.revision == store.draft_revision, "one running worker and one latest pending snapshot; no cancel-on-edit")
	check(store.undo_stack.size() == 3 and store.track_source().instances[0].position_cm[0] == 700, "coalescing retains all three user commands")
	ticks[0] = 500
	ui._sync_operation_ui()
	check(store.applying_visible() and ui.applying_row.visible and not ui.operation_dim.visible, "continuous edits do not reset the 500 ms timer")
	ui.view_settings.set_value("accessibility", "reduce_ui_motion", true)
	ui._sync_operation_ui()
	check(ui.applying_spinner.reduce_motion and ui.applying_spinner.fraction() < 0 and ui.operation_spinner.reduce_motion, "both indicators respect reduced motion and unknown progress")
	check(store.track_pieces()[0].path[0].position_cm[0] == 700, "selection and attachment path follows current A")
	bench.snap.button_pressed = true
	var item: Dictionary = store.track_source().instances[2].duplicate(true)
	item.position_cm = store.track_pieces()[0].path.back().position_cm.duplicate()
	check(p.solve_item(item, 2).snap == 0, "snapping reads moved draft endpoint")
	p.activate("action", "jump_panel")
	check(p.preview_attachment(0, 0), "attachment targets current draft road")
	p.cancel()
	release(store)
	check(first.consumed and store.document == base and store.track_edit_job != first, "old result consumed without publishing; latest pending starts")
	var current: RefCounted = store.track_edit_job
	check(current.snapshot.source == store.track_source() and store.pending_track.is_empty(), "only latest queued snapshot survives")
	bench.select_piece(0)
	p.begin_move(0, PREVIEW.point(bench.source.instances[0].position_cm))
	check(p.preview_at(Vector3(8,0,0)), "next gesture begins before result arrives")
	var ghost: Node3D = p.ghost
	release(store)
	bench._process(0)
	check(p.ghost == ghost and p.moving_index == 0 and store.validated_revision == store.draft_revision, "worker completion never cancels gesture or swaps its nodes")
	p.cancel(); bench._process(0)
	check(not bench.view.get_meta("draft_pending", false), "final preview swaps after gesture ends")
	var count: int = store.undo_stack.size()
	store.poll_track_edit()
	check(store.undo_stack.size() == count and not current.matches(store, store.track_request_id), "duplicate result cannot install or record history")
	check(store.start_track_history(false) == "" and store.track_source().instances[0].position_cm[0] == 400, "Undo restores source immediately")
	var redo_count: int = store.redo_stack.size()
	check(store.start_track_edit(store.track_source()) == "" and store.redo_stack.size() == redo_count, "no-op preserves redo")
	check(store.start_track_history(true) == "" and store.track_source().instances[0].position_cm[0] == 700, "Redo available before Undo computes")
	release(store); release(store)
	bench.select_piece(1)
	bench.delete_piece()
	check(store.track_source().instances.size() == 2 and store.track_pieces().size() == 2, "delete immediately removes draft selection/path")
	check(store.start_track_history(false) == "" and store.track_source().instances.size() == 3, "pending delete Undo restores stable IDs")
	release(store); release(store)
	var good: Dictionary = store.track_source()
	next = good.duplicate(true); next.instances[0].width_cm = 999
	check(store.start_track_edit(next) == "", "invalid draft accepted for correction")
	var valid: Dictionary = store.document.duplicate(true)
	release(store)
	check(not store.draft_error.is_empty() and store.document == valid and store.track_source() == next, "validation failure retains draft, history and last valid output")
	var failed_revision: int = store.draft_revision
	var bad_save := ProjectSettings.globalize_path("user://invalid-source-save")
	ui._start_save(bad_save)
	await settle_file(store)
	check(not results.back().ok and store.draft_error.revision == failed_revision and store.draft_error.target == bad_save and store.track_source() == next and not FileAccess.file_exists(bad_save.path_join("document.json")), "invalid project save reports revision/target and retains draft without publication")
	check(store.start_track_edit(good) == "" and store.draft_error.is_empty() and store.draft_revision > failed_revision, "next edit clears previous revision error")
	store.cancel_track_edit(); release(store)
	check(store.draft_pending() and store.track_source() == good, "calculation cancellation retains draft")
	store.start_autosave()
	check(not store.editing_locked() and not ui.operation_dim.visible, "asynchronous autosave does not dim or lock editing")
	check(store.autosave() == "", "pending draft recovery retained without dim")
	var snapshot: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(store.recovery_path()))
	check(snapshot.draft == good and snapshot.draft_revision != snapshot.validated_revision and snapshot.document == store.document, "v1 envelope separates pending draft and validated document")
	var restored := STORE.new()
	restored.track_job_factory = func(): return HeldJob.new()
	check(restored.recover(store.recovery_path()) == "" and restored.track_source() == good and restored.draft_pending() and restored.undo_stack.is_empty(), "recovery restores draft in a fresh session and schedules validation")
	release(restored); restored.shutdown_track_edit()
	ui.dialog.use_native_dialog = false
	ui._choose("save")
	check(store.editing_locked() and ui.operation_dim.visible and store.start_track_edit(good) != "", "Save As locks the submitted revision while choosing a destination")
	ui.dialog.hide(); ui.dialog.canceled.emit()
	check(not store.editing_locked() and store.track_source() == good, "cancelling destination picker unlocks without losing draft")
	p.begin_move(0, Vector3.ZERO); p.preview_at(Vector3(2,0,0))
	ui._start_save(ProjectSettings.globalize_path("user://continuous-project"))
	check(store.editing_locked() and ui.operation_dim.visible and p.tool == "", "Save cancels unsubmitted gesture and immediately dims/locks")
	check(store.file_request.revision == store.draft_revision, "save freezes last submitted revision")
	store.cancel_track_edit()
	check(not store.track_edit_job.token.is_cancelled(), "calculation-only cancellation cannot strand a frozen file request")
	check(not ui.commands.execute_id("edit.delete") and not ui.commands.execute_id("edit.undo") and not ui.commands.execute_id("file.save"), "explicit lock blocks registry and duplicate file request")
	check(store.start_track_edit(good) != "" and store.edit_track(good) != "" and store.undo() != "" and store.begin_gesture("blocked") != "" and store.set_free_roam(true) != "", "explicit lock guards direct editing APIs")
	check(not bench.input(InputEventMouseMotion.new()), "explicit lock guards pointer entry")
	check(preload("res://scripts/authoring_files.gd").apply(store, "blocked", [], {}) == store.EDIT_BUSY and ui.canvas.author.apply("blocked", []) == store.EDIT_BUSY, "file-backed direct edits reject before payload work")
	for script in [preload("res://scripts/asset_native_job.gd"), preload("res://scripts/raster_native_job.gd"), preload("res://scripts/import_native_job.gd")]:
		check(script.new().commit(store) == store.EDIT_BUSY, "native adoption is locked before consuming result or writing payloads")
	await settle_file(store)
	check(results.back().ok and not store.dirty and not ui.operation_dim.visible, "latest validated revision saved before unlocking")
	var opened := STORE.new()
	check(opened.open_project(store.project_path) == "" and opened.track_source() == good, "saved file contains frozen latest draft")
	next = good.duplicate(true); next.instances[0].position_cm[0] += 22
	store.start_track_edit(next)
	ui._start_save(store.project_path)
	store.cancel_file_operation()
	check(store.editing_locked(), "cancel keeps lock until owned calculation stops")
	await settle_file(store)
	check(not results.back().ok and store.track_source() == next and store.dirty, "cancel preserves latest draft and previous file")
	store.files = FailingFiles.new()
	ui._start_save(store.project_path)
	await settle_file(store)
	check(not results.back().ok and store.track_source() == next and store.dirty, "write failure unlocks without changing saved baseline")
	store.files = FILES.new()
	# Publication won the race: a subsequent cancellation cannot report cancelled.
	var publish_files := CancelAfterPublish.new()
	store.files = publish_files
	store.file_job_factory = func():
		var job: RefCounted = load("res://scripts/document_file_job.gd").new()
		publish_files.job = job
		return job
	ui._start_save(store.project_path)
	await settle_file(store)
	check(results.back().ok and results.back().published and not store.dirty, "successful atomic publication wins over late cancellation")
	publish_files.job = null
	store.files = FILES.new()
	store.file_job_factory = func(): return load("res://scripts/document_file_job.gd").new()
	var external := FileAccess.open(store.project_path.path_join("document.json"), FileAccess.READ_WRITE)
	external.seek_end(); external.store_string(" "); external.close()
	ui._start_save(store.project_path)
	await settle_file(store)
	check(not results.back().ok and str(results.back().error).contains("changed on disk"), "background save preserves external modification conflict")
	# Structural failure is distinct from executable connection/course diagnostics.
	next = good.duplicate(true); next.connections = []; next.checkpoints = []
	store.start_track_edit(next)
	check(store.start_file_operation("export", ProjectSettings.globalize_path("user://invalid.memap")) == "" and ui.operation_dim.visible, "export freezes and locks pending revision")
	await settle_file(store)
	check(not results.back().ok and str(results.back().error).contains("connections and courses") and not FileAccess.file_exists("user://invalid.memap"), "execution export rejects its snapshot course issues without publishing")
	# Session replacement invalidates an old completed result.
	next = store.track_source(); next.instances[0].position_cm[0] += 1
	store.start_track_edit(next)
	var old: RefCounted = store.track_edit_job
	store.new_track()
	var replacement: Dictionary = store.document.duplicate(true)
	release(store)
	check(old.consumed and store.document == replacement and store.undo_stack.is_empty(), "old session completion cannot mutate new document/history")
	await budget_checks()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("continuous_edit_validator: PASS ", checks)
	quit()

func budget_checks() -> void:
	var store := STORE.new()
	store.new_track()
	store.track_job_factory = func(): return HeldJob.new()
	var source := FIXTURE.fixture(store, 1, false)
	for i in 205:
		source.instances[0].position_cm[0] = i + 1
		check(store.start_track_edit(source) == "", "bounded command " + str(i))
	check(store.undo_stack.size() == 200 and store.history_bytes <= store.HISTORY_BYTES and not store.pending_track.is_empty(), "history and latest pending snapshot remain bounded")
	var before := JSON.stringify([store.track_source(), store.undo_stack, store.redo_stack])
	source.extra = "x".repeat(store.HISTORY_BYTES)
	check(store.start_track_edit(source).contains("16 MiB") and JSON.stringify([store.track_source(), store.undo_stack, store.redo_stack]) == before, "oversized command rejected atomically")
	store.shutdown_track_edit()
