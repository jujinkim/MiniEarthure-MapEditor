extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
const JOB := preload("res://scripts/dem_job.gd")
var checks := 0
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func _initialize() -> void: run.call_deferred()

func inspect_controls(node: Node) -> void:
	if node is Button:
		check(not node.text.to_lower().contains("download") and not node.text.contains("official region list"), "no remote source control: " + node.text)
	for child in node.get_children(): inspect_controls(child)

func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	check(ui.import_source_format.item_count == 6, "all six local vector/snapshot formats retained")
	check(ui.osm_panel != null and ui.dem_panel != null, "local crop/streaming and COG panels retained")
	for method in ["_begin_acquisition", "_new_download_job", "_open_download", "_open_overture", "_download_overture"]:
		check(not ui.has_method(method), "retired dispatcher absent: " + method)
	for path in ["res://scripts/download_job.gd", "res://scripts/download_job.gdc", "res://scripts/importers/osm_download.py"]:
		check(not FileAccess.file_exists(path) and not ResourceLoader.exists(path), "retired packaged entry absent: " + path)
	for name in ["overture_area", "overture_transportation", "overture_land_cover", "copernicus_dem"]:
		var code := FileAccess.get_file_as_string("res://scripts/importers/" + name + ".py")
		check(not code.is_empty(), "local helper packaged: " + name)
		for entry in ["def remote_features(", "def read_features(", "def open_remote(", "import urllib", "from overturemaps"]:
			check(not code.contains(entry), "remote helper absent: " + name + " " + entry)
	inspect_controls(ui)
	check(not ui.dem_panel.options().has("allow_download") and not ui.dem_panel.options().has("fallback90"), "local-only DEM options")
	for mode in ["probe", "download", "catalog", "overture", "overture-transportation", "overture-land-cover"]:
		var job := JOB.new()
		check(job.start_local({"mode":mode}, "unused", "a".repeat(32)) != "", "retired mode refused: " + mode)
		check(job.pid == -1 and job.directory == "", "rejection creates no worker or scratch")
	ui.queue_free()
	await process_frame
	print("local_only_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)
