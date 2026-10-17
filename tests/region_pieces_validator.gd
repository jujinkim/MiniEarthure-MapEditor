extends SceneTree
## Region widths are offered and compiled only for track overlays on existing maps.
const EDITOR:=preload("res://scripts/editor_main.gd")
var ui: Control
func _initialize() -> void:run.call_deferred()
func settle() -> void:
	var end:=Time.get_ticks_msec()+10000
	while ui.store.track_edit_busy and Time.get_ticks_msec()<end:await process_frame
	assert(not ui.store.track_edit_busy and ui.store.draft_error.is_empty(),str(ui.store.draft_error))
func run() -> void:
	ui=EDITOR.new();root.add_child(ui);await process_frame
	var store: RefCounted=ui.store
	var straight: Dictionary={}
	for entry: Dictionary in ui.track_workbench.catalogue.entries:
		if entry.id=="straight":straight=entry
	store.new_track(false)
	assert(not ui.track_workbench.region_overlay() and not ui.track_workbench.widths(straight).has(150.0),"standalone tracks keep 400 cm minimum")
	store.new_document()
	var d: Dictionary=store.document.duplicate(true)
	d.free_roam=true;d.bounds={"min":[-6400,-6400],"max":[16000,12800]};d.cell_size_cm=3200
	var road := {"id":"city","kind":"ground","from":"a","to":"b","points":[[1600,0,3200],[8000,0,3200]],"widths_cm":[150],"surfaces":["asphalt"],"clearance_cm":null,"sidewalk_cm":0}
	d.nodes=[{"id":"a","position":road.points[0],"level":0},{"id":"b","position":road.points[1],"level":0}];d.roads=[road]
	assert(store.open_generated(d)=="")
	var design: Dictionary=JSON.parse_string(store.bridge.road_design(JSON.stringify(road))).data
	assert(store.edit_road("city",design,150)=="")
	assert(ui.track_workbench.region_overlay() and ui.track_workbench.widths(straight).slice(0,3)==[150.0,200.0,300.0],"overlay maps offer region widths first")
	var source: Dictionary=store.track_source()
	var item: Dictionary=ui.track_workbench.placement._instance("straight",150)
	item.id="narrow";source.instances=[item];source.terrain_integration=true
	source.road_connections=[{"road":"city","start":false,"instance":"narrow"}]
	assert(store.start_track_edit(source)=="");await settle()
	var piece: Dictionary=store.document.assembled_track.pieces[0]
	assert(int(piece.width_cm)==150 and piece.path[0].position_cm==[8000.0,0.0,3200.0],"150 cm piece joins the 150 cm road end")
	print("region_pieces_validator: PASS")
	ui.queue_free();await process_frame
	quit(0)
