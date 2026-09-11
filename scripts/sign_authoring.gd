extends RefCounted
## Baked, map-owned writing. TextServer shapes once; recipients need only PNG.
const FILES := preload("./authoring_files.gd")
const SURFACE := preload("res://addons/mapkit/godot/sign_asset.gd")
const PIXELS := Vector2i(1024, 256)
const MAX_FONT_BYTES := 32 * 1024 * 1024

class SignCanvas extends Control:
	var line: TextLine
	var ink: Color
	var paper: Color
	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, Vector2(PIXELS)), paper)
		line.draw(get_canvas_item(), Vector2(24, (PIXELS.y-line.get_size().y)/2), ink)

static func bake(parent: Node, spec: Dictionary, alive: Callable = Callable()) -> Dictionary:
	if DisplayServer.get_name() == "headless": return {"error":"Text signs require a rendering display; import a prepared PNG/WebP in headless workflows."}
	var text: String = spec.get("text", "")
	if text.strip_edges().is_empty() or text.length() > 128 or "\n" in text or "\r" in text or "\t" in text:
		return {"error":"Use one nonempty line of at most 128 characters."}
	for key in ["font_source", "font_license", "language", "direction"]:
		if str(spec.get(key, "")).strip_edges().is_empty(): return {"error":"Missing sign " + key + "."}
	if spec.direction not in ["auto", "ltr", "rtl"]: return {"error":"Choose auto, ltr or rtl writing direction."}
	if spec.get("alignment", "center") not in ["left", "center", "right"]: return {"error":"Choose left, center or right alignment."}
	for key in ["ink", "paper"]:
		if spec.has(key) and not Color.html_is_valid(str(spec[key])): return {"error":"Use a hex color for " + key + "."}
	var path: String = spec.get("font_path", "")
	if path.get_extension().to_lower() not in ["ttf", "otf"]: return {"error":"Choose a licensed local TTF or OTF font."}
	var source := FILES.read(path, MAX_FONT_BYTES)
	if source.has("error"): return source
	var font := FontFile.new()
	font.data = source.bytes
	font.allow_system_fallback = false
	font.fallbacks = []
	# Explicitly reject missing codepoints before shaping; joiners and bidi controls
	# are layout inputs, never replaced with an arbitrary installed font.
	var missing: Array[String] = []
	for i in text.length():
		var cp := text.unicode_at(i)
		if cp in [0x200c, 0x200d, 0x200e, 0x200f, 0x2066, 0x2067, 0x2068, 0x2069]: continue
		if cp < 32 or not font.has_char(cp): missing.append("U+%04X" % cp)
	if not missing.is_empty(): return {"error":"Font lacks sign characters: " + ", ".join(missing)}
	var line := TextLine.new()
	line.direction = {"auto":TextServer.DIRECTION_AUTO, "ltr":TextServer.DIRECTION_LTR, "rtl":TextServer.DIRECTION_RTL}[spec.direction]
	line.alignment = {"left":HORIZONTAL_ALIGNMENT_LEFT, "center":HORIZONTAL_ALIGNMENT_CENTER, "right":HORIZONTAL_ALIGNMENT_RIGHT}[spec.get("alignment", "center")]
	var font_size := int(spec.get("font_size", 112))
	if font_size < 12 or font_size > 160: return {"error":"Font size must be 12–160 pixels."}
	if not line.add_string(text, font, font_size, str(spec.language)): return {"error":"Font could not shape this sign."}
	if line.get_size().x > PIXELS.x-48 or line.get_size().y > PIXELS.y-32:
		return {"error":"Text does not fit the sign; reduce size or shorten the line. No text was clipped."}
	var glyphs: Array = TextServerManager.get_primary_interface().shaped_text_get_glyphs(line.get_rid())
	for glyph: Dictionary in glyphs:
		if int(glyph.count) > 0 and not (int(glyph.flags) & TextServer.GRAPHEME_IS_VALID) and not (int(glyph.flags) & TextServer.GRAPHEME_IS_SPACE):
			return {"error":"Unsupported shaped cluster at character " + str(glyph.start) + "."}
	line.width = PIXELS.x-48
	var canvas := SignCanvas.new()
	canvas.line = line
	canvas.ink = Color(str(spec.get("ink", "f7f0d4")))
	canvas.paper = Color(str(spec.get("paper", "183f3b")))
	var viewport := SubViewport.new()
	viewport.size = PIXELS
	viewport.disable_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	parent.add_child(viewport)
	viewport.add_child(canvas)
	# Bounded to a few render frames. Caller owns a generation/visibility guard.
	await parent.get_tree().process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	viewport.queue_free()
	if alive.is_valid() and not alive.call(): return {"error":"Sign creation cancelled or controls changed."}
	if image == null or image.is_empty(): return {"error":"Sign rasterization failed."}
	var bytes := image.save_png_to_buffer()
	var metadata := {}
	for key in ["text", "language", "direction", "alignment", "font_source", "font_license", "ink", "paper"]:
		if spec.has(key): metadata[key] = spec[key]
	metadata.merge({"kind":"text-sign-v1", "font_sha256":FILES.digest(source.bytes), "image_sha256":FILES.digest(bytes), "pixels":[PIXELS.x,PIXELS.y], "shaper":"Godot TextServer Advanced", "font_size":font_size}, true)
	return {"bytes":bytes, "metadata":metadata, "glyphs":glyphs}

static func record(id: String, metadata: Dictionary, width_cm: int = 300, height_cm: int = 110) -> Dictionary:
	return {"id":id, "path":"pending.glb", "attribution":{"source":str(metadata.get("font_source", metadata.get("image_source", ""))), "license":str(metadata.get("font_license", metadata.get("image_license", ""))), "notice":JSON.stringify(metadata)},
		"collision":[{"center":[0,height_cm/2,0], "size_cm":[width_cm,height_cm,2]}]}
