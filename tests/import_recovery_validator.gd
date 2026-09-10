extends SceneTree
const JOB := preload("res://scripts/import_job.gd")
const PRESENCE := preload("res://scripts/import_presence.gd")
const SCAN := preload("res://scripts/import_recovery.gd")
class ReplayedPresence extends PRESENCE:
	var connections: Array[StreamPeerTCP] = []
	func poll(_now_ms: int = -1) -> void:
		if server.is_connection_available():
			var socket := server.take_connection()
			socket.put_data((owner + ":" + "0".repeat(32) + "\n").to_ascii_buffer())
			connections.append(socket)
	func close() -> void:
		for socket in connections: socket.disconnect_from_host()
		connections.clear()
		super.close()

var failures: Array[String] = []
var checks := 0
var base := ""
var source := ""
var retained := {}
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
func write(path: String, text: String) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()
	retained[path] = text.sha256_text()
func token() -> String: return Crypto.new().generate_random_bytes(16).hex_encode()
func state(scan: RefCounted, name: String) -> String:
	for row in scan.rows:
		if row.name == name: return row.state
	return "missing"
func collect(owner: RefCounted = null) -> RefCounted:
	var scan := SCAN.new()
	scan.start()
	var end := Time.get_ticks_msec() + 7000
	while not scan.done and Time.get_ticks_msec() < end:
		if owner != null: owner.poll()
		scan.poll()
		await process_frame
	check(scan.done, "discovery finishes within deadline")
	return scan
func run() -> void:
	root.gui_embed_subwindows = true
	base = ProjectSettings.globalize_path("user://import-jobs")
	source = ProjectSettings.globalize_path("user://recovery-source.geojson")
	write(source, '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[10,10],[20,10],[20,20],[10,20],[10,10]]]}}]}')
	write(ProjectSettings.globalize_path("user://keep.memap"), "prior package")
	var scan: RefCounted = await collect()
	check(scan.rows.is_empty() and not DirAccess.dir_exists_absolute(base), "empty discovery does not create scratch root")
	# Real simultaneous Editor processes, readiness-bound kill, then restart discovery.
	for phase in ["reserved", "worker"]:
		await crash_case(phase)
	var missing := token()
	write(base.path_join(missing).path_join("source.pbf"), "legacy original")
	var torn := token()
	write(base.path_join(torn).path_join(PRESENCE.MARKER), "{torn")
	var huge := token()
	write(base.path_join(huge).path_join(PRESENCE.MARKER), "x".repeat(PRESENCE.MAX_METADATA + 1))
	var pending := token()
	write(base.path_join(pending).path_join(PRESENCE.PENDING), "partial owner")
	var fake := token()
	var live := JOB.new()
	check(live._reserve_directory(token()) == "", "reserve owner for identity/port-reuse tests")
	var metadata: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(live.directory.path_join(PRESENCE.MARKER)))
	metadata.request = fake
	metadata.owner = token()
	write(base.path_join(fake).path_join(PRESENCE.MARKER), JSON.stringify(metadata))
	var invalid := token()
	metadata.request = invalid
	metadata.port = "127.0.0.1:123"
	write(base.path_join(invalid).path_join(PRESENCE.MARKER), JSON.stringify(metadata))
	var linked := token()
	var linked_marker := token()
	DirAccess.make_dir_absolute(base.path_join(linked_marker))
	var output: Array = []
	check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.symlink(sys.argv[1],sys.argv[2]); os.symlink(sys.argv[3],sys.argv[4])", live.directory, base.path_join(linked), live.directory.path_join(PRESENCE.MARKER), base.path_join(linked_marker).path_join(PRESENCE.MARKER)]), output, true) == 0, "synthetic directory/record links created")
	scan = await collect(live)
	check(state(scan, live.directory.get_file()) == "active", "matching current owner responds")
	check(state(scan, fake) == "unconfirmed", "reused live endpoint with wrong owner cannot confirm old record")
	for name in [missing, torn, huge, pending, invalid, linked, linked_marker]:
		check(state(scan, name) == "unknown", "unknown/invalid/link record retained: " + name)
	var replay := ReplayedPresence.new()
	var replay_token := token()
	DirAccess.make_dir_absolute(base.path_join(replay_token))
	check(replay.begin(base.path_join(replay_token), replay_token, "dem") == "", "persist local DEM owner record")
	scan = await collect(replay)
	check(state(scan, replay_token) == "unconfirmed", "old nonce reply cannot confirm a fresh probe")
	replay.close()
	# Idle/flooded presence connections have a strict per-owner handle/byte bound.
	var clients: Array[StreamPeerTCP] = []
	var port: int = live.presence.server.get_local_port()
	for _index in PRESENCE.MAX_PEERS + 3:
		var socket := StreamPeerTCP.new()
		check(socket.connect_to_host("127.0.0.1", port) == OK, "connect synthetic idle probe")
		clients.append(socket)
	for _frame in 12:
		live.poll()
		for socket in clients: socket.poll()
		await process_frame
	check(live.presence.peers.size() <= PRESENCE.MAX_PEERS, "presence peer admission is bounded")
	for socket in clients:
		if socket.get_status() == StreamPeerTCP.STATUS_CONNECTED: socket.put_data("x".repeat(34).to_ascii_buffer())
	for _frame in 12:
		live.poll()
		await process_frame
	check(live.presence.peers.is_empty(), "oversized requests release admitted peers without response")
	for socket in clients: socket.disconnect_from_host()
	# No response is uncertainty even while the listener is still alive.
	var silent := SCAN.new()
	silent.start()
	silent.poll()
	silent.poll(Time.get_ticks_msec() + SCAN.SCAN_MS + 1)
	check(silent.done and silent.partial and silent.probes.is_empty(), "controlled total deadline closes pending sockets")
	var aborted := SCAN.new()
	aborted.start()
	aborted.poll()
	aborted.cancel()
	aborted.poll()
	check(aborted.done and aborted.probes.is_empty() and aborted.listing == null, "cancel consumes discovery handles")
	# Unknown remnant retains persistent marker after normal owner releases.
	write(live.directory.path_join("keep.memap"), "unknown file in newly owned work")
	live.cleanup()
	check(FileAccess.file_exists(live.directory.path_join(PRESENCE.MARKER)), "cleanup remnant keeps ownership evidence")
	scan = await collect()
	check(state(scan, live.directory.get_file()) == "unconfirmed", "released owner remnant is never labelled active")
	# UI startup, explicit scan and dismissal cannot change the document/history.
	var ui: Control = load("res://main.tscn").instantiate()
	root.size = Vector2i(1024, 720)
	root.add_child(ui)
	await process_frame
	var before := JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty])
	ui.import_recovery.show_report()
	var end := Time.get_ticks_msec() + 7000
	while not ui.import_recovery.reported and Time.get_ticks_msec() < end: await process_frame
	check(ui.import_recovery.visible and ui.import_recovery.reported, "report opens and finishes")
	check(ui.import_recovery.report.text.contains("possibly interrupted") and ui.import_recovery.report.text.contains("Unknown entries"), "report explains uncertainty and preservation")
	check(ui.import_recovery.banner.text.contains("to review"), "startup work indicator exposes retained entries")
	check(ui.import_recovery.banner.get_global_rect().end.x <= root.size.x, "work indicator fits minimum window with retained entries")
	ui.import_recovery.restart()
	while not ui.import_recovery.reported and Time.get_ticks_msec() < end: await process_frame
	check(ui.import_recovery.reported, "explicit rescan finishes")
	var capture := OS.get_environment("MAPEDITOR_RECOVERY_CAPTURE")
	if capture != "" and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		print("recovery geometry: window=", ui.import_recovery.size, " report=", ui.import_recovery.report.size, " minimum=", ui.import_recovery.report.get_combined_minimum_size())
		check(ui.import_recovery.position.y >= 0 and ui.import_recovery.position.y + ui.import_recovery.size.y <= root.size.y, "recovery dialog fits minimum window")
		check(root.get_texture().get_image().save_png(capture) == OK, "capture recovery UI")
	ui.import_recovery.hide()
	check(JSON.stringify([ui.store.document, ui.store.undo_stack, ui.store.dirty]) == before, "scan/show/rescan/dismiss preserves document and history")
	ui.queue_free()
	await process_frame
	# Scope/caps: never enumerate children or load originals, even at the row limit.
	for index in SCAN.MAX_ROWS + 2: write(base.path_join("unrecognized-%03d" % index).path_join("keep.pbf"), "bounded fixture")
	scan = await collect()
	check(scan.partial and scan.rows.size() <= SCAN.MAX_ROWS and scan.entries <= SCAN.MAX_ENTRIES, "large root produces explicit bounded partial report")
	for path in retained: check(FileAccess.get_sha256(path) == retained[path], "original/record/package hash preserved: " + path.get_file())
	var saved := base + "-synthetic-saved"
	check(DirAccess.rename_absolute(base, saved) == OK, "isolate root-link fixture")
	check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.symlink(sys.argv[1],sys.argv[2],target_is_directory=True)", saved, base]), output, true) == 0, "create synthetic linked root")
	scan = await collect()
	check(scan.rows.is_empty() and scan.message.contains("linked"), "root link is not traversed")
	check(OS.execute("python3", PackedStringArray(["-c", "import os,sys; os.unlink(sys.argv[1])", base]), output, true) == 0, "remove only test root link")
	check(DirAccess.rename_absolute(saved, base) == OK, "restore synthetic root")
	print("import_recovery_validator: %s (%d assertions)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)

func crash_case(phase: String) -> void:
	var name := token()
	var ready := ProjectSettings.globalize_path("user://ready-" + name + ".json")
	var project := OS.get_environment("MAPEDITOR_TEST_PROJECT")
	var args := PackedStringArray(["--headless", "--path", project])
	var pack := OS.get_environment("MAPEDITOR_TEST_RESOURCE_PACK")
	if pack != "": args.append_array(["--main-pack", pack])
	args.append_array(["--script", project.path_join("tests/import_recovery_owner.gd"), "--", phase, name, source, ready])
	var child := OS.create_process(OS.get_executable_path(), args)
	check(child > 0, phase + " starts separate Editor")
	var end := Time.get_ticks_msec() + 15000
	while not FileAccess.file_exists(ready) and Time.get_ticks_msec() < end: await process_frame
	check(FileAccess.file_exists(ready), phase + " reaches exact interruption boundary")
	if not FileAccess.file_exists(ready):
		if child > 0: OS.kill(child)
		return
	var info: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ready))
	check(info.phase == phase, "readiness belongs to requested phase")
	var marker := base.path_join(name).path_join(PRESENCE.MARKER)
	retained[marker] = FileAccess.get_sha256(marker)
	var scan: RefCounted = await collect()
	check(state(scan, name) == "active", phase + " other Editor positively confirms ownership")
	check(OS.kill(child) == OK, phase + " kills only the ready synthetic Editor")
	scan = await collect()
	check(state(scan, name) == "unconfirmed", phase + " restart discovers retained work without asserting worker exit")
	check(FileAccess.get_sha256(marker) == retained[marker], phase + " discovery never rewrites marker")
	if info.worker > 0:
		var output: Array = []
		var script := "import os,sys,time; pid=int(sys.argv[1]); end=time.monotonic()+5\nwhile time.monotonic()<end:\n try: os.kill(pid,0)\n except ProcessLookupError: sys.exit(0)\n time.sleep(.02)\nsys.exit(1)"
		check(OS.execute("python3", PackedStringArray(["-c", script, str(int(info.worker))]), output, true) == 0, "production parent EOF watchdog stops orphan worker: " + str(output))
