extends RefCounted
## A single immutable request. The worker owns its bridge and never touches live UI.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var thread := Thread.new()
var token: RefCounted = ClassDB.instantiate("MapKitWorkToken")
var request_id := 0
var session := 0
var epoch := 0
var revision := 0
var context: Dictionary = {}
var consumed := false
var store_id := 0

func start(store: RefCounted, id: int, _operation: String, source: Dictionary, view_context: Dictionary) -> Error:
	store_id = store.get_instance_id()
	request_id = id
	session = store.session_id
	epoch = store.command_epoch
	revision = store.draft_revision
	context = view_context.duplicate(true)
	var snapshot := {"document":store.document.duplicate(true), "source":source.duplicate(true),
		"project_path":store.project_path, "command":{}, "preview":store.track_preview_cache}
	return thread.start(_prepare.bind(snapshot))

func _prepare(snapshot: Dictionary) -> Dictionary:
	token.enter()
	var begin := Time.get_ticks_usec()
	var worker: RefCounted = load("res://scripts/document_store.gd").new()
	worker.document = snapshot.document
	worker.project_path = snapshot.project_path
	var prepared: Dictionary = worker._prepare_track(snapshot.source, false)
	var prepared_at := Time.get_ticks_usec()
	if not prepared.has("error") and not prepared.get("noop", false) and not token.is_cancelled():
		prepared.preview = PREVIEW.prepare(prepared.candidate, worker.bridge, snapshot.preview, token)
		if prepared.preview.has("error"): prepared = {"error":prepared.preview.error}
	token.leave()
	if token.is_cancelled(): return {"error":"Track edit cancelled."}
	prepared.timings = {"prepare_ms":(prepared_at - begin) / 1000.0, "preview_ms":(Time.get_ticks_usec() - prepared_at) / 1000.0}
	return prepared

func matches(store: RefCounted, id: int) -> bool:
	return store_id == store.get_instance_id() and not consumed and not token.is_cancelled() and request_id == id and session == store.session_id and epoch == store.command_epoch and revision == store.draft_revision

func cancel() -> void: token.cancel()

func shutdown() -> void:
	cancel()
	if thread.is_started(): thread.wait_to_finish()

func is_alive() -> bool: return thread.is_alive()
func finish() -> Dictionary: return thread.wait_to_finish()
