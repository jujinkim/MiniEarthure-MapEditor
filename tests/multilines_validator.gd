extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
var failures: Array[String] = []
var checks := 0
func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_import(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "multipart worker terminates: " + ui.status_label.text)
func write(path: String, data: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()
func capture(name: String) -> void:
	var folder := OS.get_environment("MAPEDITOR_MULTILINES_CAPTURE_DIR")
	if DisplayServer.get_name() == "headless" or folder == "": return
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(folder.path_join(name + ".png")) == OK, "capture " + name)
func pointer(button: Button) -> void:
	await process_frame
	for down in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = button.get_global_rect().get_center() + Vector2(button.get_window().position)
		event.global_position = event.position
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = down
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
		root.push_input(event)
		await process_frame
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	root.size = Vector2i(1024,720)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var base := ProjectSettings.globalize_path("user://multilines")
	DirAccess.make_dir_recursive_absolute(base)
	var path := base.path_join("multipart roads.geojson")
	var geo := {"type":"FeatureCollection", "features":[{"type":"Feature", "properties":{"width_m":6,"surface":"gravel"},
		"geometry":{"type":"MultiLineString", "coordinates":[[[40,40],[100,40],[150,60]],[[180,80],[240,80]],[[240,120],[180,120]]]}}]}
	write(path, geo)
	var source_hash := FileAccess.get_sha256(path)
	check(ui.store.save_project(base.path_join("original")) == "", "save baseline")
	var package := base.path_join("original.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(ui.store.project_path, package)).ok, "export baseline")
	check(JSON.parse_string(ui.store.bridge.open_package(package)).ok, "load baseline bridge")
	var baseline_chunk: String = ui.store.bridge.generate_chunk(0,0)
	var package_hash := FileAccess.get_sha256(package)
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.store.document == before and ui.store.undo_stack.is_empty(), "review is nonmutating: " + ui.status_label.text)
	if ui.pending_import == null:
		ui.store.dirty = false
		ui.queue_free()
		await process_frame
		quit(1)
		return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	check(raw.feature_count == 1 and raw.point_count == 7 and raw.patches.size() == 9, "source feature and output record counts")
	check(ui.import_summary.text.contains("geojson_multilines") and ui.import_summary.text.contains("disconnected") and ui.import_summary.text.contains(source_hash), "review exposes profile, policy and source hash")
	check(ui.store.bridge.generate_chunk(0,0) == baseline_chunk, "review preserves loaded bridge")
	await capture("review")
	ui._open_import_details()
	var browser: AcceptDialog = ui.import_details
	for key in ["coordinates", "geojson_multilines", "features", 0, "road_ids"]:
		var index: int = browser.page_keys.find(key)
		check(index >= 0, "exact mapping detail exists: " + str(key))
		if index >= 0: browser.descend(index)
	check(browser.current is Array and browser.current == raw.coordinates.geojson_multilines.features[0].road_ids, "exact source part ordering accessible")
	check(browser.rows.item_count == 3, "all three mapped roads accessible")
	await capture("details")
	await pointer(browser.get_ok_button())
	check(not browser.visible and ui.import_review.visible, "Back returns to review")
	for change in ["missing", "profile", "feature", "order", "count", "road", "unmapped", "endpoint", "node", "structure", "points", "type", "adapter"]:
		var bad := raw.duplicate(true)
		var meta: Dictionary = bad.coordinates.geojson_multilines
		match change:
			"missing": bad.coordinates.erase("geojson_multilines")
			"profile": meta.profile = "connect-automatically"
			"feature": meta.features[0].feature = 1
			"order": meta.features.append(meta.features[0].duplicate(true))
			"count": meta.features[0].point_counts[0] = 2
			"road": meta.features[0].road_ids.reverse()
			"unmapped":
				meta.features[0].road_ids.pop_back()
				meta.features[0].point_counts.pop_back()
			"endpoint": bad.patches[5].after.from = bad.patches[2].after.to
			"node": bad.patches[0].after.position[0] += 1
			"structure": bad.patches[2].after.kind = "bridge"
			"points": bad.patches[2].after.points = null
			"type": meta.features[0].point_counts[0] = true
			"adapter": bad.adapter = "geojson-local-v1"
		check(LAYER.new().load_value(bad,raw.layer_id) != "", "forged provenance rejected: " + change)
	await pointer(ui.import_review.get_cancel_button())
	check(ui.store.document == before, "discard preserves baseline")
	ui._start_import(path,"MIT")
	await wait_import(ui)
	await pointer(ui.import_review.get_ok_button())
	await wait_import(ui)
	check(ui.store.document.roads.size() == 3 and ui.store.document.nodes.size() == 6 and ui.store.undo_stack.size() == 1, "one atomic multipart adoption")
	check(FileAccess.get_sha256(path) == source_hash, "local source preserved after adoption")
	check(ui.store.bridge.generate_chunk(0,0) == baseline_chunk, "adoption preserves loaded bridge")
	check(ui.store.save_project(base.path_join("adopted")) == "", "save multipart document")
	check(ui.store.autosave() == "", "autosave multipart provenance")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	var reopened := STORE.new()
	check(reopened.open_project(ui.store.project_path) == "" and reopened.document == adopted, "saved geometry and exact provenance reopen")
	check(reopened.recover(ui.store.recovery_path()) == "" and reopened.document == adopted, "recovery retains parts and source mapping")
	var derived := base.path_join("adopted.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(ui.store.project_path, derived)).ok, "export multipart package")
	check(JSON.parse_string(reopened.bridge.open_package(derived)).ok, "open multipart package")
	var generated: Dictionary = JSON.parse_string(reopened.bridge.generate_chunk(0,0))
	check(generated.ok, "actual native generation of multipart roads")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty() and ui.store.document.attributions == before.attributions, "one Undo removes entire imported layer")
	check(ui.store.redo() == "" and ui.store.document == adopted, "one Redo restores exact layer")
	var saved_hash := FileAccess.get_sha256(ui.store.project_path.path_join("document.json"))
	var undo_count: int = ui.store.undo_stack.size()
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.pending_import.value.layer_id != raw.layer_id, "reimport gets a new namespace")
	ui._discard_import()
	# Selection changes, source updates and cancellation must not publish stale parts.
	ui._start_import(path,"MIT")
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null, "cancelled result not published")
	ui._start_import(path,"MIT")
	await wait_import(ui)
	ui.import_origin_x.value += 1
	ui.import_origin_x.value -= 1
	ui._adopt_import()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted, "changed/restored selection invalidates multipart review")
	ui._start_import(path,"MIT")
	await wait_import(ui)
	geo.features[0].properties.width_m = 7
	write(path,geo)
	ui._adopt_import()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted, "source mutation rejects adoption")
	# Invalid late source part and native-degenerate geometry are whole failures.
	geo.features[0].geometry.coordinates.append([])
	write(path,geo)
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted, "invalid last part rejects whole input")
	geo.features[0].geometry.coordinates = [[[40,40],[40,40]]]
	write(path,geo)
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted, "native rejects collapsed road candidate")
	check(ui.store.undo_stack.size() == undo_count, "failures preserve history")
	check(FileAccess.get_sha256(ui.store.project_path.path_join("document.json")) == saved_hash and FileAccess.get_sha256(package) == package_hash, "saved original project and package remain unchanged")
	# Geographic parts use the same owned candidate path and explicit projection.
	geo.features[0].geometry.coordinates = [[[9,55],[9.0002,55]],[[9.0002,55.0002],[9,55.0002]]]
	write(path,geo)
	var geographic_hash := FileAccess.get_sha256(path)
	ui.import_coordinate_mode.select(1)
	ui.import_origin_lon.value = 9
	ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512
	ui.import_origin_y.value = 512
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null and ui.import_summary.text.contains("EPSG:32632"), "geographic multipart review")
	ui._adopt_import()
	await wait_import(ui)
	check(ui.store.document.roads.size() == 5 and ui.store.undo_stack.size() == undo_count + 1, "geographic parts adopt together")
	check(FileAccess.get_sha256(path) == geographic_hash, "geographic source remains unchanged")
	await collections(ui)
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("multilines_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)

func collections(ui: Control) -> void:
	ui.import_coordinate_mode.select(0)
	var path := ProjectSettings.globalize_path("user://collection.geojson")
	var geo := {"type":"FeatureCollection", "features":[{"type":"Feature", "properties":{"width_m":6,"height_m":8}, "geometry":{"type":"GeometryCollection", "geometries":[
		{"type":"LineString","coordinates":[[300,300],[340,300]]},
		{"type":"GeometryCollection","geometries":[
			{"type":"MultiLineString","coordinates":[[[300,340],[340,340]],[[300,360],[340,360]]]},
			{"type":"Polygon","coordinates":[[[400,400],[420,400],[420,420],[400,420],[400,400]]]}]}]}}]}
	write(path,geo)
	var source_hash := FileAccess.get_sha256(path)
	var before: Dictionary = ui.store.document.duplicate(true)
	var undo_count: int = ui.store.undo_stack.size()
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null,"GeometryCollection native review: " + ui.status_label.text)
	if ui.pending_import == null: return
	var raw: Dictionary = ui.pending_import.value.duplicate(true)
	print("GeometryCollection reviewed hierarchy: ", var_to_str(raw.coordinates.geojson_collections.sources[0].tree), "; normalized leaves: ", raw.feature_count)
	check(raw.feature_count == 3 and collection_tree_matches(raw.coordinates.geojson_collections.sources[0].tree),"source collection tree and normalized leaf count: " + str(raw.coordinates.geojson_collections.sources[0].tree))
	check(ui.store.document == before and ui.store.undo_stack.size() == undo_count,"collection review preserves accepted document/history")
	check(ui.import_summary.text.contains("geojson_collections") and ui.import_summary.text.contains("source tree"),"collection policy and mapping shown in review")
	ui._open_import_details()
	for key in ["coordinates","geojson_collections","sources",0,"tree"]:
		var index: int = ui.import_details.page_keys.find(key)
		check(index >= 0,"collection exact detail " + str(key))
		if index >= 0: ui.import_details.descend(index)
	check(collection_tree_matches(ui.import_details.current),"complete source hierarchy is accessible: " + str(ui.import_details.current))
	await pointer(ui.import_details.get_ok_button())
	for mode: String in ["missing","profile","tree","empty","record","type","count","actual-points"]:
		var bad := raw.duplicate(true)
		var meta: Dictionary = bad.coordinates.geojson_collections
		match mode:
			"missing": bad.coordinates.erase("geojson_collections")
			"profile": meta.profile = "guessed"
			"tree": meta.sources[0].tree = [0,[0,2]]
			"empty": meta.sources[0].tree = []
			"record": meta.leaves[0].record_ids.pop_back()
			"type": meta.leaves[0].geometry = "Polygon"
			"count": meta.leaves[0].point_count = true
			"actual-points": meta.leaves[0].point_count += 1; bad.point_count += 1
		check(LAYER.new().load_value(bad,raw.layer_id) != "","forged collection mapping " + mode)
	await pointer(ui.import_review.get_ok_button())
	await wait_import(ui)
	check(ui.store.document.roads.size() == before.roads.size()+3 and ui.store.document.buildings.size() == before.buildings.size()+1,"whole collection atomic adoption: " + ui.status_label.text)
	check(ui.store.undo_stack.size() == undo_count+1,"collection is one Undo command")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before),"collection Undo preserves earlier layers")
	check(ui.store.redo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(adopted),"collection Redo restores geometry and exact tree")
	var base := ProjectSettings.globalize_path("user://collection-project")
	check(ui.store.save_project(base) == "","save collection project")
	var reopened := STORE.new()
	check(reopened.open_project(base) == "" and reopened.document == ui.store.document,"reopen exact collection metadata")
	check(JSON.parse_string(ui.store.bridge.export_project(base,base+".memap")).ok,"export collection package")
	check(JSON.parse_string(reopened.bridge.open_package(base+".memap")).ok,"open collection package")
	var generated: Dictionary = JSON.parse_string(reopened.bridge.generate_chunk(0,0))
	check(generated.ok,"generate collection roads/building")
	var found := false
	if generated.ok:
		for triangle: Dictionary in generated.data.chunk.triangles:
			found = found or triangle.object_id.contains("-collection")
	check(found,"actual generated collection geometry")
	check(FileAccess.get_sha256(path) == source_hash,"original collection unchanged")
	adopted = ui.store.document.duplicate(true)
	ui._start_import(path,"MIT")
	ui._cancel_operation()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"cancel collection without adopting")
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import != null,"fresh collection review")
	var file := FileAccess.open(path,FileAccess.READ_WRITE)
	file.seek_end(); file.store_8(32); file.close()
	ui._adopt_import()
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"changed collection source rejects adoption")
	geo.features[0].geometry.geometries.append({"type":"Point","coordinates":[1,2]})
	write(path,geo)
	ui._start_import(path,"MIT")
	await wait_import(ui)
	check(ui.pending_import == null and ui.store.document == adopted,"unsupported late collection leaf rejects all geometry")

func collection_tree_matches(value: Variant) -> bool:
	# The JSON parser produces floating values; nested Array equality compares
	# their Variant types even when each numeric leaf denotes the same index.
	return value is Array and value.size() == 2 and float(value[0]) == 0.0 and value[1] is Array and value[1].size() == 2 and float(value[1][0]) == 1.0 and float(value[1][1]) == 2.0
