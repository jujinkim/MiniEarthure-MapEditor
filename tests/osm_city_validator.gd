extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
var checks := 0
var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures.append(message); push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+60000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"city worker finishes: "+ui.status_label.text)
func run() -> void:
	if OS.get_environment("MAPEDITOR_CITY_CANDIDATE") != "":
		await validate_candidate()
		return
	# The original 1:8 city scale and the 1:3 city default run the same flow.
	for denominator in [8, 3]: await run_scale(denominator)
	print("osm_city_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)

func run_scale(denominator: int) -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui); ui._ensure_import_ui()
	ui.store.new_track(true)
	await process_frame
	var author := preload("res://scripts/authoring_tools.gd").new()
	author.configure(ui.store,ui.canvas)
	var grid_patch := {"field":"cell_size_cm","before":51200,"after":12800}
	check(author.apply("Set city cells",[grid_patch],true)=="" and ui.store.document.cell_size_cm==12800,"cell size changes generation granularity without shrinking bounds")
	check(ui.store.undo()=="" and ui.store.document.cell_size_cm==51200 and ui.store.redo()=="" and ui.store.document.cell_size_cm==12800,"cell size is one reversible command")
	ui.store.document.heightmaps.append({"cell":{"x":0,"y":0},"path":"immutable.png","spacing_cm":400,"offset_cm":0,"step_cm":1})
	check(author.apply("Unsafe terrain resize",[{"field":"cell_size_cm","before":12800,"after":6400}],true).contains("cannot change") and ui.store.document.cell_size_cm==12800,"existing terrain cannot be reinterpreted with another cell size")
	ui.store.document.heightmaps.clear()
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1)
	ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_origin_x.value=512
	ui.import_origin_y.value=512
	ui.osm_panel.enabled.button_pressed=true
	ui.osm_panel.streaming.button_pressed=true
	check(ui.osm_panel.city.button_pressed,"PBF city optimization defaults on and is labelled")
	check(ui.osm_panel.scale.value == 3 and ui.osm_panel.scale.editable and ui.osm_panel.denominator() == 3,"city scale defaults to 1:3 and is editable on a map without OSM")
	var bbox := [8.9999,54.9999,9.002,55.002]
	for i in range(4): ui.osm_panel.fields[i].value=bbox[i]
	ui.osm_panel.scale.value = denominator
	check(ui.osm_panel.denominator() == denominator and ui.osm_panel.status.text.contains("1:%d approximate map size" % denominator),"preview uses the chosen scale: "+ui.osm_panel.status.text)
	var source := ProjectSettings.globalize_path("user://city-synthetic-%d.pbf" % denominator)
	var out: Array=[]
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_city_fixture.py"),source]),out,true)==0,"synthetic city fixture: "+str(out))
	var hash := FileAccess.get_sha256(source)
	var before: Dictionary=ui.store.document.duplicate(true)
	ui._start_import(source,LAYER.OSM_LICENSE)
	await wait_import(ui)
	check(ui.pending_import!=null,"city native review: "+ui.status_label.text)
	if ui.pending_import==null: ui.queue_free(); await process_frame; return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	var meta: Dictionary=raw.coordinates.osm_city
	check(ui.pending_import.requires_generation() and ui.pending_import.generation_cell_warning()==256 and ui.pending_import.generation_cell_limit()==LAYER.MAX_CHECK_CELLS,"all city cells require native generation, including sources without structures; above 256 cells only warns")
	check(meta.before.features>meta.after.features and meta.before.positions>meta.after.positions,"automatic aggregation reduces actual geometry")
	check(meta.after.roads==1 and meta.after.buildings==3 and meta.after.areas>=2,"compatible chain/footprints/vegetation merge while named/tall buildings survive")
	check(meta.painted_pedestrian_ways==1 and ui.import_summary.text.contains("painted as drivable ground"),"the footway is disclosed as ground paint, not a road")
	check(meta.vegetation_spacing_m==32 and meta.vegetation_density_per_mille==750,"illustrative vegetation density is explicitly disclosed")
	check(meta.scale_denominator==denominator and is_equal_approx(meta.grid_m,denominator/100.0) and is_equal_approx(meta.road_clearance_m,denominator/10.0),"the city lattice and clearances follow 1:%d" % denominator)
	check(ui.import_summary.text.contains("Automatic city optimization · 1:%d" % denominator) and ui.import_summary.text.contains("→") and ui.import_summary.text.contains("÷ %d," % denominator),"review shows measured reductions at the chosen scale")
	check(ui.store.document==before,"review leaves document unchanged")
	for mutation in ["scale","requested-scale","grid","clearance","coverage","record","counts","request","excluded","vegetation"]:
		var bad: Dictionary=raw.duplicate(true)
		var request: Dictionary=ui.import_coordinates_request.duplicate(true)
		match mutation:
			"scale": bad.coordinates.osm_city.scale_denominator=1
			"requested-scale": request.osm_scale = 8 if denominator != 8 else 3
			"grid": bad.coordinates.osm_city.grid_m=0.08 if denominator != 8 else 0.03
			"clearance": bad.coordinates.osm_city.building_clearance_m=0.16 if denominator != 8 else 0.06
			"coverage": bad.coordinates.osm_city.source_ids.append("way/999999")
			"record": bad.coordinates.osm_city.groups[0].records[1]+=1
			"counts": bad.coordinates.osm_city.after.features+=1
			"request": request.erase("osm_city")
			"vegetation": bad.coordinates.osm_city.vegetation_spacing_m=8
			"excluded":
				request.osm_review_exclusions=true
				bad.coordinates.osm_review={"profile":"explicit-source-exclusions-v1","excluded":[{"source_id":meta.source_ids[0],"reason":"fixture"}]}
		check(LAYER.new().load_value(bad,ui.import_identity,request)!="","reject city mutation "+mutation)
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.buildings.size()==3 and ui.store.document.roads.size()==1,"city adoption is complete")
	check(ui.store.document.surface_areas.size()==meta.after.areas-1 and ui.store.document.surface_areas.all(func(area: Dictionary) -> bool: return area.surface=="concrete"),"the footway is adopted as painted ground, cut at cell lines")
	check(ui.store.document.zones[0].spacing_cm==roundi(3200.0/denominator) and ui.store.document.zones[0].density_per_mille==750,"city vegetation keeps its 32 source m spacing after one scale conversion")
	check(preload("res://scripts/import_units.gd").dem_denominator(ui.store.document)==denominator,"DEM and CSV read the adopted 1:%d back" % denominator)
	var adopted: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.buildings.is_empty(),"atomic city Undo")
	check(ui.store.redo()=="" and ui.store._signature(ui.store.document)==ui.store._signature(adopted),"exact city Redo")
	var project := ProjectSettings.globalize_path("user://city-roundtrip-%d" % denominator)
	check(ui.store.save_project(project)=="" and ui.store.open_project(project)=="","save and reopen city project")
	check(ui.store.document.buildings==adopted.buildings and ui.store.document.attributions==adopted.attributions,"geometry and source mappings survive reopen")
	var package := project+".memap"
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok,"city current-v1 package export")
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok,"city package reopen")
	check(JSON.parse_string(ui.store.bridge.generate_chunk(0,0)).ok,"city native geometry generation")
	check(FileAccess.get_sha256(source)==hash,"city optimization never mutates PBF")
	# The reopened map locks the city scale without any panel refresh: a stale
	# control value never reaches the request.
	ui.osm_panel.scale.set_value_no_signal(3 if denominator == 8 else 8)
	check(ui.osm_panel.denominator()==denominator and ui.osm_panel.scale_error()=="","an opened OSM map locks the city scale without a panel refresh")
	ui._start_import(source,LAYER.OSM_LICENSE)
	check(ui.busy and ui.import_coordinates_request.get("osm_scale")==denominator,"a city import into the map uses its stored 1:%d" % denominator)
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import==null and ui.store.document.buildings==adopted.buildings,"cancel keeps accepted city")
	if denominator != 8:
		# Exact OSM (1:8) into a 1:3 map is refused before any job starts.
		ui.osm_panel.city.set_pressed_no_signal(false)
		ui._start_import(source,LAYER.OSM_LICENSE)
		check(not ui.busy and ui.pending_import==null and ui.status_label.text.contains("another OSM scale"),"exact OSM into a 1:%d map is refused before the job: %s" % [denominator,ui.status_label.text])
		ui.osm_panel.city.set_pressed_no_signal(true)
	ui.osm_panel.changed()
	check(not ui.osm_panel.scale.editable and ui.osm_panel.scale.value==denominator and ui.osm_panel.denominator()==denominator,"the scale control locks to the map's OSM scale")
	ui.store.dirty=false
	ui.queue_free(); await process_frame

func validate_candidate() -> void:
	# Optional read-only diagnostic of a locally produced candidate. This never
	# adopts, saves or exports a user's map; real authoring remains an Editor UI action.
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("MAPEDITOR_CITY_CANDIDATE")))
	check(raw is Dictionary,"local city candidate is JSON")
	if raw is not Dictionary: quit(1); return
	print("city candidate serialized bytes: ",JSON.stringify(raw).to_utf8_buffer().size(),"; wire bytes: ",FileAccess.get_file_as_bytes(OS.get_environment("MAPEDITOR_CITY_CANDIDATE")).size())
	var layer := LAYER.new()
	var failure: String=layer.load_value(raw,str(raw.get("layer_id","")))
	check(failure=="","local candidate boundary: "+failure)
	if failure!="": quit(1); return
	var store := preload("res://scripts/document_store.gd").new()
	failure=store.open_project(OS.get_environment("MAPEDITOR_CITY_PROJECT"))
	check(failure=="","local project read: "+failure)
	if failure!="": quit(1); return
	var cell_size := OS.get_environment("MAPEDITOR_CITY_CELL_SIZE_CM")
	if cell_size != "": store.document.cell_size_cm = int(cell_size) # Disposable candidate only; no save.
	var before: Dictionary=store.document.duplicate(true)
	var job := preload("res://scripts/import_native_job.gd").new()
	failure=job.start_validation(store,layer,false,"city-diagnostic",OS.get_environment("MAPEDITOR_CITY_SOURCE"),Crypto.new().generate_random_bytes(16).hex_encode())
	check(failure=="","native candidate starts: "+failure)
	if failure=="":
		var previous := ""
		var previous_count := -1
		while not job.done:
			job.poll()
			var stage: String=str(job.progress.get("stage",""))
			var count := int(job.progress.get("completed",0))
			if stage!=previous or (stage=="generate" and count%16==0 and count!=previous_count):
				print("city candidate stage: ",JSON.stringify(job.progress))
				previous=stage
				previous_count=count
			await process_frame
		print("city candidate last progress: ",JSON.stringify(job.progress))
		print("city candidate native result: ",JSON.stringify(job.result))
		check(job.result.get("ok",false) and job.result.get("data",{}).get("ok",false),"native city candidate passes: "+str(job.result))
		job.cleanup()
	check(store.document==before,"diagnostic leaves user document unchanged")
	print("osm_city_candidate: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
