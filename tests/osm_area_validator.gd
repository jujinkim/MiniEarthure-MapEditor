extends SceneTree
const FIXTURE := preload("res://tests/download_validator.gd")
const LAYER := preload("res://scripts/import_layer.gd")
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_job(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+15000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"owned job terminates: "+ui.status_label.text)
func run() -> void:
	var ui := FIXTURE.FixtureUI.new()
	root.add_child(ui)
	await process_frame
	root.size = Vector2i(1024,720)
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	var before: Dictionary = ui.store.document.duplicate(true)
	ui._open_download()
	ui._begin_acquisition({"mode":"catalog"})
	await wait_job(ui)
	check(ui.osm_panel.regions.size()==1,"official catalog shape through owned worker")
	ui.osm_panel.search.text="missing"
	ui.osm_panel.search.text_changed.emit("missing")
	check(ui.osm_panel.choices.item_count==0,"region search filters")
	ui.osm_panel.search.text="monaco"
	ui.osm_panel.search.text_changed.emit("monaco")
	check(ui.osm_panel.choices.item_count==1,"region name search")
	ui.osm_panel.choices.item_selected.emit(0)
	check(ui.download_url.text.ends_with("monaco-latest.osm.pbf"),"explicit selection sets public URL")
	ui._begin_acquisition({"mode":"probe","url":ui.download_url.text})
	ui.download_url.text_changed.emit(ui.download_url.text)
	await wait_job(ui)
	check(ui.download_plan.is_empty(),"changed then restored region rejects late probe")
	ui._begin_acquisition({"mode":"probe","url":ui.download_url.text})
	await wait_job(ui)
	check(not ui.download_plan.is_empty(),"fresh source review")
	ui.download_dialog.hide()
	ui.download_dialog.confirmed.emit()
	await wait_job(ui)
	var source: String = ui.last_import_source
	check(FileAccess.file_exists(source),"source retained")
	if source=="": quit(1); return
	var original := FileAccess.get_sha256(source)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_origin_x.value=512
	ui.import_origin_y.value=512
	ui.osm_panel.open()
	ui.osm_panel.enabled.button_pressed=true
	check(ui.osm_panel.error()!="","empty crop rejected")
	var b := [9.0001,54.9999,9.0008,55.0001]
	for i in range(4): ui.osm_panel.fields[i].value=b[i]
	ui.osm_panel.area.toggle_fit()
	check(ui.osm_panel.error()=="","bounded numeric selection")
	if DisplayServer.get_name()!="headless":
		await process_frame
		check(ui.osm_panel.dialog.size.x<=1024 and ui.osm_panel.dialog.size.y<=720,"crop form fits minimum window")
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture!="":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture+".crop.png")==OK,"crop screenshot")
	ui.osm_panel.dialog.hide()
	ui.osm_panel.dialog.confirmed.emit()
	check(ui.import_dialog.visible and ui.osm_crop_button.text.contains("on"),"return to import with crop status")
	ui.import_dialog.hide()
	ui._start_import(source,LAYER.OSM_LICENSE)
	ui.osm_panel.fields[0].value+=0.000001
	ui.osm_panel.fields[0].value-=0.000001
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==before,"changed-restored crop rejects late candidate without mutation")
	ui._start_import(source,LAYER.OSM_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null,"crop native review: "+ui.status_label.text)
	if ui.pending_import==null: ui.queue_free(); await process_frame; quit(1); return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(raw.coordinates.osm_crop.counts.changed_features==2,"crossing building and road both clipped")
	check(raw.coordinates.osm_crop.counts.outside_features==1,"outside forest counted")
	check(ui.import_summary.text.contains("geometry-intersection"),"crop provenance visible")
	var bad: Dictionary=raw.duplicate(true)
	bad.coordinates.osm_crop.bbox[0]+=0.000001
	check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request)!="","crop identity mismatch rejected")
	bad=raw.duplicate(true)
	bad.coordinates.erase("osm_crop")
	check(LAYER.new().load_value(bad,ui.import_identity,ui.import_coordinates_request)!="","missing crop metadata rejected")
	ui._adopt_import()
	check(ui.store.document.buildings.size()==1 and ui.store.document.roads.size()==1,"atomic clipped layer adoption")
	check(ui.store.undo()=="","crop Undo")
	var undone: Dictionary=ui.store.document.duplicate(true)
	undone.provenance.last_edited=before.provenance.last_edited
	check(undone==before,"Undo restores map")
	check(ui.store.redo()=="","crop Redo")
	var adopted: Dictionary=ui.store.document.duplicate(true)
	ui._start_import(source,LAYER.OSM_LICENSE)
	ui._cancel_operation()
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==adopted,"cancel crop retains existing layer")
	check(FileAccess.get_sha256(source)==original,"original source unchanged")
	# Multipart/hole source passes crop and the actual native geometry validator.
	var multi := ProjectSettings.globalize_path("user://multipolygon.pbf")
	var fixture_output: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_fixture.py"),multi,"12","multipolygon"]),fixture_output,true)==0,"multipart fixture")
	b=[9.0031,55.0011,9.0049,55.0029]
	for i in range(4): ui.osm_panel.fields[i].value=b[i]
	ui._start_import(multi,LAYER.OSM_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null,"clipped holes and islands native review: "+ui.status_label.text)
	if ui.pending_import!=null:
		var zones: Array=[]
		for patch: Dictionary in ui.pending_import.value.patches:
			if patch.field=="zones": zones.append(patch.after)
		check(zones.size()==2,"clipped forest keeps outer and island")
		check(zones.any(func(z): return z.exclusions.size()==1),"clipped forest retains courtyard exclusion")
		ui._adopt_import()
		check(ui.store.undo()=="","multipart crop one-command Undo")
	ui.osm_panel.enabled.button_pressed=false
	check(ui.osm_panel.error()=="","whole-snapshot mode remains available")
	ui.queue_free()
	await process_frame
	print("osm_area_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
