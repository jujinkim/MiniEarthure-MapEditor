extends SceneTree
const SHAPE := preload("res://scripts/cylinder_wall.gd")
const STORE := preload("res://scripts/document_store.gd")
const DATA := preload("res://addons/mapkit/godot/chunk_data.gd")
var checks := 0
var ui: Control
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)
func button(node: Node, title: String) -> Button:
	if node is Button and node.text == title: return node
	for child in node.get_children():
		var result := button(child, title)
		if result != null: return result
	return null
func spin(node: Node, title: String) -> SpinBox:
	if node is HBoxContainer and node.get_child_count() == 2 and node.get_child(0) is Label and node.get_child(0).text == title and node.get_child(1) is SpinBox: return node.get_child(1)
	for child in node.get_children():
		var result := spin(child,title)
		if result != null: return result
	return null
func click(world: Vector2) -> void:
	var p: Vector2 = ui.canvas.global_position + ui.canvas.screen([world.x, world.y])
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = p
		event.global_position = p
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		root.push_input(event)
		await process_frame
func run() -> void:
	root.size = Vector2i(1440,900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	check(ui.store.apply_command("small seam fixture", [
		{"field":"bounds","before":ui.store.document.bounds,"after":{"min":[0,0],"max":[25600,25600]}},
		{"field":"cell_size_cm","before":ui.store.document.cell_size_cm,"after":12800}]) == "", "small fixture")
	check(ui.canvas.author.recipe(4,"urban") == "", "supported recipe")
	var author: RefCounted = ui.canvas.author
	author.options.wall_radius_cm = 1600
	author.options.wall_height_cm = 350
	author.options.base_cm = -50
	check(button(ui,"Cylinder wall") != null,"visible authoring tool")
	button(ui,"Cylinder wall").pressed.emit()
	check(ui.canvas.tool == "Cylinder wall", "tool wired")
	var history: int = ui.store.undo_stack.size()
	await click(Vector2(12800,12800))
	check(ui.store.document.buildings.size() == 1, "one click makes a wall: " + ui.status_label.text)
	var wall: Dictionary = ui.store.document.buildings[0].duplicate(true)
	check(wall.footprint.size() == 48 and wall.roof == "flat" and wall.height_cm == 350,"round solid, flat top")
	check(ui.store.undo_stack.size() == history+1 and ui.canvas.draft.is_empty(),"one gesture / one undo")
	check(ui.store.undo() == "" and ui.store.document.buildings.is_empty(),"undo cylinder")
	check(ui.store.redo() == "" and ui.store.document.buildings[0] == wall,"redo exact source")
	ui.canvas.set_selection(["buildings/"+str(wall.id)])
	# Show the real selected panel; the geometric detector survives save/transform.
	button(ui,"Authoring settings…").pressed.emit()
	check(button(ui.author_panel,"Apply cylinder wall") != null,"selected radius/height editor")
	spin(ui.author_panel,"Wall radius (m)").value = 20
	spin(ui.author_panel,"Wall height (m)").value = 4
	if not OS.get_environment("MAPEDITOR_CYLINDER_CAPTURE").is_empty() and DisplayServer.get_name() != "headless":
		ui.author_panel.tabs.current_tab = 4
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(OS.get_environment("MAPEDITOR_CYLINDER_CAPTURE"))==OK,"selected cylinder UI capture")
	button(ui.author_panel,"Apply cylinder wall").pressed.emit()
	check(ui.author_panel.feedback.text.begins_with("Applied"),"selected cylinder apply")
	check(SHAPE.dimensions(ui.store.document.buildings[0]).radius_cm == 2000 and ui.store.document.buildings[0].height_cm == 400,"radius and height edit changes source")
	ui.author_panel.hide()
	var before: String = JSON.stringify([ui.store.document,ui.store.undo_stack])
	ui.canvas.set_layer_state("buildings",{"locked":true})
	var locked_draft: Array[Vector2] = [Vector2(5000,5000)]
	check(author.draw("Cylinder wall",locked_draft) != "","locked wall layer rejects")
	check(JSON.stringify([ui.store.document,ui.store.undo_stack]) == before,"failed authoring retains prior state")
	ui.canvas.set_layer_state("buildings",{})
	var invalid_draft: Array[Vector2] = [Vector2(100,100)]
	check(author.draw("Cylinder wall",invalid_draft) != "","out-of-bounds circle rejected")
	check(JSON.stringify([ui.store.document,ui.store.undo_stack]) == before,"invalid radius footprint is atomic")
	var transformed: Dictionary = wall.duplicate(true)
	transformed.footprint = SHAPE.footprint(Vector2(14000,15000),2200,0.3)
	transformed.footprint.reverse()
	check(SHAPE.dimensions(transformed).radius_cm == 2200,"moved/rotated/mirrored round wall detected")
	transformed.footprint[3][0] += 50
	check(SHAPE.dimensions(transformed).is_empty(),"irregular polygon never silently converted")
	var project := ProjectSettings.globalize_path("user://cylinder-project")
	check(ui.store.save_project(project) == "","save circle project")
	var reopened := STORE.new()
	check(reopened.open_project(project) == "","reopen circle")
	check(not SHAPE.dimensions(reopened.document.buildings[0]).is_empty(),"parametric edit survives native roundtrip")
	var output := ProjectSettings.globalize_path("user://cylinder.memap")
	check(JSON.parse_string(reopened.bridge.export_project(project,output)).ok,"export collision wall")
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(native.open_package(output)).ok,"open packaged circle")
	var parts := 0
	for y in range(2):
		for x in range(2):
			var generated: Dictionary = native.generate_chunk_packed(x,y)
			check(generated.ok,"wall crossing cell seam generates")
			var chunk := DATA.view(generated.data.chunk)
			check(DATA.building_prism_count(chunk)>0,"each cell owns solid collision parts")
			parts += DATA.building_prism_count(chunk)
			var visible := false
			for i in range(DATA.count(chunk)):
				if DATA.object_id(chunk,i) == wall.id:
					visible = true
					check(not DATA.spawnable(chunk,i),"wall is never a spawn surface")
			check(visible,"wall renders from the same integer outline")
	print("cylinder_wall_validator: PASS (",checks," checks, ",parts," solid parts)")
	ui.queue_free()
	await process_frame
	quit(0)
