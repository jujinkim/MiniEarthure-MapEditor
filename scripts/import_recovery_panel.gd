extends AcceptDialog
## Read-only report remains separate from document recovery and import adoption.
const SCAN := preload("./import_recovery.gd")
var scan := SCAN.new()
var report: TextEdit
var refresh: Button
var banner: Button
var reported := false

func _ready() -> void:
	title = "Local import work"
	size = Vector2i(800, 500)
	min_size = Vector2i(620, 380)
	get_ok_button().text = "Close"
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(700, 400)
	add_child(column)
	var guidance := Label.new()
	guidance.text = "Work left after an interruption may be listed here. Files are preserved.\nTo retry, close the earlier Editor and start a new import from your original source."
	column.add_child(guidance)
	var folder := LineEdit.new()
	folder.editable = false
	folder.text = ProjectSettings.globalize_path("user://import-jobs")
	folder.tooltip_text = "Local work folder (select and copy this path for manual inspection)."
	column.add_child(folder)
	report = TextEdit.new()
	report.editable = false
	report.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	report.custom_minimum_size = Vector2(580, 250)
	report.scroll_fit_content_height = false
	report.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(report)
	refresh = Button.new()
	refresh.text = "Scan again"
	refresh.pressed.connect(restart)
	column.add_child(refresh)
	restart()

func restart() -> void:
	reported = false
	scan.start()
	refresh.disabled = not scan.done
	report.text = "Checking local import work…"
	if banner != null: banner.text = "Import work · checking…"

func show_report() -> void:
	restart()
	popup_centered(Vector2i(800, 500))

func _process(_delta: float) -> void:
	scan.poll()
	if not scan.done or reported: return
	reported = true
	refresh.disabled = false
	var active := 0
	var uncertain := 0
	var lines := PackedStringArray()
	if scan.message != "": lines.append(scan.message)
	for row in scan.rows:
		var description := "Unrecognized or incomplete record — ownership unknown."
		if row.state == "active":
			active += 1
			description = "Editor responded — leave this work with that Editor."
		elif row.state == "unconfirmed":
			description = "Editor did not confirm — possibly interrupted or temporarily unavailable."
		if row.state != "active": uncertain += 1
		lines.append("%s  [%s]\n%s" % [row.name, row.kind, description])
	if lines.is_empty(): lines.append("No leftover local import work was found in this scan.")
	if scan.partial: lines.append("Partial scan: the entry/time limit was reached. Unlisted work may remain. Scan again after other imports finish; inspect the local import-jobs folder manually if needed.")
	lines.append("This is a snapshot. An unresponsive Editor or worker may still be running. Nothing here is deleted, resumed or added to your map. Unknown entries and original files must be kept.")
	report.text = "\n\n".join(lines)
	if banner != null:
		banner.text = "Import work · %d to review" % uncertain if uncertain > 0 else "Import work · %d responding" % active if active > 0 else "Import work · clear"
		if scan.partial: banner.text += " · partial"
		banner.tooltip_text = "%d Editors responded; %d entries need review. Open the read-only report for details." % [active, uncertain]
		if scan.message != "": banner.text = "Import work · unable to inspect"

func _exit_tree() -> void:
	scan.cancel()
