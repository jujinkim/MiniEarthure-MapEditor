extends SceneTree
const EDITOR := preload("res://scripts/editor_main.gd")
const STORE := preload("res://scripts/document_store.gd")
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool, label: String) -> void:
	if not value: failures.append(label); push_error(label)
func settle(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+10000
	while ui.store.track_edit_busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.store.track_edit_busy, "bounded pipe edit completion")
func run() -> void:
	var ui := EDITOR.new(); root.add_child(ui); await process_frame
	var bench: Node = ui.track_workbench
	bench.add_piece("cylinder_curve")
	check(bench.placement.width_cm == 200, "new general pipe defaults to 2m")
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit(), "new pipe preview and placement")
	await settle(ui)
	bench.placement.cancel(); bench.select_piece(0); bench._properties()
	var widths: Array = []
	for i in bench.width.item_count: widths.append(bench.width.get_item_id(i))
	check(widths == [100,200,300,400,600], "manual 1/2/3/4/6m choices")
	check(bench.port_widths[0].min_value == 1 and bench.port_widths[1].min_value == 1, "pipe port inputs admit 1m")
	for width in [100,300,400,600]:
		bench.select_piece(0); bench._properties()
		for i in bench.width.item_count:
			if bench.width.get_item_id(i) == width: bench.width.select(i)
		bench.port_widths[0].value = float(width)/100; bench.port_widths[1].value = float(width)/100
		var before: Dictionary = ui.store.document.duplicate(true)
		bench.apply_properties(); await settle(ui)
		check(int(bench.source.instances[0].width_cm) == width and int(ui.store.document.gimmicks[0].track.radius_cm) == width/2, "source/compiled bore edit %d" % width)
		var after: Dictionary = ui.store.document.duplicate(true)
		ui._history(false); await settle(ui)
		check(ui.store.document == before, "Undo exact source and geometry %d" % width)
		ui._history(true); await settle(ui)
		check(ui.store.document == after, "Redo exact source and geometry %d" % width)
		var path := ProjectSettings.globalize_path("user://pipe-%d" % width)
		check(ui.store.save_project(path) == "", "save pipe %d" % width)
		var reopened := STORE.new()
		check(reopened.open_project(path) == "", "reopen pipe %d" % width)
		check(reopened.document.assembled_track == JSON.parse_string(JSON.stringify(after.assembled_track)), "preserved authoring size/geometry on reopen %d" % width)
	var document: Dictionary = ui.store.document.duplicate(true)
	var history: Array = ui.store.undo_stack.duplicate(true)
	bench.add_piece("cylinder"); bench.placement.width_cm = 100
	check(bench.placement.preview_at(Vector3(30,0,0)), "1m pending placement")
	var serial: int = bench.placement.serial
	bench.cancel_interaction()
	check(not bench.placement.commit(serial) and ui.store.document == document and ui.store.undo_stack == history, "cancel rejects stale preview without history")
	# The ordinary-road defaults/range are unchanged.
	bench.add_piece("straight"); check(bench.placement.width_cm == 400, "ordinary road default remains 4m"); bench.cancel_interaction()
	# Standalone template and centimetre input resolution preserve 1.25m radius.
	ui.store.new_document()
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.gimmick_panel
	for i in panel.template.item_count:
		if str(panel.template.get_item_metadata(i)) == "cylinder": panel.template.select(i)
	panel.load_controls(panel.templates.cylinder)
	check(panel.controls.radius.min_value == 0.5 and panel.controls.radius.value == 1.25, "standalone default 2.5m bore survives input quantization")
	var standalone: Dictionary = panel.draft()
	check(standalone.track.radius_cm == 125 and standalone.track.length_cm == 1600, "standalone length remains 16m")
	panel.controls.radius.value = 0.5; panel.show_preview()
	check(panel.preview.get_child(0).get_child_count() == 2, "1m standalone shared preview")
	panel.save_record()
	check(ui.store.document.gimmicks.size() == 1 and ui.store.document.gimmicks[0].track.radius_cm == 50, "save minimum standalone bore")
	check(ui.store.undo() == "" and ui.store.document.get("gimmicks", []).is_empty(), "standalone Undo")
	check(ui.store.redo() == "" and ui.store.document.gimmicks[0].track.radius_cm == 50, "standalone Redo")
	var path := ProjectSettings.globalize_path("user://standalone-pipe")
	check(ui.store.save_project(path) == "", "save standalone project")
	var reopened := STORE.new()
	check(reopened.open_project(path) == "" and reopened.document.gimmicks == JSON.parse_string(JSON.stringify(ui.store.document.gimmicks)), "standalone reopen retains explicit dimensions and colour")
	ui.queue_free(); await process_frame; await process_frame
	print("pipe_edit_validator: ", "PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
