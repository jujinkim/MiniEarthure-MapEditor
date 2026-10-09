extends RefCounted
## Publication belongs to this worker. Cancellation is advisory once publication starts.
const STORE_PATH := "res://scripts/document_store.gd"
const PACKAGE := preload("./package_work.gd")
const PAYLOADS := preload("./authoring_files.gd")
var thread := Thread.new()
var token: RefCounted = ClassDB.instantiate("MapKitWorkToken")
var package := PACKAGE.new()

func start(store: RefCounted, request: Dictionary) -> Error:
	var snapshot := {"document":store.document.duplicate(true), "project_path":store.project_path,
		"disk_path":store._disk_path, "disk_digest":store._disk_digest,
		"working":store.working_snapshot().fork(), "dirty":store.dirty,
		"signature":store._saved_signature,"canonical":store._saved_canonical,
		"terrain_state":store.terrain_state,"saved_terrain_state":store.saved_terrain_state,
		"history":(store.undo_stack + store.redo_stack).duplicate(true), "request":request.duplicate(true), "files":store.files}
	return thread.start(_run.bind(snapshot))

func _run(snapshot: Dictionary) -> Dictionary:
	var request: Dictionary = snapshot.request
	if token.is_cancelled(): return _cancelled()
	if request.operation == "save":
		var worker: RefCounted = load(STORE_PATH).new()
		worker.document = snapshot.document
		worker.project_path = snapshot.project_path
		worker._disk_path = snapshot.disk_path
		worker._disk_digest = snapshot.disk_digest
		worker.working = snapshot.working
		worker.dirty = snapshot.dirty
		worker._saved_signature = snapshot.signature
		worker._saved_canonical = snapshot.canonical
		worker.terrain_state = snapshot.terrain_state
		worker.saved_terrain_state = snapshot.saved_terrain_state
		worker.files = snapshot.files
		worker.save_token = token
		worker.undo_stack.assign(snapshot.history)
		for command: Dictionary in snapshot.history: worker.history_bytes += int(command.bytes)
		# The atomic writer may already have renamed by the time Cancel arrives.
		# Report the actual outcome; never manufacture a cancellation after success.
		if token.is_cancelled(): return _cancelled()
		token.enter()
		var failure: String = worker.save_project(request.path)
		token.leave()
		return {"ok":failure == "", "error":failure, "published":failure == "",
			"path":worker.project_path, "digest":worker._disk_digest, "signature":worker._saved_signature, "canonical":worker._saved_canonical}
	var issues: Array = snapshot.document.get("assembled_track", {}).get("geometry_issues" if snapshot.document.get("free_roam",false) else "issues", [])
	if not issues.is_empty(): return {"ok":false, "error":"Fix geometry or the selected race course before execution export: " + " / ".join(issues)}
	package.regional_side_cells = int(request.options.get("regional_side_cells", 0))
	package.working = snapshot.working
	var result: Dictionary = package.run(snapshot.document, snapshot.project_path, "export", Vector2i.ZERO, {}, bool(request.options.get("full", false)))
	if not result.ok: return {"ok":false, "error":str(result.error.code) + ": " + str(result.error.message)}
	var failure := ""
	if token.is_cancelled(): failure = "Operation cancelled; draft retained."
	else: failure = publish(result.data.path, request.path)
	PAYLOADS.remove_scratch(result.data.scratch)
	result.data.path = request.path
	return {"ok":failure == "", "error":failure, "published":failure == "", "data":result.data}

static func publish(source: String, destination: String) -> String:
	if FileAccess.file_exists(destination): return "E_EXPORT_EXISTS: Existing package preserved; choose a new filename."
	var pending := destination + ".pending-" + Crypto.new().generate_random_bytes(8).hex_encode()
	var err := DirAccess.copy_absolute(source, pending)
	if err != OK: return "E_EXPORT_IO: " + error_string(err)
	if FileAccess.get_sha256(source) != FileAccess.get_sha256(pending): return "E_EXPORT_IO: Copy verification failed; pending file retained."
	if FileAccess.file_exists(destination): return "E_EXPORT_EXISTS: Destination appeared; pending copy retained."
	err = DirAccess.rename_absolute(pending, destination)
	return "" if err == OK else "E_EXPORT_IO: Pending copy retained: " + error_string(err)

func _cancelled() -> Dictionary: return {"ok":false, "cancelled":true, "error":"Operation cancelled; draft retained."}
func cancel() -> void:
	token.cancel()
	package.cancel()
func is_alive() -> bool: return thread.is_alive()
func finish() -> Dictionary: return thread.wait_to_finish()
func shutdown() -> void:
	cancel()
	if thread.is_started(): thread.wait_to_finish()
