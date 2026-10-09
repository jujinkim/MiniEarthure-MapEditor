extends SceneTree
const TERRAIN := preload("res://scripts/terrain_tools.gd")
var failed := false
var ui: Control
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failed=true;push_error(label+" | "+ui.status_label.text)
func settle() -> void:
	var deadline := Time.get_ticks_msec()+15000
	while (ui.busy or ui.store.editing_locked()) and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy and not ui.store.editing_locked(),"bounded water/output completion")
func run() -> void:
	ui=load("res://main.tscn").instantiate();root.add_child(ui);await process_frame
	ui.store.new_track(true)
	ui.set_tool_workspace("landscape")
	check(ui.store.apply_command("Small fixture",[{"field":"bounds","before":ui.store.document.bounds,"after":{"min":[0,0],"max":[6400,6400]}},{"field":"cell_size_cm","before":ui.store.document.cell_size_cm,"after":3200}])=="","small memory map")
	var terrain := TERRAIN.new();terrain.store=ui.store
	check(terrain.begin(Vector2(3200,3200),{"mode":"lower","radius_cm":1600})=="","unsaved basin starts")
	check(terrain.step(Vector2(3200,3200),3)=="","basin step")
	terrain.last_usec=Time.get_ticks_usec();check(terrain.finish()=="","memory basin command")
	check(ui.store.start_water(Vector2(4000,3200))=="","slope fill")
	await settle()
	var water: Array=ui.store.document.get("water_bodies",[]).duplicate(true)
	check(water.size()==1 and int(water[0].flow_cm_s[0])==0 and int(water[0].flow_cm_s[1])==0,"new connected water with zero flow")
	check(ui.store.project_path.is_empty() and ui.store.dirty,"water editing needs no project path")
	ui._preview();await settle()
	check(not ui.preview_cache.is_empty(),"unsaved water preview")
	var mesh_count:=0
	for job: Dictionary in ui.preview_cache.values():
		mesh_count+=job.root.find_children("Water_*","MeshInstance3D",true,false).size()
	check(mesh_count>0,"preview contains native water renderer surfaces")
	var output:=ProjectSettings.globalize_path("user://water-export.memap")
	ui._start_package("export",output);await settle()
	check(FileAccess.file_exists(output) and ui.store.dirty and ui.store.project_path.is_empty(),"export publishes current memory without saving project")
	var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(bridge.open_package(output)).get("ok",false),"export passes native reader")
	check(JSON.parse_string(bridge.document_json()).get("data",{}).get("water_bodies",[])==water,"export uses same unsaved water")
	var project:=ProjectSettings.globalize_path("user://water-project")
	check(ui.store.start_file_operation("save",project)=="","explicit save")
	var deadline:=Time.get_ticks_msec()+15000
	while not ui.store.file_request.is_empty() and Time.get_ticks_msec()<deadline: await process_frame
	var reopened:=preload("res://scripts/document_store.gd").new()
	check(reopened.open_project(project)=="" and reopened.document.water_bodies==water,"save and reopen retain water")
	check(ui.store.undo()=="" and ui.store.document.get("water_bodies",[]).is_empty(),"water Undo retained after save")
	check(ui.store.redo()=="" and not ui.store.dirty,"water Redo reaches save baseline")
	ui.queue_free();await process_frame
	print("water_authoring_validator: ","FAIL" if failed else "PASS");quit(1 if failed else 0)
