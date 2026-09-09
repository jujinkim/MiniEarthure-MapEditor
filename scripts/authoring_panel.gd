extends AcceptDialog
const HEIGHTMAP_LAYER := preload("./heightmap_import_layer.gd")
var heightmap_candidate: RefCounted
var heightmap_review: ConfirmationDialog
var heightmap_summary: RichTextLabel
const FILES := preload("./authoring_files.gd")
var editor: Control
var author: RefCounted
var tabs: TabContainer
var feedback: Label
var source_picker: FileDialog
var fields := {}
var asset_fields := {}
var asset_before := {}
var session_signature := ""

func _ready() -> void:
	title = "Map authoring"
	size = Vector2i(800, 650)
	min_size = Vector2i(680, 500)
	unresizable = false
	var column := VBoxContainer.new()
	add_child(column)
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.offset_bottom = -55
	tabs = TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(tabs)
	feedback = Label.new()
	feedback.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	feedback.custom_minimum_size.y = 40
	column.add_child(feedback)
	source_picker = FileDialog.new()
	source_picker.access = FileDialog.ACCESS_FILESYSTEM
	source_picker.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	add_child(source_picker)
	heightmap_review = ConfirmationDialog.new()
	heightmap_review.title = "Review new heightmap source layer"
	heightmap_review.ok_button_text = "Adopt and activate tile"
	heightmap_review.cancel_button_text = "Discard"
	heightmap_review.min_size = Vector2i(640, 420)
	add_child(heightmap_review)
	heightmap_summary = RichTextLabel.new()
	heightmap_summary.custom_minimum_size = Vector2(600, 340)
	heightmap_review.add_child(heightmap_summary)
	heightmap_review.confirmed.connect(_adopt_heightmap)
	heightmap_review.canceled.connect(_discard_heightmap)
	visibility_changed.connect(func():
		if not visible:
			heightmap_review.hide()
			_discard_heightmap()
	)

func _discard_heightmap() -> void:
	if heightmap_candidate != null: heightmap_candidate.discard()
	heightmap_candidate = null

func _exit_tree() -> void:
	_discard_heightmap()

func _stage_heightmap(path: String, cell: Vector2i, spacing: int, offset: int, step: int, accuracy: int, attribution: Dictionary) -> void:
	_discard_heightmap()
	heightmap_candidate = HEIGHTMAP_LAYER.new()
	var failure: String = heightmap_candidate.stage(author.terrain, path, cell, spacing, offset, step, accuracy, attribution)
	if failure != "":
		_discard_heightmap()
		report(failure)
		return
	heightmap_summary.text = heightmap_candidate.summary()
	heightmap_review.popup_centered(Vector2i(680, 460))
	feedback.text = "Validated candidate; document unchanged. Review then adopt or discard."

func _adopt_heightmap() -> void:
	if heightmap_candidate == null: return
	report(heightmap_candidate.adopt(author.terrain))
	_discard_heightmap()

func open() -> void:
	editor.canvas.cancel_interaction()
	author = editor.canvas.author
	session_signature = editor.store._signature(editor.store.document)
	for child in tabs.get_children():
		tabs.remove_child(child)
		child.queue_free()
	fields.clear()
	feedback.text = "Choose an explicit recipe before using its features. All edits pass MapKit validation."
	_setup()
	_drawing()
	_terrain()
	_assets()
	_selected()
	popup_centered(Vector2i(800, 650))

func page(name: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = name
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 8)
	scroll.add_child(box)
	return box

func hint(box: Node, text: String) -> void:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(label)

func row(box: Node, title: String) -> HBoxContainer:
	var result := HBoxContainer.new()
	box.add_child(result)
	var label := Label.new()
	label.text = title
	label.custom_minimum_size.x = 225
	result.add_child(label)
	return result

func number(box: Node, title: String, value: float, minimum: float, maximum: float, step: float = 1) -> SpinBox:
	var control := SpinBox.new()
	control.min_value = minimum
	control.max_value = maximum
	control.step = step
	control.value = value
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row(box, title).add_child(control)
	return control

func text(box: Node, title: String, value: String) -> LineEdit:
	var control := LineEdit.new()
	control.text = value
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row(box, title).add_child(control)
	return control

func choice(box: Node, title: String, values: Array, value: String) -> OptionButton:
	var control := OptionButton.new()
	for item in values: control.add_item(str(item))
	control.selected = maxi(0, values.find(value))
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row(box, title).add_child(control)
	return control

func button(box: Node, title: String, callback: Callable) -> Button:
	var control := Button.new()
	control.text = title
	control.pressed.connect(callback)
	box.add_child(control)
	return control

func report(failure: String) -> void:
	feedback.text = failure if failure != "" else "Applied. Undo/Redo retain this as one operation."
	feedback.modulate = Color("ffab91") if failure != "" else Color("c5e1a5")
	editor._status(feedback.text)
	if failure == "": session_signature = editor.store._signature(editor.store.document)

func fresh() -> bool:
	if session_signature != editor.store._signature(editor.store.document):
		report("Document changed while this panel was open. Reopen authoring before applying.")
		return false
	return true

func _setup() -> void:
	var box := page("Map")
	hint(box, "Recipe 2: terrain-following roads, bridge/tunnel cuts. Recipe 3: buildings, entrances and repeated props. Recipe 4: custom convex proxies and materials. Changing recipe changes world identity; originals are never migrated on load.")
	var recipe := choice(box, "Recipe", ["1", "2", "3", "4"], str(int(editor.store.document.recipe_version)))
	var theme := choice(box, "Theme", ["default", "urban", "rural"], editor.store.document.theme)
	button(box, "Apply recipe and theme", func():
		if fresh(): report(author.recipe(int(recipe.get_item_text(recipe.selected)), theme.get_item_text(theme.selected)))
	)
	var bounds: Dictionary = editor.store.document.bounds.duplicate(true)
	var coordinates: Array = []
	for key in ["min", "max"]:
		for axis in range(2): coordinates.append(number(box, key.capitalize() + " " + ["X", "Y"][axis] + " (m)", float(bounds[key][axis]) / 100, -100000, 100000, 0.01))
	var base := number(box, "Implicit terrain base (m)", float(editor.store.document.terrain_base_cm) / 100, -10000, 10000, 0.01)
	button(box, "Apply bounds and terrain base", func():
		if not fresh(): return
		var next_bounds := {"min":[roundi(coordinates[0].value*100),roundi(coordinates[1].value*100)],"max":[roundi(coordinates[2].value*100),roundi(coordinates[3].value*100)]}
		var patches: Array = [{"field":"bounds","before":editor.store.document.bounds,"after":next_bounds},{"field":"terrain_base_cm","before":editor.store.document.terrain_base_cm,"after":roundi(base.value*100)}]
		report(author.apply("Edit map bounds and terrain base", patches, true))
	)
	hint(box, "Save to a project directory before importing assets or painting terrain. Use 3D Preview to inspect the common renderer after editing. Terrain seams and road junction failures appear here immediately.")

func opt_number(box: Node, title: String, key: String, minimum: float, maximum: float, metres: bool = true) -> void:
	var scale := 100.0 if metres else 1.0
	var control := number(box, title, float(author.options[key]) / scale, minimum, maximum, 0.01 if metres else 1)
	control.value_changed.connect(func(value): author.options[key] = roundi(value * scale))
	fields[key] = control

func opt_choice(box: Node, title: String, key: String, values: Array) -> void:
	var control := choice(box, title, values, str(author.options[key]))
	control.item_selected.connect(func(index): author.options[key] = values[index])
	fields[key] = control

func _drawing() -> void:
	var box := page("Drawing")
	hint(box, "Settings affect the next shape. Click points on the canvas; right-click finishes. Place uses one click. Select a building/zone before drawing an Entrance/Exclusion. Escape cancels. Matching XYZ and level reuse an explicit road node; XY crossings never connect.")
	opt_choice(box, "Road structure", "kind", ["ground", "elevated", "bridge", "underpass", "tunnel"])
	opt_number(box, "Road width (m)", "width_cm", 0.2, 100)
	opt_choice(box, "Road surface", "surface", ["asphalt", "concrete", "dirt", "gravel", "grass"])
	opt_number(box, "Start height (m)", "start_cm", -10000, 10000)
	opt_number(box, "End height (m)", "end_cm", -10000, 10000)
	opt_number(box, "Start level", "start_level", -100, 100, false)
	opt_number(box, "End level", "end_level", -100, 100, false)
	opt_number(box, "Tunnel / underpass clearance (m)", "clearance_cm", 0.01, 100)
	opt_number(box, "Sidewalk width (m; 0 = none)", "sidewalk_cm", 0, 20)
	hint(box, "Structural heights interpolate along the drawn polyline. Ground uses sampled terrain. Edit per-point heights, segment widths and surfaces in Selected after drawing.")
	opt_number(box, "Building / placement base (m)", "base_cm", -10000, 10000)
	opt_number(box, "Building wall height (m)", "height_cm", 0.01, 1000)
	opt_choice(box, "Building use", "usage", ["residential", "commercial", "industrial", "public"])
	opt_choice(box, "Building material", "material", ["concrete", "brick", "wood"])
	opt_choice(box, "Roof", "roof", ["flat", "gable"])
	opt_number(box, "Planting / repetition spacing (m)", "spacing_cm", 2, 1000)
	opt_number(box, "Planting density (per mille)", "density_per_mille", 0, 1000, false)
	var assets: Array = ["builtin:tree", "builtin:fence", "builtin:streetlight"]
	for asset: Dictionary in editor.store.document.assets: assets.append(str(asset.id))
	opt_choice(box, "Placement / repetition asset", "asset_id", assets)
	opt_number(box, "Quarter turns", "quarter_turns", 0, 3, false)
	hint(box, "Repetition supports builtin fence or streetlight; fence paths are cardinal. Gables require an axis-aligned rectangular footprint. Native overlap and clearance rules apply.")

func choose_file(target: LineEdit, filters: PackedStringArray) -> void:
	for connection in source_picker.file_selected.get_connections(): source_picker.file_selected.disconnect(connection.callable)
	source_picker.filters = filters
	source_picker.file_selected.connect(func(path): target.text = path)
	source_picker.popup_centered(Vector2i(760, 500))

func _terrain() -> void:
	var box := page("Terrain")
	hint(box, "Drag the Terrain tool to paint one continuous stroke. Neighboring edge samples change together. Sources stay unchanged; new lossless PNG16 tiles are validated before publication. Native seam failures preserve the document and history.")
	opt_choice(box, "Brush", "mode", ["raise", "lower", "flatten", "smooth"])
	opt_number(box, "Radius (m)", "radius_cm", 2, 2048)
	opt_number(box, "Raise / lower amount (m)", "amount_cm", 0.01, 100)
	opt_number(box, "Flatten target (m)", "target_cm", -10000, 10000)
	opt_number(box, "Grid spacing (m)", "grid_cm", 2, 1024)
	hint(box, "Spacing must divide the cell size and match existing grids. The source accuracy is independent of grid spacing. Import accepts exact full-cell non-interlaced grayscale16 PNGs; mismatched seams are rejected, never silently flattened.")
	var path := text(box, "Heightmap PNG", "")
	button(box, "Choose heightmap PNG…", func(): choose_file(path, PackedStringArray(["*.png ; Grayscale16 heightmap"])))
	var x := number(box, "Cell X", 0, 0, 127)
	var y := number(box, "Cell Y", 0, 0, 127)
	var offset := number(box, "Offset (cm)", 0, -1000000, 1000000)
	var step := number(box, "Step (cm)", 1, 1, 100)
	var accuracy := number(box, "Source accuracy (cm; 0 unknown)", 0, 0, 1000000)
	var source := text(box, "Source attribution", "")
	var license := text(box, "License", "")
	var notice := text(box, "Notice", "")
	button(box, "Stage heightmap for review…", func():
		if fresh(): _stage_heightmap(path.text, Vector2i(x.value, y.value), int(author.options.grid_cm), int(offset.value), int(step.value), int(accuracy.value), {"source":source.text,"license":license.text,"notice":notice.text})
	)
	button(box, "Import heightmap atomically", func():
		if fresh(): report(author.terrain.import_png(path.text, Vector2i(x.value, y.value), int(author.options.grid_cm), int(offset.value), int(step.value), int(accuracy.value), {"source": source.text, "license": license.text, "notice": notice.text}))
	)

func json_edit(box: Node, title: String, value: Variant) -> TextEdit:
	hint(box, title)
	var control := TextEdit.new()
	control.text = JSON.stringify(value, "  ")
	control.custom_minimum_size.y = 140
	box.add_child(control)
	return control

func input_json(value: String) -> Variant:
	if value.to_utf8_buffer().size() > 1024 * 1024: return null
	var parser := JSON.new()
	return parser.data if parser.parse(value) == OK else null

func _assets() -> void:
	var box := page("Assets")
	hint(box, "Import a static GLB/PNG/WebP with its original license. Select an existing ID to edit its proxies/materials; file bytes remain immutable. Box controls create a proxy; exact multi-box or convex vertices/faces are editable below in centimetres.")
	var values: Array = ["New asset"]
	for asset: Dictionary in editor.store.document.assets: values.append(str(asset.id))
	var selector := choice(box, "Asset library", values, "New asset")
	var form := VBoxContainer.new()
	box.add_child(form)
	selector.item_selected.connect(func(index):
		asset_before = {} if index == 0 else editor.store._get_value(editor.store.document, "assets", values[index]).duplicate(true)
		_asset_form(form)
	)
	asset_before = {}
	_asset_form(form)

func _asset_form(box: Node) -> void:
	for child in box.get_children():
		box.remove_child(child)
		child.queue_free()
	asset_fields.clear()
	var current := asset_before.duplicate(true)
	var id := text(box, "Asset ID", str(current.get("id", "asset-" + Crypto.new().generate_random_bytes(4).hex_encode())))
	id.editable = current.is_empty()
	var path := text(box, "New source file (optional for edit)", "")
	button(box, "Choose asset file…", func(): choose_file(path, PackedStringArray(["*.glb,*.png,*.webp ; Static assets"])))
	var attribution: Dictionary = current.get("attribution", {})
	var source := text(box, "Source", str(attribution.get("source", "")))
	var license := text(box, "License", str(attribution.get("license", "")))
	var notice := text(box, "Notice", str(attribution.get("notice", "")))
	var width := number(box, "Proxy X size (m)", 2, 0.01, 1000, 0.01)
	var height := number(box, "Proxy height (m)", 2, 0.01, 1000, 0.01)
	var depth := number(box, "Proxy Y size (m)", 2, 0.01, 1000, 0.01)
	var boxes := json_edit(box, "Box proxies: center [x,height,y], size_cm [x,height,y]", current.get("collision", [{"center": [0,100,0], "size_cm": [200,200,200]}]))
	var convexes := json_edit(box, "Convex proxies: vertices [x,height,y], outward triangular faces (recipe 4)", current.get("convex_collision", []))
	button(box, "Replace proxies with sized box", func():
		boxes.text = JSON.stringify([{"center": [0, roundi(height.value * 50), 0], "size_cm": [roundi(width.value * 100), roundi(height.value * 100), roundi(depth.value * 100)]}], "  ")
		convexes.text = "[]"
	)
	button(box, "Replace proxies with sized tetrahedron", func():
		var w := roundi(width.value * 50)
		var h := roundi(height.value * 100)
		var d := roundi(depth.value * 50)
		boxes.text = "[]"
		convexes.text = JSON.stringify([{"vertices": [[-w,0,-d],[w,0,-d],[-w,0,d],[-w,h,-d]], "faces": [[0,1,2],[0,3,1],[0,2,3],[1,3,2]]}], "  ")
	)
	var material_on := CheckButton.new()
	material_on.text = "Override material (recipe 4)"
	material_on.button_pressed = current.has("material")
	box.add_child(material_on)
	var material: Dictionary = current.get("material", {"albedo_rgba": [255,255,255,255], "metallic_per_mille":0, "roughness_per_mille":800, "double_sided":false})
	var color := ColorPickerButton.new()
	var rgba: Array = material.albedo_rgba
	color.color = Color8(rgba[0], rgba[1], rgba[2], rgba[3])
	row(box, "Albedo").add_child(color)
	var metallic := number(box, "Metallic (per mille)", material.metallic_per_mille, 0, 1000)
	var roughness := number(box, "Roughness (per mille)", material.roughness_per_mille, 0, 1000)
	var double_sided := CheckButton.new()
	double_sided.text = "Double sided"
	double_sided.button_pressed = material.double_sided
	box.add_child(double_sided)
	var texture := text(box, "Texture asset ID (optional)", str(material.get("albedo_texture", "")))
	asset_fields = {"id": id, "path": path, "source": source, "license": license, "notice": notice, "boxes": boxes, "convexes": convexes}
	button(box, "Apply asset and proxies", func():
		if not fresh(): return
		var collision: Variant = input_json(boxes.text)
		var convex: Variant = input_json(convexes.text)
		if collision is not Array or convex is not Array:
			report("Proxy fields must be valid JSON arrays; no changes applied.")
			return
		var record := {"id": id.text, "path": current.get("path", ""), "attribution": {"source": source.text, "license": license.text, "notice": notice.text}, "collision": collision}
		if not convex.is_empty(): record.convex_collision = convex
		if material_on.button_pressed:
			record.material = {"albedo_rgba": [color.color.r8, color.color.g8, color.color.b8, color.color.a8], "metallic_per_mille": int(metallic.value), "roughness_per_mille": int(roughness.value), "double_sided": double_sided.button_pressed}
			if texture.text != "": record.material.albedo_texture = texture.text
		report(author.asset(record, path.text))
	)

func _selected() -> void:
	var box := page("Selected")
	if editor.property_records.size() != 1:
		hint(box, "Select exactly one object before opening Authoring. Common batch properties stay in the inspector.")
		return
	var entry: Dictionary = editor.property_records[0].duplicate(true)
	var record: Dictionary = entry.record
	hint(box, entry.field + ": " + str(record.id))
	if entry.field == "roads":
		hint(box, "Changing endpoints updates shared graph nodes and every incident road end in one command. Locked dependencies or invalid junctions reject the entire edit.")
		var kind := choice(box, "Structure", ["ground", "elevated", "bridge", "underpass", "tunnel"], record.kind)
		var clearance := number(box, "Clearance (cm)", float(record.clearance_cm) if record.clearance_cm != null else 400, 1, 10000)
		var sidewalk := number(box, "Sidewalk (cm; 0 none)", float(record.sidewalk_cm) if record.sidewalk_cm != null else 0, 0, 2000)
		var points: Array = []
		for i in range(record.points.size()):
			hint(box, "Point %d (cm)" % i)
			var controls: Array = []
			for axis in range(3): controls.append(number(box, ["X", "Height", "Y"][axis], record.points[i][axis], -1000000, 10000000))
			points.append(controls)
		var levels: Array = []
		for node in [record.from, record.to]: levels.append(number(box, "Endpoint level: " + str(node), editor.store._get_value(editor.store.document, "nodes", node).level, -100, 100))
		var widths: Array = []
		var surfaces: Array = []
		for i in range(record.widths_cm.size()):
			widths.append(number(box, "Segment %d width (cm)" % i, record.widths_cm[i], 20, 10000))
			surfaces.append(choice(box, "Segment %d surface" % i, ["asphalt", "concrete", "dirt", "gravel", "grass"], record.surfaces[i]))
		button(box, "Apply road structure", func():
			if not fresh(): return
			var vertices: Array = []
			for controls: Array in points: vertices.append([int(controls[0].value), int(controls[1].value), int(controls[2].value)])
			var ws: Array = []
			var ss: Array = []
			for control: SpinBox in widths: ws.append(int(control.value))
			for control: OptionButton in surfaces: ss.append(control.get_item_text(control.selected))
			var structure := kind.get_item_text(kind.selected)
			report(author.edit_road(record, vertices, ws, ss, structure, int(clearance.value) if structure in ["tunnel", "underpass"] else null, int(sidewalk.value) if sidewalk.value > 0 else null, [int(levels[0].value), int(levels[1].value)]))
		)
	else:
		hint(box, "Edit exact footprint/path/entrance/exclusion vertices below; coordinates are integer centimetres. Use Drawing settings and the canvas to create new shapes. Native validation rejects overlaps, malformed rings and invalid proxies.")
		var geometry := json_edit(box, "Object record (stable ID preserved)", record)
		geometry.custom_minimum_size.y = 320
		button(box, "Apply selected geometry", func():
			if not fresh(): return
			var after: Variant = input_json(geometry.text)
			if after is not Dictionary or after.get("id") != record.id:
				report("Preserve the selected object's ID in a valid record.")
				return
			report(author.apply("Edit selected geometry", [{"field":entry.field,"id":record.id,"before":record,"after":after}]))
		)
