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
	await run_rules()
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
	check(meta.before.features>meta.after.features and meta.before.buildings>meta.after.buildings,"automatic aggregation reduces records")
	check(meta.after.roads==1 and meta.after.buildings==3 and meta.after.areas>=2,"compatible chain/vegetation merge, footprints group as parts while named/tall buildings stay records")
	check(meta.building_records.solids==8 and meta.building_records.grouped_records==1,"every source footprint stays its own solid: "+JSON.stringify(meta.building_records))
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
	# Road markings beyond the paint segment bound MapKit draws per road and cell.
	var winding: Dictionary=raw.duplicate(true)
	for patch: Dictionary in winding.patches:
		if patch.field != "roads": continue
		var road: Dictionary = patch.after
		check(road.get("sidewalk_cm") is float or road.get("sidewalk_cm") is int,"city ground roads carry an explicit sidewalk")
		var a: Array = road.points[0]
		var b: Array = road.points[-1]
		var points: Array = [a]
		for k in range(1, 80):
			points.append([a[0] + (b[0] - a[0]) * k / 80.0, a[1], a[2] + (b[2] - a[2]) * k / 80.0 + (300 if k % 2 == 0 else -300)])
		points.append(b)
		road.points = points
		road.widths_cm = []
		road.surfaces = []
		for k in range(points.size() - 1):
			road.widths_cm.append(600)
			road.surfaces.append("asphalt")
		road.markings = {"lanes":2,"center_line":true,"edge_lines":false,"crosswalk_start":false,"crosswalk_end":false}
		break
	check(LAYER.new().load_value(winding,ui.import_identity,ui.import_coordinates_request)=="City road markings exceed the paint segment bound.","reject city road markings beyond the paint segment bound")
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.buildings.size()==3 and ui.store.document.roads.size()==1,"city adoption is complete")
	check(ui.store.document.buildings.any(func(b: Dictionary) -> bool: return b.get("parts", []).size()==5),"six overlapping footprints adopt as one record with five parts")
	check(ui.store.document.surface_areas.size()==meta.after.areas-1 and ui.store.document.surface_areas.all(func(area: Dictionary) -> bool: return area.surface in ["concrete","grass"]) and ui.store.document.surface_areas.any(func(area: Dictionary) -> bool: return area.surface=="grass"),"the footway is painted concrete and the forest grass, cut at cell lines")
	check(ui.store.document.get("ground_surface")=="concrete","a city import paves unpainted ground")
	check(ui.store.document.zones[0].spacing_cm==roundi(3200.0/denominator) and ui.store.document.zones[0].density_per_mille==750,"city vegetation keeps its 32 source m spacing after one scale conversion")
	check(preload("res://scripts/import_units.gd").dem_denominator(ui.store.document)==denominator,"DEM and CSV read the adopted 1:%d back" % denominator)
	var adopted: Dictionary=ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.buildings.is_empty() and not ui.store.document.has("ground_surface"),"atomic city Undo restores the ground surface")
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

## Building parts, barriers and city ground: adopted natively, Undo, a map
## keeping its own ground surface.
func run_rules() -> void:
	for keep in [false, true]:
		var ui: Control = load("res://main.tscn").instantiate()
		root.add_child(ui); ui._ensure_import_ui()
		ui.store.new_track(true)
		await process_frame
		if keep:
			check(ui.store.apply_command("Asphalt ground",[{"field":"ground_surface","id":"","before":null,"after":"asphalt"}])=="" and ui.store.document.ground_surface=="asphalt","a user ground surface is one command")
		ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
		ui.import_source_format.select(1)
		ui.import_source_format.item_selected.emit(1)
		ui.import_origin_lon.value=9
		ui.import_origin_lat.value=55
		ui.import_origin_x.value=512
		ui.import_origin_y.value=512
		ui.osm_panel.enabled.button_pressed=true
		ui.osm_panel.streaming.button_pressed=true
		var bbox := [8.9995,54.9995,9.0135,55.004]
		for i in range(4): ui.osm_panel.fields[i].value=bbox[i]
		ui.osm_panel.scale.value = 3
		var source := ProjectSettings.globalize_path("user://city-rules-%s.pbf" % keep)
		var out: Array=[]
		check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_city_rules_fixture.py"),source]),out,true)==0,"synthetic city rules fixture: "+str(out))
		var before: Dictionary=ui.store.document.duplicate(true)
		ui._start_import(source,LAYER.OSM_LICENSE)
		await wait_import(ui)
		check(ui.pending_import!=null,"city rules native review: "+ui.status_label.text)
		if ui.pending_import==null: ui.queue_free(); await process_frame; return
		var meta: Dictionary=ui.pending_import.value.coordinates.osm_city
		check(ui.import_summary.text.contains("building records"),"review discloses building records, barriers and ground paint")
		check(ui.pending_import.limit_warnings.any(func(e: Dictionary) -> bool: return e.code=="city_ground_surface")==keep,"a kept user ground surface is disclosed, never overwritten")
		check(ui.import_summary.text.contains("Not imported:") and ui.import_summary.text.contains("Ground paint:"),"review discloses dropped and skipped city inputs and the paint breakdown")
		for mutation in ["dropped-imported", "dropped-count", "skipped"]:
			var bad: Dictionary = ui.pending_import.value.duplicate(true)
			match mutation:
				"dropped-imported": bad.coordinates.osm_city.barriers.dropped_sources = [meta.source_ids[0]]
				"dropped-count":
					var many: Array = []
					for k in range(int(meta.before.barriers) + 1): many.append("way/%d" % (900000 + k))
					bad.coordinates.osm_city.barriers.dropped_sources = many
				"skipped": bad.coordinates.osm_city.skipped = {"barrier_ways": -1}
			check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request)!="","reject city mutation "+mutation)
		ui._adopt_import()
		await wait_import(ui)
		var document: Dictionary=ui.store.document
		check(document.get("barriers",[]).size()==int(meta.after.barriers) and document.barriers.size()>=8,"barriers adopt: %d" % document.get("barriers",[]).size())
		check(document.barriers.all(func(b: Dictionary) -> bool: return b.kind in ["hedge","fence","wall"] and b.height_cm>=10 and b.height_cm<=1000 and b.thickness_cm>=5 and b.thickness_cm<=100),"barrier heights and thicknesses within MapKit ranges")
		check(document.barriers.any(func(b: Dictionary) -> bool: return b.kind=="fence" and b.height_cm==13) and document.barriers.any(func(b: Dictionary) -> bool: return b.kind=="wall" and b.height_cm==22) and document.barriers.any(func(b: Dictionary) -> bool: return b.kind=="hedge" and b.height_cm==10),"a third of the source-metre barrier heights ÷3")
		check(document.buildings.size()==6 and document.buildings.filter(func(b: Dictionary) -> bool: return not b.get("parts",[]).is_empty()).size()==3,"site and category records carry building parts")
		check(document.surface_areas.any(func(a: Dictionary) -> bool: return a.surface=="grass") and document.surface_areas.any(func(a: Dictionary) -> bool: return a.surface=="asphalt"),"green land is grass and parking asphalt")
		check(document.get("ground_surface")==("asphalt" if keep else "concrete"),"ground surface: %s" % document.get("ground_surface"))
		check(ui.store.undo()=="" and ui.store.document.get("barriers",[]).is_empty() and ui.store.document.get("ground_surface")==("asphalt" if keep else null),"Undo removes barriers and restores the ground surface")
		check(ui.store.redo()=="" and ui.store.document.barriers.size()==int(meta.after.barriers),"Redo restores barriers")
		if not keep:
			# Parts belong to their record in canvas picking and scenery rotation.
			var grouped: Dictionary = {}
			for b: Dictionary in ui.store.document.buildings:
				if b.get("parts",[]).size() == 1: grouped = b
			check(not grouped.is_empty(),"a two-solid city record exists")
			if not grouped.is_empty():
				var part: Array = grouped.parts[0].footprint
				var inside := Vector2.ZERO
				for q: Array in part: inside += Vector2(q[0],q[1])
				inside /= part.size()
				check(ui.canvas._hit(inside) == "buildings/" + str(grouped.id),"a click inside a building part picks its record")
				ui.scenery.tool = ""
				ui.scenery.selected = {"field":"buildings","record":grouped,"key":"buildings/" + str(grouped.id)}
				ui.scenery.rotate_selected()
				var turned: Dictionary = {}
				for b: Dictionary in ui.store.document.buildings:
					if b.id == grouped.id: turned = b
				var centre := Vector2.ZERO
				for q: Array in grouped.footprint: centre += Vector2(q[0],q[1])
				centre /= grouped.footprint.size()
				var expected: Array = []
				for q: Array in part:
					var d := Vector2(q[0],q[1]) - centre
					expected.append([roundi(centre.x-d.y), roundi(centre.y+d.x)])
				var got: Array = []
				for q: Array in (turned.parts[0].footprint if turned.get("parts",[]).size() == 1 else []): got.append([roundi(q[0]), roundi(q[1])])
				check(got == expected,"rotating a record turns its parts with it: " + ui.status_label.text + " " + JSON.stringify(turned.get("parts",[])) + " expected " + JSON.stringify(expected))
				check(ui.store.undo()=="" ,"rotation Undo")
		var project := ProjectSettings.globalize_path("user://city-rules-%s" % keep)
		check(ui.store.save_project(project)=="" and ui.store.open_project(project)=="" and ui.store.document.barriers.size()==int(meta.after.barriers),"barriers and parts survive save and reopen")
		check(JSON.parse_string(ui.store.bridge.export_project(project,project+".memap")).ok and JSON.parse_string(ui.store.bridge.open_package(project+".memap")).ok,"city rules package export and reopen")
		var generated: Dictionary = JSON.parse_string(ui.store.bridge.generate_chunk(0,0))
		check(generated.ok,"city rules native generation: "+str(generated.get("error","")))
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
