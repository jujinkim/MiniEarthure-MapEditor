extends SceneTree
## Road course proposals stay unsaved until Save course to map seals one Undo step.
var failed := false
func check(value: bool, message: String) -> void:
	if not value:
		failed = true
		push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.store.new_track(true)
	var patches: Array = []
	var block := 10000
	for x in 4:
		for z in 4:
			patches.append({"field":"nodes","id":"n%d-%d" % [x,z],"before":null,"after":{"id":"n%d-%d" % [x,z],"position":[10000+x*block,0,10000+z*block],"level":0}})
			for step: Vector2i in [Vector2i(1,0),Vector2i(0,1)]:
				if x+step.x >= 4 or z+step.y >= 4: continue
				var id := "r%d-%d-%d%d" % [x,z,step.x,step.y]
				patches.append({"field":"roads","id":id,"before":null,"after":{"id":id,"from":"n%d-%d" % [x,z],"to":"n%d-%d" % [x+step.x,z+step.y],
					"points":[[10000+x*block,0,10000+z*block],[10000+(x+step.x)*block,0,10000+(z+step.y)*block]],"widths_cm":[800],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}})
	check(ui.store.apply_command("Roads",patches) == "","synthetic road grid applies: " + ui.status_label.text)
	ui.show_tool_group("course")
	var tools: Node = ui.course_tools
	var before: Dictionary = ui.store.document.duplicate(true)
	tools.binding = tools.token(); tools.circuit = true; tools.road_seconds = 60; tools.road_gimmicks = 0; tools.road_shortcuts = 0
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)),"circuit proposal applicable: %s" % [tools.road_proposal.get("diagnostics",[])])
	check(ui.store.document == before,"proposal never edits the document")
	check(tools.manual_course and tools.gates.size() >= 4 and Array(tools.gates[0].position_cm).map(func(v): return int(v)) == [15000,0,10000],"gates adopted from the start road")
	check(tools.start_direction == [1000000,0],"start direction follows the camera heading")
	check(tools.save_manual(),"road course saves: " + ui.status_label.text)
	var courses: Array = ui.store.document.get("courses",[])
	check(courses.size() == 1 and courses[0].definition.mode == "circuit" and Array(courses[0].definition.start_direction).map(func(v): return int(v)) == [1000000,0],"saved as an ordinary circuit course")
	check(ui.store.undo() == "" and ui.store.document.get("courses",[]).is_empty(),"one Undo removes the road course")
	tools.binding = tools.token(); tools.road_gimmicks = 4; tools.road_seed = 11; tools.road_shortcuts = 0
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)) and not tools.road_proposal.attachments.is_empty() and not tools.road_candidate.is_empty(),"gimmicks proposed: %s" % [tools.road_proposal.diagnostics])
	check(ui.store.document == before,"gimmick proposal never edits the document")
	check(tools.save_manual(),"road course with gimmicks saves: " + ui.status_label.text)
	check(ui.store.document.get("surface_attachments",[]).size() == tools.road_proposal.attachments.size() and ui.store.document.courses.size() == 1,"course and attachments saved together")
	check(ui.store.document.roads.any(func(r): return r.has("design")),"host roads aligned on save")
	check(ui.store.undo() == "" and ui.store.document == before,"one Undo removes course, alignments and gimmicks")
	tools.binding = tools.token(); tools.road_gimmicks = 0; tools.road_shortcuts = 2
	var roads_before: int = ui.store.document.roads.size()
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)) and not tools.road_proposal.shortcuts.is_empty(),"shortcuts proposed: %s" % [tools.road_proposal.diagnostics])
	check(ui.store.document == before,"shortcut proposal never edits the document")
	check(tools.save_manual(),"road course with shortcuts saves: " + ui.status_label.text)
	check(ui.store.document.roads.size() == roads_before + 3 * tools.road_proposal.shortcuts.size(),"shortcut roads and split halves saved")
	check(ui.store.undo() == "" and ui.store.document == before,"one Undo removes course and shortcuts")
	tools.binding = tools.token(); tools.circuit = false; tools.road_gimmicks = 0; tools.road_shortcuts = 0
	check(not tools.suggest_road(Vector3(900,0,-900),Vector3(1,0,0)) and tools.road_proposal.diagnostics[0].code == "E_ROAD_COURSE_START","far start reports a blocking diagnostic")
	ui.queue_free()
	await process_frame
	quit(1 if failed else 0)
