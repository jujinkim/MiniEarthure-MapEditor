extends RefCounted
## Owns one public adapter process and a private, disposable job directory.
const PRESENCE := preload("./import_presence.gd")
var presence: RefCounted
var import_kind := "vector"
const LAYER := preload("./import_layer.gd")
const FILES := preload("./document_files.gd")
const LIMITS := preload("./limit_warnings.gd")
## Total progress/diagnostic bytes over a whole job; lines stay framed at 4 KiB.
const PIPE_LIMIT := 64 * 1024 * 1024
const RUNNING_TIME := "running_time"
const LINE_LIMIT := 4096
const READ_BUDGET := 16384
const MODULES := ["geojson.py", "pbf_places.py", "facility_csv.py", "polygon_geometry.py", "import_layer.py", "projection.py", "vertical.py", "osm_heights.py", "osm_extract.py", "osm_review.py", "osm_area.py", "osm_stream.py", "osm_disk_nodes.py", "osm_generalize.py", "overture_area.py", "overture_transportation.py", "overture_land_cover.py"]
var pid := -1
var identity := ""
var directory := ""
var output_path := ""
var stdio: FileAccess
var stderr_pipe: FileAccess
var buffer := PackedByteArray()
var received := 0
var errors := ""
var exited := false
var exit_code := -1
var cancelled := false
var failure := ""
## Past this point the job keeps running with a warning; Cancel stops it.
var deadline_ms := 0
var timeout_seconds := 120
## PBF streaming: every stage must complete before the next one starts.
var streaming := false
## Limits that warn instead of refusing (see limit_warnings.gd).
var limit_warnings: Array = []
var progress := {}
var terminal := {}
var sequence := 0
var phase := -1
## Progress counters reach the written output size, bounded by its memory guard.
var progress_limit: int = LAYER.MAX_BYTES
var stages := ["read", "parse", "convert", "write", "complete"]
var done := false
var result := {}
var output_eof := false
var error_eof := false
var _owns_directory := false
var _child_started := false
var _attempted := false

func start(source: String, license_name: String, accuracy: String, python: String, token: String, coordinates: Dictionary = {"mode":"local-metres"}, input_format: String = "geojson", source_label: String = "") -> String:
	if _attempted or cancelled: return "ImportJob instances are single use."
	_attempted = true
	if input_format not in ["geojson", "pbf", "osm", "overture", "overture-transportation", "overture-land-cover", "csv"]: return "Unsupported source format."
	if input_format != "geojson" and coordinates.get("mode") != "wgs84-utm": return "Geographic source requires explicit WGS84 origins."
	identity = token
	if not LAYER._hex(token, 32): return "Invalid import request token."
	var input := FileAccess.open(source, FileAccess.READ)
	if input == null: return "Cannot open selected source."
	var size := input.get_length()
	input.close()
	streaming = coordinates.get("osm_stream", false) == true
	if coordinates.has("osm_stream") and (not streaming or input_format != "pbf" or not coordinates.has("osm_bbox")): return "PBF streaming requires PBF input and an explicit crop area."
	if streaming:
		progress_limit = LAYER.MAX_STREAM_SOURCE_BYTES
		timeout_seconds = 900
		stages = ["read", "index_nodes", "index_ways", "index_relations", "select", "parse", "convert", "write", "complete"]
	if coordinates.has("osm_areas") and streaming:
		# Exact area boundaries are read from the captured source before indexing.
		for stage in ["region_nodes", "region_ways", "region_relations"]: stages.insert(stages.find("read") + 1, stage)
	if coordinates.get("osm_city", false):
		if not streaming: return "Automatic city optimization requires PBF streaming."
		stages.insert(stages.find("convert"), "optimize")
	if size <= 0 or size > (LAYER.MAX_STREAM_SOURCE_BYTES if streaming else LAYER.MAX_SOURCE_BYTES): return "Import source exceeds %s or is empty; PBF streaming needs an explicit crop area." % ("64 GiB" if streaming else "256 MiB")
	if streaming: LIMITS.over(limit_warnings, "stream_source_bytes", size, LAYER.WARN_STREAM_SOURCE_BYTES, "PBF source size in bytes")
	else: LIMITS.over(limit_warnings, "source_bytes", size, LAYER.WARN_SOURCE_BYTES, "Import source size in bytes")
	var reservation := _reserve_directory(token)
	if reservation != "": return reservation
	var files := FILES.new()
	for module in MODULES:
		var code := FileAccess.get_file_as_string("res://scripts/importers/" + module)
		var error := files.write(directory.path_join(module), code, "") if code != "" else "Importer module is missing."
		if error != "":
			cleanup()
			return error
	output_path = directory.path_join("layer.json")
	var arguments := PackedStringArray(["-B", "-u", directory.path_join("geojson.py"), source, output_path,
		"--coordinates", str(coordinates.get("mode", "")), "--input-format", input_format, "--license", license_name, "--accuracy", accuracy, "--layer-id", token, "--watch-parent"])
	if source_label != "": arguments.append_array(PackedStringArray(["--source-name", source_label]))
	if coordinates.get("mode") == "wgs84-utm":
		for key in ["origin", "local_origin_m"]:
			if coordinates.get(key) is not Array or coordinates[key].size() != 2:
				cleanup()
				return "Geographic/local origins are required."
		arguments.append_array(PackedStringArray(["--origin", JSON.stringify(coordinates.origin[0], "", false, true), JSON.stringify(coordinates.origin[1], "", false, true), "--local-origin", JSON.stringify(coordinates.local_origin_m[0], "", false, true), JSON.stringify(coordinates.local_origin_m[1], "", false, true)]))
	if coordinates.has("osm_bbox"):
		if input_format not in ["osm", "pbf"] or coordinates.osm_bbox is not Array or coordinates.osm_bbox.size() != 4:
			cleanup()
			return "OSM crop requires four coordinates and an OSM source."
		arguments.append("--osm-bbox")
		for value in coordinates.osm_bbox: arguments.append(JSON.stringify(value, "", false, true))
	if coordinates.has("osm_areas"):
		if not coordinates.has("osm_stream") or coordinates.osm_areas is not Array or coordinates.osm_areas.is_empty() or coordinates.osm_areas.size() > LAYER.MAX_AREAS:
			cleanup()
			return "Administrative area crops need PBF streaming and 1–64 areas."
		LIMITS.over(limit_warnings, "osm_areas", coordinates.osm_areas.size(), LAYER.WARN_AREAS, "Combined administrative areas")
		arguments.append("--osm-areas")
		for value in coordinates.osm_areas: arguments.append(str(int(value)))
	if coordinates.has("csv"):
		if input_format != "csv": cleanup(); return "CSV mapping requires CSV input."
		var csv_path := directory.path_join("csv.json")
		var csv_error: String = files.write(csv_path, JSON.stringify(coordinates.csv), "")
		if csv_error != "": cleanup(); return csv_error
		arguments.append_array(PackedStringArray(["--csv-request", csv_path]))
	if streaming: arguments.append("--osm-stream")
	if coordinates.get("osm_city", false): arguments.append("--osm-city")
	if coordinates.get("osm_review_exclusions",false):
		if not streaming: cleanup(); return "Object exclusion review requires PBF streaming."
		arguments.append("--osm-review-exclusions")
	if coordinates.has("vertical"):
		var vertical_error: String = preload("./import_vertical.gd").options_error(coordinates.vertical, limit_warnings)
		if input_format not in ["osm", "pbf"] or vertical_error != "":
			cleanup()
			return vertical_error if vertical_error != "" else "Vertical conversion requires OSM input."
		var request_path := directory.path_join("vertical.json")
		var write_error: String = files.write(request_path, JSON.stringify(coordinates.vertical), "")
		if write_error != "":
			cleanup()
			return write_error
		arguments.append_array(PackedStringArray(["--vertical-request", request_path]))
	if coordinates.has("height_supplement"):
		var height_error: String = preload("./import_height_supplement.gd").source_error(coordinates.height_supplement, limit_warnings)
		if input_format not in ["osm", "pbf"] or height_error != "":
			cleanup()
			return height_error if height_error != "" else "Height supplements require OSM input."
		var height_path := directory.path_join("height-supplement.json")
		var write_error: String = files.write(height_path, coordinates.height_supplement, "")
		if write_error != "":
			cleanup()
			return write_error
		arguments.append_array(PackedStringArray(["--height-supplement", height_path]))
	if not _launch(python, arguments):
		return "Python could not start. Choose a Python 3 executable and retry."
	deadline_ms = Time.get_ticks_msec() + timeout_seconds * 1000
	progress = {"stage": "starting", "completed": 0, "total": size, "unit": "bytes"}
	return ""

func _reserve_directory(token: String) -> String:
	var root := ProjectSettings.globalize_path("user://import-jobs")
	var parent := DirAccess.open(root.get_base_dir())
	if parent == null or parent.is_link(root.get_file()): return "Import scratch root is unavailable or is a symbolic link."
	var error := DirAccess.make_dir_recursive_absolute(root)
	if error != OK: return "Cannot create import scratch root: " + error_string(error)
	# mkdir is the reservation. A check followed by recursive creation can claim
	# an existing request (including a file/link or another Editor's new request).
	var jobs := DirAccess.open(root)
	if jobs == null: return "Cannot open import scratch root."
	error = jobs.make_dir(token)
	if error != OK: return "Cannot reserve a new import job directory: " + error_string(error)
	directory = root.path_join(token)
	_owns_directory = true
	presence = PRESENCE.new()
	var failure: String = presence.begin(directory, token, import_kind)
	if failure != "": cleanup()
	return failure

func _launch(python: String, arguments: PackedStringArray) -> bool:
	var child := _spawn(python, arguments)
	pid = int(child.get("pid", -1))
	_child_started = pid > 0
	stdio = child.get("stdio")
	stderr_pipe = child.get("stderr")
	if not _child_started or stdio == null or stderr_pipe == null:
		shutdown()
		return false
	return true

func _spawn(python: String, arguments: PackedStringArray) -> Dictionary:
	return OS.execute_with_pipe(python, arguments, false)

func _fail(message: String) -> void:
	if failure == "": failure = message
	cancel()

## Status text for the warnings of this job (empty when none).
func limit_text() -> String:
	return LIMITS.text(limit_warnings)

func cancel() -> void:
	if cancelled or done: return
	cancelled = true
	# Cache exit state: never repeatedly query or signal a reaped/reused PID.
	if pid > 0 and not exited:
		exited = not OS.is_process_running(pid)
		if exited: exit_code = OS.get_process_exit_code(pid)
		else:
			var killed := OS.kill(pid)
			if killed == OK:
				# Godot kill reaps its child; further liveness/exit queries are invalid.
				exited = true
				exit_code = -1
			elif failure == "": failure = "Could not stop importer: " + error_string(killed)

func _event(line: PackedByteArray) -> void:
	if line.size() > LINE_LIMIT:
		_fail("Import IPC line exceeds 4 KiB.")
		return
	var raw: Variant = JSON.parse_string(line.get_string_from_utf8())
	if raw is not Dictionary or raw.get("request") != identity or raw.get("seq") != sequence + 1:
		_fail("Invalid/stale import progress event.")
		return
	sequence += 1
	var index := stages.find(raw.get("stage"))
	if index < phase or index > phase + 1 or index < 0 or not terminal.is_empty() or not LAYER._count(raw.get("completed"), progress_limit) or not LAYER._count(raw.get("total"), progress_limit) or raw.completed > raw.total:
		_fail("Invalid import progress counters/stage.")
		return
	if index == phase and (raw.total != progress.total or raw.completed < progress.completed):
		_fail("Import progress regressed.")
		return
	if streaming and index > phase and phase >= 0 and progress.completed != progress.total:
		_fail("Incomplete PBF streaming stage.")
		return
	if raw.get("unit") != ("features" if raw.get("stage") == "convert" else "entities" if raw.get("stage") == "select" else "steps" if raw.get("stage") == "optimize" else "samples" if raw.get("stage") == "sample" else "bytes"):
		_fail("Invalid import progress unit.")
		return
	phase = index
	progress = raw
	if index == stages.size() - 1:
		if not LAYER._hex(raw.get("sha256"), 64) or raw.completed != raw.total or raw.total > LAYER.MAX_BYTES:
			_fail("Invalid completed import payload.")
		else: terminal = raw

func _read() -> void:
	if stdio != null and not output_eof:
		var bytes := stdio.get_buffer(READ_BUDGET)
		received += bytes.size()
		buffer.append_array(bytes)
		output_eof = stdio.get_error() == ERR_FILE_EOF or (exited and bytes.is_empty())
		if received > PIPE_LIMIT:
			_fail("Import IPC exceeds 64 MiB.")
			buffer.clear()
		else:
			var newline := buffer.find(10)
			while newline >= 0 and not cancelled:
				_event(buffer.slice(0, newline))
				buffer = buffer.slice(newline + 1)
				newline = buffer.find(10)
			if buffer.size() > LINE_LIMIT: _fail("Import IPC line exceeds 4 KiB.")
	if stderr_pipe != null and not error_eof:
		var bytes := stderr_pipe.get_buffer(READ_BUDGET)
		received += bytes.size()
		errors = (errors + bytes.get_string_from_utf8()).right(4096)
		error_eof = stderr_pipe.get_error() == ERR_FILE_EOF or (exited and bytes.is_empty())
		if received > PIPE_LIMIT: _fail("Import IPC exceeds 64 MiB.")

func poll(now_ms: int = -1) -> void:
	if presence != null: presence.poll()
	if done or pid <= 0: return
	_read()
	var now := Time.get_ticks_msec() if now_ms < 0 else now_ms
	# A long run is not a failure: warn and keep Cancel available.
	if not cancelled and now >= deadline_ms:
		var started := deadline_ms - timeout_seconds * 1000
		LIMITS.note(limit_warnings, RUNNING_TIME, maxi(timeout_seconds, int((now - started) / 1000)), timeout_seconds, "Running time in seconds; Cancel stops it")
	if not exited:
		exited = not OS.is_process_running(pid)
		if exited: exit_code = OS.get_process_exit_code(pid)
	if not exited: return
	# Drain remaining bounded pipe bytes over frames before judging completion.
	if not cancelled and (not output_eof or not error_eof): return
	if cancelled:
		result = {"ok": false, "error": {"code": "E_IMPORT_CANCELLED" if failure == "" else "E_IMPORT", "message": failure if failure != "" else "Import cancelled; existing map retained."}}
	elif exit_code != 0 or terminal.is_empty() or not buffer.is_empty():
		result = {"ok": false, "error": {"code": "E_IMPORT_EXIT", "message": "Importer exited without a valid result (exit %d). %s" % [exit_code, errors]}}
	else:
		var file := FileAccess.open(output_path, FileAccess.READ)
		if file == null or file.get_length() != int(terminal.total):
			result = {"ok": false, "error": {"code": "E_IMPORT_OUTPUT", "message": "Import output missing or has wrong size."}}
		else:
			var bytes := file.get_buffer(int(terminal.total))
			var digest := HashingContext.new()
			digest.start(HashingContext.HASH_SHA256)
			digest.update(bytes)
			result = {"ok": true, "data": JSON.parse_string(bytes.get_string_from_utf8())} if digest.finish().hex_encode() == terminal.sha256 else {"ok": false, "error": {"code": "E_IMPORT_OUTPUT", "message": "Import output hash mismatch."}}
		if file != null: file.close()
	done = true
	# The running-time note describes a live job only.
	limit_warnings = limit_warnings.filter(func(entry): return entry.get("code") != RUNNING_TIME)
	_close()
	_finish_result()
	cleanup()

func _finish_result() -> void:
	pass

func _close() -> void:
	if stdio != null: stdio.close()
	if stderr_pipe != null: stderr_pipe.close()
	stdio = null
	stderr_pipe = null
	pid = -1

func shutdown() -> void:
	cancel()
	_close()
	cleanup()

func cleanup() -> void:
	# No child ever started, or its exit was confirmed. Closing pipes alone does
	# not prove exit after a failed kill. A rejected reservation owns nothing.
	if not _owns_directory or (_child_started and not exited): return
	# Relinquish even when unknown files prevent rmdir. Never clean a later owner
	# reusing this token, and never scan/adopt scratch from an earlier process.
	_owns_directory = false
	if presence != null: presence.close()
	presence = null
	# Only files owned by this request; never recursively delete user inputs.
	for name in MODULES + ["vertical.json", "csv.json", "height-supplement.json", "source.pbf.part", "source.pbf", "source-index.sqlite", "node-ids.i64", "node-xy.i32", "copernicus_dem.py", "dem.png.part", "request.json", "source.tif.part", "layer.json"]:
		var path := directory.path_join(name)
		if FileAccess.file_exists(path): DirAccess.remove_absolute(path)
	DirAccess.remove_absolute(directory.path_join(PRESENCE.PENDING))
	var remaining := DirAccess.open(directory)
	if remaining == null: return
	if remaining.list_dir_begin() != OK: return
	var name := remaining.get_next()
	while name == PRESENCE.MARKER: name = remaining.get_next()
	remaining.list_dir_end()
	if name != "": return
	DirAccess.remove_absolute(directory.path_join(PRESENCE.MARKER))
	DirAccess.remove_absolute(directory)
