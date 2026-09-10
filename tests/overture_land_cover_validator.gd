extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
class FixtureJob extends "res://scripts/download_job.gd":
	func _spawn(python: String, arguments: PackedStringArray) -> Dictionary:
		arguments.insert(2, ProjectSettings.globalize_path("res://tests/overture_land_cover_fixture.py"))
		return OS.execute_with_pipe(python, arguments, false)
class FixtureUI extends "res://scripts/editor_main.gd":
	func _new_download_job() -> RefCounted: return FixtureJob.new()
var failures: Array[String] = []
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func _initialize() -> void: run.call_deferred()
func wait_job(ui: Control) -> void:
	var deadline := Time.get_ticks_msec() + 15000
	while ui.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not ui.busy, "Overture worker terminates: " + ui.status_label.text)
func run() -> void:
	var ui := FixtureUI.new()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.overture_release.text = "2026-08-19.0"
	ui.overture_theme.select(2)
	ui.overture_theme.item_selected.emit(2)
	ui.overture_ground.value = 0.2
	var bounds := [9,55,9.001,55.001]
	for i in range(4): ui.overture_bbox[i].value=bounds[i]
	ui._open_overture()
	if DisplayServer.get_name() != "headless":
		root.size=Vector2i(1024,720)
		ui.overture_dialog.popup_centered(Vector2i(760,560))
		await process_frame
		check(ui.overture_dialog.size.x <= 1024 and ui.overture_dialog.size.y <= 720, "area wizard fits minimum window")
		check(ui.overture_scroll.get_v_scroll_bar().max_value > ui.overture_scroll.size.y, "long source guidance remains scrollable")
		check(ui.overture_dialog.get_ok_button().get_global_rect().end.y <= 720,"review action remains inside window")
		var capture := OS.get_environment("MAPEDITOR_CAPTURE_PATH")
		if capture != "":
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(capture)==OK,"area screenshot")
	ui.overture_dialog.hide()
	check(ui.store.apply_command("Choose vegetation recipe",[{"field":"recipe_version","before":1,"after":3}])=="","explicit recipe 3 for native vegetation generation")
	var before: Dictionary=ui.store.document.duplicate(true)
	ui.overture_dialog.confirmed.emit()
	await process_frame
	check(ui.overture_review.size.x<=1024 and ui.overture_review.size.y<=720,"confirmation fits minimum window with attribution guidance")
	ui.overture_review.hide()
	ui.overture_review.confirmed.emit()
	await wait_job(ui)
	var source: String=ui.last_import_source
	check(FileAccess.file_exists(source), "Overture snapshot retained: " + ui.status_label.text)
	check(ui.store.document==before and ui.pending_import==null,"download does not mutate document")
	check(ui.import_source_format.selected==5 and ui.import_license.text==LAYER.OVERTURE_LAND_COVER_LICENSE,"explicit geoforest zonesic source/attribution")
	if not FileAccess.file_exists(source): quit(1); return
	var original:=FileAccess.get_sha256(source)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_dialog.hide()
	ui._start_import(source,LAYER.OVERTURE_LAND_COVER_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null,"Overture native review: "+ui.status_label.text)
	if ui.pending_import==null: quit(1); return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(ui.store.document==before,"review leaves document unchanged")
	check(raw.adapter=="overture-land-cover-v1" and raw.source.sha256==original,"snapshot identity preserved")
	check(ui.import_summary.text.contains("2026-08-19.0") and ui.import_summary.text.contains("synthetic fixture") and ui.import_summary.text.contains("WorldCover"),"release/source/estimate review")
	check(raw.patches.size()==3 and raw.patches[0].after.exclusions.size()==1,"forest parts and hole preserved")
	check(raw.coordinates.overture_land_cover.feature_sources[1].disposition=="other-subtype" and raw.coordinates.overture_land_cover.feature_sources[2].disposition=="lower-detail","excluded classes and duplicate detail explicitly reviewed")
	check(ui.overture_parts.disabled and not ui.overture_ground.editable,"building-only controls disabled for land cover")
	check(ui.overture_notice.text.contains("750") and ui.overture_notice.text.contains("CC-BY-4.0"),"source review retains estimated density and WorldCover notice")
	for field in ["license","adapter","profile","bbox","release","sources","missing","kind","spacing","density","unmapped","subtype","zoom","disposition","excluded","point_budget","estimates","holes","count"]:
		var bad:=raw.duplicate(true)
		var meta:Dictionary=bad.coordinates.overture_land_cover
		if field=="license":bad.source.license="MIT"
		elif field=="adapter":bad.adapter="geojson-v2"
		elif field=="profile":meta.profile="all-trees"
		elif field=="bbox":meta.bbox=[9,55,10,56]
		elif field=="release":meta.release="latest"
		elif field=="sources":meta.feature_sources[0].sources=[]
		elif field=="missing":meta.feature_sources[0].zone_ids.pop_back()
		elif field=="kind":bad.patches[0].after.kind="orchard"
		elif field=="spacing":bad.patches[0].after.spacing_cm=200
		elif field=="density":bad.patches[0].after.density_per_mille=1000
		elif field=="unmapped":meta.feature_sources[0].zone_ids[0]+="-forged"
		elif field=="subtype":meta.feature_sources[0].subtype="mangrove"
		elif field=="zoom":meta.feature_sources[0].min_zoom=7
		elif field=="disposition":meta.feature_sources[1].disposition="forest"
		elif field=="excluded":meta.feature_sources[1].zone_ids=[bad.patches[0].id]
		elif field=="point_budget":meta.source_point_count=8193
		elif field=="holes":bad.patches[0].after.exclusions=[]
		elif field=="estimates":bad.estimates.vegetation_spacing_density=0
		else:meta.source_feature_count=1
		check(LAYER.new().load_value(bad,raw.layer_id,ui.import_coordinates_request)!="","forged "+field+" rejected")
	var legacy:=STORE.new()
	legacy.document=before.duplicate(true)
	legacy.document.recipe_version=1
	check(ui.pending_import.validate_for(legacy).contains("recipe 3"),"legacy recipe requires explicit vegetation version")
	var forged:=raw.duplicate(true)
	forged.patches[0].after.polygon.resize(2)
	var invalid_layer:=LAYER.new()
	check(invalid_layer.load_value(forged,raw.layer_id)=="","geometry proceeds to native admission")
	check(invalid_layer.validate_for(ui.store)!="" and ui.store.document==before,"native rejects malformed polygon atomically")
	ui._discard_import()
	check(ui.store.document==before,"discard preserves map")
	ui._start_import(source,LAYER.OVERTURE_LAND_COVER_LICENSE)
	await wait_job(ui)
	ui._adopt_import()
	check(ui.store.document.zones.size()==3,"native atomic forest adoption")
	ui._adopt_import()
	check(ui.store.document.zones.size()==3,"one-shot candidate")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.zones.is_empty(),"one-command undo removes complete forest zones")
	check(ui.store.redo()=="" and ui.store.document==adopted,"redo restores complete forest zones/provenance")
	var project:=ProjectSettings.globalize_path("user://overture-land-cover-project")
	check(ui.store.save_project(project)=="","save provenance")
	check(ui.store.autosave()=="","recovery snapshot")
	var reopened:=STORE.new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==ui.store.document.attributions,"source notices roundtrip")
	check(reopened.recover(ui.store.recovery_path())=="","recover source layer")
	var pack:=ProjectSettings.globalize_path("user://overture-land-cover.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,pack)).ok,"package imported forest")
	var pack_hash:=FileAccess.get_sha256(pack)
	check(JSON.parse_string(ui.store.bridge.open_package(pack)).ok,"open package")
	var generated:Dictionary=JSON.parse_string(ui.store.bridge.generate_chunk(1,1))
	check(generated.ok,"same MapKit geometry generation")
	check(not generated.data.chunk.objects.is_empty(),"native forest generates trees")
	var hole: Array=ui.store.document.zones[0].exclusions[0]
	var island: Array=ui.store.document.zones[1].polygon
	for prop:Dictionary in generated.data.chunk.objects:
		check(prop.asset_id=="builtin:tree","forest emits tree asset")
		var pos:Array=prop.position
		var inside_hole:bool=pos[0]>hole[0][0] and pos[0]<hole[2][0] and pos[2]>hole[0][1] and pos[2]<hole[2][1]
		var inside_island:bool=pos[0]>=island[0][0] and pos[0]<=island[2][0] and pos[2]>=island[0][1] and pos[2]<=island[2][1]
		check(not inside_hole or inside_island,"generated tree respects hole except explicit island")
	ui.preview_x.value=1
	ui.preview_y.value=1
	ui._preview()
	await wait_job(ui)
	check(ui.preview_cache.has(Vector2i(1,1)),"shared forest rendering attached")
	var accepted:Node=ui.preview_cache[Vector2i(1,1)].root
	ui._preview()
	ui._cancel_operation()
	await wait_job(ui)
	check(ui.preview_cache[Vector2i(1,1)].root==accepted,"cancel retains accepted forest preview")
	var update:=ProjectSettings.globalize_path("user://updated-transportation.overture-land-cover.json")
	var snapshot:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source))
	for feature in snapshot.features:
		if feature.id == "a-forest": feature.properties.version=2
	var f:=FileAccess.open(update,FileAccess.WRITE)
	f.store_string(JSON.stringify(snapshot));f.close()
	ui._start_import(update,LAYER.OVERTURE_LAND_COVER_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null and ui.pending_import.value.layer_id!=raw.layer_id,"source update is fresh forest zones layer: " + ui.status_label.text)
	ui._adopt_import()
	check(ui.store.document.zones.size()==6,"update retains old forest zones")
	check(ui.store.undo()=="" and ui.store.document.zones.size()==3,"undo updated layer")
	check(ui.store.redo()=="" and ui.store.document.zones.size()==6,"redo updated layer")
	check(FileAccess.get_sha256(source)==original and FileAccess.get_sha256(pack)==pack_hash,"source/package preserved")
	var bad_path:=ProjectSettings.globalize_path("user://unknown-class.overture-land-cover.json")
	var bad_source:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source))
	bad_source.features[-1].properties.subtype="unknown-class"
	var bad_file:=FileAccess.open(bad_path,FileAccess.WRITE)
	bad_file.store_string(JSON.stringify(bad_source));bad_file.close()
	var retained:Dictionary=ui.store.document.duplicate(true)
	ui._start_import(bad_path,LAYER.OVERTURE_LAND_COVER_LICENSE)
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==retained,"unknown classification rejects whole candidate and preserves forest zones")
	ui._start_import(source,LAYER.OVERTURE_LAND_COVER_LICENSE)
	ui._cancel_operation()
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==retained,"import cancellation retains accepted forest zones")
	ui._start_import(source,LAYER.OVERTURE_LAND_COVER_LICENSE)
	await wait_job(ui)
	check(ui.store.undo()=="","change document during review")
	ui._adopt_import()
	check(ui.store.document.zones.size()==3,"stale review rejected")
	ui.last_import_source=source
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	ui.overture_bbox[2].value=9.002
	ui.overture_bbox[2].value=9.001
	await wait_job(ui)
	check(ui.last_import_source==source,"changed then restored area rejects completed selection")
	ui.overture_bbox[2].value=9.001
	ui.overture_release.text="2026-08-19.1"
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	var owned:RefCounted=ui.import_job
	var deadline:=Time.get_ticks_msec()+5000
	while ui.busy and not FileAccess.file_exists(owned.directory.path_join("download.part")) and Time.get_ticks_msec()<deadline:await process_frame
	check(ui.busy and FileAccess.file_exists(owned.directory.path_join("download.part")),"partial exists before cancellation")
	ui._cancel_operation()
	await wait_job(ui)
	check(not DirAccess.dir_exists_absolute(owned.directory) and FileAccess.get_sha256(source)==original,"cancel cleans only request partial")
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	owned=ui.import_job
	owned.poll(owned.deadline_ms)
	await wait_job(ui)
	check(owned.result.error.message.contains("timed out"),"deadline terminates helper")
	ui.overture_release.text="2026-08-19.0"
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	ui.generation+=1
	await wait_job(ui)
	check(ui.last_import_source==source,"stale document rejects remote selection")
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	await wait_job(ui)
	check(ui.last_import_source!=source,"fresh retry creates separate snapshot")
	ui._review_overture()
	ui.overture_review.hide()
	ui._download_overture()
	owned=ui.import_job
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.pid==-1 and not DirAccess.dir_exists_absolute(owned.directory),"owner close stops child")
	print("overture_land_cover_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
