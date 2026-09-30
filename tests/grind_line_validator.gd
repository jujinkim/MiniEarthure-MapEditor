extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const EDITOR := preload("res://scripts/editor_main.gd")
const PANEL := preload("res://scripts/grind_line_panel.gd")
var failures: Array[String]=[]
func _initialize() -> void: run.call_deferred()
func check(ok: bool,label: String) -> void:
	if not ok:failures.append(label);push_error(label)
func settle(screen: Control) -> void:
	var deadline:=Time.get_ticks_msec()+10000
	while screen.store.track_edit_busy and Time.get_ticks_msec()<deadline:await process_frame
	await process_frame;await process_frame
	check(not screen.store.track_edit_busy,"bounded line transaction")
func run() -> void:
	var screen:=EDITOR.new();root.add_child(screen);await process_frame
	var bench: Node=screen.track_workbench
	var panel:=PANEL.new();root.add_child(panel);panel.open(bench)
	panel.add_line(false);await settle(screen)
	check(bench.source.grind_lines.size()==1 and screen.store.document.grind_lines.size()==1,"independent palette air line")
	panel.points.text="0, 100, 0\n0, 100, 300\n300, 100, 300\n300, 100, 600"
	panel.apply_line();await settle(screen)
	check(bench.source.grind_lines[0].control_points.size()==4,"cubic authoring transaction")
	var saved: Dictionary=screen.store.document.duplicate(true)
	panel.points.text="invalid";panel.apply_line();await settle(screen)
	check(screen.store.document==saved,"invalid edit preserves current source")
	panel.add_line(false);await settle(screen)
	panel.points.text="300, 100, 600\n300, 100, 1000";panel.start_links.text="grind-1:end";panel.apply_line();await settle(screen)
	check(bench.source.grind_lines[1].start_connections.size()==1,"explicit endpoint connection")
	panel.identifier.text="landing";panel.apply_line();await settle(screen)
	panel.select(0);panel.end_links.text="landing:start";panel.apply_line();await settle(screen)
	check(bench.source.grind_lines[0].end_connections[0].line=="landing","stable named link")
	var before_delete: Dictionary=screen.store.document.duplicate(true)
	panel.select(1);panel.remove_line();await settle(screen)
	check(bench.source.grind_lines.size()==1 and bench.source.grind_lines[0].end_connections.is_empty(),"delete removes endpoint references")
	check(screen.store.undo()=="" and screen.store._signature(screen.store.document)==screen.store._signature(before_delete),"undo restores line and links")
	var path:=ProjectSettings.globalize_path("user://grind-source")
	check(screen.store.save_project(path)=="","save line source")
	var reopened:=STORE.new()
	check(reopened.open_project(path)=="" and reopened.document.grind_lines==before_delete.grind_lines,"reopen retains curves and connections")
	var next: Dictionary=bench.source.duplicate(true)
	check(screen.store.start_track_edit(next)=="","line worker request")
	var epoch: int=screen.store.command_epoch
	screen.store.cancel_track_edit();await settle(screen)
	check(screen.store._signature(screen.store.document)==screen.store._signature(before_delete) and screen.store.command_epoch==epoch,"cancel keeps source/history")
	panel.queue_free();screen.queue_free();await process_frame
	print("grind_line_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
