extends RefCounted
## Known model/worker messages are decoded only for display. Captured arguments
## (paths, identifiers and external diagnostics) remain verbatim.
const TEMPLATES := [
  "Import source exceeds %s or is empty; PBF streaming needs an explicit crop area.",
  "Cannot create import scratch root: ",
  "Cannot reserve a new import job directory: ",
  "Could not stop importer: ",
  "Importer exited without a valid result (exit %d). %s",
  "Unsupported command field: ",
  "History payload changed or is missing: ",
  "Add at least %d points; right-click finishes.",
  "Select an editable ",
  "Cannot read document: ",
  "Save failed; current and pending files were preserved: ",
  "Cannot establish local import presence: ",
  "Cannot publish import ownership record: ",
  "Unsafe project payload path: ",
  "Referenced file is missing: ",
  "Source changed during snapshot: ",
  "History payload changed: ",
  "Save As refuses a destination symlink: ",
  "Save As payload conflict: ",
  "Copied payload changed before document publication: ",
  "Cannot publish copied payload; pending file retained: ",
  "Adopt import ",
  "E_EXPORT_IO: Pending copy retained: ",
  "Cannot read source file: ",
  "Immutable payload conflict: ",
  "Cannot load the MapKit extension (status %d): %s",
  "The loaded MapKit extension is missing the required method: ",
  "Missing sign ",
  "Use a hex color for ",
  "Font lacks sign characters: ",
  "Unsupported shaped cluster at character ",
  "DEM input is missing: ",
  "Cell estimate %d exceeds the %d-byte preview work allowance.",
  "Import timed out after %d seconds; use a smaller source or retry.",
  "Generating cell %d / %d",
  "Optional 3D check %d / %d",
  "Native validation diagnostics: ",
  "Invalid native validation event: ",
  "%s: start and finish route required",
  "%s: repeated route instance",
  "%s → %s: ports do not meet in position, direction or width",
  "%s: missing connection",
  "%s: circuit is open",
  "%s: alternative must share start and finish",
  "%s: booster chain needs ten metres of road",
  "%s: landing needs six metres of supported runway",
  "%s: landing height, space or reach invalid",
  "%s: flight requires an automatic or manual approach and declared supported landing",
  "%s / %s: road clearance collision",
  "%s: ribbon self intersection or insufficient clearance",
  "%s: obstacle no longer has safe clearance"
]

static func translate(message: String) -> String:
	var direct := String(TranslationServer.translate(message))
	if direct != message: return direct
	var token := RegEx.new()
	token.compile("%[-+0-9.]*[sdifxXoc]")
	for source: String in TEMPLATES:
		if not message.begins_with(source.get_slice("%", 0)): continue
		var slots := token.search_all(source)
		if slots.is_empty(): return String(TranslationServer.translate(source)) + message.substr(source.length())
		var expression := "^"
		var cursor := 0
		for slot: RegExMatch in slots:
			expression += _escape(source.substr(cursor, slot.get_start() - cursor))
			expression += "(.*?)" if slot.get_string().ends_with("s") else "([-+0-9.]+)"
			cursor = slot.get_end()
		expression += _escape(source.substr(cursor)) + "$"
		var matcher := RegEx.new()
		matcher.compile(expression)
		var found := matcher.search(message)
		if found == null: continue
		var translated := String(TranslationServer.translate(source))
		var output := ""
		cursor = 0
		var index := 1
		for slot: RegExMatch in token.search_all(translated):
			output += translated.substr(cursor, slot.get_start() - cursor) + found.get_string(index)
			cursor = slot.get_end()
			index += 1
		return output + translated.substr(cursor)
	return message

static func _escape(value: String) -> String:
	var output := ""
	for character in value:
		if character in "\\.^$|?*+()[]{}": output += "\\"
		output += character
	return output
