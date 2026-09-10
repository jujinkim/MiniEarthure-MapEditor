extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const BROWSER := preload("res://scripts/import_review_browser.gd")
const TEXT := preload("res://scripts/import_review_text.gd")
var ui: Control
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures.append(message); push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_job() -> void:
	var deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "import joins: " + ui.status_label.text)
func wait_page(browser: AcceptDialog) -> void:
	var deadline := Time.get_ticks_msec() + 5000
	while browser.scanning and Time.get_ticks_msec() < deadline: await process_frame
	check(not browser.scanning, "bounded page scan completes")
func enter(browser: AcceptDialog, key: Variant) -> void:
	var index: int = browser.page_keys.find(key)
	check(index >= 0, "field available: " + str(key).substr(0, 80))
	if index >= 0: browser.descend(index)
func capture(name: String) -> void:
	if DisplayServer.get_name() == "headless" or OS.get_environment("MAPEDITOR_CAPTURE_PATH") == "": return
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CAPTURE_PATH") + "." + name + ".png") == OK, "capture " + name)
func pointer(button: Button) -> void:
	var window := button.get_window()
	for down in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = button.get_global_rect().get_center() + Vector2(window.position)
		event.global_position = event.position
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = down
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
		root.push_input(event)
		await process_frame
func run() -> void:
	root.size = Vector2i(1024, 720)
	ui = load("res://main.tscn").instantiate(); root.add_child(ui)
	await process_frame
	var source := ProjectSettings.globalize_path("user://source.geojson")
	var raw := '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[30,10],[30,30],[10,30],[10,10]]]}}]}'
	var file := FileAccess.open(source, FileAccess.WRITE); file.store_string(raw); file.close()
	ui._start_worker("import", source, "CC0 synthetic fixture"); await wait_job()
	check(ui.pending_import != null, "actual owned import reaches review")
	if ui.pending_import == null: await finish(); return
	var actual: RefCounted = ui.pending_import
	var before := JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack])
	var original := JSON.stringify(actual.value)
	# Stress only presentation with synthetic metadata; do not alter validated data.
	var mapping: Array = []
	for i in range(20000): mapping.append({"source_way":str(i), "source_range":[0, 2], "endpoints":[{"ref":"node-" + str(i)}]})
	var long_text := "첫 줄 🌍\n\tquoted \"source\" \\ exact\r\n".repeat(500)
	var wide := {}
	for i in range(4096): wide["field-%04d" % i] = i
	var long_key := "key 🌍 / ~ ".repeat(600)
	wide[long_key] = "full field name retained"
	var stress: RefCounted = LAYER.new()
	stress.value = actual.value.duplicate(true)
	stress.value.coordinates.osm_crop = {"policy":"synthetic-review-only", "mappings":mapping}
	stress.value.coordinates.osm_connections = {"joins":mapping}
	stress.value.coordinates.osm_stream = {"profile":"pbf-area-stream-v1", "selected":{"nodes":20000}}
	stress.value.coordinates.large_unknown = wide
	stress.value.captured_json = long_text
	stress.value.warnings = []; stress.value.estimates = {}
	for i in range(50): stress.value.warnings.append(("Warning %d " % i).rpad(512, "!"))
	stress.value.warning_count = 500
	for i in range(32): stress.value.estimates[("estimate-%d" % i).rpad(512, "x")] = i
	var fingerprint := JSON.stringify(stress.value).sha256_text()
	var summary: String = stress.summary()
	check(summary.length() <= TEXT.MAX_SUMMARY_CHARS and summary.contains("20000 items") and not summary.contains("node-19999"), "large mappings use bounded counts without full serialization")
	check(summary.contains("showing 50 of 50") and summary.contains("showing 32 of 32") and summary.contains("Browse exact details"), "existing bounded warning/estimate samples retained; source omissions explicit")
	ui._review_import(stress)
	await process_frame
	check(ui.import_review.size.x <= 1024 and ui.import_review.size.y <= 720, "summary fits minimum window")
	await capture("summary")
	ui._open_import_details()
	var browser: AcceptDialog = ui.import_details
	await process_frame
	check(browser.visible and browser.rows.item_count <= BROWSER.PAGE_ITEMS, "detail view opens bounded root")
	enter(browser, "coordinates"); enter(browser, "osm_crop"); enter(browser, "mappings")
	check(browser.page.max_value == 834 and browser.rows.item_count == 24, "large array has explicit pages")
	await process_frame
	check(browser.size.x <= 1024 and browser.size.y <= 720, "24-row detail page fits minimum window: " + str({"window":browser.size, "label":browser.location.get_combined_minimum_size(), "rows":browser.rows.get_combined_minimum_size(), "text":browser.content.get_combined_minimum_size(), "auto_height":browser.rows.auto_height}))
	await capture("mappings")
	await pointer(browser.next)
	check(browser.page.value == 2 and browser.page_keys[0] == 24, "pointer Next navigates an embedded detail dialog")
	browser.show_page(833)
	check(browser.page_keys[0] == 19992 and browser.page_keys.back() == 19999 and browser.next.disabled, "direct final page reaches all remaining records")
	enter(browser, 19999); enter(browser, "source_way")
	check(JSON.parse_string(browser.content.text) == "19999" and not browser.content.editable, "exact last mapping readable")
	browser.go_up(); browser.go_up()
	check(browser.page.value == 834, "Up restores parent page")
	browser.clear(); ui._open_import_details(); enter(browser, "captured_json")
	var recovered := ""
	for number in range(int(browser.page.max_value)):
		browser.show_page(number)
		check(browser.exact_page.length() <= BROWSER.PAGE_CHARS and browser.content.text.length() <= 6 * BROWSER.PAGE_CHARS + 2, "raw and escaped display page character bounds")
		recovered += JSON.parse_string(browser.content.text)
	check(recovered == long_text, "all exact Unicode, newline, tab, quote and backslash source text survives paging")
	await capture("raw")
	browser.clear(); ui._open_import_details(); enter(browser, "coordinates"); enter(browser, "large_unknown")
	browser.show_page(170)
	check(browser.scanning, "wide object traversal yields while skipping pages")
	await wait_page(browser)
	check(browser.page_keys.back() == long_key, "final wide-object field accessible")
	browser.descend(browser.page_keys.size() - 1, true)
	recovered = ""
	for number in range(int(browser.page.max_value)):
		browser.show_page(number); recovered += JSON.parse_string(browser.content.text)
	check(recovered == long_key, "full long field name accessible")
	browser.go_up(); await wait_page(browser)
	browser.show_page(170); browser.show_page(0)
	await process_frame
	check(not browser.scanning and browser.page_keys[0] == "field-0000" and browser.rows.item_count == 24, "old scan cannot publish over a newer page")
	browser.show_page(170)
	ui.import_origin_x.value += 1; ui.import_origin_x.value -= 1
	await process_frame
	check(ui.pending_import == null and not browser.visible and browser.current == null and browser.parents.is_empty() and browser.rows.item_count == 0 and ui.import_summary.text == "", "changed/restored selection clears review and cancels pending detail scan")
	check(JSON.stringify(stress.value).sha256_text() == fingerprint, "browsing never mutates or truncates complete provenance")
	check(JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack]) == before, "stress review preserves document/history")
	ui._review_import(actual); ui._open_import_details()
	await process_frame
	await pointer(browser.get_ok_button())
	check(not browser.visible and ui.import_review.visible and ui.pending_import == actual and browser.current == null, "pointer Back releases detail references and retains review")
	ui._adopt_import(); await wait_job()
	check(ui.store.document.buildings.size() == 1 and ui.store.undo_stack.size() == 1, "actual candidate adopts once after detail review")
	check(ui.store.document.attributions[0].notice.contains(actual.value.source.sha256), "complete attribution remains in atomic command")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo() == "" and ui.store.document.buildings.is_empty(), "Undo preserves prior map")
	check(ui.store.redo() == "" and ui.store.document == adopted, "Redo restores exact imported provenance")
	var project := ProjectSettings.globalize_path("user://review-project")
	check(ui.store.save_project(project) == "", "save reviewed layer")
	var pack := ProjectSettings.globalize_path("user://review.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project, pack)).ok, "reviewed provenance exports in native package")
	var pack_hash := FileAccess.get_sha256(pack)
	ui._review_import(actual); ui._open_import_details()
	ui.store.new_document(); await process_frame
	check(not browser.visible and ui.pending_import == null and browser.current == null, "document replacement invalidates open details")
	ui._start_worker("import", source, "CC0 synthetic fixture"); ui._cancel_operation(); await wait_job()
	check(ui.pending_import == null and not browser.visible, "cancelled worker cannot reopen old review")
	check(FileAccess.get_file_as_string(source) == raw and FileAccess.get_sha256(pack) == pack_hash and JSON.stringify(actual.value) == original, "original source, prior package and candidate preserved")
	ui._review_import(stress); ui._open_import_details(); enter(browser, "coordinates"); enter(browser, "large_unknown"); browser.show_page(170)
	await finish()
func finish() -> void:
	ui.store.dirty = false
	ui.queue_free(); await process_frame; await process_frame
	print("import_review_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)
