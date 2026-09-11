extends SceneTree
const PNG := preload("res://scripts/terrain_png.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const STORE := preload("res://scripts/document_store.gd")
var ui: Control
var checks := 0

func _initialize() -> void:
	run.call_deferred()

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		print("E03 state: ", ui.status_label.text if ui != null else "codec", " check=", checks)
		quit(1)
		assert(value, message)

func ok(failure: String, message: String) -> void:
	check(failure == "", message + ": " + failure)

func state() -> String:
	return JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.redo_stack, ui.store.history_bytes, ui.store.dirty])

func button(node: Node, title: String) -> Button:
	if node is Button and node.text == title: return node
	for child in node.get_children():
		var found := button(child, title)
		if found != null: return found
	return null

func pointer(point: Vector2, pressed: bool, which: MouseButton = MOUSE_BUTTON_LEFT) -> void:
	var event := InputEventMouseButton.new()
	event.position = point
	event.global_position = point
	event.button_index = which
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed and which == MOUSE_BUTTON_LEFT else 0
	event.pressed = pressed
	root.push_input(event)
	await process_frame

func click(point: Vector2) -> void:
	await pointer(point, true)
	await pointer(point, false)

func click_button(title: String) -> void:
	var target := button(ui, title)
	check(target != null and target.is_visible_in_tree(), "button visible: " + title)
	await click(target.get_global_rect().get_center())

func point(value: Vector2) -> Vector2:
	return ui.canvas.global_position + ui.canvas.screen([value.x, value.y])

func stroke(start: Vector2, end: Vector2) -> void:
	await pointer(point(start), true)
	var event := InputEventMouseMotion.new()
	event.position = point(end)
	event.global_position = event.position
	event.relative = point(end) - point(start)
	event.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(event)
	await process_frame
	await pointer(point(end), false)
	var deadline := Time.get_ticks_msec() + 20000
	while ui.import_job != null and Time.get_ticks_msec() < deadline: await process_frame
	check(ui.import_job == null and not ui.busy, "terrain job finishes: " + ui.status_label.text)

func shape(tool: String, vertices: Array) -> void:
	ui._set_tool(tool)
	for vertex: Vector2 in vertices: await click(point(vertex))
	if tool != "Place":
		await pointer(point(vertices.back()), true, MOUSE_BUTTON_RIGHT)
		await pointer(point(vertices.back()), false, MOUSE_BUTTON_RIGHT)

func run() -> void:
	root.size = Vector2i(1440, 900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	var heights := PackedInt64Array([-20,0,20,40,60,80,100,120,140])
	var encoded := PNG.encode(heights, 3)
	check(not encoded.has("error"), "encode lossless signed restored heights")
	var decoded := PNG.decode(encoded.bytes, 3, encoded.offset_cm, encoded.step_cm)
	check(not decoded.has("error") and decoded.heights == heights, "PNG16 exact adapter roundtrip")
	var corrupt: PackedByteArray = encoded.bytes.duplicate()
	corrupt[20] ^= 1
	check(PNG.decode(corrupt, 3, 0, 1).has("error"), "PNG checksum failure")
	check(PNG.decode(encoded.bytes, 4, 0, 1).has("error"), "full grid dimensions required")
	check(PNG.encode(PackedInt64Array([0,70000,0,0]), 2).has("error"), "lossy height range rejected")
	# Exercise all standard PNG scanline filters, including negative Paeth predictors.
	var raw := PackedByteArray()
	var previous := PackedByteArray([0,0,0,0,0,0])
	var samples := PackedInt64Array()
	for filter in range(5):
		var row := PackedByteArray([filter,250,40,3,210,120,11,254,200,1])
		# Five-pixel square gives one row per filter.
		if previous.size() != row.size(): previous.resize(row.size())
		raw.append(filter)
		for x in range(row.size()):
			var a := int(row[x-2]) if x >= 2 else 0
			var b := int(previous[x])
			var c := int(previous[x-2]) if x >= 2 else 0
			var p := a+b-c
			var predictor := 0
			match filter:
				1: predictor = a
				2: predictor = b
				3: predictor = (a+b)/2
				4: predictor = a if absi(p-a) <= absi(p-b) and absi(p-a) <= absi(p-c) else (b if absi(p-b) <= absi(p-c) else c)
			raw.append((int(row[x])-predictor)&255)
		for x in range(5): samples.append((int(row[x*2])<<8)|row[x*2+1])
		previous = row
	var filtered := PackedByteArray(PNG.SIGNATURE) + PNG.chunk("IHDR", PNG.be32(5)+PNG.be32(5)+PackedByteArray([16,0,0,0,0])) + PNG.chunk("IDAT", raw.compress(FileAccess.COMPRESSION_DEFLATE)) + PNG.chunk("IEND", PackedByteArray())
	decoded = PNG.decode(filtered, 5, 0, 1)
	check(not decoded.has("error") and decoded.heights == samples, "all PNG filters preserve 16-bit values")
	ok(ui.store.apply_command("small synthetic map", [{"field":"bounds","before":ui.store.document.bounds,"after":{"min":[0,0],"max":[12800,12800]}},{"field":"cell_size_cm","before":51200,"after":6400}]), "fixture bounds")
	var project := ProjectSettings.globalize_path("user://e03-project")
	ok(ui.store.save_project(project), "save before file authoring")
	await click_button("Authoring settings…")
	check(ui.author_panel.visible and ui.author_panel.tabs.get_tab_count() == 5, "real authoring tabs")
	ui.author_panel.hide()
	ok(ui.canvas.author.recipe(4, "rural"), "explicit recipe4/theme")
	var author: RefCounted = ui.canvas.author
	author.options.grid_cm = 800
	author.options.radius_cm = 1600
	author.options.amount_cm = 200
	ui.canvas.snap_cm = 100
	ui._set_tool("Terrain")
	var history: int = ui.store.undo_stack.size()
	await stroke(Vector2(6100,6100), Vector2(6700,6700))
	check(ui.store.document.heightmaps.size() == 4, "one stroke creates all four seam owners")
	check(ui.store.undo_stack.size() == history+1 and not ui.store.has_gesture(), "stroke is one atomic undo")
	var terrain_state: Dictionary = ui.store.document.duplicate(true)
	var first_bytes := {}
	for tile: Dictionary in ui.store.document.heightmaps:
		first_bytes[tile.path] = FILES.read(project.path_join(tile.path)).bytes
	check(ui.store.undo_stack.back().binary_mementos.size() > 0, "binary before/after mementos retained")
	check(ui.store.history_bytes >= first_bytes.values()[0].size(), "binary bytes charged to shared undo budget")
	ok(ui.store.save_project(project), "save raster source")
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	var result: Dictionary = JSON.parse_string(native.open_project(project))
	check(result.ok, "native PNG/seam acceptance: " + JSON.stringify(result))
	for y in range(2):
		for x in range(2): check(JSON.parse_string(native.generate_chunk(x,y)).ok, "native generated terrain cell")
	ok(ui.store.undo(), "undo raster")
	check(ui.store.document.heightmaps.is_empty(), "undo returns implicit flat terrain")
	ok(ui.store.redo(), "redo raster")
	check(ui.store.document.heightmaps == terrain_state.heightmaps, "redo exact binary identities")
	for mode in ["lower", "flatten", "smooth"]:
		var mode_before: String = ui.store._signature(ui.store.document)
		author.options.mode = mode
		author.options.target_cm = 0
		await stroke(Vector2(6400,6400), Vector2(6400,6400))
		check(not ui.store.has_gesture() and ui.store._signature(ui.store.document) != mode_before, "completed nonempty " + mode)
	ok(FILES.validate(ui.store, ui.store.document), "all brush modes preserve seams")
	for path: String in first_bytes: check(FILES.read(project.path_join(path)).bytes == first_bytes[path], "original raster remains immutable")
	var terrain_capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
	if terrain_capture != "" and DisplayServer.get_name() != "headless":
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(terrain_capture.get_basename() + "-terrain.png") == OK, "native terrain screenshot")
	var before := state()
	await pointer(point(Vector2(6400,6400)), true)
	ui.canvas.cancel_interaction()
	await pointer(point(Vector2(6400,6400)), false)
	check(state() == before, "cancelled stroke ignores late release")
	author.options.mode = "raise"
	await pointer(point(Vector2(6400,6400)), true)
	ui.canvas._notification(Control.NOTIFICATION_WM_WINDOW_FOCUS_OUT)
	await pointer(point(Vector2(6400,6400)), false)
	check(state() == before, "focus loss cancels without publication")
	# Import a valid but discontinuous source: native file validation must reject it.
	var flat := PackedInt64Array()
	flat.resize(81)
	flat.fill(500)
	var imported := PNG.encode(flat, 9)
	var import_path := ProjectSettings.globalize_path("user://unrelated-source.png")
	ok(FILES.write_new(import_path, imported.bytes), "synthetic independent import source")
	var failure: String = author.terrain.import_png(import_path, Vector2i.ZERO, 800, 500, 1, 500, {"source":"Synthetic E03", "license":"MIT", "notice":"Original"})
	check(failure != "" and state() == before, "bad imported seam preserves history/document: " + failure)
	check(FILES.read(import_path).bytes == imported.bytes, "rejected import does not rewrite source")
	# A flat outer cell with exact seams imports and preserves attribution/accuracy.
	flat.fill(0)
	imported = PNG.encode(flat, 9)
	var flat_path := ProjectSettings.globalize_path("user://flat-source.png")
	ok(FILES.write_new(flat_path, imported.bytes), "flat import fixture")
	ok(ui.store.undo(), "undo smooth")
	# Use separate blank map for structures; old terrain project and recovery remain.
	ok(ui.store.save_project(project), "persist terrain before next document")
	ok(ui.store.autosave(), "raster recovery snapshot")
	var recovered := STORE.new()
	ok(recovered.recover(ui.store.recovery_path()), "recover immutable raster references")
	ok(FILES.validate(recovered, recovered.document), "recovered raster native validation")
	ui._new()
	ok(ui.store.save_project(ProjectSettings.globalize_path("user://e03-structures")), "new authoring project")
	ok(author.recipe(4,"urban"), "structure recipe")
	ok(author.terrain.import_png(flat_path, Vector2i.ZERO, 6400, 0, 1, 500, {"source":"Synthetic E03", "license":"MIT", "notice":"Original"}), "valid PNG import")
	check(ui.store.document.heightmaps[0].source_accuracy_cm == 500 and ui.store.document.attributions.size() == 1, "accuracy and attribution retained")
	ok(ui.store.undo(), "undo height import and attribution together")
	check(ui.store.document.heightmaps.is_empty() and ui.store.document.attributions.is_empty(), "atomic import undo")
	# Use real viewport shape gestures on default map size.
	author.options.kind = "bridge"
	author.options.start_cm = 800
	author.options.end_cm = 800
	author.options.start_level = 1
	author.options.end_level = 1
	await shape("Road", [Vector2(10000,25000),Vector2(30000,25000)])
	check(ui.store.document.roads.size() == 1 and ui.store.document.roads[0].kind == "bridge", "canvas bridge authoring")
	await shape("Road", [Vector2(30000,25000),Vector2(50000,25000)])
	check(ui.store.document.nodes.size() == 3, "explicit XYZ/level shared bridge endpoint")
	var first: Dictionary = ui.store.document.roads[0].duplicate(true)
	var second: Dictionary = ui.store.document.roads[1].duplicate(true)
	if first.points[0][0] > second.points[0][0]:
		var swap := first
		first = second
		second = swap
	var points: Array = first.points.duplicate(true)
	points[-1][1] = 900
	ui.canvas.set_layer_state("roads", {"locked":true})
	before = state()
	failure = author.edit_road(first,points,[900],["concrete"],"bridge",null,100,[1,1])
	check(failure != "" and state() == before, "locked graph rejects all endpoint/property changes")
	ui.canvas.set_layer_state("roads", {})
	ok(author.edit_road(first,points,[900],["concrete"],"bridge",null,100,[1,1]), "shared bridge height and width edit")
	var joined := false
	for road: Dictionary in ui.store.document.roads:
		if road.id == second.id: joined = road.points[0][1] == 900
	check(joined, "incident end receives same authored height")
	ok(ui.store.undo(), "undo shared road edit")
	author.options.kind = "tunnel"
	author.options.start_cm = -800
	author.options.end_cm = -800
	author.options.start_level = -1
	author.options.end_level = -1
	await shape("Road", [Vector2(15000,40000),Vector2(45000,40000)])
	check(ui.store.document.roads.size() == 3, "tunnel floor/clearance authored and generated")
	author.options.roof = "gable"
	await shape("Building", [Vector2(10000,55000),Vector2(20000,55000),Vector2(20000,65000),Vector2(10000,65000)])
	check(ui.store.document.buildings.size() == 1, "gable footprint tool")
	var building: Dictionary = ui.store.document.buildings[0]
	ui.canvas.set_selection(["buildings/" + str(building.id)])
	await shape("Entrance", [Vector2(12000,53000),Vector2(14000,53000),Vector2(14000,55000),Vector2(12000,55000)])
	check(ui.store.document.buildings[0].get("entrances", []).size() == 1, "entrance corridor tool")
	await shape("Forest", [Vector2(60000,55000),Vector2(80000,55000),Vector2(80000,80000),Vector2(60000,80000)])
	check(ui.store.document.zones.size() == 1, "forest authoring")
	ui.canvas.set_selection(["zones/" + str(ui.store.document.zones[0].id)])
	await shape("Exclusion", [Vector2(63000,60000),Vector2(67000,60000),Vector2(67000,65000),Vector2(63000,65000)])
	check(ui.store.document.zones[0].exclusions.size() == 1, "zone exclusion tool")
	author.options.asset_id = "builtin:fence"
	author.options.start_cm = 0
	author.options.end_cm = 0
	await shape("Repeat", [Vector2(10000,85000),Vector2(40000,85000)])
	check(ui.store.document.repetitions.size() == 1, "fence repetition authoring")
	# Original MIT synthetic image; importer never changes it.
	var image := Image.create(4,4,false,Image.FORMAT_RGBA8)
	image.fill(Color("f4d03f"))
	var image_path := ProjectSettings.globalize_path("user://original-asset.png")
	check(image.save_png(image_path) == OK, "synthetic asset PNG")
	var asset := {"id":"gold-box", "path":"", "attribution":{"source":"E03 synthetic", "license":"MIT", "notice":"Original test image"}, "collision":[{"center":[0,100,0],"size_cm":[200,200,200]}]}
	ok(author.asset(asset,image_path), "asset file/proxy import")
	var bytes: PackedByteArray = FILES.read(image_path).bytes
	author.options.asset_id = "gold-box"
	author.options.base_cm = 0
	await shape("Place", [Vector2(55000,90000)])
	check(ui.store.document.placements.size() == 1, "one-click custom asset placement")
	asset = ui.store.document.assets[0].duplicate(true)
	asset.collision = []
	asset.convex_collision = [{"vertices":[[-100,0,-100],[100,0,-100],[-100,0,100],[-100,200,-100]],"faces":[[0,1,2],[0,3,1],[0,2,3],[1,3,2]]}]
	asset.material = {"albedo_rgba":[255,240,100,255],"metallic_per_mille":100,"roughness_per_mille":700,"double_sided":true}
	ok(author.asset(asset), "edit exact convex and material")
	before = state()
	asset.convex_collision[0].faces.pop_back()
	check(author.asset(asset) != "" and state() == before, "open convex rejects atomically")
	check(FILES.read(image_path).bytes == bytes, "asset original bytes preserved")
	ok(author.recipe(6, "urban"), "explicit urban recipe")
	author.options.surface = "concrete"
	await shape("Surface area", [Vector2(5000,5000),Vector2(20000,5000),Vector2(20000,15000),Vector2(5000,15000)])
	check(ui.store.document.surface_areas.size() == 1, "canvas surface paint authoring")
	var paint: Dictionary = ui.store.document.surface_areas[0]
	ok(ui.store.undo(), "undo surface area")
	check(ui.store.document.get("surface_areas", []).is_empty(), "surface undo removes paint")
	ok(ui.store.redo(), "redo surface area")
	check(ui.store.document.surface_areas[0] == paint, "surface redo preserves exact polygon/material")
	var marked: Dictionary = ui.store.document.roads[0].duplicate(true)
	marked.markings = {"lanes":2,"center_line":true,"edge_lines":true,"crosswalk_start":true,"crosswalk_end":true}
	ok(author.apply("Mark road", [{"field":"roads","id":marked.id,"before":ui.store.document.roads[0],"after":marked}]), "persist editable road markings")
	var destination: String = ui.store.project_path.path_join("authored.memap")
	ok(ui.store.save_project(ui.store.project_path), "save full authored project")
	ok(ui.store.autosave(), "authoring recovery")
	ok(recovered.recover(ui.store.recovery_path()), "recover structures and custom assets")
	ok(FILES.validate(recovered,recovered.document), "native recovered document/assets")
	result = JSON.parse_string(native.export_project(ui.store.project_path,destination))
	check(result.ok, "export authored package: " + JSON.stringify(result))
	check(JSON.parse_string(native.open_package(destination)).ok, "reopen authored package")
	ui.preview_x.value = 1
	ui.preview_y.value = 1
	ui._preview()
	for _i in range(500):
		await process_frame
		if not ui.busy: break
	check(not ui.busy and ui.status_label.text.begins_with("Preview ready"), "same MapKit renderer displays authored content")
	await click_button("Authoring settings…")
	ui.author_panel.tabs.current_tab = 3
	await process_frame
	check(ui.author_panel.asset_fields.boxes is TextEdit, "editable exact proxy UI")
	var controls: Dictionary = ui.author_panel.asset_fields
	controls.id.text = "ui-asset"
	controls.path.text = image_path
	controls.source.text = "Original scripted authoring input"
	controls.license.text = "MIT"
	controls.notice.text = "Synthetic"
	var apply := button(ui.author_panel, "Apply asset and proxies")
	var ancestor: Node = apply.get_parent()
	while ancestor != null and ancestor is not ScrollContainer: ancestor = ancestor.get_parent()
	(ancestor as ScrollContainer).ensure_control_visible(apply)
	await process_frame
	await process_frame
	await click(apply.get_global_rect().get_center() + Vector2(ui.author_panel.position))
	var asset_deadline := Time.get_ticks_msec() + 20000
	while ui.busy and Time.get_ticks_msec() < asset_deadline: await process_frame
	check(not ui.busy, "asynchronous asset job finishes: " + ui.author_panel.feedback.text)
	check(ui.store.document.assets.size() == 2, "real authoring panel Apply imports an asset: " + ui.author_panel.feedback.text)
	before = state()
	controls.boxes.text = "[invalid"
	await click(apply.get_global_rect().get_center() + Vector2(ui.author_panel.position))
	check(state() == before and ui.author_panel.feedback.text.contains("valid JSON"), "proxy UI invalid input preserves history")
	controls.boxes.text = "[]"
	var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
	if capture != "" and DisplayServer.get_name() != "headless":
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(capture) == OK, "native authoring screenshot")
	ui.author_panel.hide()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("authoring_validator: PASS; checks=", checks)
	quit(0)
