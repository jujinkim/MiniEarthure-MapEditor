extends RefCounted
## Presentation-only bounds. Never truncate or change the retained import value.
const MAX_SUMMARY_CHARS := 49152
const MAX_METADATA_CHARS := 8192
const MAX_VISITS := 128
const MAX_CHILDREN := 16
const MAX_TEXT_CHARS := 256

static func preview(value: Variant, limit: int = MAX_TEXT_CHARS) -> String:
	if value is Dictionary: return "Object · %d fields" % value.size()
	if value is Array:
		var scalar: bool = value.size() <= 4
		for index in range(mini(4, value.size())):
			if value[index] is Dictionary or value[index] is Array or value[index] is String: scalar = false
		return "Array · %d items" % value.size() + (" " + JSON.stringify(value) if scalar else "")
	if value is String:
		# Slice before escaping; never serialize an unbounded string or container.
		return JSON.stringify(value.substr(0, limit)) + (" … [%d characters; open details]" % value.length() if value.length() > limit else "")
	return JSON.stringify(value)

static func metadata(value: Dictionary) -> String:
	var state := {"text":"", "visits":0, "limited":false}
	_append(value, "", 0, state)
	return state.text + ("\nMore metadata is available in Browse exact details.\n" if state.limited else "")

static func _append(value: Variant, path: String, depth: int, state: Dictionary) -> void:
	if state.visits >= MAX_VISITS or state.text.length() >= MAX_METADATA_CHARS:
		state.limited = true
		return
	state.visits += 1
	if value is Dictionary and depth < 3:
		var count := 0
		for key: String in value:
			if count >= MAX_CHILDREN or state.visits >= MAX_VISITS or state.text.length() >= MAX_METADATA_CHARS:
				state.limited = true
				break
			count += 1
			# Raw supplemental/correction JSON is explored as exact paged text.
			if key == "json":
				state.limited = true
				continue
			_append(value[key], path + ("." if path != "" else "") + key.substr(0, 64), depth + 1, state)
	else:
		var line := path + ": " + preview(value) + "\n"
		if value is Dictionary or value is Array: state.limited = true
		var remaining: int = MAX_METADATA_CHARS - state.text.length()
		state.text += line.substr(0, remaining)
		if line.length() > remaining: state.limited = true
