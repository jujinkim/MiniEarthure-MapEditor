extends RefCounted
## One run of `acquire_city_sources.py` (search, osm, dem or preflight) in a
## private scratch folder. The script and the offline helper modules it imports
## are copied there so exported Editors run the same code. Progress is one JSON
## object per stdout line; the last line is {"result"} or {"error"}. Single use:
## start → poll every frame until `done` → read `result`; cancel kills the child.
const FILES := preload("./document_files.gd")
const SCRIPT := "acquire_city_sources.py"
const HELPERS := ["osm_area.py", "import_layer.py", "polygon_geometry.py", "projection.py", "copernicus_dem.py"]
const LINE_LIMIT := 256 * 1024
const PIPE_LIMIT := 8 * 1024 * 1024
const READ_BUDGET := 65536
const COMMANDS := ["search", "osm", "dem", "preflight"]

var command := ""
var pid := -1
var directory := ""
var stdio: FileAccess
var stderr_pipe: FileAccess
var buffer := PackedByteArray()
var received := 0
var errors := ""
var exited := false
var exit_code := -1
var output_eof := false
var error_eof := false
var cancelled := false
var done := false
## {stage, done, total} of the latest progress line.
var progress := {}
## {ok:true, data} or {ok:false, error}.
var result := {}
var _answer: Variant = null
var _failure := ""
var _attempted := false

## Arguments follow the subcommand (see the script's --help). "" on start.
func start(python: String, subcommand: String, arguments: PackedStringArray) -> String:
	if _attempted: return "Unknown city source command."
	_attempted = true
	if subcommand not in COMMANDS: return "Unknown city source command."
	if python.strip_edges() == "": return "Python could not start. Choose a Python 3 executable."
	command = subcommand
	var root := ProjectSettings.globalize_path("user://city-source-jobs")
	var error := DirAccess.make_dir_recursive_absolute(root)
	if error != OK: return "Cannot create the source job folder: " + error_string(error)
	var token := "%d-%d" % [Time.get_unix_time_from_system() * 1000, randi()]
	error = DirAccess.make_dir_absolute(root.path_join(token))
	if error != OK: return "Cannot create the source job folder: " + error_string(error)
	directory = root.path_join(token)
	DirAccess.make_dir_absolute(directory.path_join("importers"))
	var files := FILES.new()
	var copies := {SCRIPT: "res://scripts/" + SCRIPT}
	for helper: String in HELPERS: copies["importers/" + helper] = "res://scripts/importers/" + helper
	for target: String in copies:
		var code := FileAccess.get_file_as_string(copies[target])
		var failure: String = files.write(directory.path_join(target), code, "") if code != "" else "Importer module is missing."
		if failure != "":
			cleanup()
			return failure
	var full := PackedStringArray(["-B", "-u", directory.path_join(SCRIPT), subcommand])
	full.append_array(arguments)
	var child := OS.execute_with_pipe(python, full, false)
	pid = int(child.get("pid", -1))
	stdio = child.get("stdio")
	stderr_pipe = child.get("stderr")
	if pid <= 0 or stdio == null or stderr_pipe == null:
		_close()
		cleanup()
		return "Python could not start. Choose a Python 3 executable."
	return ""

func cancel() -> void:
	if cancelled or done: return
	cancelled = true
	if pid > 0 and not exited:
		exited = not OS.is_process_running(pid)
		if not exited and OS.kill(pid) == OK: exited = true

func poll() -> void:
	if done or pid <= 0: return
	_read()
	if not exited:
		exited = not OS.is_process_running(pid)
		if exited: exit_code = OS.get_process_exit_code(pid)
	if not exited: return
	if not cancelled and (not output_eof or not error_eof): return
	if cancelled: result = {"ok":false, "error":_failure if _failure != "" else "Cancelled"}
	elif _failure != "": result = {"ok":false, "error":_failure}
	elif _answer is Dictionary and _answer.has("result"): result = {"ok":true, "data":_answer.result}
	elif _answer is Dictionary and _answer.has("error"): result = {"ok":false, "error":str(_answer.error)}
	else: result = {"ok":false, "error":"Importer exited without a valid result (exit %d). %s" % [exit_code, errors.strip_edges()]}
	done = true
	_close()
	cleanup()

func shutdown() -> void:
	cancel()
	_close()
	cleanup()

func _read() -> void:
	if stdio != null and not output_eof:
		var bytes := stdio.get_buffer(READ_BUDGET)
		received += bytes.size()
		buffer.append_array(bytes)
		output_eof = stdio.get_error() == ERR_FILE_EOF or (exited and bytes.is_empty())
		if received > PIPE_LIMIT: _fail("Invalid city source output.")
		var newline := buffer.find(10)
		while newline >= 0 and not cancelled:
			_line(buffer.slice(0, newline))
			buffer = buffer.slice(newline + 1)
			newline = buffer.find(10)
		if buffer.size() > LINE_LIMIT: _fail("Invalid city source output.")
	if stderr_pipe != null and not error_eof:
		var bytes := stderr_pipe.get_buffer(READ_BUDGET)
		errors = (errors + bytes.get_string_from_utf8()).right(4096)
		error_eof = stderr_pipe.get_error() == ERR_FILE_EOF or (exited and bytes.is_empty())

func _line(line: PackedByteArray) -> void:
	var value: Variant = JSON.parse_string(line.get_string_from_utf8())
	if value is not Dictionary: _fail("Invalid city source output.")
	elif _answer != null: _fail("Invalid city source output.")
	elif value.has("result") or value.has("error"): _answer = value
	elif value.get("stage") is String: progress = value
	else: _fail("Invalid city source output.")

func _fail(message: String) -> void:
	if _failure == "": _failure = message
	cancel()

func _close() -> void:
	if stdio != null: stdio.close()
	if stderr_pipe != null: stderr_pipe.close()
	stdio = null
	stderr_pipe = null

## Removes only the copied modules and the job folder; never caller files.
func cleanup() -> void:
	if directory == "" or (pid > 0 and not exited): return
	for helper: String in HELPERS: DirAccess.remove_absolute(directory.path_join("importers").path_join(helper))
	DirAccess.remove_absolute(directory.path_join("importers"))
	DirAccess.remove_absolute(directory.path_join(SCRIPT))
	DirAccess.remove_absolute(directory)
	directory = ""
