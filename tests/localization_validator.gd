extends SceneTree
const LOCALE := preload("res://scripts/localization.gd")
const I18N := preload("res://scripts/locale_text.gd")
const FONT := preload("res://scripts/ui_font.gd")
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok: failures.append(message); push_error(message)
func restart_locale() -> Node:
	var old := root.get_node("Locale")
	root.remove_child(old)
	old.free()
	var next := LOCALE.new()
	next.name = "Locale"
	root.add_child(next)
	return next
func run() -> void:
	var locale := root.get_node("Locale")
	check(locale.active_locale == "en", "English first launch independent of OS")
	check(locale.set_language("ko") and locale.active_locale == "en" and TranslationServer.get_locale() == "en", "save only; running locale unchanged")
	locale = restart_locale()
	check(locale.active_locale == "ko" and I18N.t("File") == "파일", "saved locale applied at next startup")
	var good_path: String = locale.preferences_path
	locale.preferences_path = "user://absent/language.cfg"
	check(not locale.set_language("ja") and locale.selected_locale == "ko", "save failure preserves prior choice")
	locale.preferences_path = good_path
	check(not locale.set_language("missing"), "unavailable selection rejected")
	var config := ConfigFile.new()
	check(config.load(good_path) == OK and config.get_value("ui", "language") == "ko", "failed save preserves prior file")
	var ids := PackedStringArray()
	var defaults := ""
	var keys: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://translations/en.json")).messages
	var missing: Array[String] = []
	for code in ["en", "ko", "ja"]:
		check(locale.set_language(code), "save " + code)
		locale = restart_locale()
		var ui: Control = load("res://main.tscn").instantiate()
		root.add_child(ui)
		await process_frame
		check(I18N.display("File: missing connection") == I18N.t("%s: missing connection") % "File", "native issue retains authored ID")
		var serialized := JSON.stringify(ui.store.document)
		check(I18N.display("Add at least 4 points; right-click finishes.") == I18N.t("Add at least %d points; right-click finishes.") % 4, "known diagnostic arguments " + code)
		check(I18N.display("Cannot read document: File") == I18N.t("Cannot read document: ") + "File", "diagnostic filename matching key preserved")
		check(I18N.display("Generating cell 3 / -2") == I18N.t("Generating cell %d / %d") % [3, -2], "dynamic worker progress " + code)
		check(I18N.filters(["*.memap ; Map package"])[0] == "*.memap ;" + I18N.t("Map package"), "filter description only translated")
		var original_locale := TranslationServer.get_locale()
		check(locale.set_language("ja" if code != "ja" else "en"), "save with document open")
		check(JSON.stringify(ui.store.document) == serialized and TranslationServer.get_locale() == original_locale, "document bytes/hash and active UI unchanged by selection")
		check(I18N.error({"code":"E_UNKNOWN","message":"external diagnostic 123"}).contains("external diagnostic 123"), "unknown diagnostic preserved")
		var current := PackedStringArray()
		for command: Dictionary in ui.commands.commands:
			current.append(command.id)
			for value: String in [command.group, command.label, command.description, command.reason]:
				if str(command.id).begins_with("favorite.") and value.begins_with("Favorite "): continue
				for part: String in value.split("\n"):
					if not part.is_empty() and not keys.has(value) and not keys.has(part) and not missing.has(part): missing.append(part)
		if ids.is_empty(): ids = current; defaults = JSON.stringify(ui.commands.DEFAULT_FAVORITES)
		check(ids == current and defaults == JSON.stringify(ui.commands.DEFAULT_FAVORITES), "command IDs/favorites do not depend on locale")
		ui.commands._filter(I18N.t("Frame selection"))
		check(ui.commands.results.item_count > 0, "localized command search " + code)
		ui.commands._filter("view.frame")
		check(ui.commands.results.item_count > 0, "stable ID search " + code)
		ui.commands._filter("Frame selection")
		check(ui.commands.results.item_count > 0, "original command search " + code)
		var option: OptionButton = ui.author_panel.choice(ui, "Structure", ["ground", "bridge"], "bridge")
		check(option.get_item_metadata(option.selected) == "bridge", "translated choices preserve document value")
		var authored: LineEdit = ui.author_panel.text(ui, "Name", "File")
		check(authored.text == "File", "authored name matching a translation key preserved")
		var font := FONT.create()
		check(font.fallbacks.size() == 1 and not font.fallbacks[0].allow_system_fallback, "bundled fallback without system fonts")
		var messages: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://translations/%s.json" % code)).messages
		for glyph in "▶▼": check(font.has_char(glyph.unicode_at(0)), "section marker glyph")
		var glyphs := {}
		for value: String in messages.values():
			for glyph in value:
				var cp := glyph.unicode_at(0)
				if cp >= 128: glyphs[cp] = true
		for cp: int in glyphs: check(font.has_char(cp), "bundled glyph U+%04X" % cp)
		ui.store.dirty = false
		ui.queue_free()
		for i in 5: await process_frame
	if not missing.is_empty(): print("MISSING_COMMAND_KEYS=" + JSON.stringify(missing))
	check(missing.is_empty(), "command display catalog coverage")
	var file := FileAccess.open(good_path, FileAccess.WRITE)
	file.store_string("broken config [")
	file = null
	locale = restart_locale()
	check(locale.active_locale == "en", "corrupt preference falls back to English")
	config.set_value("ui", "language", "missing")
	config.save(good_path)
	locale = restart_locale()
	check(locale.active_locale == "en", "unavailable locale falls back to English")
	print("localization_validator: " + ("PASS" if failures.is_empty() else "FAIL") + " " + JSON.stringify(failures))
	quit(0 if failures.is_empty() else 1)
