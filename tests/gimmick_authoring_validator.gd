extends SceneTree
var failed := false
func _initialize() -> void: run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok: failed = true; push_error(label)
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.gimmick_panel
	var ramp: Dictionary = panel.draft()
	var entry_height := -INF
	for v: Array in ramp.parts[0].vertices:
		if v[2] == -225: entry_height = maxf(entry_height, v[1])
	check(entry_height == 0 and ramp.position[1] == 0, "new ramp has no entry step or floating placement")
	check(ui.store.apply_command("Ramp probe", [{"field":"gimmicks", "id":ramp.id, "before":null, "after":ramp}]) == "", "native validates current ramp")
	check(ui.store.undo() == "", "ramp probe restored")
	for i in panel.template.item_count:
		if panel.template.get_item_text(i) == "platform": panel.template.select(i)
	panel.load_controls(panel.templates.platform)
	panel.controls.X.value = 32
	panel.controls.Z.value = 32
	panel.controls.deltaY.value = 2
	panel.controls.period.value = 4
	panel.controls.time.value = 1
	panel.show_preview()
	var g: Dictionary = panel.draft()
	check(g.motion.delta_cm[1] == 200 and g.motion.period_ms == 4000,"declarative motion properties")
	check(panel.preview.get_child(0).position.y > 0.9,"preview clock moves platform")
	check(panel.preview.get_child(1).mesh.size.y >= 2,"full swept envelope preview")
	panel.save_record()
	check(ui.store.document.get("gimmicks",[]).size() == 1,"native validated save")
	panel.controls.period.value = 6
	panel.save_record()
	check(ui.store.document.gimmicks.size() == 1 and ui.store.document.gimmicks[0].motion.period_ms == 6000,"repeat save edits stable identity")
	check(ui.store.undo() == "" and ui.store.document.gimmicks[0].motion.period_ms == 4000,"document undo")
	check(ui.store.redo() == "" and ui.store.document.gimmicks[0].motion.period_ms == 6000,"document redo")
	for kind in ["target_speed","jump_height","air_ring","loop","cylinder"]:
		panel.before = {}
		for i in panel.template.item_count:
			if panel.template.get_item_text(i) == kind: panel.template.select(i)
		panel.load_controls(panel.templates[kind])
		panel.controls.X.value = 32
		panel.controls.Z.value = 32
		panel.controls.landing.value = 4
		panel.controls.pitch.value = 15
		panel.controls.roll.value = -12
		var candidate: Dictionary = panel.draft()
		check(candidate.rotation_mdeg[0] == 15000 and candidate.rotation_mdeg[2] == -12000,"full Euler controls")
		if candidate.has("effect"): check(candidate.effect.jump_height_cm == 300 and candidate.effect.strength_percent == 100,"effect defaults")
		check(ui.store.apply_command("Special",[{"field":"gimmicks","id":candidate.id,"before":null,"after":candidate}]) == "","save "+kind)
		check(ui.store.undo() == "" and ui.store.redo() == "","undo/redo "+kind)
		panel.show_preview()
		check(panel.preview.get_child(0).get_child_count()>0,"resolved preview "+kind)
	var pose: Transform3D = panel.surface_pose(Vector3(1,2,3),Vector3.LEFT,Vector3.FORWARD)
	check(pose.basis.y.is_equal_approx(Vector3.LEFT) and pose.origin==Vector3(1,2,3),"surface normal placement")
	var saved: String = ProjectSettings.globalize_path("user://special-roundtrip")
	var expected: Array = ui.store.document.gimmicks.duplicate(true)
	check(ui.store.save_project(saved) == "","save special project")
	var reopened := preload("res://scripts/document_store.gd").new()
	check(reopened.open_project(saved) == "" and reopened.document.gimmicks == expected,"reopen complete special parameters")
	ui._preview()
	var deadline := Time.get_ticks_msec()+15000
	while (ui.busy or ui.preview_cache.is_empty()) and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.preview_cache.is_empty(),"ordinary cell preview ready")
	if not ui.preview_cache.is_empty():
		check(ui.preview_cache.values()[0].root.get_children().any(func(n): return n.has_meta("gimmick_id")),"normal preview contains declared structures")
	ui.queue_free()
	await process_frame
	print("gimmick_authoring_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
