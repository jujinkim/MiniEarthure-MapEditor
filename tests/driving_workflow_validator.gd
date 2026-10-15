extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
var ui: Control
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message); push_error(message)
func settle() -> void:
	var until := Time.get_ticks_msec()+15000
	while ui.store.track_edit_busy and Time.get_ticks_msec()<until: await process_frame
	check(not ui.store.track_edit_busy and not ui.store.draft_pending(),"track validation settles: "+str(ui.store.draft_error))
func key(code: Key, shift := false) -> bool:
	var event := InputEventKey.new(); event.pressed = true; event.keycode = code; event.shift_pressed = shift
	return ui.commands.handle_key(event)
func run() -> void:
	ui = UI.new(); root.add_child(ui)
	await process_frame; await process_frame
	ui.start_panel.hide()
	check(ui.view_mode == "3d" and ui.author_panel.tabs.get_tab_count() == 0 and ui.import_dialog == null and ui.generation_panel == null,"primary 3D and lazy advanced panels")
	check(key(KEY_PAGEUP) and is_equal_approx(ui.spatial.height,1),"PageUp changes next placement by 1 metre")
	check(key(KEY_PAGEDOWN,true) and is_equal_approx(ui.spatial.height,0.9),"Shift PageDown changes next placement by 0.1 metre")
	var text := LineEdit.new(); ui.add_child(text); text.grab_focus()
	check(not key(KEY_PAGEUP) and is_equal_approx(ui.spatial.height,0.9),"text input blocks height shortcut")
	text.release_focus(); text.queue_free()
	var popup := AcceptDialog.new(); ui.add_child(popup); popup.popup_centered()
	check(not key(KEY_PAGEUP),"popup blocks height shortcut")
	popup.hide(); popup.queue_free()
	var bench: Node = ui.track_workbench
	bench.add_piece("straight")
	check(bench.placement.preview_at(Vector3.ZERO),"manual plane preview")
	check(int(bench.placement.candidate.item.position_cm[1]) == 90,"preview uses work height")
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._cancel_editing()
	check(ui.store.document == before,"Escape semantics discard preview")
	ui.spatial.height = 0; ui.spatial.manual = false
	bench.add_piece("straight")
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit(),"first piece commits")
	await settle()
	check(bench.placement.port_locked(),"new exit stays selected for connected placement")
	var frozen: Array = bench.placement.candidate.get("item",{}).get("position_cm",[]).duplicate()
	key(KEY_PAGEUP)
	check(bench.placement.candidate.item.position_cm == frozen,"height key keeps port alignment")
	for _i in 5:
		bench.add_piece("straight")
		check(bench.placement.commit(),"connected preview can be confirmed without numeric input")
		await settle()
	check(bench.source.paths[0].pieces.size() == 6 and bench.source.connections.size() == 5,"assembly order owns default route")
	ui.show_tool_group("course")
	ui.course_tools.suggest()
	check(ui.course_tools.proposal.applicable and ui.course_tools.gates.size() >= 2,"manual sprint course proposal: "+str(ui.course_tools.proposal))
	check(ui.store.track_source().checkpoints.is_empty(),"query does not change document")
	var undo_count: int = ui.store.undo_stack.size()
	check(ui.course_tools.apply_proposal(),"explicit course apply")
	await settle()
	check(ui.store.undo_stack.size() == undo_count+1 and ui.store.track_source().checkpoints.size()>=2,"proposal is one Undo operation")
	check(ui.store.undo() == "","course undo accepted"); await settle()
	check(ui.store.track_source().checkpoints.is_empty(),"course undo restores absent checkpoints")
	check(ui.store.redo() == "","course redo accepted"); await settle()
	ui._test_drive()
	var cp: Dictionary = ui.store.track_source().checkpoints[0]
	var start: Array = ui.store.track_pieces()[0].path[int(cp.sample)].position_cm
	check(roundi(ui.drive_x.value*100)==int(start[0]) and roundi(ui.drive_y.value*100)==int(start[2]) and ui.drive_surface.get_item_metadata(ui.drive_surface.selected)=="assembled-road-0","test drive uses course start and surface")
	ui.drive_dialog.hide()
	ui.show_tool_group("roads")
	bench.placement.set_free(true)
	bench.select_piece(0)
	bench.placement.begin_move(0,Vector3.ZERO)
	bench.placement.last_point = Vector3.ZERO
	ui.spatial.change_height(1)
	check(bench.placement.candidate.item.position_cm[1] == 100,"height-only move previews")
	ui._cancel_editing()
	check(ui.store.track_source().instances[0].position_cm[1] == 0,"move cancellation retains original")
	var building := {"id":"import-check","footprint":[[0,1000],[400,1000],[400,1400],[0,1400]],"base_cm":0,"height_cm":400,"usage":"residential","material":"brick","roof":"flat"}
	var prepared: Dictionary = ui.store._prepare_command("Import fixture",[{"field":"buildings","id":building.id,"before":null,"after":building}])
	check(not prepared.has("error"),"nonempty track import promotion prepares")
	if not prepared.has("error"):
		var codec := preload("res://scripts/import_command.gd")
		check(not codec.decode(codec.encode(prepared)).has("error"),"owned import transfer permits only unchanged track composition")
		var seeded := preload("res://scripts/document_store.gd").new()
		seeded.document = ui.store.document.duplicate(true)
		seeded.document.assembled_track.seed_source = seeded.document.assembled_track.authoring
		seeded.document.assembled_track.erase("authoring")
		var seed_prepared: Dictionary = seeded._prepare_command("Seed composition",[{"field":"buildings","id":building.id,"before":null,"after":building}])
		check(not seed_prepared.has("error"),"seed source composition prepares: "+str(seed_prepared.get("error","")))
		if not seed_prepared.has("error"): check(not codec.decode(codec.encode(seed_prepared)).has("error"),"seed source composition transfers without geometry changes")
	ui.show_tool_group("scenery")
	ui.scenery.activate("builtin:tree")
	ui.scenery.candidate = {"id":"keep-tree","asset_id":"builtin:tree","position":[600,0,1200],"quarter_turns":0,"yaw_offset_mdeg":0}
	check(ui.scenery.commit(),"scenery command")
	var scenery: Array = ui.store.document.placements.duplicate(true)
	ui.show_tool_group("roads")
	bench.placement.set_free(false)
	bench.anchor_id = bench.source.instances.back().id
	bench.add_piece("straight")
	check(bench.placement.commit(),"track edit after scenery")
	await settle()
	check(ui.store.document.placements == scenery,"scenery survives subsequent track compilation")
	var path := ProjectSettings.globalize_path("user://driving-flow")
	check(ui.store.save_project(path) == "","mixed document saves")
	var reopened := preload("res://scripts/document_store.gd").new()
	check(reopened.open_project(path) == "" and reopened.document.placements == scenery and reopened.track_source().instances.size()==7,"track and scenery reopen together")
	ui.course_tools.suggest()
	ui.store.new_track()
	check(not ui.course_tools.apply_proposal(),"proposal from previous document is rejected")
	# Four gentle turns close directly, without entering coordinates or path lists.
	ui.show_tool_group("roads")
	bench.anchor_id = ""; bench.placement.set_free(false)
	for i in 4:
		bench.add_piece("gentle90")
		if i == 0: check(bench.placement.preview_at(Vector3.ZERO),"circuit first piece preview")
		check(bench.placement.commit(),"circuit connected piece")
		await settle()
	ui.show_tool_group("course")
	ui.course_tools.preview_closure()
	check(ui.course_tools.closure.ok,"circuit closure is validated: "+str(ui.course_tools.closure))
	check(ui.course_tools.apply_closure(),"explicit circuit connection")
	await settle()
	ui.course_tools.suggest()
	check(ui.course_tools.proposal.applicable,"circuit suggestion")
	check(ui.course_tools.apply_proposal(),"circuit course application")
	await settle()
	var circuit_path := ProjectSettings.globalize_path("user://circuit-flow")
	check(ui.store.save_project(circuit_path) == "","circuit saves")
	var exported: Dictionary = JSON.parse_string(ui.store.bridge.export_project(circuit_path,ProjectSettings.globalize_path("user://circuit-flow.memap")))
	check(exported.ok,"assembled circuit exports: "+str(exported.get("error",{})))
	ui.queue_free(); await process_frame; await process_frame
	print("driving_workflow_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
