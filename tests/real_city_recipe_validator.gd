extends SceneTree
## Real-city recipe v1: parsing, relative paths, wizard round trip and area lookup
## through the PBF place search (synthetic fixture), including an ambiguous area stop.
const UI := preload("res://scripts/editor_main.gd")
const RECIPE := preload("res://scripts/real_city_recipe.gd")
var failed := false
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
	# The wizard's recipe parses back unchanged.
	ui.open_real_city()
	var wizard: ConfirmationDialog = ui.real_city_wizard
	wizard.pbf.text = source
	wizard._found([{"name":"가상시","admin_level":"8","source_id":"relation/1","issue":"","bbox":[9,55,9.0002,55.0002]}])
	wizard.project.text = "/tmp/p"; wizard.package.text = "/tmp/m.memap"; wizard.scale.value = 4; wizard.signal_style.select(1)
	var built: Dictionary = RECIPE.parse(JSON.stringify(wizard.recipe()))
	check(built.ok and built.recipe.areas == [{"name":"가상시","source_id":"relation/1"}] and built.recipe.scale == 4 and built.recipe.traffic.signal_style == "vertical" and not built.recipe.has("dem"),"wizard recipe: "+str(built))
	wizard.hide()
	check(FileAccess.get_sha256(source)==hash,"source PBF preserved")
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	print("real_city_recipe_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
