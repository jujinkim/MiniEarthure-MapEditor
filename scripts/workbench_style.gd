extends RefCounted
## Project-owned MIT SVGs and a shared cream / ink workbench theme.
const CREAM := Color("fff7e6")
const INK := Color("202020")
const YELLOW := Color("ffda57")
const BLUE := Color("85c7f2")
const CORAL := Color("ff947e")
static var textures: Dictionary = {}

static func box(color: Color, shadow := false) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = INK
	style.set_border_width_all(2)
	style.set_content_margin_all(6)
	if shadow:
		style.shadow_color = INK
		style.shadow_offset = Vector2(3, 3)
		style.shadow_size = 1
	return style

static func create_theme() -> Theme:
	var result := Theme.new()
	result.default_font_size = 14
	for type in ["Label", "Button", "CheckBox", "CheckButton", "MenuButton", "OptionButton", "LineEdit", "TextEdit", "Tree", "ItemList", "TabBar", "TabContainer", "PopupMenu", "Window", "TooltipLabel"]:
		for color in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color", "font_selected_color", "font_hover_pressed_color", "font_readonly_color"]:
			result.set_color(color, type, INK)
		result.set_color("font_disabled_color", type, Color("777367"))
		result.set_color("font_unselected_color", type, INK)
		result.set_color("font_placeholder_color", type, Color("706b60"))
		result.set_color("caret_color", type, INK)
		result.set_color("selection_color", type, BLUE)
		result.set_stylebox("focus", type, box(BLUE * Color(1, 1, 1, 0)))
	for type in ["Button", "OptionButton", "MenuButton"]:
		result.set_stylebox("normal", type, box(CREAM, true))
		result.set_stylebox("hover", type, box(YELLOW, true))
		result.set_stylebox("pressed", type, box(BLUE))
		result.set_stylebox("hover_pressed", type, box(BLUE, true))
		result.set_stylebox("disabled", type, box(Color("e5dfd0")))
		var focus := box(Color.TRANSPARENT)
		focus.border_color = Color("1c65a0")
		focus.set_border_width_all(3)
		result.set_stylebox("focus", type, focus)
	for type in ["PanelContainer", "PopupPanel", "PopupMenu", "Tree", "ItemList", "TabContainer", "TooltipPanel"]:
		result.set_stylebox("panel", type, box(CREAM))
	for type in ["LineEdit", "TextEdit"]:
		result.set_stylebox("normal", type, box(Color("fffdf6")))
		result.set_stylebox("read_only", type, box(Color("ece5d6")))
	for type in ["Tree", "ItemList"]:
		result.set_stylebox("selected", type, box(YELLOW))
		result.set_stylebox("selected_focus", type, box(BLUE))
	for type in ["TabContainer", "TabBar"]:
		result.set_stylebox("tab_selected", type, box(YELLOW))
		result.set_stylebox("tab_unselected", type, box(CREAM))
		result.set_stylebox("tab_hovered", type, box(BLUE))
	result.set_stylebox("embedded_border", "Window", box(CREAM, true))
	result.set_constant("h_separation", "GridContainer", 6)
	result.set_constant("v_separation", "GridContainer", 6)
	return result

static func icon_name(label: String) -> String:
	var value := label.to_lower().replace(" ", "_")
	if FileAccess.file_exists("res://ui/icons/" + value + ".svg"): return value
	for pair in [["jump_panel", "panel"], ["acceleration", "panel"], ["boost", "panel"], ["air_ring", "loop"], ["cylinder", "cylinder"], ["hairpin", "hairpin"], ["uturn", "hairpin"], ["loop", "loop"], ["slope", "slope"], ["spiral", "loop"], ["curve", "curve"], ["gentle", "curve"], ["turn", "curve"], ["jump", "jump"], ["straight", "road"], ["terrain", "slope"], ["surface", "area"], ["island", "area"], ["exclusion", "area"], ["entrance", "connect"], ["checkpoint", "flag"], ["route", "route"], ["snap", "snap"], ["connect", "connect"], ["delete", "delete"], ["remove", "minus"], ["cancel", "cancel"], ["save", "save"], ["apply", "check"], ["validate", "check"], ["generate", "generate"], ["seed", "generate"], ["import", "import"], ["export", "export"], ["restore", "undo"], ["recover", "undo"], ["frame", "frame"], ["fit", "frame"], ["preview", "3d"], ["command", "search"], ["search", "search"], ["add", "plus"], ["new", "plus"], ["obstacle", "obstacle"], ["barrier", "obstacle"], ["shortcuts", "keyboard"]]:
		if pair[0] in value: return pair[1]
	return "settings"

static func icon(id: String) -> Texture2D:
	var name := icon_name(id)
	if not textures.has(name): textures[name] = load("res://ui/icons/" + name + ".svg")
	return textures[name]

static func decorate(button: Button, label: String, description := "", icon_id := "", tile := false) -> void:
	button.set_meta("action_label", label)
	button.text = ""
	button.icon = icon(icon_id if icon_id != "" else label)
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
