extends "./import_job.gd"

func start_local(request: Dictionary, python: String, token: String) -> String:
	if pid != -1 or directory != "": return "DemJob instances are single use."
	if not LAYER._hex(token, 32): return "Invalid DEM token."
	identity = token
	if request.get("mode") not in ["dem-plan", "dem"]: return "Unsupported local DEM operation."
	stages = ["acquire", "sample", "write", "complete"]
	progress_limit = 64 * 1024 * 1024
	directory = ProjectSettings.globalize_path("user://import-jobs/" + token)
	if DirAccess.dir_exists_absolute(directory): return "DEM job already exists."
	var files := FILES.new()
	for module in ["geojson.py", "polygon_geometry.py", "import_layer.py", "projection.py", "copernicus_dem.py"]:
		var code := FileAccess.get_file_as_string("res://scripts/importers/" + module)
		var error := files.write(directory.path_join(module), code, "") if code != "" else "DEM module missing."
		if error != "":
			cleanup()
			return error
	var failure := files.write(directory.path_join("request.json"), JSON.stringify(request), "")
	if failure != "":
		cleanup()
		return failure
	output_path = directory.path_join("layer.json")
	var child := _spawn(python, PackedStringArray(["-B", "-u", directory.path_join("copernicus_dem.py"), directory.path_join("request.json"), output_path, "--layer-id", token, "--watch-parent"]))
	pid = int(child.get("pid", -1))
	stdio = child.get("stdio")
	stderr_pipe = child.get("stderr")
	if pid <= 0 or stdio == null or stderr_pipe == null:
		shutdown()
		return "Python could not start; choose a Python 3 executable."
	deadline_ms = Time.get_ticks_msec() + 120000
	progress = {"stage":"starting", "completed":0, "total":0, "unit":"bytes"}
	return ""
