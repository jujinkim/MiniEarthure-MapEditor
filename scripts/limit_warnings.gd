extends RefCounted
## Limits on the user's own data that warn instead of refusing work.
## One entry per code keeps the largest actual value and an occurrence count.
## Messages are English literals; they are translated only for display.
const I18N := preload("./locale_text.gd")
const MAX_ENTRIES := 64
const MAX_CODE := 64
const MAX_MESSAGE := 240
const RUNTIME_SUFFIX := "; the game refuses maps beyond this"
## MapKit Authoring generation cap for the user's own cells; above the game's
## 500,000 a generated cell warns `cell_triangles` instead of failing.
const AUTHORING_TRIANGLES := 2000000

static func note(list: Array, code: String, actual: int, limit: int, message: String, runtime_rejects := false) -> void:
	for entry: Variant in list:
		if entry is Dictionary and entry.get("code") == code:
			entry.count = int(entry.get("count", 1)) + 1
			if actual > int(entry.get("actual", 0)): entry.actual = actual
			entry.runtime_rejects = entry.get("runtime_rejects", false) == true or runtime_rejects
			return
	list.append({"code":code, "actual":actual, "limit":limit, "message":message, "runtime_rejects":runtime_rejects, "count":1})

## Note `actual` when it is above `limit`. Returns true when a warning was noted.
static func over(list: Array, code: String, actual: int, limit: int, message: String, runtime_rejects := false) -> bool:
	if actual <= limit: return false
	note(list, code, actual, limit, message, runtime_rejects)
	return true

static func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value)) and float(value) >= 0 and float(value) <= 9.0e15

static func valid_entry(entry: Variant) -> bool:
	if entry is not Dictionary or entry.get("code") is not String or entry.get("message") is not String: return false
	if entry.code.is_empty() or entry.code.length() > MAX_CODE or entry.message.strip_edges().is_empty() or entry.message.length() > MAX_MESSAGE: return false
	for c in entry.message + entry.code:
		if c.unicode_at(0) < 32: return false
	return _number(entry.get("actual")) and _number(entry.get("limit")) and entry.get("runtime_rejects", false) is bool and _number(entry.get("count", 1))

## Merge entries received from an owned child. Every valid entry is kept while
## `into` holds fewer than MAX_ENTRIES codes (repeated codes always merge).
## False when `from` is not an Array or holds an invalid entry; valid entries
## are still merged.
static func merge(into: Array, from: Variant) -> bool:
	if from == null: return true
	if from is not Array: return false
	var ok := true
	for entry: Variant in from:
		if not valid_entry(entry):
			ok = false
			continue
		if into.size() >= MAX_ENTRIES and not into.any(func(known): return known is Dictionary and known.get("code") == entry.code): continue
		note(into, entry.code, int(entry.actual), int(entry.limit), entry.message, entry.get("runtime_rejects", false))
	return ok

## Merge the top-level `warnings` of a MapKit Authoring response (JSON-parsed or
## packed Dictionary, ok or not): [{code, actual, limit, message, runtime_rejects}].
static func native(into: Array, response: Variant) -> bool:
	return merge(into, response.get("warnings")) if response is Dictionary else true

## Merge preformatted helper texts ("Limit warning: <message> (<actual> > <limit>)"
## plus the optional RUNTIME_SUFFIX, see importers/import_layer.py limit_text).
## Each text becomes one entry keyed by its message; malformed texts are skipped.
static func merge_texts(into: Array, texts: Variant) -> void:
	if texts is not Array: return
	var pattern := RegEx.create_from_string("^(?:Limit warning: )?(.+) \\((\\d{1,15}) > (\\d{1,15})\\)(; the game refuses maps beyond this)?$")
	for text: Variant in texts.slice(0, MAX_ENTRIES):
		if text is not String or text.length() > 512: continue
		var found := pattern.search(text)
		if found == null: continue
		var message := found.get_string(1).left(MAX_MESSAGE)
		var entry := {"code":"helper_" + message.md5_text().left(16), "actual":int(found.get_string(2)), "limit":int(found.get_string(3)), "message":message, "runtime_rejects":found.get_string(4) != ""}
		if not valid_entry(entry): continue
		merge(into, [entry])

## A bounded copy for a size-limited result file.
static func compact(list: Array, max_bytes: int = 2048) -> Array:
	var result: Array = []
	for entry: Variant in list:
		if result.size() >= MAX_ENTRIES: break
		if entry is not Dictionary: continue
		var copy := {"code":str(entry.get("code", "")).left(MAX_CODE), "actual":int(entry.get("actual", 0)), "limit":int(entry.get("limit", 0)), "message":str(entry.get("message", "")).left(MAX_MESSAGE), "runtime_rejects":entry.get("runtime_rejects", false) == true}
		if not valid_entry(copy): continue
		result.append(copy)
		if JSON.stringify(result).to_utf8_buffer().size() > max_bytes:
			result.pop_back()
			break
	return result

static func text(list: Array) -> String:
	if list.is_empty(): return ""
	var lines: Array[String] = [I18N.t("Limit warnings:")]
	for entry: Variant in list:
		if entry is not Dictionary: continue
		var line := "- %s (%d > %d)" % [I18N.t(str(entry.get("message", ""))), int(entry.get("actual", 0)), int(entry.get("limit", 0))]
		if entry.get("runtime_rejects", false) == true: line += I18N.t(RUNTIME_SUFFIX)
		lines.append(line)
	return "\n".join(lines)
