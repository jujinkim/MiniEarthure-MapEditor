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
	check(bench.placement.width_cm == 400, "new general pipe defaults to 4m")
	check(bench.placement.preview_at(Vector3.ZERO) and bench.placement.commit(), "new pipe preview and placement")
	await settle(ui)
	bench.placement.cancel(); bench.select_piece(0); bench._properties()
	var widths: Array = []
	for i in bench.width.item_count: widths.append(bench.width.get_item_id(i))
	check(widths == [400,600], "manual 4/6m choices")
	check(bench.port_widths[0].min_value == 4 and bench.port_widths[1].min_value == 4, "pipe port inputs admit 4m")
	for width in [600,400]:
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
	bench.add_piece("cylinder"); bench.placement.width_cm = 400
	check(bench.placement.preview_at(Vector3(30,0,0)), "4m pending placement")
	var serial: int = bench.placement.serial
	bench.cancel_interaction()
	check(not bench.placement.commit(serial) and ui.store.document == document and ui.store.undo_stack == history, "cancel rejects stale preview without history")
	# The ordinary-road defaults/range are unchanged.
	bench.add_piece("straight"); check(bench.placement.width_cm == 400, "ordinary road default remains 4m"); bench.cancel_interaction()
	# Standalone defaults and controls use the shared catalogue.
	ui.store.new_document()
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.gimmick_panel
	for i in panel.template.item_count:
		if str(panel.template.get_item_metadata(i)) == "cylinder": panel.template.select(i)
	panel.load_controls(panel.templates.cylinder)
	check(panel.controls.radius.min_value == 2.0 and panel.controls.radius.value == 2.0, "standalone default 4m bore")
	var standalone: Dictionary = panel.draft()
	check(standalone.track.radius_cm == 200 and standalone.track.length_cm == 1600, "standalone length remains 16m")
	panel.controls.radius.value = 2.0; panel.show_preview()
	check(panel.preview.get_child(0).get_child_count() == 2, "4m standalone shared preview")
	panel.save_record()
	check(ui.store.document.gimmicks.size() == 1 and ui.store.document.gimmicks[0].track.radius_cm == 200, "save minimum standalone bore")
	check(ui.store.undo() == "" and ui.store.document.get("gimmicks", []).is_empty(), "standalone Undo")
	check(ui.store.redo() == "" and ui.store.document.gimmicks[0].track.radius_cm == 200, "standalone Redo")
	var path := ProjectSettings.globalize_path("user://standalone-pipe")
	check(ui.store.save_project(path) == "", "save standalone project")
	var reopened := STORE.new()
	check(reopened.open_project(path) == "" and reopened.document.gimmicks == JSON.parse_string(JSON.stringify(ui.store.document.gimmicks)), "standalone reopen retains explicit dimensions and colour")
	await stored_sizes(ui)
	ui.queue_free(); await process_frame; await process_frame
	print("pipe_edit_validator: ", "PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)

func stored_sizes(ui: Control) -> void:
	for bore: int in [200, 300]:
		var package := ProjectSettings.globalize_path("res://addons/mapkit/crates/mapkit-package/tests/fixtures/stored-pipe-%d-v1.memap" % bore)
		var project := ProjectSettings.globalize_path("user://stored-%d" % bore)
		var opened: Dictionary = JSON.parse_string(ui.store.bridge.open_package(package))
		check(opened.ok, "read stored package")
		var unpacked: Dictionary = JSON.parse_string(ui.store.bridge.unpack_source(project))
		check(unpacked.ok, "unpack stored %dm pipe" % bore)
		var failure: String = ui.store.open_project(project)
		check(failure == "", "open saved narrow package: " + failure)
		if not failure.is_empty(): continue
		var original: Dictionary = ui.store.document.duplicate(true)
		var bench: Node = ui.track_workbench
		bench.refresh(); bench.select_piece(2); bench._properties()
		check(bench.width.get_selected_id() == bore and bench.port_widths[0].value == bore/100.0, "opening controls preserves stored width")
		check(not ui.store.track_pieces()[2].path.is_empty(), "stored path remains visible")
		var rejected: Dictionary = JSON.parse_string(ui.store.bridge.compile_track_source(JSON.stringify(ui.store.track_source())))
		check(not rejected.ok and ui.store.document == original, "narrow recompilation rejected without mutation")
		var source: Dictionary = ui.store.track_source().duplicate(true)
		for item: Dictionary in source.instances:
			if int(item.width_cm) < 400: item.width_cm = 400
			if int(item.entry_width_cm) < 400: item.entry_width_cm = 400
			if int(item.exit_width_cm) < 400: item.exit_width_cm = 400
		check(ui.store.start_track_edit(source) == "", "explicitly repair narrow source")
		await settle(ui)
		check(ui.store.draft_error.is_empty() and not ui.store.draft_pending(), "repair compiles")
		var repaired: Dictionary = ui.store.document.duplicate(true)
		check(ui.store.undo() == "", "undo repair accepted")
		ui.store.cancel_track_edit(); await settle(ui)
		check(ui.store.document == repaired and ui.store.draft_pending(), "cancelled stored restoration preserves current map")
		ui.store.retry_track_edit(); await settle(ui)
		check(ui.store.document == original and not ui.store.draft_pending(), "Undo restores exact stored geometry without recompilation")
		check(ui.store.redo() == "", "redo repair accepted"); await settle(ui)
		check(ui.store.document == repaired, "Redo restores new geometry")
	# A standalone saved cylinder is also readable, but geometry edits need new dimensions.
	ui.store.new_document()
	var templates: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://addons/mapkit/godot/driving_templates.json"))
	var old: Dictionary = templates.cylinder.duplicate(true)
	old.id = "saved-narrow"; old.track.radius_cm = 125
	ui.store.document.gimmicks = [old]
	var before: Dictionary = ui.store.document.duplicate(true)
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.gimmick_panel
	panel.load_controls(old)
	check(panel.controls.radius.value == 1.25, "stored standalone radius is not clamped")
	var changed := old.duplicate(true); changed.track.length_cm = 1800
	check(not ui.store.apply_command("narrow geometry", [{"field":"gimmicks","id":old.id,"before":old,"after":changed}]).is_empty(), "narrow standalone edit rejected")
	check(ui.store.document == before, "failed standalone edit preserves document")
	changed.track.radius_cm = 200
	check(ui.store.apply_command("repair standalone", [{"field":"gimmicks","id":old.id,"before":old,"after":changed}]) == "", "standalone repair")
	check(ui.store.undo() == "" and int(ui.store.document.gimmicks[0].track.radius_cm) == 125, "standalone Undo restores old radius")
