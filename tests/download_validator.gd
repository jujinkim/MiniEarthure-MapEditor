extends SceneTree
const JOB := preload("res://scripts/download_job.gd")
class FixtureJob extends "res://scripts/download_job.gd":
	func _spawn(python: String, arguments: PackedStringArray) -> Dictionary:
		arguments.insert(2, ProjectSettings.globalize_path("res://tests/download_child_fixture.py"))
		return OS.execute_with_pipe(python, arguments, false)
class FixtureUI extends "res://scripts/editor_main.gd":
	func _new_download_job() -> RefCounted: return FixtureJob.new()
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_job(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "download/import terminates: " + ui.status_label.text)
func run() -> void:
	var ui := FixtureUI.new()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.download_url.text = "https://download.geofabrik.de/europe/monaco-latest.osm.pbf"
	ui._open_download()
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	await wait_job(ui)
	check(not ui.download_plan.is_empty(), "provider plan received through owned child IPC: " + ui.status_label.text)
	if ui.download_plan.is_empty(): quit(1); return
	check(ui.download_summary.text.contains("Expected transfer:") and ui.download_summary.text.contains("ODbL"), "size/license review")
	check(not ui.download_dialog.get_ok_button().disabled, "explicit download available after review")
	if DisplayServer.get_name() != "headless":
		root.size = Vector2i(1024,720)
		ui.download_dialog.popup_centered(Vector2i(760,460))
		await process_frame
		check(ui.download_dialog.size.x <= 1024 and ui.download_dialog.size.y <= 720, "download wizard fits minimum window")
		await RenderingServer.frame_post_draw
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "": check(root.get_texture().get_image().save_png(capture) == OK, "wizard screenshot")
	var before: Dictionary = ui.store.document.duplicate(true)
	ui.download_dialog.hide()
	ui.download_dialog.confirmed.emit()
	await wait_job(ui)
	var source: String = ui.last_import_source
	check(FileAccess.file_exists(source), "completed original published: " + ui.status_label.text)
	check(ui.store.document == before and ui.pending_import == null, "download alone never adopts")
	check(ui.import_dialog.visible and ui.import_source_format.selected == 1, "continue to explicit origins")
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_dialog.hide()
	ui._start_import(source, ui.IMPORT_LAYER.OSM_LICENSE)
	await wait_job(ui)
	check(ui.pending_import != null, "downloaded PBF reaches native review: " + ui.status_label.text)
	if ui.pending_import == null: quit(1); return
	check(ui.import_summary.text.contains("https://download.geofabrik.de/"), "provider provenance survives local conversion")
	ui._adopt_import()
	check(ui.store.document.buildings.size() == 1, "explicit atomic adoption")
	check(ui.store.undo() == "", "downloaded source Undo succeeds")
	var undone: Dictionary = ui.store.document.duplicate(true)
	undone.provenance.last_edited = before.provenance.last_edited
	check(undone == before, "downloaded source Undo restores document except edit timestamp")
	check(ui.store.redo() == "", "downloaded source Redo")
	var original := FileAccess.get_sha256(source)
	var plan: Dictionary = ui.download_plan.duplicate(true)
	var cancelled_target := ProjectSettings.globalize_path("user://cancelled.osm.pbf")
	ui._begin_acquisition({"mode":"download", "plan":plan, "destination":cancelled_target})
	var owned: RefCounted = ui.import_job
	ui._cancel_operation()
	await wait_job(ui)
	check(not FileAccess.file_exists(cancelled_target) and not DirAccess.dir_exists_absolute(owned.directory), "cancelled partial/job cleanup")
	check(FileAccess.get_sha256(source) == original, "cancellation preserves completed original")
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	ui.download_url.text = "https://download.geofabrik.de/europe/andorra-latest.osm.pbf"
	await wait_job(ui)
	check(ui.download_plan.is_empty() and ui.download_dialog.get_ok_button().disabled, "changed URL rejects late plan")
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	await wait_job(ui)
	check(not ui.download_plan.is_empty(), "fresh retry after cancellation/stale reply")
	ui.download_url.text = "https://download.geofabrik.de/europe/slow-latest.osm.pbf"
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	await wait_job(ui)
	plan = ui.download_plan.duplicate(true)
	ui._begin_acquisition({"mode":"download", "plan":plan, "destination":cancelled_target})
	owned = ui.import_job
	var partial_deadline := Time.get_ticks_msec() + 5000
	while ui.busy and int(owned.progress.get("completed",0)) == 0 and Time.get_ticks_msec() < partial_deadline: await process_frame
	check(ui.busy and FileAccess.file_exists(owned.directory.path_join("download.part")), "actual partial exists before cancel")
	ui._cancel_operation()
	await wait_job(ui)
	check(not FileAccess.file_exists(cancelled_target) and not DirAccess.dir_exists_absolute(owned.directory), "mid-transfer cancellation removes only owned partial")
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	owned = ui.import_job
	owned.poll(owned.deadline_ms)
	await wait_job(ui)
	check(owned.result.error.message.contains("timed out") and not DirAccess.dir_exists_absolute(owned.directory), "deadline stops acquisition and cleans partial")
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	ui.generation += 1
	await wait_job(ui)
	check(ui.download_plan.is_empty(), "document generation rejects completed plan")
	ui._begin_acquisition({"mode":"probe", "url":ui.download_url.text})
	owned = ui.import_job
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.pid == -1 and not DirAccess.dir_exists_absolute(owned.directory), "owner close stops child and cleans job")
	print("download_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
