extends RefCounted
const SIGNS := preload("./sign_authoring.gd")
const FILES := preload("./authoring_files.gd")
var panel: AcceptDialog
var controls := {}
var revision := 0
var baking := false
var scratch := ""

func setup(owner: AcceptDialog) -> void:
	panel = owner
	var box: VBoxContainer = panel.page("Signs")
	panel.hint(box, "Map writing stays independent of UI language. Create a sign from a licensed font, or import a prepared PNG. Place it as a separate asset in Drawing; the building stays unchanged. Select an existing sign asset to restore text and provenance; reselect its licensed font to edit. Imported images retain their original layout.")
	var saved := {}
	for asset: Dictionary in panel.editor.store.document.assets:
		if asset.id == panel.author.options.asset_id:
			var parser := JSON.new()
			if parser.parse(str(asset.attribution.get("notice", ""))) == OK:
				var value: Variant = parser.data
				if value is Dictionary and str(value.get("kind", "")).ends_with("sign-v1"): saved = value
	controls.id = panel.text(box, "Sign asset ID", panel.author.options.asset_id if not saved.is_empty() else "map-sign")
	controls.text = panel.text(box, "Text", str(saved.get("text", "")))
	controls.font_path = panel.text(box, "Local TTF / OTF path", "")
	controls.font_source = panel.text(box, "Font / image source", str(saved.get("font_source", saved.get("image_source", ""))))
	controls.font_license = panel.text(box, "Font / image license", str(saved.get("font_license", saved.get("image_license", ""))))
	controls.language = panel.text(box, "Language(s), e.g. ar or ko,en", str(saved.get("language", "en")))
	controls.direction = panel.choice(box, "Writing direction", ["auto", "ltr", "rtl"], str(saved.get("direction", "auto")))
	controls.alignment = panel.choice(box, "Alignment", ["left", "center", "right"], str(saved.get("alignment", "center")))
	controls.font_size = panel.number(box, "Font size (pixels)", int(saved.get("font_size", 112)), 12, 160)
	controls.paper = panel.text(box, "Background hex color", str(saved.get("paper", "183f3b")))
	controls.ink = panel.text(box, "Text hex color", str(saved.get("ink", "f7f0d4")))
	controls.image_path = panel.text(box, "Prepared PNG path", "")
	controls.width = panel.number(box, "Width (m)", float(saved.get("width_cm",300))/100, .1, 20, .01)
	controls.height = panel.number(box, "Height (m)", float(saved.get("height_cm",110))/100, .1, 10, .01)
	for control: Control in controls.values():
		if control is LineEdit: control.text_changed.connect(func(_value): _invalidate())
		elif control is SpinBox: control.value_changed.connect(func(_value): _invalidate())
		elif control is OptionButton: control.item_selected.connect(func(_value): _invalidate())
	panel.button(box, "Create text sign", _bake)
	panel.button(box, "Import prepared sign image", _import)
	panel.visibility_changed.connect(_invalidate)
	panel.editor.store.changed.connect(_invalidate)

func _invalidate() -> void:
	revision += 1

func selection() -> Dictionary:
	var spec := {}
	for key: String in controls:
		var control: Control = controls[key]
		if control is OptionButton: spec[key] = control.get_item_text(control.selected)
		elif control is SpinBox: spec[key] = control.value
		else: spec[key] = control.text
	return spec

func _bake() -> void:
	if baking or panel.editor.busy or not panel.fresh(): return
	var spec := selection()
	var epoch := revision
	baking = true
	panel.feedback.text = "Shaping and drawing sign…"
	var result := await SIGNS.bake(panel, spec, func(): return panel.visible and epoch == revision and spec == selection())
	baking = false
	if result.has("error"):
		panel.report(result.error)
		return
	# Asset preparation, cancellation and adoption use the existing killable worker.
	_stage(spec, result.bytes, result.metadata)

func _import() -> void:
	if baking or panel.editor.busy or not panel.fresh(): return
	var spec := selection()
	if str(spec.font_source).strip_edges().is_empty() or str(spec.font_license).strip_edges().is_empty():
		panel.report("Record the image source and license.")
		return
	if str(spec.image_path).get_extension().to_lower() != "png":
		panel.report("Choose a prepared PNG sign image.")
		return
	var source := FILES.read(spec.image_path, 16*1024*1024)
	if source.has("error"):
		panel.report(source.error)
		return
	var metadata := {"kind":"image-sign-v1", "image_source":spec.font_source, "image_license":spec.font_license,
		"language":spec.language, "direction":"prepared-image", "image_sha256":FILES.digest(source.bytes)}
	_stage(spec, source.bytes, metadata)

func _stage(spec: Dictionary, png: PackedByteArray, metadata: Dictionary) -> void:
	var width := roundi(spec.width*100)
	var height := roundi(spec.height*100)
	var bytes := SIGNS.SURFACE.encode(png,width,height)
	if bytes.is_empty():
		panel.report("Sign source or dimensions exceed the authoring limit.")
		return
	metadata["width_cm"]=width;metadata["height_cm"]=height
	scratch = ProjectSettings.globalize_path("user://sign-bakes/" + FILES.digest(bytes) + ".glb")
	var failure := FILES.write_new(scratch, bytes)
	if failure != "": panel.report(failure)
	else: panel._start_asset(SIGNS.record(spec.id,metadata,width,height),scratch)

func teardown() -> void:
	_invalidate()
	panel.visibility_changed.disconnect(_invalidate)
	panel.editor.store.changed.disconnect(_invalidate)
