extends Node
## Private process entrypoint. The supervising Editor owns all scratch and output.
const LAYER := preload("./import_layer.gd")
const PAYLOADS := preload("./authoring_files.gd")
const JOB := preload("./import_native_job.gd")
var directory := ""
var identity := ""
var sequence := 0
var watcher := Thread.new()

func _ready() -> void: run.call_deferred()

static func watch_parent() -> void:
	# No scene calls or native session sharing. EOF on the inherited pipe kills
	# this disposable process even if its main thread is inside generate_chunk.
	if OS.read_buffer_from_stdin(1) != PackedByteArray([113]): OS.kill(OS.get_process_id())

func progress(stage: String, completed: int, total: int) -> void:
	sequence += 1
	var unit := "cells" if stage == "generate" else "bytes" if stage in ["source", "snapshot", "recheck", "complete"] else "steps"
	print(JSON.stringify({"request":identity, "seq":sequence, "stage":stage, "completed":completed, "total":total, "unit":unit}))

func source_error(request: Dictionary, stage: String) -> String:
	var file := FileAccess.open(request.source, FileAccess.READ)
	if file == null: return "Import source is unavailable; retry from the original source."
	var count := file.get_length()
	if count != int(request.layer.source.bytes) or count > 2 * 1024 * 1024 * 1024:
		file.close()
		return "Import source changed after conversion."
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	var completed := 0
	var reported := 0
	progress(stage, 0, count)
	while completed < count:
		var bytes := file.get_buffer(mini(1024 * 1024, count - completed))
		if bytes.is_empty():
			file.close()
			return "Import source changed while reading."
		hash.update(bytes)
		completed += bytes.size()
		# At most 128 progress events for a 2 GiB input, not one per block.
		if completed - reported >= 16 * 1024 * 1024 or completed == count:
			progress(stage, completed, count)
			reported = completed
	var stable: bool = file.get_length() == count and hash.finish().hex_encode() == request.layer.source.sha256
	file.close()
	return "" if stable else "Import source changed after conversion."

func run() -> void:
	var args := OS.get_cmdline_user_args().slice(1)
	if args.size() != 3 or not LAYER._hex(args[1], 32) or not LAYER._hex(args[2], 64): get_tree().quit(2); return
	directory = args[0]
	identity = args[1]
	if watcher.start(watch_parent) != OK: get_tree().quit(2); return
	var read := PAYLOADS.read(directory.path_join("request.json"), JOB.REQUEST_LIMIT)
	var failure := str(read.get("error", ""))
	var hashes := {}
	var prepared := {}
	var request: Variant
	if failure == "":
		if PAYLOADS.digest(read.bytes) != args[2]: failure = "Native validation input changed."
		else: request = JSON.parse_string(read.bytes.get_string_from_utf8())
	if failure == "" and request is Dictionary and request.get("kind") == "terrain":
		finish(preload("./terrain_native_worker.gd").validate(request, directory, identity, progress))
		return
	if failure == "" and request is Dictionary and request.get("kind") == "asset":
		finish(preload("./asset_native_worker.gd").validate(request, directory, identity, progress))
		return
	if failure == "" and request is Dictionary and request.get("kind") == "png":
		finish(preload("./heightmap_native_worker.gd").validate(request, directory, identity, progress))
		return
	if failure == "" and request is Dictionary and request.get("kind") == "dem":
		var output: Dictionary = preload("./dem_native_worker.gd").validate(request, directory, identity, progress)
		finish(output)
		return
	if failure == "" and (request is not Dictionary or request.get("request") != identity or request.get("document") is not Dictionary or request.get("layer") is not Dictionary or request.get("project") is not String or request.get("source") is not String): failure = "Invalid native validation request."
	if failure == "": failure = source_error(request, "source")
	if failure == "":
		progress("validate", 0, 1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var layer := LAYER.new()
		failure = layer.load_value(request.layer, str(request.layer.get("layer_id", "")))
		if failure == "":
			failure = layer.validate_for(store, {"scratch":directory.path_join("candidate"), "hashes":hashes, "expected_payloads":request.get("expected_payloads", ""), "progress":progress})
		if failure == "":
			progress("prepare", 0, 1)
			prepared = store._prepare_command("Adopt import " + str(layer.value.source.name), layer.patches(store))
			failure = str(prepared.get("error", ""))
			if prepared.get("noop", false): failure = "Import command has no changes."
			if failure == "": progress("prepare", 1, 1)
	var output := {"ok":false, "request":identity}
	if failure == "":
		output.payloads = JSON.stringify(hashes).sha256_text()
		failure = JOB.COMMAND.write_bundle(directory, {"prepared":JOB.COMMAND.encode(prepared)}, output)
	# Recheck after command/envelope serialization and disk output as well.
	if failure == "": failure = source_error(request, "recheck")
	# A large source rehash can take time. Recheck project payloads after it as
	# well, so a terrain edit during that interval cannot publish stale geometry.
	if failure == "":
		for path: String in hashes:
			if FileAccess.get_sha256(request.project.path_join(path)) != hashes[path]:
				failure = "Project payload changed before native validation completion."
				break
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE", "message":failure.left(2000)}
	finish(output)

func finish(output: Dictionary) -> void:
	var bytes := JSON.stringify(output).to_utf8_buffer()
	var error := PAYLOADS.write_new(directory.path_join("layer.json"), bytes)
	if error != "":
		# No valid terminal event: parent reports the missing result and retires us.
		OS.kill(OS.get_process_id())
		return
	sequence += 1
	print(JSON.stringify({"request":identity, "seq":sequence, "stage":"complete", "completed":bytes.size(), "total":bytes.size(), "unit":"bytes", "sha256":PAYLOADS.digest(bytes)}))
	watcher.wait_to_finish()
	get_tree().quit(0)
