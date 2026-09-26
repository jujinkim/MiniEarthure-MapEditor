extends SceneTree
var failed := false
func _initialize() -> void: run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok: failed=true;push_error(label);quit(1)
func run() -> void:
	var ui: Control=load("res://main.tscn").instantiate();root.add_child(ui);await process_frame
	var author: RefCounted=ui.canvas.author
	author.options.water_surface_cm=100;author.options.water_bottom_cm=-500
	author.options.water_flow_x=25
	var outline: Array[Vector2]=[Vector2(1000,1000),Vector2(5000,1000),Vector2(5000,5000),Vector2(1000,5000)]
	check(author.draw("Water",outline)=="","draw validated water polygon")
	var body: Dictionary=ui.store.document.water_bodies[0]
	ui.canvas.selected.assign(["water_bodies/"+str(body.id)])
	var island: Array[Vector2]=[Vector2(2000,2000),Vector2(3000,2000),Vector2(3000,3000),Vector2(2000,3000)]
	check(author.draw("Island",island)=="","draw dry island")
	check(ui.store.document.water_bodies[0].islands.size()==1,"island stored")
	check(ui.store.undo()=="" and ui.store.document.water_bodies[0].islands.is_empty(),"island undo")
	check(ui.store.redo()=="" and ui.store.document.water_bodies[0].islands.size()==1,"island redo")
	body=ui.store.document.water_bodies[0].duplicate(true)
	var changed:=body.duplicate(true);changed.surface_cm=125
	check(author.apply("Water height",[{"field":"water_bodies","id":body.id,"before":body,"after":changed}])=="","edit water level")
	check(ui.store.undo()=="" and ui.store.redo()=="","water property undo/redo")
	var project:=ProjectSettings.globalize_path("user://water-project")
	check(ui.store.save_project(project)=="","save water source")
	var reopened:=preload("res://scripts/document_store.gd").new()
	check(reopened.open_project(project)=="" and reopened.document.water_bodies==ui.store.document.water_bodies,"source roundtrip preserves water and islands")
	ui._preview()
	var deadline:=Time.get_ticks_msec()+15000
	while (ui.busy or ui.preview_cache.is_empty()) and Time.get_ticks_msec()<deadline:await process_frame
	check(not ui.preview_cache.is_empty(),"preview completes with shared water renderer")
	var mesh_count:=0
	for job: Dictionary in ui.preview_cache.values():
		mesh_count+=job.root.find_children("Water_*","MeshInstance3D",true,false).size()
	check(mesh_count>0,"preview contains water surfaces")
	var output:=ProjectSettings.globalize_path("user://water-export.memap")
	ui._start_package("export",output)
	deadline=Time.get_ticks_msec()+15000
	while ui.busy and Time.get_ticks_msec()<deadline:await process_frame
	check(FileAccess.file_exists(output),"exported water package")
	var bridge:RefCounted=ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(bridge.open_package(output)).get("ok",false),"export passes native reader")
	check(JSON.parse_string(bridge.document_json()).data.water_bodies==ui.store.document.water_bodies,"export preserves water properties")
	ui.queue_free();await process_frame
	print("water_authoring_validator: ","FAIL" if failed else "PASS");quit(1 if failed else 0)
