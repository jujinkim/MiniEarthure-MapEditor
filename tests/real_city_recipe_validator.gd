extends SceneTree
## Real-city recipe v1: parsing (areas or bbox), relative paths, wizard round trip and area lookup
## through the PBF place search (synthetic fixture), including an ambiguous area stop.
const UI := preload("res://scripts/editor_main.gd")
const RECIPE := preload("res://scripts/real_city_recipe.gd")
const AUTO := preload("res://scripts/real_city_auto.gd")
var failed := false
## Records the automatic retry without running the Editor steps.
class Retry extends "res://scripts/real_city_recipe.gd":
	var calls: Array = []
	var answers: Array = []
	func _run(_recipe: Dictionary, side_m: float) -> Dictionary:
		calls.append(side_m)
		return answers[calls.size() - 1].duplicate(true)
func check(ok: bool, message: String) -> void:
	if not ok: failed=true; push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var base := {"version":1,"pbf":"src/a.pbf","areas":[{"name":"가상시"}],"project":"out/p","package":"/abs/m.memap"}
	var parsed: Dictionary = RECIPE.parse(JSON.stringify(base), "/work/recipes")
	check(parsed.ok and parsed.recipe.pbf == "/work/recipes/src/a.pbf" and parsed.recipe.project == "/work/recipes/out/p" and parsed.recipe.package == "/abs/m.memap","paths resolve against the recipe file")
	for broken: Array in [[{"extra":1},"Unknown recipe key"],[{"version":2},"version"],[{"areas":[]},"areas"],[{"areas":[{"source_id":"relation/1"}]},"name"],[{"scale":9},"Scale"],[{"traffic":{"driving_side":"middle"}},"traffic"],[{"facilities":{"csv":"a.csv"}},"facilities needs"]]:
		var value := base.duplicate(true)
		value.merge(broken[0], true)
		var result: Dictionary = RECIPE.parse(JSON.stringify(value))
		check(not result.ok and str(result.error).contains(broken[1]),"refused: "+str(broken[0])+" → "+str(result.get("error")))
	check(not RECIPE.parse("[1]").ok,"a recipe is an object")
	var boxed := base.duplicate(true)
	boxed.erase("areas"); boxed.bbox = [8.4, 60.39, 8.49, 60.435]
	parsed = RECIPE.parse(JSON.stringify(boxed))
	check(parsed.ok and parsed.recipe.bbox == [8.4, 60.39, 8.49, 60.435],"a bbox recipe needs no areas: "+str(parsed))
	for broken: Variant in [[8.4,60.39,8.49],[8.49,60.39,8.4,60.435],[8.4,"60.39",8.49,60.435],[8.4,60.39,181,60.435],"8.4,60.39,8.49,60.435"]:
		boxed.bbox = broken
		check(not RECIPE.parse(JSON.stringify(boxed)).ok,"refused bbox: "+str(broken))
	boxed.bbox = [8.4, 60.39, 8.49, 60.435]; boxed.areas = base.areas
	check(str(RECIPE.parse(JSON.stringify(boxed)).get("error")).contains("one of areas"),"areas and bbox are exclusive")
	boxed.erase("areas"); boxed.erase("bbox")
	check(str(RECIPE.parse(JSON.stringify(boxed)).get("error")).contains("one of areas"),"a recipe needs areas, a place or a bbox")
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
	var outputs := ProjectSettings.globalize_path("user://existing.memap")
	FileAccess.open(outputs, FileAccess.WRITE).store_string("x")
	var guard: RefCounted = RECIPE.new(null)
	var stopped: Dictionary = await guard._run({"package":outputs, "project":"user://none"}, false)
	check(not stopped.ok and stopped.failed_step == "outputs","an existing package stops the build first: "+str(stopped))
	DirAccess.remove_absolute(outputs)
	# A place's automatic area over a package limit is retried as the square, then smaller squares.
	var area_fail := {"ok":false, "failed_step":"export", "status":"E_LIMIT: manifest or expanded package exceeds limits", "extent":{"kind":"area"}}
	var retry := Retry.new(null)
	var square_fail := {"ok":false, "failed_step":"osm_adopt", "status":"Building and placement checks need more work than the game allows; the game refuses maps beyond this", "extent":{"kind":"bbox", "side_m":5000.0}}
	retry.answers = [area_fail, square_fail, {"ok":true}]
	var first_project := ProjectSettings.globalize_path("user://retry-project")
	DirAccess.make_dir_recursive_absolute(first_project)
	var retried: Dictionary = await retry.run({"place":{"name":"x"}, "project":first_project, "package":first_project + ".memap"})
	check(retry.calls == [0.0, 5000.0, 3750.0] and retried.ok and retried.attempts.size() == 2 and retried.attempts[0].failed_step == "export","limit failures retry with shrinking squares: "+str(retry.calls))
	check(retried.attempts[0].get("project") == first_project + "-attempt-1" and DirAccess.dir_exists_absolute(first_project + "-attempt-1") and not DirAccess.dir_exists_absolute(first_project),"the first attempt's project is kept aside")
	DirAccess.remove_absolute(first_project + "-attempt-1")
	retry = Retry.new(null)
	square_fail.extent.side_m = 2500.0
	retry.answers = [square_fail, {"ok":true}]
	await retry.run({"place":{"name":"x"}, "project":"/nonexistent/p", "package":"/nonexistent/m.memap"})
	check(retry.calls == [0.0],"no square below 2 km: "+str(retry.calls))
	for case: Array in [[{"areas":[]}, area_fail], [{"place":{"name":"x"}}, {"ok":false, "failed_step":"osm_review", "status":"E_IMPORT_NATIVE: road point out of range", "extent":{"kind":"area"}}]]:
		retry = Retry.new(null)
		retry.answers = [case[1], {"ok":true}]
		case[0].merge({"project":"/nonexistent/p", "package":"/nonexistent/m.memap"})
		await retry.run(case[0])
		check(retry.calls == [0.0],"no retry: "+str(case))
	# Automatic choices (real_city_auto.gd).
	check(AUTO.traffic({"code":"JP","driving_side":"","basis":"subdivision"}) == {"driving_side":"left","signal_style":"horizontal","country":"JP","basis":"subdivision"},"Japan: left, horizontal")
	check(AUTO.traffic({"code":"NO","driving_side":"","basis":"boundary"}).driving_side == "right" and AUTO.traffic({"code":"NO"}).signal_style == "vertical","Norway: right, vertical")
	check(AUTO.traffic({"code":"US","driving_side":"left","basis":"boundary"}).driving_side == "left","a driving_side tag on the country wins")
	check(AUTO.traffic({}) == {"driving_side":"right","signal_style":"horizontal","country":"","basis":"default"},"unknown country keeps the Editor default")
	var jongno := [126.948904, 37.565795, 127.023419, 37.632353]
	check(AUTO.cells(jongno, 3, 12800) == 360,"Jongno at 1:3 is 360 cells: "+str(AUTO.cells(jongno, 3, 12800)))
	var context := {"areas":[{"name":"Osaka","source_id":"relation/2","admin_level":"7","bbox":[135.4,34.6,135.6,34.75],"km2":290.0},{"name":"Chuo","source_id":"relation/3","admin_level":"8","bbox":[135.49,34.66,135.53,34.70],"km2":8.8},{"name":"1-chome","source_id":"relation/4","admin_level":"10","bbox":[135.500,34.668,135.511,34.669],"km2":0.08}],"country":{}}
	var choice: Dictionary = AUTO.extent(context, [135.5016, 34.669], 3, 12800)
	check(choice.kind == "area" and choice.area.source_id == "relation/3","the largest containing area that fits: "+str(choice))
	choice = AUTO.extent({"areas":[context.areas[2]]}, [135.5016, 34.669], 3, 12800)
	check(choice.kind == "bbox" and choice.side_m == 5000.0 and choice.cells <= AUTO.MAX_CELLS,"a tiny area gives the 5 km square: "+str(choice))
	check(absf((choice.bbox[3] - choice.bbox[1]) * AUTO.M_PER_DEGREE - 5000.0) < 1.0 and absf((choice.bbox[0] + choice.bbox[2]) * 0.5 - 135.5016) < 0.000002,"the square is centred on the place")
	choice = AUTO.extent({}, [8.45, 60.42], 1, 12800)
	check(choice.kind == "bbox" and choice.side_m < 5000.0 and choice.cells <= AUTO.MAX_CELLS,"at 1:1 the square shrinks to the cell budget: "+str(choice))
	var ui := UI.new()
	root.add_child(ui); ui._ensure_import_ui()
	await process_frame
	ui.import_python.text=OS.get_environment("MINIEARTHURE_PYTHON")
	var source := ProjectSettings.globalize_path("user://places.pbf")
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
	check(built.ok and built.recipe.areas == [{"name":"가상시","source_id":"relation/1"}] and built.recipe.scale == 4 and built.recipe.traffic == {"signal_style":"vertical"} and not built.recipe.has("dem"),"wizard recipe: "+str(built))
	check(wizard.traffic().driving_side == "left" and wizard.traffic().signal_style == "vertical","automatic side from the country, explicit signals: "+str(wizard.traffic()))
	wizard.matches.select(1, false); wizard._selected(1, true)
	check(wizard.matches.get_selected_items() == PackedInt32Array([1]),"a named place is selected alone")
	wizard.signal_style.select(0)
	built = RECIPE.parse(JSON.stringify(wizard.recipe()))
	check(built.ok and built.recipe.place == {"name":"가상마을","source_id":"node/5"} and not built.recipe.has("traffic") and not built.recipe.has("areas"),"wizard place recipe: "+str(built))
	check(wizard.extent().kind == "bbox" and wizard.status.text.contains("km"),"the wizard shows the automatic extent: "+wizard.status.text)
	wizard.hide()
	check(FileAccess.get_sha256(source)==hash,"source PBF preserved")
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("real_city_recipe_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
