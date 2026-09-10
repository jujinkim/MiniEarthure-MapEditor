extends ConfirmationDialog
const LAYER := preload("./dem_import_layer.gd")
var editor: Control
var fields := {}
var mosaic: CheckBox
var selection_revision := 0
var requested_revision := -1
var source: LineEdit
var summary: TextEdit
var review: ConfirmationDialog
var review_text: RichTextLabel
var picker: FileDialog
var requested := {}
var plan := {}
var destination := ""
var candidate: RefCounted

func _ready() -> void:
	title = "Local Copernicus DEM · 2021 source to local terrain cells"
	ok_button_text = "Copy reviewed local source and sample"
	get_ok_button().disabled = true
	var column := VBoxContainer.new()
	column.custom_minimum_size.x = 710
	add_child(column)
	var explanation := Label.new()
	explanation.text = "DSM includes buildings/vegetation. WGS84 → local UTM; EGM2008 heights.\nSingle cell or mosaic ≤ 4×4 cells; each ≤ 1024 m. Bilinear; no missing-data or seam repair."
	column.add_child(explanation)
	var grid := GridContainer.new()
	grid.columns = 4
	column.add_child(grid)
	for item in [["Cell columns",1,4,1,1],["Cell rows",1,4,1,1],["Longitude",-180,180,0,0.000001],["Latitude",-80,84,0,0.000001],["Local origin x (m)",-100000,100000,0,0.01],["Local origin y (m)",-100000,100000,0,0.01],["Cell x",0,100000,0,1],["Cell y",0,100000,0,1],["Spacing (cm)",200,102400,3200,1],["EGM2008 at local zero (m)",-10000,10000,0,0.01]]:
		fields[item[0]] = editor._import_number(grid,item[0],item[1],item[2],item[3],item[4])
		fields[item[0]].value_changed.connect(func(_value): invalidate())
	mosaic = CheckBox.new()
	mosaic.text = "Multi-source / multi-cell mosaic (local source is a folder of official tile filenames)"
	column.add_child(mosaic)
	mosaic.toggled.connect(_mosaic_changed)
	source = LineEdit.new()
	source.placeholder_text = "Local 2021 GLO-30 COG (.tif)"
	column.add_child(source)
	source.text_changed.connect(func(_value): invalidate())
	picker = FileDialog.new()
	picker.access = FileDialog.ACCESS_FILESYSTEM
	picker.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	picker.filters = PackedStringArray(["*.tif,*.tiff ; Copernicus GeoTIFF"])
	add_child(picker)
	picker.file_selected.connect(func(path): source.text = path; invalidate())
	picker.dir_selected.connect(func(path): source.text = path; invalidate())
	editor._button(column,"Choose local COG / mosaic folder…",func():
		picker.file_mode = FileDialog.FILE_MODE_OPEN_DIR if mosaic.button_pressed else FileDialog.FILE_MODE_OPEN_FILE
		picker.popup_centered(Vector2i(800,550)))
	editor._button(column,"Review area, source size and license / retry",prepare)
	summary = TextEdit.new()
	summary.editable = false
	summary.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	summary.custom_minimum_size = Vector2(710,145)
	column.add_child(summary)
	confirmed.connect(acquire)
	canceled.connect(invalidate)
	review = ConfirmationDialog.new()
	review.title = "Review DEM layer · explicit terrain activation"
	review.ok_button_text = "Adopt all reviewed terrain"
	review.cancel_button_text = "Discard"
	review_text = RichTextLabel.new()
	review_text.custom_minimum_size = Vector2(700,440)
	review.add_child(review_text)
	add_child(review)
	review.confirmed.connect(adopt)
	review.canceled.connect(discard)
	_mosaic_changed(false)
	editor.store.changed.connect(_document_changed)

func _mosaic_changed(enabled: bool) -> void:
	fields["Cell columns"].editable=enabled
	fields["Cell rows"].editable=enabled
	source.placeholder_text="Local folder containing official 2021 GLO-30 tile filenames" if enabled else "Local 2021 GLO-30 COG (.tif)"
	invalidate()

func _mosaic_summary() -> String:
	var bytes := 0
	for item: Dictionary in plan.sources: bytes+=int(item.source.bytes)
	var text := "Review %d cells from %d sources · %d bytes total\nLocal start cell: %s · columns/rows: %s · spacing: %s cm\nWGS84 bounds (west, south, east, north): %s\nEGM2008 heights minus %s m at local zero. DSM includes buildings and vegetation.\nBilinear sampling; source accuracy unknown; output spacing is not accuracy.\nIncludes conservative east/south interpolation support; no missing-data repair.\n" % [plan.cells.size(),plan.sources.size(),bytes,str(requested.cell),str(requested.cell_count),str(requested.spacing_cm),str(plan.bbox),str(requested.vertical_zero_m)]
	for item: Dictionary in plan.sources:
		text+="\nTile %s · GLO-%d%s · %d bytes\n%s\n%s\n%s\n" % [str(item.tile),item.resolution_m,"",item.source.bytes,item.source.path,"SHA-256: "+str(item.source.sha256),item.notice]
	return text+"\nLicense: "+LAYER.LICENSE+"\nCompleted sources survive cancel/failure. Review expires after 10 minutes."

func options() -> Dictionary:
	var result := {"coordinates":{"mode":"wgs84-utm","origin":[fields.Longitude.value,fields.Latitude.value],"local_origin_m":[fields["Local origin x (m)"].value,fields["Local origin y (m)"].value]},"cell":[fields["Cell x"].value,fields["Cell y"].value],"cell_size_cm":editor.store.document.cell_size_cm,"map_min_cm":editor.store.document.bounds.min.duplicate(),"spacing_cm":fields["Spacing (cm)"].value,"vertical_zero_m":fields["EGM2008 at local zero (m)"].value,"source":source.text.strip_edges()}

	if mosaic.button_pressed: result["cell_count"] = [fields["Cell columns"].value,fields["Cell rows"].value]
	return result

func open() -> void:
	if editor.busy: return
	editor.import_dialog.hide()
	popup_centered(Vector2i(780,600))

func _document_changed() -> void:
	plan.clear()
	get_ok_button().disabled = true
	if editor.dem_mode.begins_with("dem") and editor.import_job != null: editor.import_job.cancel()

func invalidate() -> void:
	selection_revision += 1
	_document_changed()
	discard()

func discard() -> void:
	if candidate != null: candidate.discard()
	candidate = null
	if review != null: review.hide()

func prepare() -> void:
	if editor.busy: return
	invalidate()
	if editor.store.project_path == "" or editor.store.has_gesture():
		editor._status("Save the project and finish gestures before DEM import.")
		return
	requested = options().duplicate(true)
	requested_revision = selection_revision
	editor._begin_dem({"mode":"dem-plan","options":requested})
	summary.text = "Checking projected cells and local source hashes. The source is copied only after review."

func acquire() -> void:
	if editor.busy or plan.is_empty() or requested != options() or requested_revision != selection_revision: return
	var folder := ProjectSettings.globalize_path("user://import-sources")
	if DirAccess.make_dir_recursive_absolute(folder) != OK:
		editor._status("Cannot create DEM capture folder.")
		return
	destination = folder.path_join(Crypto.new().generate_random_bytes(16).hex_encode()+".tif")
	editor._begin_dem({"mode":"dem","plan":plan.duplicate(true),"destination":destination})
	get_ok_button().disabled = true

func finish(mode: String, result: Dictionary) -> void:
	if not result.ok:
		summary.text = str(result.error.message)
		editor._status("E_DEM: " + summary.text)
		return
	if editor.generation != editor.worker_generation or requested != options() or requested_revision != selection_revision:
		editor._status("DEM request changed; completed source retained without adoption.")
		return
	if result.get("data") is not Dictionary:
		editor._status("Invalid DEM result.")
		return
	if mode == "dem-plan":
		if JSON.stringify(result.data.get("options")) != JSON.stringify(requested) or result.data.get("adapter") != ("copernicus-dem-v2" if requested.has("cell_count") else "copernicus-dem-v1") or result.data.get("license") != LAYER.LICENSE:
			editor._status("DEM review does not match requested source.")
			return
		plan = result.data
		summary.text = "Review before local copying: source accuracy unknown locally; output spacing is not source accuracy.\nBilinear samples become local height = EGM2008 height − chosen local-zero height.\n" + JSON.stringify(plan,"  ")
		if requested.has("cell_count"): summary.text = _mosaic_summary()
		get_ok_button().disabled = false
		return
	discard()
	candidate = LAYER.new()
	var failure: String = candidate.stage_dem(editor.canvas.author.terrain,result.data,plan,destination)
	if failure != "":
		discard()
		editor._status("E_DEM: " + failure + " Complete source retained: " + destination)
		return
	review_text.text = candidate.summary()
	review.popup_centered(Vector2i(760,520))

func adopt() -> void:
	if candidate == null: return
	var failure: String = candidate.adopt(editor.canvas.author.terrain)
	editor._status("DEM layer adopted; save explicitly." if failure == "" else failure)
	discard()

func _exit_tree() -> void:
	discard()
