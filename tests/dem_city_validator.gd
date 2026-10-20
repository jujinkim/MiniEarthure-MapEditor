extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const JOB := preload("res://scripts/dem_native_job.gd")
const DEM := preload("res://scripts/dem_import_layer.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func wait_job() -> void:
	var deadline := Time.get_ticks_msec()+120000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"bounded city DEM completes: "+ui.status_label.text)
func run() -> void:
	# The original 1:8 city scale and the 1:3 city default read back the same way.
	for denominator in [8, 3]: await run_scale(denominator)
	print("dem_city_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)

func run_scale(denominator: int) -> void:
	ui=load("res://main.tscn").instantiate()
	root.add_child(ui); ui._ensure_import_ui()
	await process_frame
	ui.store.new_document()
	var patches: Array=[
		{"field":"bounds","before":ui.store.document.bounds.duplicate(true),"after":{"min":[0,0],"max":[102400,153600]}},
		{"field":"cell_size_cm","before":ui.store.document.cell_size_cm,"after":12800},
		{"field":"nodes","id":"a","before":null,"after":{"id":"a","position":[1000,0,2000],"level":0}},
		{"field":"nodes","id":"b","before":null,"after":{"id":"b","position":[20000,0,2000],"level":0}},
		{"field":"roads","id":"r","before":null,"after":{"id":"r","from":"a","to":"b","points":[[1000,0,2000],[20000,0,2000]],"widths_cm":[200],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}}]
	var prefix: String="import-"+"b".repeat(32)+"-"
	var coordinates: Dictionary={"mode":"wgs84-utm","origin":[9.5,55.5],"local_origin_m":[0,0]}
	var notice: Dictionary={"source":"synthetic OSM","license":"CC0","notice":JSON.stringify({"adapter":"osm-extract-v1","layer_id":"b".repeat(32),"coordinates":coordinates,"authored_units":{"source_denominator":denominator,"profile":"osm-import-1to%d-v1" % denominator}})}
	patches.append({"field":"attributions","id":ui.store.record_id("attributions",notice),"before":null,"after":notice})
	for index in range(4):
		var x:=5000+13000*index
		var id: String="manual" if index==2 else prefix+str(index)
		patches.append({"field":"buildings","id":id,"before":null,"after":{"id":id,"footprint":[[x,8000],[x+400,8000],[x+400,8400],[x,8400]],"height_cm":600,"base_cm":123 if index==1 else 0,"roof":"flat","material":"concrete","usage":"residential"}})
	check(ui.store.apply_command("synthetic city",patches)=="","96-cell synthetic bounds and road")
	ui.csv_panel.use_imported_frame()
	check(ui.import_coordinate_mode.selected == 1 and ui.import_origin_lon.value == 9.5 and ui.import_origin_lat.value == 55.5 and ui.import_origin_x.value == 0 and ui.import_origin_y.value == 0, "CSV reuses the same source frame without applying map scale twice")
	var project := ProjectSettings.globalize_path("user://dem-city-%d" % denominator)
	check(ui.store.save_project(project)=="","save isolated test project")
	var source := ProjectSettings.globalize_path("user://synthetic-city-%d.tif" % denominator)
	var python := OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var output: Array=[]
	check(OS.execute(python,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/dem_fixture.py"),source]),output,true)==0,"synthetic source: "+str(output))
	var source_hash := FileAccess.get_sha256(source)
	ui.import_python.text=python
	var panel: ConfirmationDialog=ui.dem_panel
	panel.mosaic.button_pressed=true
	panel.source.text=source
	panel.fields.Longitude.value=9.5
	panel.fields.Latitude.value=55.5
	panel.fields["Cell columns"].value=8
	panel.fields["Cell rows"].value=12
	panel.fields["Spacing (cm)"].value=400
	panel.use_imported_frame()
	check(panel.options().coordinates==JSON.parse_string(JSON.stringify(coordinates)) and panel.options().cell_count==[8.0,12.0] and panel.options().spacing_cm==400 and panel.options().get("osm_denominator")==float(denominator),"reuse OSM origin, stored 1:%d scale and complete extent: " % denominator+JSON.stringify(panel.options()))
	panel.ground_buildings.button_pressed=true
	var before: String=JSON.stringify(ui.store.document)
	panel.prepare();await wait_job()
	check(panel.plan.get("cells",[]).size()==96,"review covers all 96 cells: "+ui.status_label.text)
	if not panel.plan.is_empty():
		panel.acquire();await wait_job()
		check(panel.candidate!=null,"native whole-city DEM review")
		check(JSON.stringify(ui.store.document)==before,"review leaves live document unchanged")
		if panel.candidate!=null:
			check(panel.candidate.value.heightmaps.size()==96,"all reviewed descriptors present")
			var grounding: Dictionary=panel.candidate.value.dem.grounding
			check(grounding.estimated and grounding.changes.size()==2 and grounding.samples==16,"only zero-base imported buildings get explicit perimeter estimates")
			var first: Dictionary=panel.candidate.value.heightmaps[0]
			var subset: Dictionary=panel.plan.options.duplicate(true);subset.cell_count=[1.0,1.0]
			var grounding_tool:=preload("res://scripts/dem_building_grounding.gd")
			var partial: Dictionary=grounding_tool.prepare(ui.store,[first],{first.path:FileAccess.get_file_as_bytes(panel.destination+".cell-0.png")},subset)
			check(not partial.has("error") and partial.receipt.changes.size()==1 and partial.receipt.skipped_partial==1,"partial DEM never grounds an uncovered building")
			if not partial.has("error"):
				var base_patch: Dictionary=partial.patches[0]
				check(grounding_tool.valid_patch(base_patch,true) and not grounding_tool.valid_patch(base_patch,false),"explicit grounding choice gates base patches")
				base_patch.after.height_cm+=1
				check(not grounding_tool.valid_patch(base_patch,true),"transfer cannot change building height")
			subset.coordinates.origin[0]+=0.001
			check(grounding_tool.prepare(ui.store,[first],{},subset).get("error","").contains("Projection"),"mismatched source frame rejects estimated grounding")
			var excessive: Dictionary=panel.candidate_data.duplicate(true)
			# Above 256 cells only warns; the 1024-cell bound still refuses before launch.
			while excessive.outputs.size()<=DEM.MAX_CELLS: excessive.outputs.append(excessive.outputs[0])
			var rejected := JOB.new()
			check(rejected.start_dem(ui.store,excessive,panel.plan,panel.destination,false,"test","a".repeat(32)).contains("count") and rejected.directory=="","1025 outputs reject before launch")
			var history_size: int=ui.store.undo_stack.size()
			panel.adopt()
			var adopted: RefCounted=ui.import_job
			await wait_job()
			check(adopted.expected_cells==96 and adopted.generated_all and adopted.generation_limit==DEM.MAX_CELLS,"96 actual road/terrain cells generated before adoption")
			check(ui.store.document.heightmaps.size()==96 and ui.store.undo_stack.size()==history_size+1,"entire DEM is one command")
			var buildings:= {}
			for building: Dictionary in ui.store.document.buildings: buildings[building.id]=building
			check(buildings[prefix+"0"].base_cm>0 and buildings[prefix+"0"].height_cm==600 and buildings[prefix+"1"].base_cm==123 and buildings.manual.base_cm==0,"base changes preserve building heights and authored bases")
			check(ui.store.undo()=="" and ui.store.document.heightmaps.is_empty(),"one Undo removes all cells")
			check(ui.store.document.buildings[0].base_cm==0,"same Undo restores building base")
			check(ui.store.redo()=="" and ui.store.document.heightmaps.size()==96,"one Redo restores all cells")
			check(ui.store.save_project(project)=="","save all terrain payloads")
			var reopened := STORE.new()
			check(reopened.open_project(project)=="" and reopened.document==ui.store.document,"reopen preserves every cell and receipt")
	check(FileAccess.get_sha256(source)==source_hash,"original source unchanged")
	ui.store.dirty=false
	ui.queue_free();await process_frame
