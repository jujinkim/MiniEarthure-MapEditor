extends "./import_job.gd"

func start_acquisition(request: Dictionary, python: String, token: String) -> String:
	if pid != -1 or directory != "": return "DownloadJob instances are single use."
	if not LAYER._hex(token, 32): return "Invalid download token."
	identity = token
	stages = ["acquire", "write", "complete"]
	if request.get("provider") == "Copernicus":
		stages = ["acquire", "sample", "write", "complete"]
		progress_limit = 64 * 1024 * 1024
	directory = ProjectSettings.globalize_path("user://import-jobs/" + token)
	if DirAccess.dir_exists_absolute(directory): return "Download job already exists."
	var files := FILES.new()
	for module in ["osm_download.py", "geojson.py", "polygon_geometry.py", "import_layer.py", "projection.py", "osm_extract.py", "osm_area.py", "overture_area.py", "overture_transportation.py", "overture_land_cover.py", "copernicus_dem.py"]:
		var code := FileAccess.get_file_as_string("res://scripts/importers/" + module)
		var error := files.write(directory.path_join(module), code, "") if code != "" else "Download module missing."
		if error != "":
			cleanup()
			return error
	var failure := files.write(directory.path_join("request.json"), JSON.stringify(request), "")
	if failure != "":
		cleanup()
		return failure
	output_path = directory.path_join("layer.json")
	var entry := "overture_area.py" if request.get("provider") == "Overture" else "osm_download.py"
	if request.get("mode") == "overture-transportation": entry = "overture_transportation.py"
	if request.get("mode") == "overture-land-cover": entry = "overture_land_cover.py"
	if request.get("provider") == "Copernicus": entry = "copernicus_dem.py"
	var child := _spawn(python, PackedStringArray(["-B", "-u", directory.path_join(entry), directory.path_join("request.json"), output_path, "--layer-id", token, "--watch-parent"]))
	pid = int(child.get("pid", -1))
	stdio = child.get("stdio")
	stderr_pipe = child.get("stderr")
	if pid <= 0 or stdio == null or stderr_pipe == null:
		shutdown()
		return "Python could not start; choose a Python 3 executable."
	deadline_ms = Time.get_ticks_msec() + 120000
	progress = {"stage":"starting", "completed":0, "total":0, "unit":"bytes"}
	return ""
