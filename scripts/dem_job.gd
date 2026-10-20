extends "./import_job.gd"
const DEM := preload("./dem_import_layer.gd")

func start_local(request: Dictionary, python: String, token: String) -> String:
	if _attempted or cancelled: return "DemJob instances are single use."
	_attempted = true
	if not LAYER._hex(token, 32): return "Invalid DEM token."
	identity = token
	if request.get("mode") not in ["dem-plan", "dem"]: return "Unsupported local DEM operation."
	import_kind = request.mode
	stages = ["acquire", "sample", "write", "complete"]
	# Acquire progress counts whole tile bytes (at most four 64 MiB tiles).
	progress_limit = DEM.MAX_SOURCES * DEM.MAX_SOURCE_BYTES
	var reservation := _reserve_directory(token)
	if reservation != "": return reservation
	var files := FILES.new()
	# geojson.py imports osm_extract (and its review module) at load time.
	for module in ["geojson.py", "osm_extract.py", "osm_review.py", "polygon_geometry.py", "import_layer.py", "projection.py", "copernicus_dem.py"]:
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
	if not _launch(python, PackedStringArray(["-B", "-u", directory.path_join("copernicus_dem.py"), directory.path_join("request.json"), output_path, "--layer-id", token, "--watch-parent"])):
		return "Python could not start; choose a Python 3 executable."
	deadline_ms = Time.get_ticks_msec() + 120000
	progress = {"stage":"starting", "completed":0, "total":0, "unit":"bytes"}
	return ""
