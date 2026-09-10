extends SceneTree
const LAYER := preload("res://scripts/import_layer.gd")
const STORE := preload("res://scripts/document_store.gd")
const UI := preload("res://scripts/editor_main.gd")
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
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	check(ui.store.apply_command("Choose road recipe",[{"field":"recipe_version","before":1,"after":2}])=="","explicit recipe 2 for native junction generation")
	var before: Dictionary=ui.store.document.duplicate(true)
	var source := ProjectSettings.globalize_path("user://overture_transportation_validator.gd.json")
	var output: Array = []
	check(OS.execute(ui.import_python.text, PackedStringArray(["-B", ProjectSettings.globalize_path("res://tests/overture_transportation_fixture.py"), "--snapshot", source]), output, true) == 0, "local synthetic snapshot")
	ui.import_source_format.select(4)
	ui.import_source_format.item_selected.emit(4)
	check(ui.import_license.text == LAYER.OVERTURE_TRANSPORTATION_LICENSE, "explicit local source attribution")
	if not FileAccess.file_exists(source): quit(1); return
	var original:=FileAccess.get_sha256(source)
	ui.import_origin_lon.value=9
	ui.import_origin_lat.value=55
	ui.import_dialog.hide()
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null,"Overture native review: "+ui.status_label.text)
	if ui.pending_import==null: quit(1); return
	var raw: Dictionary=ui.pending_import.value.duplicate(true)
	check(ui.store.document==before,"review leaves document unchanged")
	check(raw.adapter=="overture-transportation-v1" and raw.source.sha256==original,"snapshot identity preserved")
	check(ui.import_summary.text.contains("2026-08-19.0") and preload("res://tests/import_review_helpers.gd").source_readable(ui, "overture_transportation", "segment_sources") and ui.import_summary.text.contains("Chosen road plane"),"release/source/estimate review")
	check(raw.coordinates.overture_transportation.segment_sources[0].connectors[1].vertex==null and raw.coordinates.overture_transportation.segment_sources[0].connectors[1].resolved_at==0.5,"off-vertex mapping reaches native review")
	check(raw.patches.size()==7,"four connectors and three split roads")
	for field in ["license","adapter","provenance","bbox","release","sources","missing","endpoint","height","width","unmapped","order","budget","span_order","span_gap","span_width","span_surface","span_geometry","span_missing","span_boundary","span_one","source_fraction","position_profile","position_at","position_displacement","position_vertex","position_endpoint"]:
		var bad:=raw.duplicate(true)
		var meta: Dictionary=bad.coordinates.overture_transportation
		if field=="license":bad.source.license="MIT"
		elif field=="adapter":bad.adapter="geojson-v2"
		elif field=="bbox":meta.bbox=[9,55,10,56]
		elif field=="release":meta.release="latest"
		elif field=="sources":meta.segment_sources[0].sources=[]
		elif field=="missing":meta.connector_sources.pop_back()
		elif field=="endpoint":bad.patches[4].after.to=bad.patches[0].id
		elif field=="height":bad.patches[4].after.points[0][1]=900
		elif field=="width":bad.patches[4].after.widths_cm[0]=1
		elif field=="unmapped":meta.segment_sources[0].road_ids[0]="unmapped"
		elif field=="order":meta.segment_sources[0].connectors.reverse()
		elif field=="budget":meta.source_position_count=8193
		elif field=="span_order":meta.segment_sources[0].road_spans[0].fractions.reverse()
		elif field=="span_gap":meta.segment_sources[0].physical_rules.width_rules[1][0]=0.3
		elif field=="span_width":meta.segment_sources[0].road_spans[0].widths_cm[0]=5
		elif field=="span_surface":meta.segment_sources[0].road_spans[0].surfaces[0]="dirt"
		elif field=="span_geometry":meta.segment_sources[0].road_spans[0].points_cm[1][0]+=1
		elif field=="span_missing":meta.segment_sources[0].road_spans.pop_back()
		elif field=="span_one":meta.segment_sources[0].road_spans[0].fractions[1]=1
		elif field=="position_profile":meta.connection_profile="unknown"
		elif field=="position_at":meta.segment_sources[0].connectors[1].resolved_at=0.6
		elif field=="position_displacement":meta.segment_sources[0].connectors[1].displacement_m=0.002
		elif field=="position_vertex":meta.segment_sources[0].connectors[1].vertex=1
		elif field=="position_endpoint":meta.segment_sources[0].connectors[0].vertex=null
		elif field=="source_fraction":meta.segment_sources[0].source_fractions[1]=0.4
		elif field=="span_boundary":meta.segment_sources[0].road_spans[0].fractions[1]=0.3
		else:bad.coordinates.erase("overture_transportation")
		check(LAYER.new().load_value(bad,raw.layer_id,ui.import_coordinates_request)!="","forged "+field+" rejected")
	ui._discard_import()
	check(ui.store.document==before,"discard preserves map")
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	ui._adopt_import()
	check(ui.store.document.roads.size()==3,"native atomic graph adoption")
	ui._adopt_import()
	check(ui.store.document.roads.size()==3,"one-shot candidate")
	var roads: Array = ui.store.document.roads
	check(roads[0].to==roads[1].from and roads[0].to==roads[2].from,"internal connector forms native T junction")
	check(roads[0].widths_cm==[600.0,400.0] and roads[1].surfaces==["asphalt","dirt"],"scoped physical arrays survive native adoption: " + JSON.stringify([roads[0].widths_cm, roads[1].surfaces]))
	check(roads[0].points.size()==3 and ui.store.document.nodes.size()==4,"property boundaries add vertices without false connectors")
	var adopted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store.document.roads.is_empty() and ui.store.document.nodes.is_empty(),"one-command undo removes complete graph")
	check(ui.store.redo()=="" and ui.store.document==adopted,"redo restores complete graph/provenance")
	var project:=ProjectSettings.globalize_path("user://overture-transportation-project")
	check(ui.store.save_project(project)=="","save provenance")
	check(ui.store.autosave()=="","recovery snapshot")
	var reopened:=STORE.new()
	check(reopened.open_project(project)=="" and reopened.document.attributions==ui.store.document.attributions,"source notices roundtrip")
	check(reopened.recover(ui.store.recovery_path())=="","recover source layer")
	var pack:=ProjectSettings.globalize_path("user://overture-transportation.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,pack)).ok,"package imported roads")
	var pack_hash:=FileAccess.get_sha256(pack)
	check(JSON.parse_string(ui.store.bridge.open_package(pack)).ok,"open package")
	check(JSON.parse_string(ui.store.bridge.generate_chunk(1,1)).ok,"same MapKit geometry generation")
	var update:=ProjectSettings.globalize_path("user://updated-transportation.overture-roads.json")
	var snapshot:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source))
	for feature in snapshot.features:
		if feature.id == "east": feature.properties.width_rules[0].value=7
	var f:=FileAccess.open(update,FileAccess.WRITE)
	f.store_string(JSON.stringify(snapshot));f.close()
	ui._start_import(update,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	check(ui.pending_import!=null and ui.pending_import.value.layer_id!=raw.layer_id,"source update is fresh graph layer: " + ui.status_label.text)
	ui._adopt_import()
	check(ui.store.document.roads.size()==6,"update retains old graph")
	check(ui.store.undo()=="" and ui.store.document.roads.size()==3,"undo updated layer")
	check(ui.store.redo()=="" and ui.store.document.roads.size()==6,"redo updated layer")
	check(FileAccess.get_sha256(source)==original and FileAccess.get_sha256(pack)==pack_hash,"source/package preserved")
	var bad_path:=ProjectSettings.globalize_path("user://missing-connector.overture-roads.json")
	var bad_source:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source))
	bad_source.features.pop_front()
	var bad_file:=FileAccess.open(bad_path,FileAccess.WRITE)
	bad_file.store_string(JSON.stringify(bad_source));bad_file.close()
	var retained:Dictionary=ui.store.document.duplicate(true)
	ui._start_import(bad_path,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==retained,"missing connector rejects whole candidate and preserves graph")
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	ui._cancel_operation()
	await wait_job(ui)
	check(ui.pending_import==null and ui.store.document==retained,"import cancellation retains accepted graph")
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	check(ui.store.undo()=="","change document during review")
	ui._adopt_import()
	check(ui.store.document.roads.size()==3,"stale review rejected")
	ui.last_import_source=source
	# Surviving local helper lifetime: deadline, stale response, retry and owner close.
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	var owned: RefCounted = ui.import_job
	owned.poll(owned.deadline_ms)
	await wait_job(ui)
	check(owned.result.error.message.contains("timed out"),"deadline terminates local helper")
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	ui.generation += 1
	await wait_job(ui)
	check(ui.pending_import == null,"stale document rejects local candidate")
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	await wait_job(ui)
	check(ui.pending_import != null,"fresh local retry succeeds")
	ui._discard_import()
	ui._start_import(source,LAYER.OVERTURE_TRANSPORTATION_LICENSE)
	owned=ui.import_job
	ui.store.dirty=false
	ui.queue_free()
	await process_frame
	check(owned.pid==-1 and not DirAccess.dir_exists_absolute(owned.directory),"owner close stops local child")
	check(FileAccess.get_sha256(source)==original,"original snapshot retained after lifetime checks")
	print("overture_transportation_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
