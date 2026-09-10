extends "res://tests/dem_mosaic_validator.gd"
const JOB := preload("res://scripts/dem_native_job.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const PNG := preload("res://scripts/terrain_png.gd")

class StopNative extends JOB:
	var reached := false
	var expire := false
	var target_phase := 1
	func _event(line: PackedByteArray) -> void:
		super._event(line)
		if phase == target_phase and not reached:
			reached = true
			if expire: deadline_ms = 0
			else: cancel()

class MissingNative extends JOB:
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary: return {}

class FaultNative extends JOB:
	var mode := "wait"
	func _spawn(_path: String, _arguments: PackedStringArray) -> Dictionary:
		return OS.execute_with_pipe(OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON"), PackedStringArray(["-B", "-u", ProjectSettings.globalize_path("res://tests/native_child_fixture.py"), mode, identity, directory]), false)

class PartialNative extends FaultNative:
	func _spawn(path: String, arguments: PackedStringArray) -> Dictionary:
		var child := super._spawn(path, arguments)
		child.stderr.close()
		child.erase("stderr")
		return child

class CorruptTransfer extends JOB:
	func _finish_result() -> void:
		if result.get("ok", false) and result.data.get("ok", false):
			var file := FileAccess.open(directory.path_join("bundle.bin"), FileAccess.WRITE)
			file.store_8(0)
			file.close()
		super._finish_result()

class ChangeDuringNative extends JOB:
	var path := ""
	var replacement := PackedByteArray()
	var changed := false
	func _event(line: PackedByteArray) -> void:
		super._event(line)
		if phase == 1 and not changed:
			changed = true
			var file := FileAccess.open(path, FileAccess.WRITE)
			file.store_buffer(replacement)
			file.close()

var raster_result := {}
var source_plan := {}
var capture := ""
func test_name() -> String: return "dem_native_validator"
func start_closing_work(panel: ConfirmationDialog) -> void:
	panel.plan=source_plan.duplicate(true);panel.candidate_data=raster_result.duplicate(true)
	panel._start_native(false)
	check(ui.import_job is JOB,"owner close targets actual native DEM child")
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func start(job: RefCounted, previous: Dictionary = {}, id: String = "") -> String:
	return job.start_dem(ui.store,raster_result,source_plan,capture,not previous.is_empty(),"test",token() if id == "" else id,previous)
func await_native(job: RefCounted) -> void:
	var until := Time.get_ticks_msec()+20000
	while not job.done and Time.get_ticks_msec()<until:
		job.poll()
		await process_frame
	check(job.done,"DEM native child completes: "+job.failure)
	if not job.done: job.shutdown()
	check(job.exited and job.pid==-1,"DEM child exit/reap confirmed")
func write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
func accepted(job: RefCounted) -> bool:
	return job.result.get("ok",false) and job.result.get("data",{}).get("ok",false) and not job.bundle.is_empty()

func native_checks(data: Dictionary, reviewed: Dictionary, destination: String, before: String) -> void:
	raster_result=data.duplicate(true);source_plan=reviewed.duplicate(true);capture=destination
	var panel: ConfirmationDialog=ui.dem_panel
	var bridge_before: String=ui.store.bridge.document_json()
	for scenario in [[1,false],[1,true],[5,false],[5,true]]:
		var expire: bool = scenario[1]
		var stopped:=StopNative.new();stopped.expire=expire;stopped.target_phase=scenario[0]
		check(start(stopped)=="","start real raster validation cancel/deadline")
		await await_native(stopped)
		check(stopped.reached and stopped.cancelled and not accepted(stopped),"native admission yields cancellation")
		check(stopped.failure.contains("timed out") if expire else stopped.failure=="","DEM native cancellation reason")
		check(not DirAccess.dir_exists_absolute(stopped.directory) and state()==before,"retire only owned snapshot; no partial terrain")
	var initial:=JOB.new()
	check(start(initial)=="","fresh raster retry")
	await await_native(initial)
	check(accepted(initial) and initial.expected_cells==0 and initial.generated_all,"all raster files/native seams checked without roads")
	if not accepted(initial): return
	check(initial.bundle.blob_paths.size()<=4 and initial.bundle.patches.size()==5,"four cells plus provenance and immutable blobs transferred")
	check(not DirAccess.dir_exists_absolute(initial.directory),"bundle read before owned scratch retired")
	var previous: Dictionary={"layer_id":initial.bundle.value.layer_id,"payloads":initial.result.data.payloads}
	var guarded := preload("res://tests/command_guard_store.gd").new()
	guarded.document = ui.store.document.duplicate(true); guarded.project_path = ui.store.project_path
	var guarded_job := JOB.new()
	check(guarded_job.start_dem(guarded,raster_result,source_plan,capture,true,"test",token(),previous)=="","start guarded DEM command")
	await await_native(guarded_job)
	check(accepted(guarded_job),"DEM canonical command prepared in child")
	if accepted(guarded_job):
		guarded.forbid_preparation = true
		check(guarded_job.commit(guarded)=="" and guarded.forbidden_calls==0,"DEM final commit avoids native/command/provenance serialization")
		guarded.forbid_preparation = false
		check(guarded.undo_stack.size()==1 and guarded.undo()=="" and guarded.redo()=="","prepared DEM binary command supports single Undo/Redo")
	check(state()==before,"independent DEM history never changes live UI")
	# Every source category is rechecked, including the final mosaic output.
	for path: String in [source_plan.sources[3].source.path,capture+".source-3.tif",raster_result.outputs[3].png_path]:
		var bytes: PackedByteArray=FILES.read(path).bytes
		var replacement:=bytes.duplicate();replacement[replacement.size()-1]^=1
		write(path,replacement)
		var changed:=JOB.new()
		check(start(changed,previous)=="","start changed source/capture/output check")
		await await_native(changed)
		check(not accepted(changed) and state()==before,"same-size changed file rejects whole mosaic")
		write(path,bytes)
	var during:=ChangeDuringNative.new()
	during.path=source_plan.sources[0].source.path
	var original: PackedByteArray=FILES.read(during.path).bytes
	during.replacement=original.duplicate();during.replacement[during.replacement.size()-1]^=1
	check(start(during)=="","start source mutation during native validation")
	await await_native(during)
	check(during.changed and not accepted(during),"post-native source recheck rejects changed original")
	write(during.path,original)
	var corrupt:=CorruptTransfer.new()
	check(start(corrupt)=="","start bundle transfer corruption")
	await await_native(corrupt)
	check(not accepted(corrupt) and corrupt.result.error.message.contains("transfer"),"bounded bundle hash rejects partial transfer")
	# Admission, launch, IPC and owner cleanup use the shared native supervisor.
	var missing:=MissingNative.new()
	check(start(missing)!="" and missing.pid==-1 and not DirAccess.dir_exists_absolute(missing.directory),"missing child retires reservation")
	var partial:=PartialNative.new()
	check(start(partial)!="" and partial.exited and not DirAccess.dir_exists_absolute(partial.directory),"partial child handles are killed and reaped")
	var occupied:=ProjectSettings.globalize_path("user://import-jobs/")+token()
	DirAccess.make_dir_recursive_absolute(occupied)
	var conflict:=JOB.new()
	check(start(conflict,{},occupied.get_file())!="" and DirAccess.dir_exists_absolute(occupied),"existing scratch cannot be claimed")
	DirAccess.remove_absolute(occupied)
	for mode in ["wrong-request","regress","flood","partial","crash","diagnostic","premature-success","invalid-error"]:
		var faulty:=FaultNative.new();faulty.mode=mode
		check(start(faulty)=="","start faulty DEM child "+mode)
		await await_native(faulty)
		check(not accepted(faulty) and state()==before,"invalid IPC/crash cannot adopt "+mode)
	var orphan:=JOB.new()
	check(start(orphan)=="","start parent EOF fixture")
	orphan.stdio.close();orphan.stdio=null;orphan.output_eof=true
	await await_native(orphan)
	check(not accepted(orphan),"parent EOF ends owned DEM helper")
	var unknown:=FaultNative.new()
	check(start(unknown)=="","start scratch preservation fixture")
	write(unknown.directory.path_join("unknown-user-file"),PackedByteArray([1,2,3]))
	unknown.shutdown()
	check(FileAccess.file_exists(unknown.directory.path_join("unknown-user-file")),"unknown scratch file remains after cancellation")
	# Retire this test's own known fixture only.
	DirAccess.remove_absolute(unknown.directory.path_join("unknown-user-file"))
	DirAccess.remove_absolute(unknown.directory.path_join(unknown.PRESENCE.MARKER))
	DirAccess.remove_absolute(unknown.directory)
	var oversized:=JOB.new()
	var large:=raster_result.duplicate(true);large.extension="x".repeat(JOB.REQUEST_LIMIT)
	check(oversized.start_dem(ui.store,large,source_plan,capture,false,"test",token()).contains("24 MiB") and oversized.directory=="","request budget before scratch/launch")
	for malformed in [null, 7, [], [null]]:
		var invalid:=raster_result.duplicate(true);invalid.outputs=malformed
		check(JOB.new().start_dem(ui.store,invalid,source_plan,capture,false,"test",token())!="","malformed output admission refuses without a script error")
	check(JOB.new().start_dem(ui.store,raster_result,source_plan,capture,true,"test",token()).contains("reviewed"),"unreviewed adoption rejected")
	check(ui.store.bridge.document_json()==bridge_before and state()==before,"all rejected jobs preserve live bridge/document/history")
	# Exercise UI staleness at review and at asynchronous adoption, with no source
	# reacquisition. Each fresh review is tied to the exact original selections.
	panel.adopt()
	var cancelled: RefCounted=ui.import_job
	check(cancelled is JOB and ui.busy,"UI adoption launches new owned native child")
	panel.fields["Spacing (cm)"].value+=1
	panel.fields["Spacing (cm)"].value-=1
	await wait_job()
	check(cancelled.cancelled and panel.candidate==null and state()==before,"same-frame changed/restored selection cancels adoption")
	for mutation in ["document","project","candidate","layer"]:
		panel.plan=source_plan.duplicate(true);panel.candidate_data=raster_result.duplicate(true)
		panel._start_native(false);await wait_job()
		check(panel.candidate!=null,"fresh UI review before "+mutation)
		if panel.candidate==null: return
		panel.adopt()
		var pending: RefCounted=ui.import_job
		var project: String=ui.store.project_path
		var theme: String=ui.store.document.theme
		match mutation:
			"document": ui.store.document.theme+=" changed"
			"project": ui.store.project_path+="-changed"
			"candidate": panel.candidate.value.layer_id="f".repeat(32)
			"layer":
				ui.canvas.set_layer_state("heightmaps",{"locked":true});ui.layers.state_changed.emit()
				ui.canvas.set_layer_state("heightmaps",{});ui.layers.state_changed.emit()
		await wait_job()
		check(panel.candidate==null and pending.exited and ui.status_label.text.contains("STALE"),"stale UI work refuses "+mutation)
		ui.store.document.theme=theme;ui.store.project_path=project
	check(state()==before,"UI stale paths retain accepted state")
	# A disposable document with a ground road requires actual generation in all
	# four affected cells, while the UI's loaded document/bridge remain untouched.
	var roads:=STORE.new();roads.document=ui.store.document.duplicate(true);roads.project_path=ui.store.project_path
	roads.document.nodes=[{"id":"a","position":[10000,0,20000],"level":0},{"id":"b","position":[30000,0,20000],"level":0}]
	roads.document.roads=[{"id":"road","from":"a","to":"b","points":[[10000,0,20000],[30000,0,20000]],"widths_cm":[800],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}]
	var generated:=JOB.new()
	check(generated.start_dem(roads,raster_result,source_plan,capture,false,"test",token())=="","start road/DEM cell generation")
	await await_native(generated)
	check(accepted(generated) and generated.expected_cells==4 and generated.generated_all,"four required native terrain/road cells generated: "+str(generated.result))
	check(ui.store.bridge.document_json()==bridge_before and state()==before,"native generation retains loaded bridge")
	roads.document.roads=[];roads.document.nodes=[];roads.document.bounds.max=[153600,102400]
	var seam:=JOB.new()
	check(seam.start_dem(roads,raster_result,source_plan,capture,false,"test",token())=="","start external-neighbor seam check")
	await await_native(seam)
	check(not accepted(seam) and str(seam.result).contains("E_SEAM"),"native seam failure rejects complete DEM candidate")

	# Atomic adoption carries binary mementos. Deleting an installed generated
	# payload (our isolated fixture) must reject Redo until exact bytes return.
	var adopt:=JOB.new()
	check(start(adopt,previous)=="","start reviewed mosaic adoption")
	await await_native(adopt)
	check(accepted(adopt),"review identity survives unrelated failed requests")
	if not accepted(adopt): return
	var payloads: Dictionary=adopt.bundle.retained.duplicate()
	check(adopt.commit(ui.store)=="" and ui.store.document.heightmaps.size()==4,"one command activates all mosaic cells")
	check(adopt.commit(ui.store)!="","completed job cannot commit twice")
	check(ui.store.undo()=="" and ui.store.document.heightmaps.is_empty(),"single Undo removes complete native adoption")
	for path: String in payloads: DirAccess.remove_absolute(ui.store.project_path.path_join(path))
	check(ui.store.redo().contains("missing") and ui.store.document.heightmaps.is_empty(),"missing binary payload rejects Redo atomically")
	for path: String in payloads: write(ui.store.project_path.path_join(path),payloads[path])
	check(ui.store.redo()=="" and ui.store.document.heightmaps.size()==4,"Redo succeeds after exact fixture bytes return")
	for path: String in payloads: check(FILES.read(ui.store.project_path.path_join(path)).bytes==payloads[path],"Redo restores exact PNG bytes")
	# Reimport the same cells with an interior change to old terrain. Before-image
	# must be transferred together with new bytes for exact Undo validation.
	var heightmap: Dictionary=ui.store.document.heightmaps[0]
	var old_path: String=ui.store.project_path.path_join(heightmap.path)
	var bytes: PackedByteArray=FILES.read(old_path).bytes
	var changed_payload:=JOB.new()
	check(start(changed_payload)=="","review existing terrain replacement")
	await await_native(changed_payload)
	check(accepted(changed_payload),"old terrain included in review fingerprint")
	var retained_review: Dictionary={"layer_id":changed_payload.bundle.value.layer_id,"payloads":changed_payload.result.data.payloads}
	write(old_path,bytes+PackedByteArray([0]))
	var stale_payload:=JOB.new();check(start(stale_payload,retained_review)=="","start changed old payload adoption")
	await await_native(stale_payload)
	check(not accepted(stale_payload),"old replaced payload cannot change after review")
	write(old_path,bytes)
	# A changed, seam-compatible old tile has a different path from the imported
	# output; the child must carry both byte arrays, not just the new raster.
	var side:=int(ui.store.document.cell_size_cm)/int(heightmap.spacing_cm)+1
	var decoded: Dictionary=PNG.decode(bytes,side,int(heightmap.offset_cm),int(heightmap.step_cm))
	decoded.heights[side+1]+=1
	var encoded: Dictionary=PNG.encode(decoded.heights,side)
	var edited:=heightmap.duplicate(true)
	edited.path="editor/"+FILES.digest(encoded.bytes)+".png";edited.offset_cm=encoded.offset_cm;edited.step_cm=encoded.step_cm
	check(FILES.write_new(ui.store.project_path.path_join(edited.path),encoded.bytes)=="","install isolated edited terrain")
	check(ui.store.apply_command("edit old tile",[{"field":"heightmaps","id":ui.store.record_id("heightmaps",heightmap),"before":heightmap.duplicate(true),"after":edited}])=="","select distinct prior tile")
	var replacing:=JOB.new();check(start(replacing)=="","review distinct old/new tile")
	await await_native(replacing)
	check(accepted(replacing) and replacing.bundle.retained.has(edited.path) and replacing.bundle.retained.has(heightmap.path),"transfer contains distinct before/after PNG mementos")
	if not accepted(replacing): return
	var replace_adopt:=JOB.new()
	check(start(replace_adopt,{"layer_id":replacing.bundle.value.layer_id,"payloads":replacing.result.data.payloads})=="","revalidate replacement before commit")
	await await_native(replace_adopt)
	check(accepted(replace_adopt) and replace_adopt.commit(ui.store)=="","adopt replacement as one command")
	check(ui.store.undo()=="" and ui.canvas.author.terrain.descriptor(Vector2i(0,0)).path==edited.path,"single Undo restores previous descriptor")
	check(FILES.read(ui.store.project_path.path_join(edited.path)).bytes==encoded.bytes,"previous PNG bytes preserved")
	check(ui.store.undo()=="","undo fixture terrain edit")
	# Restore caller's empty document and history, without touching user files.
	check(ui.store.undo()=="","restore empty fixture document")
	ui.store.redo_stack.clear();ui.store.history_bytes=0
	for command: Dictionary in ui.store.undo_stack: ui.store.history_bytes+=int(command.bytes)
	var restored: Array=JSON.parse_string(state())
	var expected: Array=JSON.parse_string(before)
	check(restored[0].provenance.last_edited>=expected[0].provenance.last_edited,"successful edits advance provenance time")
	expected[0].provenance.last_edited=restored[0].provenance.last_edited
	check(restored==expected,"binary exercise restores geometry/history; edit timestamp advances")
