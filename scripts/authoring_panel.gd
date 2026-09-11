extends AcceptDialog
const HEIGHTMAP_JOB := preload("./heightmap_native_job.gd")
const ASSET_JOB := preload("./asset_native_job.gd")
var asset_revision := 0
var asset_identity := ""
var asset_request := {}
var asset_cancel: Button
const HEIGHTMAP_LAYER := preload("./heightmap_import_layer.gd")
var heightmap_candidate: RefCounted
var heightmap_review: ConfirmationDialog
var heightmap_summary: RichTextLabel
var heightmap_controls := {}
var heightmap_request := {}
var heightmap_revision := 0
var heightmap_identity := ""
var heightmap_payloads := ""
var heightmap_review_selection := ""
var heightmap_review_epoch := -1
var heightmap_cancel: Button
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
var sign_panel: RefCounted

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
	heightmap_cancel = Button.new()
	heightmap_cancel.text = "Cancel PNG validation"
	heightmap_cancel.visible = false
	heightmap_cancel.pressed.connect(_discard_heightmap)
	column.add_child(heightmap_cancel)
	asset_cancel = Button.new()
	asset_cancel.text = "Cancel asset validation"
	asset_cancel.visible = false
	asset_cancel.pressed.connect(_discard_asset)
	column.add_child(asset_cancel)
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
	editor.store.changed.connect(_invalidate_heightmap)
	editor.store.changed.connect(_invalidate_asset)
	visibility_changed.connect(func():
		if not visible:
			heightmap_review.hide()
			_discard_heightmap()
			_discard_asset()
	)

func _invalidate_asset() -> void:
	asset_revision += 1
	_discard_asset()

func _discard_asset() -> void:
	if editor != null and editor.import_job is ASSET_JOB: editor.import_job.cancel()
	asset_identity = ""
	asset_request.clear()

func asset_selection() -> String:
	var controls := {}
	for key: String in asset_fields:
		var control: Control = asset_fields[key]
		if control is SpinBox: controls[key] = control.value
		elif control is ColorPickerButton: controls[key] = control.color.to_html()
		elif control is CheckButton: controls[key] = control.button_pressed
		else: controls[key] = control.text
	return JSON.stringify([asset_revision, asset_request, asset_before, controls, editor.canvas.layer_state, [sign_panel.revision, sign_panel.selection()] if sign_panel != null else []]).sha256_text()

func _start_asset(record: Dictionary, source: String) -> void:
	if editor.busy or not fresh(): return
	_discard_asset()
	asset_request = {"record":record.duplicate(true), "source":source}
	var job := ASSET_JOB.new()
	job.editor_generation = editor.generation
	var failure := job.start_asset(editor.store, record, source, asset_selection(), Crypto.new().generate_random_bytes(16).hex_encode())
	if failure != "":
		_discard_asset()
		report(failure)
		return
	asset_identity = job.identity
	editor.import_job = job
	editor.worker_generation = editor.generation
	editor.busy = true
	editor.import_progress.visible = true
	asset_cancel.visible = true
	feedback.text = "Checking asset and preparing Undo · 120s deadline · Cancel preserves the map."

func asset_progress(progress: Dictionary) -> void:
	if not progress.is_empty(): feedback.text = "Asset %s · %d / %d %s · 120s deadline" % [progress.stage, progress.completed, progress.total, progress.unit]

func finish_asset(job: RefCounted, result: Dictionary) -> void:
	asset_cancel.visible = false
	if asset_identity != job.identity or editor.generation != job.editor_generation or not job.done or not job.exited or not job.matches(editor.store, asset_selection()):
		_discard_asset()
		report("Asset validation cancelled or stale; apply again.")
		return
	asset_identity = ""
	var failure := "Incomplete asset validation."
	if result.get("ok", false) and result.get("data", {}).get("ok", false) and not job.bundle.is_empty(): failure = job.commit(editor.store)
	elif not result.get("ok", false) or not result.get("data", {}).get("ok", false): failure = editor.store.reason(result.get("data", result))
	_discard_asset()
	report(failure)

func _invalidate_heightmap() -> void:
	heightmap_revision += 1
	_discard_heightmap()

func _discard_heightmap() -> void:
	if editor != null and editor.import_job is HEIGHTMAP_JOB: editor.import_job.cancel()
	heightmap_identity = ""
	heightmap_payloads = ""
	heightmap_request.clear()
	if heightmap_candidate != null: heightmap_candidate.discard()
	heightmap_candidate = null
	if heightmap_review != null: heightmap_review.hide()

func _exit_tree() -> void:
	_discard_heightmap()
	_discard_asset()

func heightmap_selection() -> String:
	var controls := {}
	for key: String in heightmap_controls:
		var control: Control = heightmap_controls[key]
		controls[key] = control.value if control is SpinBox else control.text
	return JSON.stringify([heightmap_revision, heightmap_request, controls, author.options.grid_cm,
		heightmap_candidate.value if heightmap_candidate != null else {}, editor.canvas.layer_state]).sha256_text()

func _stage_heightmap(path: String, cell: Vector2i, spacing: int, offset: int, step: int, accuracy: int, attribution: Dictionary) -> void:
	if editor.busy: return
	_discard_heightmap()
	heightmap_request = {"path":path, "cell":[cell.x, cell.y], "spacing":spacing, "offset":offset, "step":step, "accuracy":accuracy, "attribution":attribution.duplicate(true)}
	_start_heightmap(false)

func _start_heightmap(adopting: bool) -> void:
	if editor.busy: return
	if not editor.canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true):
		_discard_heightmap()
		report("Show and unlock terrain before PNG validation.")
		return
	var job := HEIGHTMAP_JOB.new()
	job.editor_generation = editor.generation
	var previous := {"layer_id":heightmap_candidate.value.layer_id, "payloads":heightmap_payloads} if adopting else {}
	var failure := job.start_png(editor.store, heightmap_request, adopting, heightmap_selection(), Crypto.new().generate_random_bytes(16).hex_encode(), previous)
	if failure != "":
		_discard_heightmap()
		report(failure)
		return
	heightmap_identity = job.identity
	editor.import_job = job
	editor.worker_generation = editor.generation
	editor.busy = true
	editor.import_progress.visible = true
	heightmap_cancel.visible = true
	feedback.text = "Checking PNG before %s · 120s deadline · Cancel preserves the map." % ("adoption" if adopting else "review")

func heightmap_progress(progress: Dictionary) -> void:
	if progress.is_empty(): return
	feedback.text = "PNG %s · %d / %d %s · 120s deadline" % [progress.stage, progress.completed, progress.total, progress.unit]

func finish_heightmap(job: RefCounted, result: Dictionary) -> void:
	heightmap_cancel.visible = false
	if heightmap_identity != job.identity or editor.generation != job.editor_generation or not job.done or not job.exited or not job.matches(editor.store, heightmap_selection()):
		_discard_heightmap()
		report("PNG validation cancelled or stale; stage the source again.")
		return
	heightmap_identity = ""
	if not result.get("ok", false) or not result.get("data", {}).get("ok", false) or job.bundle.is_empty():
		_discard_heightmap()
		report(editor.store.reason(result.get("data", result)))
		return
	if job.adopting:
		var failure: String = job.commit(editor.store)
		_discard_heightmap()
		report(failure)
		return
	heightmap_candidate = HEIGHTMAP_LAYER.new()
	heightmap_candidate.value = job.bundle.value.duplicate(true)
	heightmap_payloads = result.data.payloads
	heightmap_review_epoch = editor.store.command_epoch
	heightmap_review_selection = heightmap_selection()
	heightmap_candidate.recheck_source = true
	heightmap_summary.text = heightmap_candidate.summary()
	heightmap_review.popup_centered(Vector2i(680, 460))
	feedback.text = "Validated candidate; document unchanged. Review then adopt or discard."

func _adopt_heightmap() -> void:
	if heightmap_candidate == null or editor.busy: return
	if heightmap_review_epoch != editor.store.command_epoch or heightmap_review_selection != heightmap_selection():
		_discard_heightmap()
		report("PNG review changed; stage the source again.")
		return
	heightmap_review.hide()
	_start_heightmap(true)

func open() -> void:
	if editor.busy: return
	if not editor.layers.state_changed.is_connected(_invalidate_heightmap): editor.layers.state_changed.connect(_invalidate_heightmap)
	if not editor.layers.state_changed.is_connected(_invalidate_asset): editor.layers.state_changed.connect(_invalidate_asset)
	_discard_heightmap()
	_discard_asset()
	heightmap_controls.clear()
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
	if sign_panel != null: sign_panel.teardown()
	sign_panel = preload("./sign_panel.gd").new()
	sign_panel.setup(self)
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
	hint(box, "Recipe 2: terrain-following roads, bridge/tunnel cuts. Recipe 3: buildings, entrances and repeated props. Recipe 4: custom convex proxies and materials. Recipe 6: ground paving, road markings and connected sidewalks. Changing recipe changes world identity; originals are never migrated on load.")
	var recipe := choice(box, "Recipe", ["1", "2", "3", "4", "5", "6"], str(int(editor.store.document.recipe_version)))
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
	control.value_changed.connect(func(value):
		author.options[key] = roundi(value * scale)
		editor.canvas.authoring_revision += 1
	)
	fields[key] = control

func opt_choice(box: Node, title: String, key: String, values: Array) -> void:
	var control := choice(box, title, values, str(author.options[key]))
	control.item_selected.connect(func(index):
		author.options[key] = values[index]
		editor.canvas.authoring_revision += 1
	)
	fields[key] = control

func _drawing() -> void:
	var box := page("Drawing")
	hint(box, "Settings affect the next shape. Click points on the canvas; right-click finishes. Place uses one click. Select a building/zone before drawing an Entrance/Exclusion. Escape cancels. Matching XYZ and level reuse an explicit road node; XY crossings never connect.")
	opt_choice(box, "Road structure", "kind", ["ground", "elevated", "bridge", "underpass", "tunnel"])
	opt_number(box, "Road width (m)", "width_cm", 0.2, 100)
	opt_choice(box, "Road / ground area surface", "surface", ["asphalt", "concrete", "dirt", "gravel", "grass"])
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
	hint(box, "Cylinder wall: choose the tool and click its centre. A solid round barrier uses the same visible and collision outline. Base and material are shared with the settings above.")
	opt_number(box, "Cylinder wall radius (m)", "wall_radius_cm", 0.25, 500)
	opt_number(box, "Cylinder wall height (m)", "wall_height_cm", 0.01, 1000)
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
	source_picker.file_selected.connect(func(path): target.text = path; target.text_changed.emit(path))
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
	heightmap_controls = {"path":path, "x":x, "y":y, "spacing":fields.grid_cm, "offset":offset, "step":step, "accuracy":accuracy, "source":source, "license":license, "notice":notice}
	for control: Control in heightmap_controls.values():
		if control is SpinBox: control.value_changed.connect(func(_value): _invalidate_heightmap())
		else: control.text_changed.connect(func(_value): _invalidate_heightmap())

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
	_invalidate_asset()
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
	asset_fields = {"id": id, "path": path, "source": source, "license": license, "notice": notice, "boxes": boxes, "convexes": convexes,
		"width":width, "height":height, "depth":depth, "material_on":material_on, "color":color, "metallic":metallic, "roughness":roughness, "double_sided":double_sided, "texture":texture}
	for control: Control in asset_fields.values():
		if control is SpinBox: control.value_changed.connect(func(_value): _invalidate_asset())
		elif control is ColorPickerButton: control.color_changed.connect(func(_value): _invalidate_asset())
		elif control is CheckButton: control.toggled.connect(func(_value): _invalidate_asset())
		elif control is LineEdit: control.text_changed.connect(func(_value): _invalidate_asset())
		elif control is TextEdit: control.text_changed.connect(_invalidate_asset)
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
		_start_asset(record, path.text)
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
		var markings_on := CheckButton.new()
		markings_on.text = "Road markings (recipe 6)"
		markings_on.button_pressed = record.has("markings")
		box.add_child(markings_on)
		var appearance: Dictionary = record.get("markings", {"lanes":2,"center_line":true,"edge_lines":true,"crosswalk_start":false,"crosswalk_end":false})
		var lanes := number(box, "Lane count", appearance.lanes, 1, 8)
		var mark_controls := {}
		for key in ["center_line", "edge_lines", "crosswalk_start", "crosswalk_end"]:
			var control := CheckButton.new()
			control.text = str(key).replace("_", " ").capitalize()
			control.button_pressed = appearance[key]
			box.add_child(control)
			mark_controls[key] = control
		button(box, "Apply road markings", func():
			if not fresh(): return
			var before: Dictionary = editor.store._get_value(editor.store.document, "roads", record.id).duplicate(true)
			var after := before.duplicate(true)
			if markings_on.button_pressed:
				after.markings = {"lanes":int(lanes.value)}
				for key in mark_controls: after.markings[key] = mark_controls[key].button_pressed
			else: after.erase("markings")
			report(author.apply("Edit road markings", [{"field":"roads","id":record.id,"before":before,"after":after}]))
		)
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
		var cylinder: Dictionary = author.CYLINDER.dimensions(record) if entry.field == "buildings" else {}
		if not cylinder.is_empty():
			hint(box, "Cylinder wall · solid collision · 48 sides")
			var cx := number(box, "Centre X (m)", cylinder.center.x / 100.0, -100000, 100000, 0.01)
			var cy := number(box, "Centre Y (m)", cylinder.center.y / 100.0, -100000, 100000, 0.01)
			var radius := number(box, "Wall radius (m)", cylinder.radius_cm / 100.0, 0.25, 500, 0.01)
			var base := number(box, "Base (m)", record.base_cm / 100.0, -10000, 10000, 0.01)
			var height := number(box, "Wall height (m)", record.height_cm / 100.0, 0.01, 1000, 0.01)
			button(box, "Apply cylinder wall", func():
				if not fresh(): return
				var after := record.duplicate(true)
				after.footprint = author.CYLINDER.footprint(Vector2(roundi(cx.value * 100), roundi(cy.value * 100)), roundi(radius.value * 100), cylinder.phase)
				after.base_cm = roundi(base.value * 100)
				after.height_cm = roundi(height.value * 100)
				report(author.apply("Edit cylinder wall", [{"field": "buildings", "id": record.id, "before": record, "after": after}]))
			)
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
