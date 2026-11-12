extends VBoxContainer
## City mode → Map & data: start a map from real data, add sources to the open
## map, see what it is built from, then test drive and export. Every action uses
## the Editor's existing commands and import reviews.
const I18N := preload("./locale_text.gd")
const STYLE := preload("./workbench_style.gd")
const UNITS := preload("./import_units.gd")
var ui: Control
var summary: Label
var credits: Label

func build(owner_ui: Control) -> void:
	ui = owner_ui
	add_theme_constant_override("separation", 6)
	_heading("Create from real data")
	ui.commands.button(self, "create.real_city")
	ui.commands.button(self, "create.osm")
	_heading("Add data to this map")
	STYLE.button(self, "Import Copernicus DEM…", _terrain, "", "import")
	STYLE.button(self, "Import facility CSV…", _facilities, "", "import")
	ui.commands.button(self, "file.import_vector")
	_heading("This map")
	summary = ui._label(self, "")
	credits = ui._label(self, "")
	credits.add_theme_font_size_override("font_size", 12)
	ui.commands.button(self, "validate.test_drive")
	ui.commands.button(self, "file.export_map")
	ui.store.changed.connect(func(): if visible: refresh())

func _heading(text: String) -> void:
	var label: Label = ui._label(self, text)
	label.add_theme_color_override("font_color", STYLE.BLUE)

func _terrain() -> void:
	ui._ensure_import_ui()
	ui.dem_panel.open()

func _facilities() -> void:
	ui._ensure_import_ui()
	ui.import_source_format.select(6)
	ui.import_source_format.item_selected.emit(6)
	ui._import_geojson()

## What the open map is: real-data scale, contents and source credits.
func refresh() -> void:
	if ui == null: return
	var document: Dictionary = ui.store.document
	var scale: Dictionary = UNITS.osm_scale(document)
	var lines: Array[String] = []
	if int(scale.get("denominator", 0)) > 0: lines.append(I18N.t("Real-data map at 1:%d") % int(scale.denominator))
	else: lines.append(I18N.t("No real data yet: create a real-city map or import OSM."))
	lines.append(I18N.t("%d roads · %d buildings · %d terrain cells") % [document.get("roads", []).size(), document.get("buildings", []).size(), document.get("heightmaps", []).size()])
	if not document.get("play_area", []).is_empty(): lines.append(I18N.t("Play area boundary set"))
	summary.text = "\n".join(lines)
	var names: Array = []
	for attribution: Variant in document.get("attributions", []):
		if attribution is Dictionary and str(attribution.get("source", "")) != "" and str(attribution.source) not in names: names.append(str(attribution.source))
	credits.text = I18N.t("Sources: %s") % ", ".join(names) if not names.is_empty() else ""
	credits.visible = not names.is_empty()
