extends RefCounted
## A fresh font/cache for each UI owner; no process-wide glyph cache.
static func create() -> Font:
	var latin: Font = ThemeDB.fallback_font.duplicate(true)
	var region := "jp" if TranslationServer.get_locale().begins_with("ja") else "kr"
	# ResourceLoader honors exported font remaps; IGNORE keeps this owner's
	# FontFile/TextServer cache independent of other screens.
	var cjk: FontFile = ResourceLoader.load("res://fonts/NotoSansCJK%s-Regular.otf" % region, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
	cjk.allow_system_fallback = false
	cjk.set_cache_capacity(64, 16)
	if latin is FontFile: latin.allow_system_fallback = false
	latin.fallbacks = [cjk]
	latin.set_cache_capacity(64, 16)
	return latin
