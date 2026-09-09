extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const SNAPSHOT := preload("res://scripts/project_snapshot.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const WORK := preload("res://scripts/package_work.gd")
const INDEX := preload("res://scripts/preview_index.gd")
var ui: Control
var checks := 0

func _initialize() -> void:
	run.call_deferred()

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		print("E04 check ", checks, ": ", ui.status_label.text if ui != null else "files")
		quit(1)
		assert(value, message)

func ok(value: String, message: String) -> void:
	check(value == "", message + ": " + value)

func wait_work() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline:
		await create_timer(0.002).timeout
	check(not ui.busy, "worker/attachment completes by deadline")

func building(id: String, x: int) -> Dictionary:
	return {"id":id, "footprint":[[x,1000],[x+2000,1000],[x+2000,3000],[x,3000]], "base_cm":0, "height_cm":1000, "usage":"residential", "material":"brick", "roof":"flat"}

func add_building(id: String, x: int) -> void:
	ok(ui.store.apply_command("building", [{"field":"buildings", "id":id, "before":null, "after":building(id,x)}]), "add building")

func click_button(node: Node, title: String) -> bool:
	if node is Button and node.text == title:
		var point: Vector2 = node.get_global_rect().get_center()
		for pressed in [true,false]:
			var event := InputEventMouseButton.new()
			event.position = point
			event.global_position = point
			event.button_index = MOUSE_BUTTON_LEFT
			event.pressed = pressed
			root.push_input(event)
		return true
	for child in node.get_children():
		if click_button(child,title): return true
	return false

func run() -> void:
	root.size = Vector2i(1440,900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	ok(ui.store.apply_command("bounds", [{"field":"bounds", "before":ui.store.document.bounds, "after":{"min":[-51200,-51200], "max":[307200,307200]}}]), "negative origin / seven cells")
	add_building("near", 1000)
	ui.preview_x.value = 1
	ui.preview_y.value = 1
	check(click_button(ui,"3D Preview"), "actual preview button")
	await wait_work()
	check(ui.preview_cache.has(Vector2i(1,1)), "native cell attached")
	var old: Node = ui.preview_cache[Vector2i(1,1)].root
	var generated: int = ui.preview_stats.generated
	ui._preview()
	await wait_work()
	check(ui.preview_stats.generated == generated and ui.preview_cache[Vector2i(1,1)].root == old, "unchanged cell reuses renderer root")
	add_building("remote", 250000)
	ui.preview_due = 0
	ui._preview()
	await wait_work()
	check(ui.preview_stats.generated == generated and ui.preview_cache[Vector2i(1,1)].root == old, "distant changed object does not regenerate unaffected cell")
	var before: Dictionary = ui.store.document.buildings[0].duplicate(true)
	var after := before.duplicate(true)
	after.height_cm += 500
	ok(ui.store.apply_command("height", [{"field":"buildings", "id":before.id, "before":before, "after":after}]), "local change")
	check(is_instance_valid(old) and old.visible, "prior preview remains during debounce")
	var automatic_deadline := Time.get_ticks_msec() + 20000
	while ui.preview_due > 0 and Time.get_ticks_msec() < automatic_deadline: await create_timer(0.002).timeout
	check(ui.preview_due == 0, "document edit automatically schedules visible cell")
	await wait_work()
	check(ui.preview_stats.generated == generated + 1 and ui.preview_cache[Vector2i(1,1)].root != old, "local changed cell replaces once")
	old = ui.preview_cache[Vector2i(1,1)].root
	ui._preview()
	ui._cancel_operation()
	await wait_work()
	check(ui.preview_cache[Vector2i(1,1)].root == old, "cancelled late result cannot replace preview")
	# Changing spinner while a result is in flight must never use its old cell/camera.
	ui._preview()
	ui.preview_x.value = 5
	ui.preview_due = 0
	await wait_work()
	check(not ui.preview_cache.has(Vector2i(5,1)), "stale selection discards result")
	ui._preview()
	await wait_work()
	check(ui.preview_cache.has(Vector2i(5,1)), "new selected cell ready")
	for x in [0,2,3,4]:
		ui.preview_x.value = x
		ui.preview_due = 0
		ui._preview()
		await wait_work()
	check(ui.preview_cache.size() == 4, "bounded four-cell LRU")
	# Unsaved snapshot validation/export does not save or mutate the document.
	var document_before: String = JSON.stringify(ui.store.document)
	ui._validate()
	await wait_work()
	check(ui.last_export_report.get("cell_count",0) == 49, "native report cell count")
	check(ui.last_export_report.base_package_bytes == ui.last_export_report.package_bytes, "no-user compressed base accounting")
	check(ui.last_export_report.full_generation_cells == 0, "full 3D is optional")
	check(JSON.stringify(ui.store.document) == document_before and ui.store.dirty, "validation preserves source and dirty state")
	ui.export_report.hide()
	var export_path := ProjectSettings.globalize_path("user://e04-export.memap")
	ui._start_package("export", export_path)
	ui._cancel_operation()
	await wait_work()
	check(not FileAccess.file_exists(export_path), "cancel never publishes destination")
	ui._start_package("export", export_path)
	# A real revision change invalidates publication even if packing later succeeds.
	add_building("during-export", 200000)
	ui.preview_due = 0
	await wait_work()
	check(not FileAccess.file_exists(export_path), "stale export never publishes destination")
	ui._start_package("export", export_path)
	await wait_work()
	check(FileAccess.file_exists(export_path), "validated snapshot published")
	var digest := FileAccess.get_sha256(export_path)
	ui.export_report.hide()
	ui._start_package("export", export_path)
	check(not ui.busy and FileAccess.get_sha256(export_path) == digest, "existing package never overwritten")
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(native.open_package(export_path)).ok, "export reopens with public native")
	# Save As copies asset bytes AND history-only immutable payloads.
	ui.preview_enabled = false
	ui.preview_due = 0
	ui.store.new_document()
	var source := ProjectSettings.globalize_path("user://e04-source")
	ok(ui.store.save_project(source), "initial save")
	var image := Image.create(4,4,false,Image.FORMAT_RGBA8)
	image.fill(Color.YELLOW)
	var bytes := image.save_png_to_buffer()
	var path := "editor/" + FILES.digest(bytes) + ".png"
	var asset := {"id":"image", "path":path, "attribution":{"source":"Synthetic E04","license":"MIT","notice":"Original"}, "collision":[{"center":[0,100,0],"size_cm":[200,200,200]}]}
	ok(FILES.apply(ui.store,"asset",[{"field":"assets","id":"image","before":null,"after":asset}], {path:bytes}), "immutable asset command")
	ok(ui.store.undo(), "asset becomes history-only redo")
	var target := ProjectSettings.globalize_path("user://e04-copy")
	ok(ui.store.save_project(target), "Save As includes history-only files")
	check(FileAccess.get_file_as_bytes(target.path_join(path)) == bytes, "history file copied byte-exactly")
	ok(ui.store.redo(), "redo after relocation")
	ok(ui.store.undo(), "undo after relocation")
	ok(ui.store.redo(), "redo again")
	ok(ui.store.save_project(target), "save copied asset")
	check(FileAccess.get_file_as_bytes(source.path_join(path)) == bytes, "original payload retained")
	var reopened := STORE.new()
	ok(reopened.open_project(target), "copied project opens independently")
	var second_copy := ProjectSettings.globalize_path("user://e04-current-copy")
	ok(reopened.save_project(second_copy), "Save As copies current referenced asset")
	check(FileAccess.get_file_as_bytes(second_copy.path_join(path)) == bytes, "current asset byte-exact copy")
	ok(reopened.autosave(), "relocated recovery")
	var recovered := STORE.new()
	ok(recovered.recover(reopened.recovery_path()), "recover copied project")
	check(recovered.project_path == second_copy, "recovery keeps copied origin")
	var collision_target := ProjectSettings.globalize_path("user://e04-conflict")
	ok(FILES.write_new(collision_target.path_join(path), "unrelated".to_utf8_buffer()), "conflict fixture")
	var state := JSON.stringify([ui.store.document,ui.store.project_path,ui.store.undo_stack,ui.store.redo_stack,ui.store.dirty])
	check(ui.store.save_project(collision_target) != "", "conflicting destination rejected")
	check(JSON.stringify([ui.store.document,ui.store.project_path,ui.store.undo_stack,ui.store.redo_stack,ui.store.dirty]) == state, "failed Save As keeps session/history")
	check(not FileAccess.file_exists(collision_target.path_join("document.json")), "failed copy publishes no document")
	# Detailed user-asset byte report, optional full generation and overview render.
	ui.full_generation.button_pressed = true
	ui._validate()
	await wait_work()
	check(ui.last_export_report.full_generation_cells == 4, "opt-in full generation checks every cell")
	check(ui.last_export_report.user_asset_bytes == bytes.size() and ui.last_export_report.user_asset_compressed_bytes > 0, "expanded and compressed assets distinguished")
	check(ui.last_export_report.base_package_bytes + ui.last_export_report.user_asset_compressed_bytes == ui.last_export_report.package_bytes, "package partition exact")
	var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
	if capture != "" and DisplayServer.get_name() != "headless":
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(capture) == OK, "rendered capacity/overview capture")
	ui.export_report.hide()
	# Corruption blocks export and preserves prior successful package.
	var file := FileAccess.open(target.path_join(path),FileAccess.WRITE)
	file.store_string("corrupt")
	file.close()
	ui._start_package("export", export_path + "-bad.memap")
	await wait_work()
	check(not FileAccess.file_exists(export_path + "-bad.memap") and FileAccess.get_sha256(export_path) == digest, "invalid source cannot publish or alter existing package")
	check(ui.status_label.text.contains("E_"), "native validation failure is visible")
	# An oversized file is rejected before allocation/copy/publication.
	var huge := FileAccess.open(target.path_join(path),FileAccess.WRITE)
	huge.seek(SNAPSHOT.MAX_BYTES)
	huge.store_8(0)
	huge.close()
	check(not SNAPSHOT.capture(ui.store.document,target).ok, "snapshot byte limit before allocation")
	# Dense terrain must span frames, and cancellation after a batch retains old root.
	ui.store.new_document()
	var dense_source := ProjectSettings.globalize_path("user://e04-dense")
	ok(ui.store.save_project(dense_source), "dense source")
	ui.preview_x.value = 0
	ui.preview_y.value = 0
	ui._preview()
	await wait_work()
	old = ui.preview_cache[Vector2i.ZERO].root
	var heights := PackedInt64Array()
	heights.resize(257 * 257)
	heights.fill(0)
	var encoded := preload("res://scripts/terrain_png.gd").encode(heights,257)
	var tile_path := "editor/" + FILES.digest(encoded.bytes) + ".png"
	var tile := {"cell":{"x":0,"y":0},"path":tile_path,"spacing_cm":200,"offset_cm":encoded.offset_cm,"step_cm":encoded.step_cm,"source_accuracy_cm":200}
	ok(FILES.apply(ui.store,"dense terrain",[{"field":"heightmaps","id":ui.store.record_id("heightmaps",tile),"before":null,"after":tile}],{tile_path:encoded.bytes}), "dense native source")
	ui.preview_due = 0
	ui.set_process(false)
	ui._preview()
	var deadline := Time.get_ticks_msec() + 20000
	while ui.worker.is_alive() and Time.get_ticks_msec() < deadline: await create_timer(0.002).timeout
	check(not ui.worker.is_alive(), "dense worker completes")
	ui._process(0)
	check(not ui.render_job.is_empty() and old.visible and not ui.render_staged.visible, "hidden staged attachment preserves prior view")
	ui._advance_attachment()
	check(not ui.render_job.is_empty() and old.visible, "bounded attachment yields between frames")
	ui._cancel_operation()
	check(ui.render_job.is_empty() and ui.preview_cache[Vector2i.ZERO].root == old and old.visible, "mid-attachment cancellation releases only candidate")
	ui.set_process(true)
	var frames: int = ui.preview_stats.attachment_frames
	ui._preview()
	await wait_work()
	check(ui.preview_stats.attachment_frames > frames + 1, "dense preview completes over multiple frames")
	check(ui.preview_cache[Vector2i.ZERO].root != old, "dense result atomically replaces prior preview")
	# Refuse excessive work from source-derived estimate without generation.
	var too_large: Dictionary = ui.store.document.duplicate(true)
	too_large.zones = [{"id":"dense-zone","kind":"forest","polygon":[[0,0],[51200,0],[51200,51200],[0,51200]],"spacing_cm":200,"density_per_mille":1000,"exclusions":[]}]
	var extra_zone: Dictionary = too_large.zones[0].duplicate(true)
	extra_zone.id = "dense-zone-2"
	too_large.zones.append(extra_zone)
	extra_zone = extra_zone.duplicate(true)
	extra_zone.id = "dense-zone-3"
	too_large.zones.append(extra_zone)
	var captured := SNAPSHOT.capture(too_large,dense_source)
	check(captured.ok, "budget fixture document")
	var staged := SNAPSHOT.stage(captured.data)
	check(staged.ok, "budget fixture native")
	check(not WORK.new().allowance(staged.data.bridge,Vector2i.ZERO).ok, "estimate rejects oversized preview work")
	FILES.remove_scratch(staged.data.path)
	print("E04 metrics: ", JSON.stringify(ui.preview_stats))
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("preview_export_validator: PASS (", checks, " checks)")
	quit(0)
