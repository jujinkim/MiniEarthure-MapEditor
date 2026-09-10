extends SceneTree
const JOB := preload("res://scripts/import_native_job.gd")
const LAYER := preload("res://scripts/import_layer.gd")
const FILES := preload("res://scripts/authoring_files.gd")

class CancelDuringGeneration extends JOB:
	var reached := false
	var expire := false
	func _event(line: PackedByteArray) -> void:
		super._event(line)
		if phase == 4 and not reached:
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
		if child.has("stderr"): child.stderr.close()
		child.erase("stderr")
		return child

var ui: Control
var entry: Node
var source := ""
var layer: RefCounted
var checks := 0
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func state() -> String: return JSON.stringify([ui.store.document,ui.store.undo_stack,ui.store.redo_stack,ui.store.history_bytes,ui.store.dirty])
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func wait_ui() -> void:
	var until := Time.get_ticks_msec() + 20000
	var frames := 0
	while ui.busy and Time.get_ticks_msec() < until:
		frames += 1
		await process_frame
	check(not ui.busy, "UI operation completes: " + ui.status_label.text)
	check(frames > 0, "operation yields frames")
func wait_job(job: RefCounted) -> void:
	var until := Time.get_ticks_msec() + 20000
	while not job.done and Time.get_ticks_msec() < until:
		job.poll()
		await process_frame
	check(job.done, "native child retires: " + job.failure)
	if not job.done: job.shutdown()
func start(job: RefCounted, id: String = "") -> String:
	return job.start_validation(ui.store, layer, false, "test", source, token() if id == "" else id)
func write(path: String, bytes: PackedByteArray) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()

func run() -> void:
	entry = load("res://scripts/editor_entry.tscn").instantiate()
	root.add_child(entry)
	ui = entry.get_child(0)
	check(ui is Control,"default product entry routes to Editor UI")
	await process_frame
	ui.import_python.text = OS.get_environment("MAPEDITOR_TEST_IMPORT_PYTHON")
	ui.import_source_format.select(1); ui.import_source_format.item_selected.emit(1)
	ui.import_origin_lon.value = 9; ui.import_origin_lat.value = 55
	ui.import_origin_x.value = 512; ui.import_origin_y.value = 512
	check(ui.store.apply_command("Recipe 2",[{"field":"recipe_version","before":1,"after":2}]) == "", "explicit connected recipe")
	var project := ProjectSettings.globalize_path("user://native-project")
	check(ui.store.save_project(project) == "", "save baseline")
	var heights := PackedInt64Array(); heights.resize(17*17); heights.fill(0)
	var encoded: Dictionary = preload("res://scripts/terrain_png.gd").encode(heights,17)
	var image := ProjectSettings.globalize_path("user://terrain.png")
	write(image,encoded.bytes)
	var height := preload("res://scripts/heightmap_import_layer.gd").new()
	check(height.stage(ui.canvas.author.terrain,image,Vector2i(1,1),3200,0,1,0,{"source":"Synthetic flat terrain","license":"MIT","notice":"fixture"}) == "" and height.adopt(ui.canvas.author.terrain) == "", "file-backed candidate terrain")
	check(ui.store.save_project(project) == "", "save file-backed baseline")
	var package := ProjectSettings.globalize_path("user://prior.memap")
	check(JSON.parse_string(ui.store.bridge.export_project(project,package)).ok and JSON.parse_string(ui.store.bridge.open_package(package)).ok, "prior package loaded")
	var bridge_before: String = ui.store.bridge.document_json()
	var package_hash := FileAccess.get_sha256(package)
	var before := state()
	source = ProjectSettings.globalize_path("user://chains.pbf")
	var output: Array = []
	check(OS.execute(ui.import_python.text,PackedStringArray(["-B",ProjectSettings.globalize_path("res://tests/osm_fixture.py"),source,"12","chains"]),output,true) == 0,"synthetic chain fixture")
	var original: PackedByteArray = FILES.read(source).bytes
	ui._start_import(source,LAYER.OSM_LICENSE)
	await wait_ui()
	check(ui.pending_import != null,"asynchronous native review: " + ui.status_label.text)
	if ui.pending_import == null: await finish(); return
	layer = ui.pending_import
	check(LAYER._hex(layer.native_payload_digest,64),"review binds file-backed snapshot")
	check(state() == before and ui.store.bridge.document_json() == bridge_before,"review preserves document/history/live package bridge")
	# Each real child is cancelled in its generation phase. No timeout sleeps.
	for expire in [false,true]:
		var job := CancelDuringGeneration.new(); job.expire = expire
		check(start(job) == "","start real native cancellation/deadline")
		await wait_job(job)
		check(job.reached and job.exited and not job.result.ok,"actual native generation is stopped and reaped")
		check(job.failure.contains("timed out") if expire else job.failure == "","deadline/cancel reason")
		check(not DirAccess.dir_exists_absolute(job.directory),"partial snapshot removed only after native exit")
		check(state() == before and ui.store.bridge.document_json() == bridge_before,"cancel/deadline retains loaded bridge/history")
	# A new job succeeds after both kinds of retirement.
	var retry := JOB.new()
	check(start(retry) == "","fresh native retry")
	await wait_job(retry)
	check(retry.result.ok and retry.result.data.ok,"fresh child validates full cells")
	check(not DirAccess.dir_exists_absolute(retry.directory),"successful snapshot/result/log retired")
	# Changes to selected source and referenced payload after review must be refused.
	write(source,original + PackedByteArray([0]))
	ui._adopt_import(); await wait_ui()
	check(ui.status_label.text.contains("source changed") and state() == before,"source replacement between review/adopt refuses atomically")
	write(source,original)
	ui.pending_import = layer; ui.import_review_generation = ui.generation
	var payload: String = project.path_join(ui.store.document.heightmaps[0].path)
	var original_payload: PackedByteArray = FILES.read(payload).bytes
	heights[8*17+8] = 1
	write(payload,preload("res://scripts/terrain_png.gd").encode(heights,17).bytes)
	ui._adopt_import(); await wait_ui()
	check(ui.status_label.text.contains("payload changed since import review") and state() == before,"valid but changed terrain cannot silently replace reviewed surface")
	write(payload,original_payload)
	# Admission refuses an oversized source payload before snapshot allocation.
	var huge := FileAccess.open(payload,FileAccess.WRITE)
	huge.seek(FILES.MAX_PAYLOAD_BYTES); huge.store_8(0); huge.close()
	var bounded := JOB.new()
	check(start(bounded) == "","start bounded payload check")
	await wait_job(bounded)
	check(bounded.result.ok and not bounded.result.data.ok and bounded.result.data.error.message.contains("64 MiB"),"native snapshot enforces 64 MiB before reading")
	write(payload,original_payload)
	# Selection revision at review and at completion is checked independently.
	ui.pending_import = layer; ui.import_review_generation = ui.generation
	ui.import_origin_x.value += 1
	ui._adopt_import()
	check(not ui.busy and ui.pending_import == null and state() == before,"changed origin invalidates review before launch")
	ui.import_origin_x.value -= 1
	ui.pending_import = layer; ui.import_review_generation = ui.generation
	ui._adopt_import()
	var late: RefCounted = ui.import_job
	ui._cancel_operation(); await wait_ui()
	check(state() == before and ui.pending_import == null,"UI cancel during native adoption preserves state")
	ui._finish_native_import(late,{"ok":true,"data":{"ok":true,"request":late.identity,"payloads":layer.native_payload_digest}})
	check(state() == before and ui.pending_import == null,"late successful result cannot revive cancelled adoption")
	ui.pending_import = layer; ui.import_review_generation = ui.generation
	ui._adopt_import()
	ui._finish_native_import(late,{"ok":true,"data":{"ok":true,"request":late.identity,"payloads":layer.native_payload_digest}})
	check(state() == before and ui.pending_import == null,"old request cannot publish into a new validation")
	await wait_ui()
	check(ui.store.document.roads.size() == 10,"fresh validated adoption is one atomic command")
	check(ui.store.undo() == "" and ui.store.document.roads.is_empty(),"one Undo removes all imported roads")
	check(ui.store.redo() == "" and ui.store.document.roads.size() == 10,"Redo restores exact graph")
	check(ui.store.undo() == "","restore baseline for lifecycle faults")
	before = state()
	await lifecycle_faults(before)
	check(FileAccess.get_sha256(package) == package_hash and FILES.read(source).bytes == original and FILES.read(payload).bytes == original_payload,"all original source/payload/prior-package bytes preserved")
	# Close the actual UI while its native child is alive.
	ui._start_native_import(layer,false)
	var closing: RefCounted = ui.import_job
	check(closing != null and closing.pid > 0,"native child started before close")
	ui.store.dirty = false
	ui.queue_free(); await process_frame
	check(closing.exited and closing.pid == -1 and not DirAccess.dir_exists_absolute(closing.directory),"Editor close kills and reaps child before owned cleanup")
	ui = null
	await finish()

func lifecycle_faults(before: String) -> void:
	for job: RefCounted in [MissingNative.new(),PartialNative.new()]:
		check(start(job) != "","failed/partial native launch rejected")
		check(job.pid == -1 and not DirAccess.dir_exists_absolute(job.directory),"failed launch owns no remaining files/process")
		check(start(job).contains("single use"),"failed object cannot be relaunched")
	var occupied := token()
	var directory := ProjectSettings.globalize_path("user://import-jobs/" + occupied)
	write(directory.path_join("candidate/document.json"),"unrelated".to_utf8_buffer())
	var rejected := JOB.new()
	check(start(rejected,occupied) != "","existing native job directory is never claimed")
	rejected.shutdown()
	check(FileAccess.get_file_as_string(directory.path_join("candidate/document.json")) == "unrelated","unclaimed candidate preserved")
	for mode in ["wrong-request","regress","over-cells","flood","partial","crash","wrong-result","premature-success","invalid-error","diagnostic"]:
		var bad := FaultNative.new(); bad.mode = mode
		check(start(bad) == "","start native IPC fault " + mode)
		await wait_job(bad)
		check(not bad.result.ok and bad.exited,"reject and retire " + mode)
		check(not DirAccess.dir_exists_absolute(bad.directory) and state() == before,"fault cleanup and state preservation " + mode)
	var live := FaultNative.new()
	check(start(live) == "","start owned waiting child")
	var until := Time.get_ticks_msec()+10000
	while live.sequence == 0 and Time.get_ticks_msec()<until:
		live.poll(); await process_frame
	check(live.sequence == 1,"waiting child reached handshake")
	var recovery := preload("res://scripts/import_recovery.gd").new()
	recovery.start()
	while not recovery.done:
		live.poll(); recovery.poll(); await process_frame
	var active := false
	for row: Dictionary in recovery.rows:
		if row.name == live.identity and row.kind == "native" and row.state == "active": active = true
	check(active,"native job is recognized by bounded ownership discovery")
	live.cleanup()
	check(FileAccess.file_exists(live.directory.path_join("request.json")),"cleanup refuses live native worker")
	write(live.directory.path_join("candidate/keep.memap"),"unknown".to_utf8_buffer())
	live.shutdown()
	check(FileAccess.get_file_as_string(live.directory.path_join("candidate/keep.memap")) == "unknown" and FileAccess.file_exists(live.directory.path_join("owner.json")),"unknown candidate and recovery ownership marker preserved")
	# Actual worker loses its supervising pipe: no orphan native process remains.
	var orphan := JOB.new()
	check(start(orphan) == "","start actual native parent-loss child")
	var orphan_pid: int = orphan.pid
	orphan.stdio.close(); orphan.stdio = null; orphan.output_eof = true
	await wait_job(orphan)
	check(orphan.exited and not orphan.result.ok and not DirAccess.dir_exists_absolute(orphan.directory),"parent-pipe EOF terminates actual child and retires scratch, pid="+str(orphan_pid))

func finish() -> void:
	if ui != null:
		ui.store.dirty = false; ui.queue_free(); await process_frame
	if is_instance_valid(entry): entry.queue_free(); await process_frame
	print("import_native_validator: %s (%d checks)" % ["PASS" if failures.is_empty() else str(failures),checks])
	quit(0 if failures.is_empty() else 1)
