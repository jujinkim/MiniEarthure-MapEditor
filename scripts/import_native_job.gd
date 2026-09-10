extends "./import_job.gd"
## One killable Godot child owns native candidate state; never the live bridge.
const PAYLOADS := preload("./authoring_files.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const REQUEST_LIMIT := 24 * 1024 * 1024
const RESULT_LIMIT := 4096
var layer: RefCounted
var adopting := false
var editor_generation := -1
var document_signature := ""
var layer_signature := ""
var project_source := ""
var selection_signature := ""
var owned_payloads: Array[String] = []
var startup_seen := false
var generated_all := false
var source_rechecked := false

func start_validation(store: RefCounted, candidate: RefCounted, adopt: bool, selection: String, source: String, token: String) -> String:
	if _attempted or cancelled: return "Native import jobs are single use."
	_attempted = true
	if not LAYER._hex(token, 32) or not candidate.has_structures(): return "Invalid structural validation request."
	identity = token
	import_kind = "native"
	layer = candidate
	adopting = adopt
	selection_signature = selection
	project_source = store.project_path
	document_signature = JSON.stringify(store.document).sha256_text()
	layer_signature = JSON.stringify(candidate.value).sha256_text()
	for field in ["assets", "heightmaps"]:
		for record: Dictionary in store.document.get(field, []):
			var path := str(record.path)
			if not SNAPSHOT.safe_relative(path): return "Unsafe native candidate payload path."
			if path not in owned_payloads: owned_payloads.append(path)
	var bytes := JSON.stringify({"request":token, "document":store.document, "layer":candidate.value,
		"project":project_source, "source":source, "expected_payloads":candidate.native_payload_digest if adopt else ""}).to_utf8_buffer()
	if bytes.size() > REQUEST_LIMIT: return "Native import request exceeds 24 MiB."
	var failure := _reserve_directory(token)
	if failure != "": return failure
	failure = PAYLOADS.write_new(directory.path_join("request.json"), bytes)
	if failure == "" and DirAccess.make_dir_absolute(directory.path_join("candidate")) != OK: failure = "Cannot reserve native candidate directory."
	if failure != "":
		cleanup()
		return failure
	output_path = directory.path_join("layer.json")
	timeout_seconds = 120
	deadline_ms = Time.get_ticks_msec() + timeout_seconds * 1000
	stages = ["source", "validate", "snapshot", "open", "generate", "recheck", "complete"]
	progress = {"stage":"starting native validation", "completed":0, "total":1, "unit":"steps"}
	var arguments := PackedStringArray(["--headless", "--no-header", "--log-file", directory.path_join("native.log")])
	var resource_path := ProjectSettings.globalize_path("res://")
	if resource_path != "": arguments.append_array(PackedStringArray(["--path", resource_path]))
	# Normal exports find their embedded/adjacent PCK. Godot consumes --main-pack
	# before exposing script arguments; bare-engine PCK launchers provide it here.
	var pack := OS.get_environment("MAPEDITOR_RESOURCE_PACK")
	if pack != "":
		if not pack.is_absolute_path() or not FileAccess.file_exists(pack):
			cleanup()
			return "MAPEDITOR_RESOURCE_PACK must name the running Editor's absolute PCK path."
		arguments.append_array(PackedStringArray(["--path", pack.get_base_dir(), "--main-pack", pack]))
	arguments.append_array(PackedStringArray(["--", "--native-import-validation", directory, identity, PAYLOADS.digest(bytes)]))
	if not _launch(OS.get_executable_path(), arguments): return "Native validator could not start; retry with a complete Editor installation."
	return ""

func matches(store: RefCounted, selection: String) -> bool:
	return selection == selection_signature and store.project_path == project_source and not store.has_gesture() and JSON.stringify(store.document).sha256_text() == document_signature and JSON.stringify(layer.value).sha256_text() == layer_signature

func _event(line: PackedByteArray) -> void:
	if line.size() > LINE_LIMIT:
		_fail("Native validation event exceeds 4 KiB.")
		return
	# godot-rust prints one initialization banner before the worker starts. It is not
	# part of the result protocol; permit only that bounded startup line once.
	var text := line.get_string_from_utf8()
	if sequence == 0 and not startup_seen and text.length() < 256 and text.begins_with("Initialize godot-rust (") and text.ends_with(")"):
		startup_seen = true
		return
	var parser := JSON.new()
	if parser.parse(text) != OK or parser.data is not Dictionary:
		_fail("Invalid native validation event: " + text.left(256))
		return
	var raw: Dictionary = parser.data
	if raw.get("request") != identity or raw.get("seq") != sequence + 1 or not terminal.is_empty():
		_fail("Stale or duplicate native validation event.")
		return
	var index := stages.find(raw.get("stage"))
	var terminal_event := index == stages.size() - 1
	var limit := RESULT_LIMIT if terminal_event else 16 if raw.get("stage") == "generate" else PAYLOADS.MAX_PAYLOAD_BYTES if raw.get("stage") == "snapshot" else 2 * 1024 * 1024 * 1024 if raw.get("stage") in ["source", "recheck"] else 1
	var unit := "cells" if raw.get("stage") == "generate" else "bytes" if raw.get("stage") in ["source", "snapshot", "recheck", "complete"] else "steps"
	if index < 0 or index < phase or (not terminal_event and index > phase + 1) or raw.get("unit") != unit or not LAYER._count(raw.get("completed"), limit) or not LAYER._count(raw.get("total"), limit) or raw.completed > raw.total:
		_fail("Invalid native validation progress budget/stage.")
		return
	if index == phase and (raw.total != progress.total or raw.completed < progress.completed):
		_fail("Native validation progress regressed.")
		return
	sequence += 1
	phase = index
	progress = raw
	if raw.stage == "generate": generated_all = raw.total > 0 and raw.completed == raw.total
	if raw.stage == "recheck": source_rechecked = raw.total == int(layer.value.source.bytes) and raw.completed == raw.total
	if terminal_event:
		if not LAYER._hex(raw.get("sha256"), 64) or raw.completed != raw.total or raw.total <= 0:
			_fail("Invalid native validation result.")
		else:
			terminal = raw
			# Child waits for this acknowledgement before joining its parent-pipe
			# watcher. EOF instead terminates the child even inside native code.
			stdio.store_string("q")
			stdio.flush()

func _read() -> void:
	super._read()
	if errors != "" and not cancelled: _fail("Native validation diagnostics: " + errors)

func poll(now_ms: int = -1) -> void:
	super.poll(now_ms)
	if not done or not result.get("ok", false): return
	var data: Variant = result.get("data")
	var valid: bool = data is Dictionary and data.get("request") == identity and data.get("ok") is bool
	if valid and data.ok: valid = generated_all and source_rechecked and LAYER._hex(data.get("payloads"), 64)
	elif valid: valid = data.get("error") is Dictionary and data.error.get("code") == "E_IMPORT_NATIVE" and data.error.get("message") is String and data.error.message.length() <= 2000
	if not valid: result = {"ok":false, "error":{"code":"E_IMPORT_NATIVE", "message":"Invalid or incomplete native validation result."}}

func cleanup() -> void:
	if not _owns_directory or (_child_started and not exited): return
	var root := DirAccess.open(directory)
	if root != null and not root.is_link("native.log") and FileAccess.file_exists(directory.path_join("native.log")): DirAccess.remove_absolute(directory.path_join("native.log"))
	if root == null or root.is_link("candidate"):
		super.cleanup()
		return
	var candidate := directory.path_join("candidate")
	var paths: Array[String] = ["document.json"]
	paths.append_array(owned_payloads)
	var directories := {}
	for relative: String in paths:
		var parts := relative.split("/")
		var cursor := candidate
		var safe := true
		for part in parts:
			var parent := DirAccess.open(cursor)
			if parent == null or parent.is_link(part):
				safe = false
				break
			cursor = cursor.path_join(part)
		if not safe: continue
		if FileAccess.file_exists(cursor): DirAccess.remove_absolute(cursor)
		cursor = cursor.get_base_dir()
		while cursor.begins_with(candidate + "/"):
			directories[cursor] = true
			cursor = cursor.get_base_dir()
	var ordered := directories.keys()
	ordered.sort_custom(func(a: String, b: String): return a.length() > b.length())
	for path: String in ordered: DirAccess.remove_absolute(path)
	# rmdir preserves unknown files/directories. Never adopt recovery scratch.
	DirAccess.remove_absolute(candidate)
	super.cleanup()
