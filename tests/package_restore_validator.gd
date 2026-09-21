extends "./preview_export_validator.gd"

func run() -> void:
	root.size = Vector2i(1440,900)
	ui = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	await process_frame
	ui.preview_enabled = false
	ui.preview_due = 0
	var source := ProjectSettings.globalize_path("user://package-original")
	ok(ui.store.save_project(source),"save original source")
	var image := Image.create(4,4,false,Image.FORMAT_RGBA8)
	image.fill(Color.CORNFLOWER_BLUE)
	var bytes := image.save_png_to_buffer()
	var asset_path := "editor/"+FILES.digest(bytes)+".png"
	var asset := {"id":"preserved-image","path":asset_path,"attribution":{"source":"Synthetic regional fixture","license":"MIT","notice":"Original"},"collision":[{"center":[0,100,0],"size_cm":[200,200,200]}]}
	ok(FILES.apply(ui.store,"asset",[{"field":"assets","id":asset.id,"before":null,"after":asset}],{asset_path:bytes}),"source payload")
	ok(ui.store.save_project(source),"save source payload")
	var canonical: String = SNAPSHOT.capture(ui.store.document,source).data.canonical
	var destination := ProjectSettings.globalize_path("user://editor-package.memap")
	ui.regional_grouping.value = 1
	ui._start_package("export",destination)
	ui._cancel_operation()
	await wait_work()
	check(not FileAccess.file_exists(destination),"cancelled regional export never publishes")
	ui._start_package("export",destination)
	await wait_work()
	check(FileAccess.file_exists(destination),"actual Editor regional export")
	check(ui.last_export_report.get("package_bytes", 0) > 0, "validated package report")
	check(ui.last_export_report.package_bytes == FileAccess.get_file_as_bytes(destination).size(),"complete transfer bytes include shared assets")
	check(ui.store.project_path == source and SNAPSHOT.capture(ui.store.document,source).data.canonical == canonical,"export preserves editable source")
	ui.export_report.hide()
	var digest := FileAccess.get_sha256(destination)
	ui._start_package("export",destination)
	check(not ui.busy and FileAccess.get_sha256(destination) == digest,"existing regional artifact preserved")
	ui.dialog_action = "reopen_package"
	ui._path_selected(destination)
	await wait_work()
	check(ui.store.project_path == destination+".source","actual reopen adopts new restored project")
	check(ui.store.bridge.canonical_document() == canonical,"canonical source survives export and reopen")
	check(FileAccess.get_file_as_bytes(ui.store.project_path.path_join(asset_path)) == bytes,"unused original asset preserved exactly")
	ui.dialog_action = "reopen_package"
	ui._path_selected(destination)
	check(not ui.busy and ui.store.project_path == destination+".source","existing restored project never overwritten")
	var corrupt := ProjectSettings.globalize_path("user://corrupt.memap")
	var damaged := FileAccess.get_file_as_bytes(destination)
	damaged[-1] = damaged[-1] ^ 1
	ok(FILES.write_new(corrupt,damaged),"damaged fixture")
	ui._path_selected(corrupt)
	await wait_work()
	check(ui.store.bridge.canonical_document() == canonical and not DirAccess.dir_exists_absolute(corrupt+".source"),"failed audit preserves current document and publishes no project")
	check(FileAccess.get_file_as_bytes(source.path_join(asset_path)) == bytes,"original files retained")
	var cancelled := WORK.new()
	cancelled.cancel()
	var cancel_path := destination + ".cancelled"
	check(not cancelled.reopen_package(destination, cancel_path).ok and not DirAccess.dir_exists_absolute(cancel_path), "pre-cancel never restores files")
	# Complete a restore after the requesting document generation was superseded.
	var late_path := ProjectSettings.globalize_path("user://late-package.memap")
	ok(FILES.write_new(late_path, FileAccess.get_file_as_bytes(destination)), "late-result fixture")
	ui.set_process(false)
	ui.dialog_action = "reopen_package"
	ui._path_selected(late_path)
	ui.generation += 1
	var deadline := Time.get_ticks_msec() + 20000
	while ui.worker.is_alive() and Time.get_ticks_msec() < deadline: await create_timer(0.002).timeout
	check(not ui.worker.is_alive(), "late restore completes")
	ui._process(0)
	ui.set_process(true)
	check(ui.store.project_path == destination + ".source" and ui.store.bridge.canonical_document() == canonical, "late restored project does not replace active document")
	check(FileAccess.file_exists(late_path + ".source/document.json"), "completed late restore remains available to user")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
	print("package_restore_validator: PASS (",checks," checks; export, full audit, cancel, reopen, unused payload, corruption, no overwrite)")
	quit(0)
