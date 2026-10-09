extends SceneTree
const EDITOR:=preload("res://scripts/editor_main.gd")
const STORE:=preload("res://scripts/document_store.gd")
var ui: Control
func _initialize() -> void:run.call_deferred()
func settle() -> void:
	var end:=Time.get_ticks_msec()+10000
	while ui.store.track_edit_busy and Time.get_ticks_msec()<end:await process_frame
	assert(not ui.store.track_edit_busy and ui.store.draft_error.is_empty(),str(ui.store.draft_error))
func settle_preview() -> void:
	var road_tools: RefCounted=ui.track_workbench.road_tools
	var end:=Time.get_ticks_msec()+15000
	while (road_tools.environment_job!=null or not road_tools.render_pending.is_empty()) and Time.get_ticks_msec()<end:await process_frame
	assert(road_tools.environment_job==null and road_tools.render_pending.is_empty(),"environment preview deadline")
func run() -> void:
	ui=EDITOR.new();root.add_child(ui);await process_frame
	var store: RefCounted=ui.store
	store.new_document()
	var d: Dictionary=store.document.duplicate(true)
	d.free_roam=true;d.bounds={"min":[-6400,-6400],"max":[16000,12800]};d.terrain_base_cm=200;d.cell_size_cm=3200
	var sample: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://addons/mapkit/examples/roads/document.json"))
	var road: Dictionary=sample.roads[0].duplicate(true)
	road.id="editable";road.kind="ground";road.from="a";road.to="b";road.points=[[1600,500,3200],[8000,500,3200]];road.widths_cm=[600];road.surfaces=["asphalt"];road.sidewalk_cm=0
	d.nodes=[{"id":"a","position":road.points[0],"level":0},{"id":"b","position":road.points[1],"level":0}];d.roads=[road]
	d.buildings=[{"id":"keep","footprint":[[11000,8000],[12000,8000],[12000,9000],[11000,9000]],"base_cm":200,"height_cm":500,"usage":"commercial","material":"concrete","roof":"flat","entrances":[],"holes":[]}]
	assert(store.open_generated(d)=="")
	var design: Dictionary=JSON.parse_string(store.bridge.road_design(JSON.stringify(road))).data
	assert(store.edit_road("editable",design,600)=="")
	var original_buildings: Array=store.document.buildings.duplicate(true)
	var original: String=store._signature(store.document)
	var source: Dictionary=store.track_source()
	var item: Dictionary=ui.track_workbench.placement._instance("straight",400)
	item.id="placed";source.instances=[item];source.terrain_integration=true
	source.road_connections=[{"road":"editable","start":false,"instance":"placed"}]
	assert(store.start_track_edit(source)=="");await settle()
	assert(store.document.buildings==original_buildings and store.document.roads[0].design==design)
	assert(store.document.assembled_track.pieces[0].path[0].position_cm==[8000.0,500.0,3200.0])
	assert(store.undo()=="");await settle()
	assert(store._signature(store.document)==original,"first track placement Undo restores exact original document")
	assert(store.redo()=="");await settle()
	var attached: Dictionary={"id":"jump","surface":{"surface_id":"editable","station_cm":2400},"kind":"jump_panel","height_cm":200,"panel_width_percent":50,"panel_alignment":"center","side":1}
	var attachment_error: String=store.edit_surface_attachments([attached])
	assert(attachment_error=="",attachment_error)
	var before: String=store._signature(store.document)
	for point: Array in design.control_points:point[1]+=100
	assert(store.edit_road("editable",design,600)=="")
	assert(store.document.assembled_track.pieces[0].path[0].position_cm[1]==600)
	assert(store.document.gimmicks[0].position[1]>500)
	assert(store.undo_stack.back().patches.all(func(p):return p.field not in ["track_document","heightmaps","buildings"]))
	assert(store.history_bytes<store.HISTORY_BYTES)
	assert(store.undo()=="" and store._signature(store.document)==before)
	assert(store.redo()=="")
	var tab_document: String=store._signature(store.document)
	ui.set_tool_workspace("landscape");assert(not ui.track_workbench.active)
	ui.set_tool_workspace("track");assert(ui.track_workbench.active and store._signature(store.document)==tab_document)
	assert(store.set_free_roam(false)=="" and ui.track_workbench.active)
	assert(store.set_free_roam(true)=="" and ui.track_workbench.active)
	var retained: String=store._signature(store.document)
	assert(store.edit_road("editable",design,999999)!="" and store._signature(store.document)==retained)
	var path:=ProjectSettings.globalize_path("user://mixed-road")
	assert(store.save_project(path)=="")
	var reopened:=STORE.new();assert(reopened.open_project(path)=="")
	assert(reopened.document.roads==store.document.roads and reopened.document.surface_attachments==store.document.surface_attachments)
	var exported: Dictionary=JSON.parse_string(store.bridge.export_project(path,ProjectSettings.globalize_path("user://mixed.memap")))
	assert(exported.ok,str(exported))
	var collision: Dictionary=JSON.parse_string(store.bridge.source_preview(JSON.stringify(store.document),path,3,3))
	assert(collision.ok,str(collision))
	assert(collision.data.triangles.any(func(t):return t.object_id=="editable" and t.contact_class==3),str(store.document.bounds)+" cell="+str(store.document.cell_size_cm)+" triangles="+str(collision.data.triangles.slice(0,3)))
	var road_tools: RefCounted=ui.track_workbench.road_tools
	road_tools.select("editable");await settle_preview()
	assert(not road_tools.rendered.is_empty() and road_tools.environment_epoch==store.command_epoch)
	var cell: Vector2i=road_tools.rendered.keys()[0]
	var root_id: int=road_tools.rendered[cell].job.root.get_instance_id()
	road_tools.request_cell(road_tools.environment_cell);await settle_preview()
	assert(road_tools.rendered[cell].job.root.get_instance_id()==root_id,"unchanged environment mesh reused")
	road_tools.request_cell(road_tools.environment_cell)
	store.new_document();await settle_preview()
	assert(road_tools.rendered.is_empty(),"late terrain preview cannot replace a different document")
	ui.queue_free();await process_frame;await process_frame
	print("composite_road_validator: PASS · shared ports/actions, source preservation, Undo, policy, save/reopen/export")
	quit()
