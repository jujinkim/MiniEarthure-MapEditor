extends SceneTree
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)
func models(node: Node) -> Array[Node3D]:
	var out: Array[Node3D] = []
	if node.has_meta("mapkit_asset_id"): out.append(node)
	for child: Node in node.get_children(): out.append_array(models(child))
	return out
func until(predicate: Callable) -> void:
	var end := Time.get_ticks_msec() + 15000
	while not predicate.call() and Time.get_ticks_msec() < end: await process_frame
	check(predicate.call(), "preview completes")
func run() -> void:
	var source := OS.get_environment("MINIEARTHURE_TEST_MEMAP")
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var inspected: Dictionary = JSON.parse_string(bridge.open_package(source))
	check(inspected.ok, "independent validated source")
	var directory := ProjectSettings.globalize_path("user://synthetic-assets")
	DirAccess.make_dir_recursive_absolute(directory)
	var zip := ZIPReader.new()
	check(zip.open(source) == OK, "synthetic fixture reader")
	# Only these known synthetic payloads are copied into this isolated test project.
	for name in ["document.json", "checker.png", "tetra.glb"]:
		var file := FileAccess.open(directory.path_join(name),FileAccess.WRITE)
		file.store_buffer(zip.read_file(name))
		file.close()
	zip.close()
	var ui: Node = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	check(ui.store.open_project(directory) == "", "Editor opens asset project")
	ui._document_changed()
	ui._preview()
	await until(func(): return not ui.busy)
	check(str(ui.status_label.text).begins_with("Preview ready"), "actual Editor preview attaches shared renderer: " + str(ui.status_label.text))
	check(models(ui.preview_world).size() == 2, "Editor displays both custom model instances")
	var model: Node3D = models(ui.preview_world)[0]
	var weak: WeakRef = weakref(model)
	var destination := directory.path_join("exported.memap")
	var exported: Dictionary = JSON.parse_string(bridge.export_project(directory,destination))
	check(exported.ok and exported.data.world_content_hash == inspected.data.world_content_hash, "Editor save/export preserves content including assets/materials")
	# Invalid replacement keeps the previous visible preview and original package.
	var file := FileAccess.open(directory.path_join("tetra.glb"),FileAccess.WRITE)
	file.store_buffer(PackedByteArray([0,1,2]))
	file.close()
	ui._preview()
	await until(func(): return not ui.busy)
	check(not str(ui.status_label.text).begins_with("Preview ready") and weak.get_ref() != null, "invalid asset replacement retains previous preview")
	check(JSON.parse_string(bridge.open_package(source)).data.package_sha256 == inspected.data.package_sha256, "original input is preserved")
	ui.store.dirty = false
	ui.queue_free()
	for _i in 3: await process_frame
	check(weak.get_ref() == null, "Editor releases model resources")
	print("asset_preview_validator: ", "PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
