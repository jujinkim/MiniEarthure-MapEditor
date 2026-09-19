extends SceneTree
const WORK := preload("res://scripts/package_work.gd")
const STORE := preload("res://scripts/document_store.gd")
class Estimate extends RefCounted:
	var bytes := WORK.PREVIEW_BYTES * 3 / 4
	var calls := 0
	func query_cells(_a: int,_b: int,_c: int,_d: int,_limit: int) -> String:
		return JSON.stringify({"ok":true,"data":{"geometry_cells":[{"x":0,"y":0}]}})
	func estimate_chunk(_x: int,_y: int) -> String:
		calls += 1
		return JSON.stringify({"ok":true,"data":{"generation_scratch_bytes":bytes,"triangles":0,"max_object_id_bytes":0,"objects":0,"presentation_bytes":0,"building_prisms":0,"asset_convexes":0}})
var failed := false
func check(value: bool, message: String) -> void:
	if not value: failed = true; push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var store := STORE.new()
	store.new_document()
	var snapshot := {"document":store.document,"hashes":{}}
	var index := {"cells":{}}
	var native := Estimate.new()
	var work := WORK.new()
	var report := work.density_report(native,snapshot,index,{})
	check(report.ok and report.data["0/0"].warning == "high", "75 percent work allowance warns without object count")
	var reused := work.density_report(native,snapshot,index,report.data)
	check(reused.ok and native.calls == 1, "unchanged chunk estimate reused")
	native.bytes = WORK.PREVIEW_BYTES + 1
	report = work.density_report(native,snapshot,index,{})
	check(report.ok and report.data["0/0"].warning == "over limit", "warning is nonblocking; preview allowance remains enforced separately")
	native.bytes = WORK.PREVIEW_BYTES * 3 / 4 - 1
	report = work.density_report(native,snapshot,index,{})
	check(report.ok and report.data["0/0"].warning == "", "reduced cost clears warning")
	work.cancel()
	check(not work.density_report(native,snapshot,index,{}).ok, "cancelled analysis cannot publish")
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var panel: Control = ui.density_panel
	panel.rows = report.data
	panel._show_rows()
	panel._select(0)
	check(panel.details.text.contains("estimates"), "cost details distinguish estimates")
	panel.record_preview(Vector2i.ZERO,report.data["0/0"].signature,5.01)
	check(panel.measured_delays.has("0/0") and panel.details.text.contains("measured"), "slow preview is a separate measured warning")
	var epoch: int = panel.generation
	check(ui.store.apply_command("Seed",[{"field":"seed","before":ui.store.document.seed,"after":43}]).is_empty(), "edit accepted while warnings exist")
	check(panel.generation > epoch and panel.rows.is_empty() and panel.measured_delays.is_empty(), "edit invalidates estimated and measured results")
	epoch = panel.generation
	check(ui.store.undo().is_empty() and panel.generation > epoch, "Undo invalidates density generation")
	epoch = panel.generation
	check(ui.store.redo().is_empty() and panel.generation > epoch, "Redo invalidates density generation")
	var before: int = panel.generation
	ui.store.new_document()
	check(panel.generation > before and panel.rows.is_empty() and ui.canvas.density_cells.is_empty(), "document replacement clears stale results immediately")
	panel.cancel()
	check(panel.due == 0 and panel.rows.is_empty(), "cancel clears pending publication")
	ui.queue_free()
	await process_frame
	print("chunk_density_validator: ", "FAIL" if failed else "PASS")
	quit(1 if failed else 0)
