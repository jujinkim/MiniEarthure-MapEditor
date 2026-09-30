extends RefCounted
## A single immutable request. The worker owns its bridge and never touches live UI.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var thread := Thread.new()
var token: RefCounted = ClassDB.instantiate("MapKitWorkToken")
var request_id := 0
var session := 0
var epoch := 0
var context: Dictionary = {}
var consumed := false
var store_id := 0

func start(store: RefCounted, id: int, operation: String, source: Dictionary, view_context: Dictionary) -> Error:
	store_id = store.get_instance_id()
	request_id = id
	session = store.session_id
	epoch = store.command_epoch
	context = view_context.duplicate(true)
	var snapshot := {"document":store.document.duplicate(true), "source":source.duplicate(true), "operation":operation,
		"project_path":store.project_path, "command":{}, "preview":store.track_preview_cache}
	if operation != "edit":
		var history: Array = store.undo_stack if operation == "undo" else store.redo_stack
		if not history.is_empty(): snapshot.command = history.back().duplicate(true)
	return thread.start(_prepare.bind(snapshot))

func _prepare(snapshot: Dictionary) -> Dictionary:
	token.enter()
	var begin := Time.get_ticks_usec()
	var worker: RefCounted = load("res://scripts/document_store.gd").new()
	worker.document = snapshot.document
	worker.project_path = snapshot.project_path
	var prepared: Dictionary
	if snapshot.operation == "edit": prepared = worker._prepare_track(snapshot.source)
	elif snapshot.command.is_empty(): prepared = {"noop":true}
	else: prepared = worker._prepare_history(snapshot.command, snapshot.operation == "undo")
	var prepared_at := Time.get_ticks_usec()
	if not prepared.has("error") and not prepared.get("noop", false) and not token.is_cancelled():
		prepared.preview = PREVIEW.prepare(prepared.candidate, worker.bridge, snapshot.preview, token)
		if prepared.preview.has("error"): prepared = {"error":prepared.preview.error}
	token.leave()
	if token.is_cancelled(): return {"error":"Track edit cancelled."}
	prepared.timings = {"prepare_ms":(prepared_at - begin) / 1000.0, "preview_ms":(Time.get_ticks_usec() - prepared_at) / 1000.0}
	prepared.operation = snapshot.operation
	return prepared

func matches(store: RefCounted, id: int) -> bool:
	return store_id == store.get_instance_id() and not consumed and not token.is_cancelled() and request_id == id and session == store.session_id and epoch == store.command_epoch

func cancel() -> void: token.cancel()

func shutdown() -> void:
	cancel()
	if thread.is_started(): thread.wait_to_finish()
