extends SceneTree
## Bounded synthetic timing probe. No user files or prolonged performance run.
const EDITOR := preload("res://scripts/editor_main.gd")
var screen: Control
var rows: Array = []
var seeded_source: Dictionary = {}
var frame_clock := 0
var max_frame_gap_ms := 0.0

static func source_identity(source: Dictionary) -> Dictionary:
	var shapes := {}
	for piece: Dictionary in source.instances:
		shapes[piece.preset] = int(shapes.get(piece.preset, 0)) + 1
	return {"sha256":JSON.stringify(source).sha256_text(), "pieces":source.instances.size(), "shapes":shapes}

func native_hash() -> String:
	var config := ConfigFile.new()
	assert(config.load("res://addons/mapkit/mapkit.gdextension") == OK)
	for key: String in config.get_section_keys("libraries"):
		var matches := true
		for feature: String in key.split("."):
			matches = matches and OS.has_feature(feature)
		if matches:
			return FileAccess.get_sha256("res://addons/mapkit/" + str(config.get_value("libraries", key)))
	assert(false, "benchmark native library not found")
	return ""

func _initialize() -> void:
	process_frame.connect(func():
		var now := Time.get_ticks_usec()
		if frame_clock > 0: max_frame_gap_ms = maxf(max_frame_gap_ms, (now - frame_clock) / 1000.0)
		frame_clock = now)
	run.call_deferred()

func settle() -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while screen.store.get("track_edit_busy") == true and Time.get_ticks_msec() < deadline: await process_frame
	assert(screen.store.get("track_edit_busy") != true, "track benchmark timeout")

func sample(label: String, operation: Callable) -> Dictionary:
	var begin := Time.get_ticks_usec()
	frame_clock = begin
	max_frame_gap_ms = 0.0
	var epoch: int = screen.store.command_epoch
	operation.call()
	var submit := Time.get_ticks_usec() - begin
	await settle()
	var complete := (Time.get_ticks_usec() - begin) / 1000.0
	assert(label == "selection" or screen.store.command_epoch > epoch, "benchmark edit did not commit: " + label + " " + screen.status_label.text)
	await process_frame # Include deferred inspector work and scene retirement.
	return {"operation":label, "frame_gap_ms":max_frame_gap_ms, "worker":screen.store.get("last_track_timings"), "main_ms":maxf(submit / 1000.0, float(screen.store.get("last_track_apply_ms")) if screen.store.get("last_track_apply_ms") != null and label != "selection" else 0.0), "submit_ms":submit / 1000.0, "apply_ms":float(screen.store.get("last_track_apply_ms")) if screen.store.get("last_track_apply_ms") != null and label != "selection" else 0.0, "complete_ms":complete}

static func fixture(store: RefCounted, count: int, grounded: bool, seed_source: Dictionary = {}) -> Dictionary:
	# Empty current source comes from a real new draft, not a hand-written schema.
	if grounded and not seed_source.is_empty():
		var cropped := seed_source.duplicate(true)
		# Retain actual seed shapes/heights; extend larger controls with isolated
		# copies of those seed pieces, preserving original seed settings.
		while cropped.instances.size() < count:
			var index: int = cropped.instances.size()
			var copy: Dictionary = seed_source.instances[index % seed_source.instances.size()].duplicate(true)
			copy.id = "fixture-copy-%d" % index
			copy.position_cm[0] += 40000 * (1 + index / seed_source.instances.size())
			cropped.instances.append(copy)
		cropped.instances.resize(count)
		var ids: Array = cropped.instances.map(func(item): return item.id)
		cropped.connections = cropped.connections.filter(func(edge): return ids.has(edge.from) and ids.has(edge.to))
		for route: Dictionary in cropped.paths: route.pieces = route.pieces.filter(func(id): return ids.has(id))
		cropped.checkpoints = cropped.checkpoints.filter(func(cp): return ids.has(cp.piece))
		cropped.actions = cropped.actions.filter(func(action): return ids.has(action.piece) and (action.landing == null or ids.has(action.landing.piece)))
		cropped.attachments = cropped.attachments.filter(func(attachment): return ids.has(attachment.piece))
		return cropped
	var source: Dictionary = store.track_source()
	source.settings.circuit = false
	source.grounded_supports = grounded
	source.original_seed = source.settings.duplicate(true) if grounded else null
	source.instances = []
	source.connections = []
	source.paths = [{"id":"base", "pieces":[]}]
	source.checkpoints = []
	source.actions = []
	source.attachments = []
	for i in count:
		var item := {"id":"p-%d" % i, "preset":"straight", "position_cm":[0, 300 if grounded else 0, i * 800], "rotation_mdeg":[0,0,0], "width_cm":400, "entry_width_cm":400, "exit_width_cm":400, "control_points":[]}
		if i > 0:
			item = JSON.parse_string(store.bridge.snap_track_instance(JSON.stringify(item), JSON.stringify(source.instances.back()))).data
			source.connections.append({"from":"p-%d" % (i - 1), "to":item.id})
		source.instances.append(item)
		source.paths[0].pieces.append(item.id)
	source.checkpoints = [{"piece":"p-0", "sample":0}, {"piece":"p-%d" % (count - 1), "sample":1}]
	return source

func run() -> void:
	screen = EDITOR.new()
	root.add_child(screen)
	await process_frame
	var bench: Node = screen.track_workbench
	var source_path := OS.get_environment("TRACK_BENCH_SOURCE")
	if not source_path.is_empty():
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(source_path))
		assert(parsed is Dictionary and parsed.has("instances"), "invalid TRACK_BENCH_SOURCE")
		seeded_source = parsed
	elif OS.get_environment("TRACK_BENCH_SEED") == "1":
		var settings: Dictionary = bench.catalogue.defaults.duplicate(true)
		settings.seed = 42
		settings.duration_seconds = 90
		var generated: Dictionary = JSON.parse_string(screen.store.bridge.generate_track(JSON.stringify(settings), ProjectSettings.globalize_path("user://benchmark-seed.memap")))
		assert(generated.ok, str(generated.get("error", {})))
		seeded_source = JSON.parse_string(screen.store.bridge.track_authoring_source(JSON.stringify(generated.data.document))).data
	var output_path := OS.get_environment("TRACK_BENCH_SAVE_SOURCE")
	if not output_path.is_empty():
		assert(not seeded_source.is_empty() and not FileAccess.file_exists(output_path), "save source requires a new path")
		var output := FileAccess.open(output_path, FileAccess.WRITE)
		assert(output != null)
		output.store_string(JSON.stringify(seeded_source, "\t") + "\n")
		output.close()
		print("TRACK_BENCH_SAVED ", output_path)
		screen.queue_free()
		await process_frame
		quit()
		return
	print("TRACK_BENCH_INPUT ", JSON.stringify({"source":source_identity(seeded_source) if not seeded_source.is_empty() else {},
		"file_sha256":FileAccess.get_sha256(source_path) if not source_path.is_empty() else "",
		"editor_revision":OS.get_environment("TRACK_BENCH_EDITOR_REVISION"), "mapkit_revision":OS.get_environment("TRACK_BENCH_MAPKIT_REVISION"),
		"native_sha256":native_hash(), "godot":Engine.get_version_info().string}))
	for grounded in ([true] if OS.get_environment("TRACK_BENCH_PROBE") == "1" else [false, true]):
		for count in ([49] if OS.get_environment("TRACK_BENCH_PROBE") == "1" else [10, 25, 49]):
			screen.store.new_track()
			var source := fixture(screen.store, count, grounded, seeded_source)
			print("TRACK_BENCH_FIXTURE ", JSON.stringify({"count":count, "grounded":grounded, "source":source_identity(source)}))
			var failure: String = screen.store.edit_track(source)
			if failure != "": push_error(failure); quit(1); return
			await process_frame
			for repetition in (1 if OS.get_environment("TRACK_BENCH_PROBE") == "1" else 3):
				var timings: Array = []
				timings.append(await sample("selection", func(): bench.selection.item_selected.emit(repetition % count)))
				bench.add_piece("straight")
				bench.placement.preview_at(Vector3(100,0,0)) # Cold ghost preparation is separate.
				var pointer: Array = []
				for step in 30:
					var begin := Time.get_ticks_usec()
					bench.placement.preview_at(Vector3(100 + step,0,0))
					pointer.append((Time.get_ticks_usec() - begin) / 1000.0)
				bench.cancel_interaction()
				var origin: Vector3 = bench.PREVIEW.point(bench.source.instances[0].position_cm)
				if bench.placement.has_method("begin_move"): bench.placement.begin_move(0, origin)
				var drag: Array = []
				for step in (30 if bench.placement.has_method("begin_move") else 0):
					var begin := Time.get_ticks_usec()
					bench.placement.preview_at(origin + Vector3(step + 1, 0, 0))
					drag.append((Time.get_ticks_usec() - begin) / 1000.0)
				bench.cancel_interaction()
				var next: Dictionary = bench.source.duplicate(true)
				next.instances[0].position_cm[0] += 100
				timings.append(await sample("move", func(): bench._commit(next)))
				bench.selected = 0
				timings.append(await sample("add", bench.duplicate_piece))
				next = bench.source.duplicate(true)
				next.instances[0].exit_width_cm = 600 if repetition % 2 == 0 else 400
				timings.append(await sample("property", func(): bench._commit(next)))
				bench.selected = bench.source.instances.size() - 1
				timings.append(await sample("delete", bench.delete_piece))
				timings.append(await sample("undo", screen._history.bind(false)))
				timings.append(await sample("redo", screen._history.bind(true)))
				rows.append({"count":count, "grounded":grounded, "seed_generated":grounded and not seeded_source.is_empty(), "repeat":repetition, "timings":timings, "pointer_ms":pointer, "drag_ms":drag})
				await process_frame
	print("TRACK_BENCHMARK ", JSON.stringify(rows))
	screen.queue_free()
	await process_frame
	quit()
