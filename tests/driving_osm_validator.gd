extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var ui: Control
func _initialize() -> void: run.call_deferred()
func wait_import() -> void:
	var end := Time.get_ticks_msec()+20000
	while ui.busy and Time.get_ticks_msec()<end: await process_frame
	assert(not ui.busy,ui.status_label.text)
func preview_ready() -> void:
	var road: RefCounted = ui.track_workbench.road_tools
	var end := Time.get_ticks_msec()+15000
	while (road.environment_job != null or not road.render_pending.is_empty()) and Time.get_ticks_msec()<end: await process_frame
	assert(road.environment_job == null and road.render_pending.is_empty(),"bounded surface preview")
func run() -> void:
	ui = UI.new(); root.add_child(ui); ui._ensure_import_ui()
	await process_frame; await process_frame
	ui.start_panel.hide()
	var path := ProjectSettings.globalize_path("user://driving-roads.pbf")
	var python := OS.get_environment("MINIEARTHURE_PYTHON")
	var output: Array = []
	assert(OS.execute(python,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/driving_osm_fixture.py"),path]),output,true) == 0,str(output))
	ui.import_python.text = python
	ui.import_source_format.select(1); ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = 9; ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 0; ui.import_origin_y.value = 0
	ui.osm_panel.enabled.button_pressed = true; ui.osm_panel.streaming.button_pressed = true
	for i in 4: ui.osm_panel.fields[i].value = [8.9999,54.9999,9.0101,55.0031][i]
	var before: Dictionary = ui.store.document.duplicate(true)
	var before_signature: String = ui.store._signature(before)
	ui._start_import(path,ui.IMPORT_LAYER.OSM_LICENSE); await wait_import()
	assert(ui.pending_import != null,ui.status_label.text)
	assert(ui.store.document == before and ui.import_summary.text.contains("New map extent"),"review is read-only and shows proposed extent")
	var forged: Dictionary = ui.pending_import.value.duplicate(true)
	forged.coordinates.osm_ground_endpoints[0].refs[0] = "999999"
	assert(ui.IMPORT_LAYER.new().load_value(forged,ui.import_identity,ui.import_coordinates_request) != "","forged source junction identity rejected")
	ui._discard_import()
	assert(ui.store.document == before,"discard preserves blank track")
	ui._start_import(path,ui.IMPORT_LAYER.OSM_LICENSE); await wait_import()
	ui._adopt_import(); await wait_import()
	assert(ui.store.document.roads.size() == 3,ui.status_label.text)
	var adopted: Dictionary = ui.store.document.duplicate(true)
	var undo_error: String = ui.store.undo()
	assert(undo_error == "",undo_error)
	assert(ui.store._signature(ui.store.document) == before_signature,"import Undo restores content including extent and assembly")
	assert(ui.store.redo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(adopted))
	var road: RefCounted = ui.track_workbench.road_tools
	await preview_ready()
	assert(ui.store.document.nodes.size() == 4,"source shared junction uses one node")
	var record: Dictionary = ui.store.document.roads[0]
	road.select(record.id); await preview_ready()
	assert(ui.store._signature(ui.store.document) == ui.store._signature(adopted) and not record.has("design"),"opening raw OSM road never rewrites it")
	var found := false
	for triangle: Dictionary in road.triangles:
		if triangle.object_id != record.id or not triangle.spawnable: continue
		var center := (PREVIEW.point(triangle.vertices[0])+PREVIEW.point(triangle.vertices[1])+PREVIEW.point(triangle.vertices[2]))/3
		ui.preview_camera.frame(center,32)
		var hit: Dictionary = road.raycast(ui.preview_camera.camera.unproject_position(center),true)
		if hit.road == record.id: found = true; break
	assert(found,"3D picking returns actual generated road object identity")
	# The first road's to-node is a shared three-way junction.
	road.point_index = road.design.control_points.size()-1
	var original_point: Array = road.design.control_points[road.point_index].duplicate()
	road.change_height(0.1); ui._cancel_editing()
	assert(ui.store._signature(ui.store.document) == ui.store._signature(adopted),"height draft Escape preserves OSM geometry")
	road.change_height(0.1)
	assert(road.commit_direct(),ui.status_label.text+" design="+str(road.design)+" roads="+str(ui.store.document.roads)+" nodes="+str(ui.store.document.nodes))
	var shared: String = record.to
	for item: Dictionary in ui.store.document.roads:
		if item.from == shared: assert(item.points[0][1] == original_point[1]+10,"shared junction start follows atomic native edit")
		if item.to == shared: assert(item.points[-1][1] == original_point[1]+10,"shared junction end follows atomic native edit")
	assert(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(adopted),"shared junction edit one Undo")
	assert(ui.store.redo() == "")
	await preview_ready()
	var attachment := {"id":"osm-jump","surface":{"surface_id":record.id,"station_cm":1500},"kind":"jump_panel","height_cm":100,"panel_width_percent":50,"panel_alignment":"center","side":1}
	assert(ui.store.edit_surface_attachments([attachment]) == "","ordinary edited road supports gimmicks")
	ui.show_tool_group("course")
	ui.course_tools.manual_course = true; ui.course_tools.original = {}; ui.course_tools.binding = ui.course_tools.token(); ui.course_tools.circuit = false
	ui.course_tools.gates = []
	for point: Array in [ui.store.document.roads[0].points[0],ui.store.document.roads[0].points[-1]]:
		ui.course_tools.gates.append({"position_cm":point.duplicate(),"radius_cm":230,"shape":"sphere","placement_mode":"road_snap","surface_id":record.id})
	assert(ui.course_tools.save_manual(),ui.status_label.text)
	ui._test_drive()
	assert(roundi(ui.drive_x.value*100) == int(ui.course_tools.gates[0].position_cm[0]),"manual course start forwarded")
	ui.drive_dialog.hide()
	ui.show_tool_group("scenery")
	ui.scenery.activate("builtin:tree")
	ui.scenery.candidate = {"id":"osm-tree","asset_id":"builtin:tree","position":[0,0,-1000],"quarter_turns":0,"yaw_offset_mdeg":0}
	assert(ui.scenery.commit())
	ui._cancel_editing()
	road.focus_point(Vector3(0,0,10)); await preview_ready()
	ui.preview_camera.frame(Vector3(0,1,10),16)
	var click := InputEventMouseButton.new(); click.button_index = MOUSE_BUTTON_LEFT; click.pressed = true
	click.position = ui.preview_camera.camera.unproject_position(Vector3(0,1,10))
	assert(ui.scenery.input(click) and ui.scenery.selected.get("record",{}).get("id") == "osm-tree","actual rendered scenery can be selected in 3D")
	ui.scenery.adjust_height(1)
	assert(ui.scenery.commit(),"selected scenery height move commits")
	assert(ui.store.document.placements[0].position[1] == 100)
	assert(ui.store.undo() == "" and ui.store.document.placements[0].position[1] == 0,"scenery move Undo")
	await preview_ready()
	assert(ui.scenery.input(click))
	ui.scenery.cancel()
	ui.scenery.rotate_selected()
	assert(ui.store.document.placements[0].quarter_turns == 1,"scenery rotation is a document edit")
	ui.canvas.delete_selection()
	assert(ui.store.document.placements.is_empty(),"scenery Delete uses selected source ID")
	assert(ui.store.undo() == "" and ui.store.document.placements.size() == 1,"scenery deletion Undo")
	var project := ProjectSettings.globalize_path("user://osm-driving")
	assert(ui.store.save_project(project) == "")
	var reopened := preload("res://scripts/document_store.gd").new()
	assert(reopened.open_project(project) == "" and reopened.document == ui.store.document,"roads, course, gimmicks and scenery reopen")
	var exported: Dictionary = JSON.parse_string(ui.store.bridge.export_project(project,ProjectSettings.globalize_path("user://osm-driving.memap")))
	assert(exported.ok,str(exported))
	ui.queue_free(); await process_frame; await process_frame
	print("driving_osm_validator: PASS")
	quit()
