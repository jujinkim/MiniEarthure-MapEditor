extends SceneTree
## Road course proposals stay unsaved until Save course to map seals one Undo step.
var failed := false
func check(value: bool, message: String) -> void:
	if not value:
		failed = true
		push_error(message)
func _initialize() -> void: run.call_deferred()
## Every edit, Undo included, restamps provenance.last_edited to the second; compare the rest.
func same(a: Dictionary, b: Dictionary) -> bool:
	var left := a.duplicate(true); var right := b.duplicate(true)
	left.provenance.erase("last_edited"); right.provenance.erase("last_edited")
	return left == right
## Node and road patches for an n×n street grid from (100 m, 100 m).
func grid(n: int, block: int, width: int) -> Array:
	var patches: Array = []
	for x in n:
		for z in n:
			patches.append({"field":"nodes","id":"n%d-%d" % [x,z],"before":null,"after":{"id":"n%d-%d" % [x,z],"position":[10000+x*block,0,10000+z*block],"level":0}})
			for step: Vector2i in [Vector2i(1,0),Vector2i(0,1)]:
				if x+step.x >= n or z+step.y >= n: continue
				var id := "r%d-%d-%d%d" % [x,z,step.x,step.y]
				patches.append({"field":"roads","id":id,"before":null,"after":{"id":id,"from":"n%d-%d" % [x,z],"to":"n%d-%d" % [x+step.x,z+step.y],
					"points":[[10000+x*block,0,10000+z*block],[10000+(x+step.x)*block,0,10000+(z+step.y)*block]],"widths_cm":[width],"surfaces":["asphalt"],"kind":"ground","clearance_cm":null,"sidewalk_cm":null}})
	return patches
func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	ui.store.new_track(true)
	check(ui.store.apply_command("Roads",grid(4,10000,800)) == "","synthetic road grid applies: " + ui.status_label.text)
	ui.show_tool_group("course")
	var tools: Node = ui.course_tools
	var before: Dictionary = ui.store.document.duplicate(true)
	tools.binding = tools.token(); tools.circuit = true; tools.road_seconds = 60; tools.road_gimmicks = 0; tools.road_shortcuts = 0
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)),"circuit proposal applicable: %s" % [tools.road_proposal.get("diagnostics",[])])
	check(same(ui.store.document,before),"proposal never edits the document")
	check(tools.manual_course and tools.gates.size() >= 4 and Array(tools.gates[0].position_cm).map(func(v): return int(v)) == [15000,0,10000],"gates adopted from the start road")
	check(tools.start_direction == [1000000,0],"start direction follows the camera heading")
	check(tools.save_manual(),"road course saves: " + ui.status_label.text)
	var courses: Array = ui.store.document.get("courses",[])
	check(courses.size() == 1 and courses[0].definition.mode == "circuit" and Array(courses[0].definition.start_direction).map(func(v): return int(v)) == [1000000,0],"saved as an ordinary circuit course")
	check(ui.store.undo() == "" and ui.store.document.get("courses",[]).is_empty(),"one Undo removes the road course")
	tools.binding = tools.token(); tools.road_gimmicks = 4; tools.road_seed = 11; tools.road_shortcuts = 0
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)) and not tools.road_proposal.attachments.is_empty() and not tools.road_candidate.is_empty(),"gimmicks proposed: %s" % [tools.road_proposal.diagnostics])
	check(same(ui.store.document,before),"gimmick proposal never edits the document")
	check(tools.save_manual(),"road course with gimmicks saves: " + ui.status_label.text)
	check(ui.store.document.get("surface_attachments",[]).size() == tools.road_proposal.attachments.size() and ui.store.document.courses.size() == 1,"course and attachments saved together")
	check(ui.store.document.roads.any(func(r): return r.has("design")),"host roads aligned on save")
	check(ui.store.undo() == "" and same(ui.store.document,before),"one Undo removes course, alignments and gimmicks")
	tools.binding = tools.token(); tools.road_gimmicks = 0; tools.road_shortcuts = 2
	var roads_before: int = ui.store.document.roads.size()
	check(tools.suggest_road(Vector3(150,0,-100),Vector3(1,0,0)) and not tools.road_proposal.shortcuts.is_empty(),"shortcuts proposed: %s" % [tools.road_proposal.diagnostics])
	check(same(ui.store.document,before),"shortcut proposal never edits the document")
	check(tools.save_manual(),"road course with shortcuts saves: " + ui.status_label.text)
	check(ui.store.document.roads.size() == roads_before + 3 * tools.road_proposal.shortcuts.size(),"shortcut roads and split halves saved")
	check(ui.store.undo() == "" and same(ui.store.document,before),"one Undo removes course and shortcuts")
	# One seed picks the start, direction and extras; its time/weather only drive the preview.
	tools.binding = tools.token(); tools.road_gimmicks = 2; tools.road_shortcuts = 1; tools.race_seed = 5
	check(tools.seed_race() and tools.gates.size() >= 2,"seeded race proposed: %s" % [tools.road_proposal.get("diagnostics",[])])
	var seeded: Dictionary = JSON.parse_string(ui.store.bridge.seed_road_course(JSON.stringify(before),JSON.stringify({"seed":5,"mode":"circuit","duration_seconds":60,"gimmicks":2,"shortcuts":1}))).data
	check(tools.gates == seeded.suggestion.gates and is_equal_approx(ui.preview_time.value,seeded.time_minutes/60.0),"seed gates and preview time adopted together")
	check(same(ui.store.document,before),"seeded race never edits the document before saving")
	check(tools.save_manual() and ui.store.document.courses.size() == 1,"seeded race saves: " + ui.status_label.text)
	check(ui.store.document.get("environment") == before.get("environment"),"seed time/weather stay out of the map environment")
	check(ui.store.undo() == "" and same(ui.store.document,before),"one Undo removes the seeded race")
	tools.binding = tools.token(); tools.circuit = false; tools.road_gimmicks = 0; tools.road_shortcuts = 0
	check(not tools.suggest_road(Vector3(900,0,-900),Vector3(1,0,0)) and tools.road_proposal.diagnostics[0].code == "E_ROAD_COURSE_START","far start reports a blocking diagnostic")
	# Narrow 1:8-style streets with buildings in every block corner: ground cuts are
	# blocked, so the corners receive elevated chords (stub, ramp/crest chord, stub).
	ui.store.new_track(true)
	var city := grid(6,6000,150)
	for x in 5:
		for z in 5:
			for corner: Vector2i in [Vector2i(0,0),Vector2i(1,0),Vector2i(0,1),Vector2i(1,1)]:
				var lo := Vector2i(10000+x*6000,10000+z*6000) + corner * 3700 + Vector2i(300,300)
				var id := "b%d-%d-%d%d" % [x,z,corner.x,corner.y]
				city.append({"field":"buildings","id":id,"before":null,"after":{"id":id,"footprint":[[lo.x,lo.y],[lo.x+1700,lo.y],[lo.x+1700,lo.y+1700],[lo.x,lo.y+1700]],
					"base_cm":0,"height_cm":80,"usage":"commercial","material":"concrete","roof":"flat"}})
	check(ui.store.apply_command("City",city) == "","synthetic city applies: " + ui.status_label.text)
	var city_before: Dictionary = ui.store.document.duplicate(true)
	tools.binding = tools.token(); tools.circuit = true; tools.road_seconds = 60; tools.road_gimmicks = 0; tools.road_shortcuts = 2
	check(tools.suggest_road(Vector3(130,0,-100),Vector3(1,0,0)) and not tools.road_proposal.shortcuts.is_empty(),"elevated shortcuts proposed: %s" % [tools.road_proposal.diagnostics])
	check(tools.road_proposal.shortcuts.all(func(s): return s.form != "ground"),"blocked corners use elevated forms")
	roads_before = ui.store.document.roads.size()
	check(tools.save_manual(),"road course with elevated shortcuts saves: " + ui.status_label.text)
	check(ui.store.document.roads.size() == roads_before + 5 * tools.road_proposal.shortcuts.size(),"stubs, elevated chords and split halves saved")
	check(ui.store.document.roads.any(func(r): return r.kind == "elevated" and str(r.id).begins_with("shortcut-")),"elevated chord saved")
	check(ui.store.undo() == "" and same(ui.store.document,city_before),"one Undo removes course and elevated shortcuts")
	if not failed: print("road_course_validator: PASS")
	ui.queue_free()
	await process_frame
	quit(1 if failed else 0)
