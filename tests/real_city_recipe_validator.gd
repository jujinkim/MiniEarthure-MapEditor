extends SceneTree
## Real-city recipe v1: parsing (areas or bbox), relative paths, wizard round trip and area lookup
## through the PBF place search (synthetic fixture), including an ambiguous area stop, and the
## report's input fingerprint and code identity over a synthetic adopted document, and the
## -failed set-aside of a failed headless run's outputs.
const SCRATCH := preload("res://tests/validator_scratch.gd")
const UI := preload("res://scripts/editor_main.gd")
const RECIPE := preload("res://scripts/real_city_recipe.gd")
const AUTO := preload("res://scripts/real_city_auto.gd")
## Per-run scratch folder (tests/validator_scratch.gd), removed on exit.
var scratch: String = SCRATCH.fresh(get_script().resource_path.get_file().get_basename())
func _finalize() -> void: SCRATCH.remove(scratch)
var failed := false
## Records the automatic retry without running the Editor steps.
class Retry extends "res://scripts/real_city_recipe.gd":
	var calls: Array = []
	var answers: Array = []
	func _run(_recipe: Dictionary, side_m: float) -> Dictionary:
		calls.append(side_m)
		return answers[calls.size() - 1].duplicate(true)
## A job that is still running after its step timed out.
class Busy extends "res://scripts/real_city_recipe.gd":
	func _busy() -> bool: return true
func check(ok: bool, message: String) -> void:
	if not ok: failed=true; push_error(message)
func _initialize() -> void: run.call_deferred()
## A synthetic adopted document: OSM, facility CSV and a two-tile DEM notice.
func synthetic(pbf_sha := "a".repeat(64), tile_sha := "b".repeat(64), scale := 3, cell_cm := 12800, names := ["seoul.osm.pbf", "N37E126.tif", "N37E127.tif", "shops.csv"]) -> Dictionary:
	var osm := {"import_version":1, "adapter":"osm-extract-v1", "layer_id":"1".repeat(32), "source":{"name":names[0], "bytes":1000, "sha256":pbf_sha, "license":"ODbL", "accuracy":"unknown"},
		"coordinates":{"mode":"wgs84-utm", "pyproj":"3.7.2", "proj":"9.5.1", "osm_crop":{"bbox":[126.95, 37.56, 127.02, 37.63], "areas":[{"source_id":"relation/9"}, {"source_id":"relation/2"}], "shapely":"2.1.2", "geos":"3.13.1"}, "osm_city":{"scale_denominator":scale}},
		"authored_units":{"profile":"city-1to%d" % scale, "source_denominator":scale}}
	var dem := {"import_version":1, "adapter":"copernicus-dem-v1", "dem":{"receipt":{"options":{"source":"tiles"}, "sources":[{"source":{"name":names[1], "bytes":500, "sha256":tile_sha}}, {"source":{"name":names[2], "bytes":600, "sha256":"c".repeat(64)}}]}}}
	var csv := {"import_version":1, "adapter":"facility-csv-v1", "source":{"name":names[3], "bytes":80, "sha256":"d".repeat(64), "license":"CC0", "accuracy":"unknown"}}
	var attributions: Array = [osm, dem, csv].map(func(n): return {"source":"x", "license":"y", "notice":JSON.stringify(n)})
	attributions.append({"source":"hand", "license":"own", "notice":"not json"})
	attributions.append({"source":"hand", "license":"own", "notice":"[1]"})
	return {"cell_size_cm":cell_cm, "traffic":{"driving_side":"right", "signal_style":"horizontal", "basis":"boundary"}, "attributions":attributions}
## A failed headless run's outputs are renamed `-failed`, never deleted (set_aside_failed).
func check_set_aside() -> void:
	var project := scratch.path_join("fail/project")
	var package := scratch.path_join("fail/export/city.memap")
	var outputs := func() -> void:
		DirAccess.make_dir_recursive_absolute(project)
		DirAccess.make_dir_recursive_absolute(package.get_base_dir())
		FileAccess.open(project.path_join("document.json"), FileAccess.WRITE).store_string("{}")
		FileAccess.open(package, FileAccess.WRITE).store_string("pkg")
	var both_kept := func() -> bool: return FileAccess.file_exists(project.path_join("document.json")) and FileAccess.file_exists(package)
	var recipe := {"project":project, "package":package}
	outputs.call()
	var runner: RefCounted = RECIPE.new(null)
	var report := {"ok":false, "failed_step":"dem_review"}
	runner.set_aside_failed(recipe, report)
	check(report.get("failed_outputs") == {"project":project + "-failed", "package":package + "-failed"} and not report.has("set_aside_error"),"a failed run records its set-aside outputs: "+str(report))
	check(FileAccess.file_exists(project + "-failed/document.json") and FileAccess.get_file_as_string(package + "-failed") == "pkg" and not DirAccess.dir_exists_absolute(project) and not FileAccess.file_exists(package),"the project and package are renamed -failed with their contents")
	# Only the project exists (a DEM step failure): only it moves.
	DirAccess.make_dir_recursive_absolute(project)
	FileAccess.open(project.path_join("document.json"), FileAccess.WRITE).store_string("{}")
	report = {"ok":false, "failed_step":"dem_plan"}
	runner.set_aside_failed(recipe, report)
	check(str(report.get("set_aside_error")).contains(project + "-failed") and not report.has("failed_outputs") and FileAccess.file_exists(project.path_join("document.json")),"an existing -failed target refuses and keeps the output: "+str(report))
	DirAccess.remove_absolute(project.path_join("document.json")); DirAccess.remove_absolute(project)
	# An existing package target moves nothing, not even the project.
	outputs.call()
	DirAccess.remove_absolute(project + "-failed/document.json"); DirAccess.remove_absolute(project + "-failed")
	report = {"ok":false, "failed_step":"export_limits"}
	runner.set_aside_failed(recipe, report)
	check(str(report.get("set_aside_error")).contains(package + "-failed") and not report.has("failed_outputs") and both_kept.call() and not DirAccess.dir_exists_absolute(project + "-failed"),"an existing package target keeps both outputs: "+str(report))
	for kept: Array in [[{"ok":false, "failed_step":"outputs"}, runner, "an outputs stop renames nothing"], [{"ok":true}, runner, "a successful run renames nothing"], [{"ok":false, "failed_step":"dem_acquire"}, Busy.new(null), "a running job renames nothing"]]:
		var stopped: Dictionary = kept[0]
		kept[1].set_aside_failed(recipe, stopped)
		check(both_kept.call() and not stopped.has("failed_outputs") and stopped.has("set_aside_error") == (kept[1] is Busy),kept[2]+": "+str(stopped))
	report = {"ok":false, "failed_step":"areas"}
	runner.set_aside_failed({"project":scratch.path_join("fail/none"), "package":scratch.path_join("fail/none.memap")}, report)
	check(not report.has("failed_outputs") and not report.has("set_aside_error"),"no outputs, nothing recorded: "+str(report))
	# A project folder that already existed and was never saved into keeps its name.
	var before := scratch.path_join("fail/before")
	DirAccess.make_dir_recursive_absolute(before)
	report = {"ok":false, "failed_step":"areas"}
	runner.set_aside_failed({"project":before, "package":scratch.path_join("fail/before.memap")}, report)
	check(DirAccess.dir_exists_absolute(before) and not DirAccess.dir_exists_absolute(before + "-failed") and not report.has("failed_outputs") and not report.has("set_aside_error"),"an existing unsaved project folder is not renamed: "+str(report))
	# A package inside the project folder is renamed before the folder moves.
	var nested := scratch.path_join("fail/nested")
	DirAccess.make_dir_recursive_absolute(nested)
	FileAccess.open(nested.path_join("document.json"), FileAccess.WRITE).store_string("{}")
	FileAccess.open(nested.path_join("city.memap"), FileAccess.WRITE).store_string("pkg")
	report = {"ok":false, "failed_step":"export"}
	runner.set_aside_failed({"project":nested, "package":nested.path_join("city.memap")}, report)
	check(report.get("failed_outputs") == {"project":nested + "-failed", "package":nested + "-failed/city.memap-failed"} and not report.has("set_aside_error") and FileAccess.get_file_as_string(nested + "-failed/city.memap-failed") == "pkg" and not FileAccess.file_exists(nested + "-failed/city.memap"),"a nested package loses the success name: "+str(report))
	# A project folder that holds the recipe or report keeps its path; the package still moves.
	var home := scratch.path_join("fail/home")
	DirAccess.make_dir_recursive_absolute(home)
	FileAccess.open(home.path_join("document.json"), FileAccess.WRITE).store_string("{}")
	FileAccess.open(home.path_join("city.memap"), FileAccess.WRITE).store_string("pkg")
	report = {"ok":false, "failed_step":"export"}
	runner.set_aside_failed({"project":home, "package":home.path_join("city.memap")}, report, [home.path_join("recipe.json"), ""])
	check(report.get("failed_outputs") == {"package":home.path_join("city.memap-failed")} and str(report.get("set_aside_error")).contains("recipe or report") and FileAccess.file_exists(home.path_join("document.json")) and not DirAccess.dir_exists_absolute(home + "-failed"),"a project folder holding the recipe keeps its path: "+str(report))
## The recipe report's input fingerprint and code identity (real_city_recipe.gd).
func check_inputs() -> void:
	var recipe := {"version":1, "pbf":"/home/u/src/seoul.osm.pbf", "areas":[{"name":"a"}], "project":"/home/u/out/p", "package":"/home/u/out/m.memap", "python":"/home/u/.venv/bin/python",
		"dem":"/home/u/dem", "dem_zero_m":20.5, "facilities":{"csv":"/home/u/src/shops.csv", "license":"CC0", "name_column":"n", "latitude_column":"lat", "longitude_column":"lon"}, "full_check":true, "mobile_check":false}
	var document := synthetic()
	var source_namespace := RECIPE.layer_identity(recipe,"osm","a".repeat(64))
	var relocated := recipe.duplicate(true)
	relocated.pbf = "/another/source.pbf"; relocated.project = "/another/project"; relocated.package = "/another/map.memap"
	relocated.dem = "/another/tiles"; relocated.python = "/another/python"; relocated.facilities.csv = "/another/facilities.csv"
	check(RECIPE.layer_identity(relocated,"osm","a".repeat(64)) == source_namespace,"output/source paths do not change source-object namespace")
	check(RECIPE.layer_identity(recipe,"osm","b".repeat(64)) != source_namespace and RECIPE.layer_identity(recipe,"facilities","a".repeat(64)) != source_namespace,"source bytes and role bind object namespace")
	relocated.scale = 4
	check(RECIPE.layer_identity(relocated,"osm","a".repeat(64)) != source_namespace,"generation settings bind object namespace")
	var values: Dictionary = RECIPE.inputs(recipe, document, false)
	var digest: String = RECIPE.fingerprint(values)
	check(digest.length() == 64 and values.sources.size() == 4 and values.osm.size() == 1 and values.osm[0].crop.areas == ["relation/2", "relation/9"] and values.osm[0].scale_denominator == 3 and values.osm[0].pyproj == "3.7.2","inputs from the adopted notices: "+str(values))
	check(values.sources.map(func(s): return s.role) == ["dem", "dem", "facilities", "osm"] and values.sources.all(func(s): return s.keys() == ["role", "bytes", "sha256"]),"sources by role then hash, without names: "+str(values.sources))
	check(values.facilities == {"encoding":"utf-8", "category":"", "source_url":"", "accuracy":"unknown", "license":"CC0", "name_column":"n", "latitude_column":"lat", "longitude_column":"lon"} and values.dem == {"zero_m":20.5, "skipped":false} and values.traffic == {"driving_side":"right", "signal_style":"horizontal"},"settings without paths: "+str(values))
	var corrected := document.duplicate(true)
	var notice: Dictionary = JSON.parse_string(corrected.attributions[0].notice)
	notice.coordinates.road_overrides = {"request":{"osm_sha256":"a".repeat(64), "ways":[{"source_id":"way/1", "width_m":20, "lanes":6}]}}
	corrected.attributions[0].notice = JSON.stringify(notice)
	check(RECIPE.fingerprint(RECIPE.inputs(recipe, corrected, false)) != digest, "author road corrections affect the input fingerprint")
	var reversed := document.duplicate(true)
	reversed.attributions.reverse()
	check(RECIPE.inputs(recipe, reversed, false) == values,"attribution order does not matter")
	var text := JSON.stringify(values, "", true, true)
	check(not text.contains("/home/u") and not text.contains("seoul") and not text.contains(".tif") and not text.contains("shops"),"no paths or file names in the canonical JSON: "+text)
	var moved := recipe.duplicate(true)
	for key in ["pbf", "project", "package", "python", "dem"]: moved[key] = "/elsewhere/" + str(moved[key]).get_file()
	moved.facilities.csv = "/elsewhere/renamed.csv"
	moved.full_check = false; moved.mobile_check = true
	check(RECIPE.fingerprint(RECIPE.inputs(moved, synthetic("a".repeat(64), "b".repeat(64), 3, 12800, ["copy.pbf", "t1.tif", "t2.tif", "renamed.csv"]), false)) == digest,"paths, file names and check-only keys keep the fingerprint")
	var dem_zero := recipe.duplicate(true)
	dem_zero.dem_zero_m = 21.0
	for changed: Array in [["PBF hash", recipe, synthetic("e".repeat(64))], ["DEM tile hash", recipe, synthetic("a".repeat(64), "f".repeat(64))], ["scale", recipe, synthetic("a".repeat(64), "b".repeat(64), 4)], ["cell size", recipe, synthetic("a".repeat(64), "b".repeat(64), 3, 6400)], ["dem_zero_m", dem_zero, document]]:
		check(RECIPE.fingerprint(RECIPE.inputs(changed[1], changed[2], false)) != digest,changed[0]+" changes the fingerprint")
	check(RECIPE.fingerprint(RECIPE.inputs(recipe, document, true)) != digest,"a skipped DEM changes the fingerprint")
	check(RECIPE.source_names(document).map(func(s): return s.name) == ["N37E126.tif", "N37E127.tif", "shops.csv", "seoul.osm.pbf"],"source names follow the source order: "+str(RECIPE.source_names(document)))
	var no_dem := recipe.duplicate(true)
	no_dem.erase("dem")
	var empty_dem := recipe.duplicate(true)
	empty_dem.dem = ""
	check(not RECIPE.inputs(no_dem, document, false).has("dem") and RECIPE.inputs(empty_dem, document, false) == RECIPE.inputs(no_dem, document, false),"an empty dem is the same input as no dem")
	var no_osm := document.duplicate(true)
	no_osm.attributions = no_osm.attributions.filter(func(a): return not str(a.notice).contains("osm-extract-v1"))
	check(RECIPE.fingerprint(RECIPE.inputs(recipe, no_osm, false)) == "" and RECIPE.fingerprint(RECIPE.inputs(recipe, {}, false)) == "","no fingerprint before OSM is adopted")
	var code: Dictionary = RECIPE.code_identity()
	var hex := RegEx.create_from_string("^[0-9a-f]{64}$")
	check(hex.search(str(code.get("editor_scripts"))) != null and RECIPE.code_identity() == code and str(code.get("godot")) == Engine.get_version_info().string,"code identity: "+str(code))
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(hex.search(str(code.get("mapkit"))) != null and not code.has("mapkit_reason") and code.mapkit == str(bridge.build_fingerprint()),"code.mapkit is the loaded MapKit build fingerprint: "+str(code))
	# Reference: hashlib with the implementation_fingerprint.py framing; an empty file is framed, not skipped.
	check(RECIPE.digest_files([["b.py", PackedByteArray()], ["a.gd", "x\n".to_utf8_buffer()]]) == "4bf1c6c10c9c11e3b1adf837e7c252d9b685ec93fa8c8d11aee42c3df7aa6d42","empty file digest matches hashlib")
	check(RECIPE._lf(PackedByteArray([97, 13, 10, 98, 13, 99, 13])) == PackedByteArray([97, 10, 98, 13, 99, 13]),"CR LF becomes LF; lone CR stays")
func run() -> void:
	var base := {"version":1,"pbf":"src/a.pbf","areas":[{"name":"가상시"}],"project":"out/p","package":"/abs/m.memap"}
	var parsed: Dictionary = RECIPE.parse(JSON.stringify(base), "/work/recipes")
	check(parsed.ok and parsed.recipe.pbf == "/work/recipes/src/a.pbf" and parsed.recipe.project == "/work/recipes/out/p" and parsed.recipe.package == "/abs/m.memap","paths resolve against the recipe file")
	for broken: Array in [[{"extra":1},"Unknown recipe key"],[{"version":2},"version"],[{"areas":[]},"areas"],[{"areas":[{"source_id":"relation/1"}]},"name"],[{"scale":9},"Scale"],[{"traffic":{"driving_side":"middle"}},"traffic"],[{"facilities":{"csv":"a.csv"}},"facilities needs"]]:
		var value := base.duplicate(true)
		value.merge(broken[0], true)
		var result: Dictionary = RECIPE.parse(JSON.stringify(value))
		check(not result.ok and str(result.error).contains(broken[1]),"refused: "+str(broken[0])+" → "+str(result.get("error")))
	var corrections := {"osm_sha256":"a".repeat(64), "ways":[{"source_id":"way/1", "width_m":20, "lanes":6}]}
	check(RECIPE.parse(JSON.stringify(base.merged({"road_overrides":corrections}))).ok, "snapshot-bound road corrections parse")
	for bad: Variant in [null, {}, {"osm_sha256":"short", "ways":[]}, {"osm_sha256":"a".repeat(64), "ways":[{"source_id":"way/1", "width_m":20, "lanes":17}]}]:
		check(not RECIPE.parse(JSON.stringify(base.merged({"road_overrides":bad}))).ok, "invalid road correction refused")
	var receipt := {"request":corrections, "applied":[{"source_id":"way/1", "width_m":20, "lanes":6, "original_width_m":null, "original_lanes":null}]}
	var raw := {"adapter":"osm-extract-v1", "source":{"sha256":"a".repeat(64)}, "coordinates":{"osm_city":{}, "road_overrides":receipt}}
	var city := preload("res://scripts/import_city.gd")
	check(city.road_override_receipt(raw, {"road_overrides":corrections}) == "", "matching receipt accepted")
	check(city.road_override_receipt(raw, {"osm_city":true}) != "", "unrequested correction refused")
	raw.source.sha256 = "b".repeat(64)
	check(city.road_override_receipt(raw, {}) != "", "snapshot mismatch refused")
	raw.source.sha256 = "a".repeat(64); receipt.applied = []
	check(city.road_override_receipt(raw, {}) != "", "missing correction receipt refused")
	check(not RECIPE.parse("[1]").ok,"a recipe is an object")
	var boxed := base.duplicate(true)
	boxed.erase("areas"); boxed.bbox = [8.4, 60.39, 8.49, 60.435]
	parsed = RECIPE.parse(JSON.stringify(boxed))
	check(parsed.ok and parsed.recipe.bbox == [8.4, 60.39, 8.49, 60.435],"a bbox recipe needs no areas: "+str(parsed))
	for broken: Variant in [[8.4,60.39,8.49],[8.49,60.39,8.4,60.435],[8.4,"60.39",8.49,60.435],[8.4,60.39,181,60.435],"8.4,60.39,8.49,60.435"]:
		boxed.bbox = broken
		check(not RECIPE.parse(JSON.stringify(boxed)).ok,"refused bbox: "+str(broken))
	boxed.bbox = [8.4, 60.39, 8.49, 60.435]; boxed.areas = base.areas
	check(str(RECIPE.parse(JSON.stringify(boxed)).get("error")).contains("one of center"),"areas and bbox are exclusive")
	boxed.erase("areas"); boxed.erase("bbox")
	check(str(RECIPE.parse(JSON.stringify(boxed)).get("error")).contains("one of center"),"a recipe needs areas, a place or a bbox")
	boxed.place = {"name":"Dagali", "source_id":"node/1"}
	parsed = RECIPE.parse(JSON.stringify(boxed))
	check(parsed.ok and parsed.recipe.place.name == "Dagali","a place recipe: "+str(parsed))
	for broken: Variant in [{}, {"name":""}, {"name":"a","admin_level":"8"}, "Dagali"]:
		boxed.place = broken
		check(not RECIPE.parse(JSON.stringify(boxed)).ok,"refused place: "+str(broken))
	boxed.place = {"name":"Dagali"}
	for traffic: Variant in [{}, {"driving_side":"left"}, {"signal_style":"vertical"}]:
		boxed.traffic = traffic
		check(RECIPE.parse(JSON.stringify(boxed)).ok,"traffic keys are optional: "+str(traffic))
	boxed.traffic = {"side":"left"}
	check(not RECIPE.parse(JSON.stringify(boxed)).ok,"unknown traffic key refused")
	# Earlier output is never built over.
	var outputs := scratch.path_join("existing.memap")
	FileAccess.open(outputs, FileAccess.WRITE).store_string("x")
	var guard: RefCounted = RECIPE.new(null)
	var stopped: Dictionary = await guard._run({"package":outputs, "project":scratch.path_join("none")}, false)
	check(not stopped.ok and stopped.failed_step == "outputs","an existing package stops the build first: "+str(stopped))
	DirAccess.remove_absolute(outputs)
	# A limit failure keeps the requested circle and never retries/shrinks.
	var retry := Retry.new(null)
	retry.answers = [{"ok":false, "failed_step":"export", "status":"E_LIMIT"}]
	var stopped_circle: Dictionary = await retry.run({"center":[9.0,55.0], "radius_km":1.5, "project":"/nonexistent/p", "package":"/nonexistent/m.memap"})
	check(retry.calls == [0.0] and not stopped_circle.ok, "circle limit failures remain explicit")
	var circle_recipe := {"version":1, "pbf":"map.pbf", "center":[9.00010012345678,55.00010012345678], "project":"p", "package":"m.memap"}
	check(RECIPE.parse(JSON.stringify(circle_recipe)).ok, "centre with default radius")
	for bad in [0, -1, 21, "1.5"]:
		circle_recipe.radius_km = bad
		check(not RECIPE.parse(JSON.stringify(circle_recipe)).ok, "invalid radius refused")
	check_set_aside()
	check_inputs()
	# Automatic choices (real_city_auto.gd).
	check(AUTO.traffic({"code":"JP","driving_side":"","basis":"subdivision"}) == {"driving_side":"left","signal_style":"horizontal","country":"JP","basis":"subdivision"},"Japan: left, horizontal")
	check(AUTO.traffic({"code":"NO","driving_side":"","basis":"boundary"}).driving_side == "right" and AUTO.traffic({"code":"NO"}).signal_style == "vertical","Norway: right, vertical")
	check(AUTO.traffic({"code":"US","driving_side":"left","basis":"boundary"}).driving_side == "left","a driving_side tag on the country wins")
	check(AUTO.traffic({}) == {"driving_side":"right","signal_style":"horizontal","country":"","basis":"default"},"unknown country keeps the Editor default")
	var jongno := [126.948904, 37.565795, 127.023419, 37.632353]
	check(AUTO.cells(jongno, 3, 12800) == 360,"Jongno at 1:3 is 360 cells: "+str(AUTO.cells(jongno, 3, 12800)))
	var context := {"areas":[{"name":"Osaka","source_id":"relation/2","admin_level":"7","bbox":[135.4,34.6,135.6,34.75],"km2":290.0},{"name":"Chuo","source_id":"relation/3","admin_level":"8","bbox":[135.49,34.66,135.53,34.70],"km2":8.8},{"name":"1-chome","source_id":"relation/4","admin_level":"10","bbox":[135.500,34.668,135.511,34.669],"km2":0.08}],"country":{}}
	var choice: Dictionary = AUTO.extent(context, [135.5016, 34.669], 3, 12800)
	check(choice.kind == "circle" and choice.radius_km == 2.0 and choice.center == [135.5016, 34.669], "place search supplies a fixed circle centre")
	check(AUTO.extent({}, [8.45, 60.42], 1, 12800).radius_km == 2.0, "cell budget never shrinks requested radius")
	var ui := UI.new()
	root.add_child(ui); ui._ensure_import_ui()
	await process_frame
	ui.import_python.text=OS.get_environment("MINIEARTHURE_PYTHON")
	var source := scratch.path_join("places.pbf")
	var output: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/pbf_places_fixture.py"),source]),output,true)==0,"synthetic PBF fixture: "+str(output))
	var hash := FileAccess.get_sha256(source)
	var runner: RefCounted = RECIPE.new(ui)
	var recipe: Dictionary = RECIPE.parse(JSON.stringify({"version":1,"pbf":source,"areas":[{"name":"가상시"}],"project":"p","package":"m.memap"})).recipe
	var areas: Variant = await runner._areas(recipe)
	check(areas is Array and areas.size()==1 and areas[0].name=="가상시","area found by exact name: "+str(runner.report))
	check(not ui.osm_panel.dialog.visible and not ui.osm_panel.search_callback.is_valid(),"recipe search keeps the crop dialog closed")
	recipe.areas = [{"name":"가상시","source_id":"relation/999999"}]
	check(await runner._areas(recipe) == null and runner.report.area_candidates.size()==1 and str(runner.report.error).contains("0 exact matches"),"a wrong source_id stops with the candidates")
	ui.osm_panel.selected_areas = []
	ui.osm_panel.fit_bbox([8.4, 60.39, 8.49, 60.435])
	check(ui.osm_panel.bbox() == [8.4, 60.39, 8.49, 60.435] and ui.osm_panel.enabled.button_pressed and ui.osm_panel.streaming.button_pressed and ui.osm_panel.error() == "","a recipe bbox streams that rectangle: "+str(ui.osm_panel.bbox())+" "+ui.osm_panel.error())
	check(is_equal_approx(ui.import_origin_lon.value, 8.445) and is_equal_approx(ui.import_origin_lat.value, 60.4125),"the bbox centre is the import origin")
	# The wizard's recipe parses back unchanged.
	ui.open_real_city()
	var wizard: ConfirmationDialog = ui.real_city_wizard
	wizard.pbf.text = source
	var japan := {"areas":[], "country":{"code":"JP","name":"日本","driving_side":"left","basis":"boundary"}}
	wizard._found({"places":[{"name":"가상시","admin_level":"8","source_id":"relation/1","issue":"","bbox":[9,55,9.0002,55.0002],"context":japan}],
		"anchors":[{"name":"가상마을","source_id":"node/5","kind":"place=village","tier":2,"point":[9.0001,55.0001],"issue":"","context":japan}]})
	wizard.project.text = "/tmp/p"; wizard.package.text = "/tmp/m.memap"; wizard.scale.value = 4; wizard.signal_style.select(2)
	var built: Dictionary = RECIPE.parse(JSON.stringify(wizard.recipe()))
	check(built.ok and built.recipe.center == [9.0001, 55.0001] and built.recipe.radius_km == 2.0 and built.recipe.scale == 4 and built.recipe.traffic == {"signal_style":"vertical"} and not built.recipe.has("dem"),"wizard recipe: "+str(built))
	check(wizard.traffic().driving_side == "left" and wizard.traffic().signal_style == "vertical","automatic side from the country, explicit signals: "+str(wizard.traffic()))
	wizard.matches.select(1, false); wizard._selected(1, true)
	check(wizard.matches.get_selected_items() == PackedInt32Array([1]),"a named place is selected alone")
	wizard.signal_style.select(0)
	built = RECIPE.parse(JSON.stringify(wizard.recipe()))
	check(built.ok and built.recipe.center == [9.0001, 55.0001] and not built.recipe.has("traffic") and not built.recipe.has("areas"),"wizard place recipe: "+str(built))
	check(wizard.extent().kind == "circle" and wizard.status.text.contains("km"),"the wizard shows the automatic extent: "+wizard.status.text)
	wizard.hide()
	var supplemental := scratch.path_join("regional-buildings.json")
	var coverage := [8.97,54.98,9.03,55.02]
	var auxiliary_snapshot := {"type":"FeatureCollection","release":"2026-10-21.0","bbox":coverage,"features":[{"type":"Feature","properties":{"id":"synthetic-reserved","height":4,"sources":[]},"geometry":{"type":"Polygon","coordinates":[[[9.001,55.001],[9.0011,55.001],[9.0011,55.0011],[9.001,55.0011],[9.001,55.001]]]}}]}
	var snapshot_file := FileAccess.open(supplemental,FileAccess.WRITE)
	snapshot_file.store_string(JSON.stringify(auxiliary_snapshot));snapshot_file.close()
	# The complete worker path retains high-precision centre/radius provenance.
	var fixed := {"version":1, "pbf":source, "center":[9.00010012345678,55.00010012345678], "radius_km":1.5,
		"project":scratch.path_join("circle/project"), "package":scratch.path_join("circle/city.memap"), "full_check":false,
		"regional":{"version":1,"road_conflicts":"trim_buildings","profile":{"architecture":"nordic_timber","climate":"cold","settlement":"village","terrain":"mountain"}},
		"road_overrides":{"osm_sha256":hash, "ways":[{"source_id":"way/2", "width_m":20, "lanes":6}]},
		"traffic":{"driving_side":"right", "signal_style":"horizontal"}}
	fixed.regional.buildings = {"path":supplemental,"sha256":FileAccess.get_sha256(supplemental),"release":"2026-10-21.0","bbox":coverage,"source_url":"https://example.invalid/synthetic","license":"MIT synthetic"}
	var circular: Dictionary = await runner.run(fixed)
	check(circular.ok and not ui.store.document.get("play_area", []).is_empty(), "fixed circle worker, adoption and v1 export: " + str(circular.get("status", "")))
	check(ui.store.document.get("roads", []).any(func(r): return r.get("widths_cm", []).any(func(w): return int(w) == 667) and r.get("markings", {}).get("lanes") == 6), "road correction survives worker, adoption and v1 export")
	check(circular.get("inputs", {}).get("osm", []).any(func(o): return city.same_road_overrides(o.get("road_overrides", {}), fixed.road_overrides)), "adopted correction enters report fingerprint")
	check(circular.get("inputs", {}).get("osm", []).any(func(o): return city.same_regional(o.get("regional"), city.regional_input(fixed.regional))),"regional inputs enter the report fingerprint")
	check(ui.store.document.get("environment", {}).get("architecture") == "nordic_timber" and circular.has("regional"),"regional worker prepares, applies and exports the selected profile: "+JSON.stringify(circular))
	check(ui.store.document.buildings.any(func(b): return str(b.id).begins_with("regional-ov-synthetic-reserved-")),"supplemental building survives complete recipe")
	check(circular.get("road_footprint_corrections") is Array,"recipe exposes the authorized footprint correction receipt")
	check(ui.store.document.attributions.any(func(a): return str(a.source).contains("Overture Buildings") and str(a.license).contains("MIT synthetic")),"source credits are readable without parsing provenance")
	for attribution: Dictionary in ui.store.document.attributions:
		var source_receipt: Variant = JSON.parse_string(attribution.notice)
		if source_receipt is Dictionary and source_receipt.get("adapter") == "osm-extract-v1":
			check(source_receipt.coordinates.osm_city.get("auxiliary_building_obstacles") == 1 and not attribution.notice.contains("regional_building_blockers"),"auxiliary envelope is transient; only its count is reported")
	if circular.ok:
		var first := ui.store.document.duplicate(true)
		var repeated := fixed.duplicate(true)
		repeated.project = scratch.path_join("repeat/project"); repeated.package = scratch.path_join("repeat/city.memap")
		var repeat_report: Dictionary = await runner.run(repeated)
		check(repeat_report.ok,"repeat identical recipe in a new destination: "+str(repeat_report.get("status","")))
		var second := ui.store.document.duplicate(true)
		for value: Dictionary in [first,second]:
			value.provenance.erase("first_created");value.provenance.erase("last_edited")
		var changed: Array = first.keys().filter(func(key): return JSON.stringify(first[key],"",true,true) != JSON.stringify(second.get(key),"",true,true))
		check(changed.is_empty(),"recipe object identities, placement and classification repeat; changed fields: "+str(changed))
	# Regional fill shares the owned-worker cancellation/stale-result contract.
	if circular.ok:
		check(ui.store.undo() == "", "undo regional composition")
		var snapshot: String = ui.store._signature(ui.store.document)
		var cancelled := preload("res://scripts/generation_native_job.gd").new()
		check(cancelled.start_generation(ui.store,{"mode":"fill","regional":fixed.regional},OS.get_environment("MINIEARTHURE_PYTHON")) == "", "start regional cancellation")
		cancelled.cancel()
		await wait_regional(cancelled)
		check(cancelled.commit(ui.store) != "" and ui.store._signature(ui.store.document) == snapshot,"cancelled regional worker preserves previous result")
		cancelled.cleanup()
		var stale := preload("res://scripts/generation_native_job.gd").new()
		check(stale.start_generation(ui.store,{"mode":"fill","regional":fixed.regional},OS.get_environment("MINIEARTHURE_PYTHON")) == "", "start regional stale preview")
		await wait_regional(stale)
		check(stale.result.get("ok", false),"regional fill review ready: "+str(stale.result.get("error")))
		var seed: int = ui.store.document.seed
		check(ui.store.apply_command("Changed seed",[{"field":"seed","before":seed,"after":seed+1}]) == "", "mutate after regional preview")
		check(ui.store.undo() == "", "restore content with a new command epoch")
		check(stale.commit(ui.store) != "" and ui.store._signature(ui.store.document) == snapshot,"stale regional preview rejects even after content restoration")
		stale.cleanup()
	ui.preview_enabled = false
	wizard.hide()
	check(FileAccess.get_sha256(source)==hash,"source PBF preserved")
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("real_city_recipe_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func wait_regional(job: RefCounted) -> void:
	var deadline := Time.get_ticks_msec() + 30000
	while (not job.done or not job.exited) and Time.get_ticks_msec() < deadline:
		job.poll()
		await process_frame
	if not job.done or not job.exited: job.shutdown()
	check(job.done and job.exited,"regional worker completed and reaped")
