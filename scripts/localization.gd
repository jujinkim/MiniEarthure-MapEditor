extends Node
## App-owned UI preferences. Document, worker and command identities stay unchanged.
const PREFERENCES := "user://ui_language.cfg"
const LANGUAGES := {"en":"English", "ko":"한국어", "ja":"日本語"}
var preferences_path := PREFERENCES
var selected_locale := "en"
var active_locale := "en"
var _translations: Array[Translation] = []
var _available := {"en":true}

func _enter_tree() -> void:
	TranslationServer.set_locale("en")

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if not args.is_empty() and args[0] == "--native-import-validation": return
	for code: String in LANGUAGES:
		var pack: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://translations/%s.json" % code))
		if pack is not Dictionary or pack.get("schema") != 1 or pack.get("locale") != code or pack.get("messages") is not Dictionary: continue
		var translation := Translation.new()
		translation.locale = code
		for key: String in pack.messages: translation.add_message(key, pack.messages[key])
		TranslationServer.add_translation(translation)
		_translations.append(translation)
		_available[code] = true
	var config := ConfigFile.new()
	if config.load(preferences_path) == OK:
		var saved: Variant = config.get_value("ui", "language", "en")
		if saved is String and _available.has(saved): selected_locale = saved
	active_locale = selected_locale
	TranslationServer.set_locale(active_locale)

func set_language(code: String) -> bool:
	if not _available.has(code): return false
	var config := ConfigFile.new()
	config.set_value("ui", "language", code)
	var temporary := preferences_path + ".tmp"
	if config.save(temporary) != OK: return false
	if DirAccess.rename_absolute(temporary, preferences_path) != OK: return false
	selected_locale = code
	return true

func _exit_tree() -> void:
	for translation: Translation in _translations: TranslationServer.remove_translation(translation)
	_translations.clear()
