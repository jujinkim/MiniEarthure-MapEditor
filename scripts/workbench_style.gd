extends RefCounted
## Project-owned Luna-inspired chrome. No OS theme or import cache is required.
const PANEL := Color("ece9d8")
const PAPER := Color("ffffff")
const INK := Color("1f2b3d")
const BLUE := Color("245edb")
const SELECTION := Color("dcebff")
const YELLOW := Color("ffcc66")
const CORAL := Color("df704b")
const BORDER := Color("8a9aaf")
const GRID := Color("d3dce7")
const CANVAS := Color("f4f6fa")
static var textures: Dictionary = {}
const ICON_NAMES := [
	"2d", "3d", "area", "building", "cancel",
	"check", "connect", "curve", "cylinder", "delete",
	"down", "duplicate", "export", "flag", "forest",
	"frame", "free_curve", "generate", "hairpin", "help",
	"import", "jump", "keyboard", "loop", "minus",
	"new", "obstacle", "open", "orchard", "panel",
	"piece_acceleration_panel", "piece_air_ring", "piece_approach", "piece_banked_chicane", "piece_boost_chain",
	"piece_chicane", "piece_chicane_narrow", "piece_curve", "piece_curve_down", "piece_curve_left",
	"piece_curve_left_down", "piece_curve_left_up", "piece_curve_up", "piece_cylinder", "piece_cylinder_curve",
	"piece_cylinder_curve_left", "piece_cylinder_s_rise", "piece_cylinder_uturn", "piece_cylinder_uturn_left", "piece_cylinder_wide",
	"piece_cylinder_wide_curve", "piece_cylinder_wide_curve_left", "piece_cylinder_wide_s_rise", "piece_cylinder_wide_uturn", "piece_cylinder_wide_uturn_left",
	"piece_finish_plaza", "piece_flight_curve", "piece_free_curve", "piece_gentle45", "piece_gentle45_left",
	"piece_gentle90", "piece_gentle90_left", "piece_hairpin", "piece_hairpin_left", "piece_jump",
	"piece_jump_panel", "piece_loop", "piece_offset_jump", "piece_overpass", "piece_right90",
	"piece_right90_left", "piece_roller_waves", "piece_sharp135", "piece_sharp135_left", "piece_sharp_curve",
	"piece_sharp_curve_left", "piece_slope", "piece_slope_down", "piece_slope_up", "piece_spiral180_left_down",
	"piece_spiral180_left_up", "piece_spiral180_right_down", "piece_spiral180_right_up", "piece_spiral360_left_down", "piece_spiral360_left_up",
	"piece_spiral360_right_down", "piece_spiral360_right_up", "piece_spiral90_left_down", "piece_spiral90_left_up", "piece_spiral90_right_down",
	"piece_spiral90_right_up", "piece_spiral_down", "piece_spiral_up", "piece_sprint_lane", "piece_straight",
	"piece_straight_narrow", "piece_tube_entry", "piece_tube_exit", "piece_zigzag", "piece_zigzag_narrow",
	"place", "plus", "redo", "repeat", "road",
	"rotate_left", "rotate_right", "route", "save", "search",
	"select", "settings", "slope", "snap", "split",
	"undo", "up", "water",
]

static func box(color: Color, border := BORDER, inset := 6) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = border
	style.set_border_width_all(1)
	style.set_content_margin_all(inset)
	style.set_corner_radius_all(3)
	return style

static func bevel(top: Color, bottom: Color, border := BORDER, pressed := false) -> StyleBoxTexture:
	# Nine-slice artwork is made in memory so even cold source launches have chrome.
	var pixels := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	for y in 16:
		for x in 16:
			if (x == 0 or x == 15) and (y < 2 or y > 13): continue
			if (y == 0 or y == 15) and (x < 2 or x > 13): continue
			var color := top.lerp(bottom, float(y) / 15.0)
			if x == 0 or x == 15 or y == 0 or y == 15: color = border
			elif x == 1 or y == 1: color = border.lightened(0.3) if pressed else Color.WHITE
			elif x == 14 or y == 14: color = Color.WHITE if pressed else bottom.darkened(0.12)
			pixels.set_pixel(x, y, color)
	var style := StyleBoxTexture.new()
	style.texture = ImageTexture.create_from_image(pixels)
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: style.set_texture_margin(side, 4)
	style.set_content_margin_all(6)
	return style

static func svg_texture(source: String) -> Texture2D:
	var pixels := Image.new()
	if source.is_empty() or pixels.load_svg_from_string(source) != OK or pixels.is_invisible(): return null
	return ImageTexture.create_from_image(pixels)

static func checkbox(checked: bool, disabled := false) -> Texture2D:
	var ink := "9298a0" if disabled else "28549a"
	var mark := '<path d="M4 8l3 3 5-7" fill="none" stroke="#3d8e36" stroke-width="2"/>' if checked else ""
	return svg_texture('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect x="1" y="1" width="13" height="13" rx="2" fill="#ffffff" stroke="#' + ink + '"/>' + mark + '</svg>')

static func create_theme() -> Theme:
	var result := Theme.new()
	result.default_font_size = 14
	var focus := box(Color.TRANSPARENT, BLUE, 0)
	for type in ["Label", "Button", "CheckBox", "CheckButton", "MenuButton", "OptionButton", "LineEdit", "TextEdit", "Tree", "ItemList", "TabBar", "TabContainer", "PopupMenu", "Window", "TooltipLabel", "RichTextLabel"]:
		for color in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color", "font_selected_color", "font_hover_pressed_color", "font_readonly_color", "font_unselected_color"]:
			result.set_color(color, type, INK)
		result.set_color("font_disabled_color", type, Color("858a92"))
		result.set_color("font_placeholder_color", type, Color("687588"))
		result.set_color("caret_color", type, INK)
		result.set_color("selection_color", type, SELECTION)
		result.set_stylebox("focus", type, focus)
	for type in ["Button", "OptionButton"]:
		result.set_stylebox("normal", type, bevel(Color("ffffff"), Color("e5e4dd")))
		result.set_stylebox("hover", type, bevel(Color("fffdf2"), Color("ffe5a5"), Color("d3a44d")))
		result.set_stylebox("pressed", type, bevel(Color("c0d5f4"), Color("e3efff"), BLUE, true))
		result.set_stylebox("hover_pressed", type, bevel(Color("cfdef5"), Color("edf5ff"), BLUE, true))
		result.set_stylebox("disabled", type, box(Color("e8e7e2"), Color("b6babf")))
		for state in ["normal", "hover", "pressed", "focus", "hover_pressed"]: result.set_color("icon_" + state + "_color", type, Color.WHITE)
		result.set_color("icon_disabled_color", type, Color(0.65, 0.68, 0.72, 0.6))
	for type in ["MenuButton", "CheckBox", "CheckButton"]:
		var empty := StyleBoxEmpty.new()
		empty.content_margin_left = 6
		empty.content_margin_right = 6
		for state in ["normal", "disabled"]: result.set_stylebox(state, type, empty)
		var hover := box(SELECTION, BORDER, 3)
		hover.content_margin_left = 6
		hover.content_margin_right = 6
		for state in ["hover", "pressed", "hover_pressed"]: result.set_stylebox(state, type, hover)
	for type in ["CheckBox", "CheckButton"]:
		for checked in [false, true]:
			var state := "checked" if checked else "unchecked"
			result.set_icon(state, type, checkbox(checked))
			result.set_icon(state + "_disabled", type, checkbox(checked, true))
	for type in ["PanelContainer", "PopupPanel", "TabContainer", "AcceptDialog"]: result.set_stylebox("panel", type, box(PANEL))
	for type in ["PopupMenu", "Tree", "ItemList"]: result.set_stylebox("panel", type, box(PAPER))
	result.set_stylebox("hover", "PopupMenu", box(SELECTION, Color("9db8dc"), 3))
	result.set_stylebox("panel", "TooltipPanel", box(Color("ffffe1"), Color("66738a")))
	for type in ["LineEdit", "TextEdit"]:
		result.set_stylebox("normal", type, box(PAPER))
		result.set_stylebox("read_only", type, box(Color("efefec")))
	for type in ["Tree", "ItemList"]:
		result.set_stylebox("selected", type, box(SELECTION, BORDER, 2))
		result.set_stylebox("selected_focus", type, box(SELECTION, BLUE, 2))
	for type in ["TabContainer", "TabBar"]:
		result.set_stylebox("tab_selected", type, bevel(Color("ffffff"), PANEL, Color("7a9ac4")))
		result.set_stylebox("tab_unselected", type, box(Color("deded6")))
		result.set_stylebox("tab_hovered", type, box(Color("fff3d2"), Color("d3a44d")))
	for type in ["HScrollBar", "VScrollBar"]:
		result.set_stylebox("scroll", type, box(Color("e5e9f0"), Color("ccd3df"), 6))
		result.set_stylebox("grabber", type, bevel(Color("ebf3ff"), Color("bbcee8")))
		result.set_stylebox("grabber_highlight", type, bevel(Color("ffffff"), SELECTION, BLUE))
		result.set_stylebox("grabber_pressed", type, bevel(SELECTION, Color("a8bfdf"), BLUE, true))
	result.set_stylebox("embedded_border", "Window", box(BLUE, Color("1945a4")))
	result.set_color("title_color", "Window", Color.WHITE)
	result.set_constant("title_height", "Window", 28)
	result.set_constant("h_separation", "GridContainer", 6)
	result.set_constant("v_separation", "GridContainer", 6)
	result.set_constant("h_separation", "HFlowContainer", 4)
	result.set_constant("v_separation", "HFlowContainer", 6)
	return result

static func icon_name(label: String) -> String:
	var value := label.to_lower().replace(" ", "_")
	if value in ICON_NAMES: return value
	for pair in [["jump_panel", "panel"], ["acceleration", "panel"], ["boost", "panel"], ["air_ring", "loop"], ["cylinder", "cylinder"], ["hairpin", "hairpin"], ["uturn", "hairpin"], ["loop", "loop"], ["slope", "slope"], ["spiral", "loop"], ["curve", "curve"], ["gentle", "curve"], ["turn", "curve"], ["jump", "jump"], ["straight", "road"], ["terrain", "slope"], ["surface", "area"], ["island", "area"], ["exclusion", "area"], ["entrance", "connect"], ["checkpoint", "flag"], ["route", "route"], ["snap", "snap"], ["connect", "connect"], ["delete", "delete"], ["remove", "minus"], ["cancel", "cancel"], ["save", "save"], ["apply", "check"], ["validate", "check"], ["generate", "generate"], ["seed", "generate"], ["import", "import"], ["export", "export"], ["restore", "undo"], ["recover", "undo"], ["frame", "frame"], ["fit", "frame"], ["preview", "3d"], ["command", "search"], ["search", "search"], ["add", "plus"], ["new", "plus"], ["obstacle", "obstacle"], ["barrier", "obstacle"], ["shortcuts", "keyboard"]]:
		if pair[0] in value: return pair[1]
	return "settings"

static func _read_icon(path: String) -> Texture2D:
	# Source .import metadata may survive while its .ctex cache is absent. Avoid
	# asking ResourceLoader to follow that broken remap on a cold source launch.
	var imported := ConfigFile.new()
	if FileAccess.file_exists(path + ".import") and imported.load(path + ".import") == OK:
		var compiled: String = imported.get_value("remap", "path", "")
		if not compiled.is_empty() and FileAccess.file_exists(compiled):
			return load(path) as Texture2D
	if FileAccess.file_exists(path):
		return svg_texture(FileAccess.get_file_as_string(path))
	if FileAccess.file_exists(path + ".import"): return null
	# Exported PCKs retain remapped resources, not necessarily loose SVG sources.
	if ResourceLoader.exists(path): return load(path) as Texture2D
	return null

static func icon(id: String) -> Texture2D:
	var name := icon_name(id)
	if textures.has(name): return textures[name]
	var path := "res://ui/icons/" + name + ".svg"
	var texture := _read_icon(path)
	if texture != null:
		var pixels := texture.get_image()
		if pixels == null or pixels.is_empty() or pixels.is_invisible(): texture = null
	if texture == null:
		push_warning("MapEditor icon unavailable: " + path + "; showing the action name.")
	else:
		textures[name] = texture
	return texture

static func decorate(button: Button, label: String, description := "", icon_id := "", tile := false) -> void:
	button.set_meta("action_label", label)
	button.icon = icon(icon_id if icon_id != "" else label)
	button.text = label if button.icon == null else ""
	button.expand_icon = true
	button.add_theme_constant_override("icon_max_width", 30 if tile else 24)
	button.custom_minimum_size = Vector2(52, 52) if tile else Vector2(40, 40)
	button.tooltip_text = label + ("\n" + description if description != "" else "")
	button.focus_mode = Control.FOCUS_ALL
	button.accessibility_name = label

static func button(parent: Node, label: String, action: Callable, description := "", icon_id := "", tile := false) -> Button:
	var control := Button.new()
	decorate(control, label, description, icon_id, tile)
	control.pressed.connect(action)
	parent.add_child(control)
	return control
