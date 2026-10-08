extends "./import_native_job.gd"
## Preview does not publish. Apply consumes exactly one current result.
var request := {}
var bundle := {}

func start_generation(store: RefCounted, generation: Dictionary, python: String) -> String:
	if _attempted or cancelled or store.has_gesture(): return "Finish the current gesture before generation."
	if generation.get("mode") == "fill" and (store.project_path.is_empty() or store.document.has("assembled_track")): return "Save a free-roam project before completing an area."
	_attempted = true
	identity = Crypto.new().generate_random_bytes(16).hex_encode()
	import_kind = "native"
	adopting = true
	structural = true
	document_signature = JSON.stringify(store.document).sha256_text()
	document_epoch = store.command_epoch
	_store_id = store.get_instance_id()
	project_source = store.project_path
	request = {"kind":"environment","request":identity,"document":store.document.duplicate(true),"project":project_source,"generation":generation.duplicate(true),"python":python}
	var bytes := JSON.stringify(request).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "Generation request exceeds 24 MiB; reduce the selected area."
	var failure := _start_request(bytes)
	deadline_ms = Time.get_ticks_msec()+600000
	return failure

func _source_bytes() -> int: return 0

func matches(store: RefCounted, _selection: String = "") -> bool:
	return not cancelled and store.get_instance_id() == _store_id and store.command_epoch == document_epoch and store.project_path == project_source and not store.has_gesture() and JSON.stringify(store.document).sha256_text() == document_signature

func _decode_command(output: Dictionary) -> void:
	bundle = COMMAND.read_bundle(directory,output)
	var failure := str(bundle.get("error",""))
	if failure == "" and (bundle.get("request") != identity or bundle.get("report") is not Dictionary or bundle.get("payloads") is not Dictionary or bundle.get("snapshot") is not Dictionary): failure = "Invalid environment result."
	if failure == "" and request.generation.mode == "fill" and not bundle.report.get("noop",false):
		_prepared = COMMAND.decode(bundle.get("prepared"),false,true)
		failure = str(_prepared.get("error",""))
	if failure != "":
		bundle = {}
		result = {"ok":false,"error":{"code":"E_IMPORT_NATIVE","message":failure}}

func commit(store: RefCounted, destination: String = "") -> String:
	if store.editing_locked(): return store.EDIT_BUSY
	if _consumed or not done or not exited or bundle.is_empty() or not matches(store): return "Stale or incomplete environment preview. Generate a new preview."
	if not bundle.report.diagnostics.errors.is_empty(): return "Resolve generation diagnostics before applying."
	if request.generation.mode == "fill":
		for path: String in bundle.get("source_hashes",{}):
			if not SNAPSHOT.safe_relative(path) or FileAccess.get_sha256(project_source.path_join(path))!=bundle.source_hashes[path]: return "Project payload changed since generation preview. Generate a new preview."
		if bundle.report.get("noop",false):
			_consumed = true
			return ""
		for path: String in bundle.payloads:
			if not SNAPSHOT.safe_relative(path): return "Unsafe generation payload."
			var failure := FILES_INSTALL(store.project_path.path_join(path),bundle.payloads[path])
			if failure != "": return failure
		_consumed = true
		return store._install_command(_prepared)
	if not destination.is_absolute_path() or DirAccess.dir_exists_absolute(destination) or FileAccess.file_exists(destination): return "Choose a new project directory."
	# A new sibling directory is published with one rename. Until this succeeds
	# neither the live document nor the selected destination is changed.
	var pending := destination+".pending-"+identity
	var failure := SNAPSHOT.copy_to(bundle.snapshot,pending)
	if failure != "": return failure
	if DirAccess.dir_exists_absolute(destination) or FileAccess.file_exists(destination): return "Destination appeared; choose a new project directory."
	if DirAccess.rename_absolute(pending,destination) != OK: return "Cannot publish generated project."
	_consumed = true
	return ""

func FILES_INSTALL(path: String, bytes: PackedByteArray) -> String:
	return SNAPSHOT.install_payload(path,bytes,PAYLOADS.digest(bytes))

func cleanup() -> void:
	if not _owns_directory or (_child_started and not exited): return
	# This subtree is exclusively reserved for this job, never a user source or
	# selected destination. Parent cancellation joins/reaps before retiring it.
	if cancelled and Engine.get_main_loop() is SceneTree:
		# Python's parent watcher exits within 100 ms even while OS.execute was
		# interrupted. Retire scratch after that bounded exit interval.
		var retired := directory
		Engine.get_main_loop().create_timer(.3).timeout.connect(func(): PAYLOADS.remove_scratch(retired))
	else: PAYLOADS.remove_scratch(directory)
	_owns_directory = false
