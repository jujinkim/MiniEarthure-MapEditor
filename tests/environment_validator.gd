extends SceneTree
const UI := preload("res://scripts/editor_main.gd")
var failed := false
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	if not value: failed=true; push_error(message)
func run() -> void:
	var ui := UI.new()
	root.add_child(ui)
	await process_frame
	ui.author_panel.open()
	var panel: RefCounted = ui.author_panel.environment_panel
	check(panel != null,"public environment authoring panel")
	var original: Dictionary=ui.store.document.duplicate(true)
	panel.fields.architecture = func(): return "cycladic"
	panel.fields.climate = func(): return "mediterranean"
	panel.fields.settlement = func(): return "village"
	panel.fields.terrain = func(): return "coast"
	panel.regions.text = '[{"id":"canal","concept":"metropolis","architecture":"venetian","terrain":"canal","polygon":[[0,0],[1000,0],[1000,1000]]}]'
	panel._apply()
	check(ui.store.document.recipe_version==1 and ui.store.document.has("environment"),"current v1 environment profile")
	check(ui.store.document.environment.architecture == "cycladic" and ui.store.document.environment.terrain == "coast", "catalogue axes adopted")
	var accepted: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.undo()=="" and ui.store._signature(ui.store.document) == ui.store._signature(original),"undo restores the current original document")
	check(ui.store.redo()=="" and ui.store.document.environment==accepted.environment,"redo restores profile")
	ui.author_panel.open()
	panel=ui.author_panel.environment_panel
	panel.regions.text="[{}]"
	panel._apply()
	check(ui.store.document.environment==accepted.environment,"invalid region cannot mutate source")
	var before_style: Dictionary = ui.store.document.duplicate(true)
	check(ui.store.apply_command("Ground appearance", [{"field":"ground_style_id","before":null,"after":"ground/rock"}]) == "", "ground style is a document value")
	check(ui.store.document.ground_style_id == "ground/rock", "ground style retained")
	check(ui.store.undo() == "" and ui.store._signature(ui.store.document) == ui.store._signature(before_style), "ground style undo restores omission")
	check(ui.store.apply_command("Invalid ground appearance", [{"field":"ground_style_id","before":null,"after":"building/modern/office/glass"}]) != "", "cross-domain style rejected")
	check(ui.store._signature(ui.store.document) == ui.store._signature(before_style), "invalid style leaves source intact")
	ui.store.new_document()
	check(ui.store.apply_command("Synthetic region profile",[{"field":"environment","before":null,"after":accepted.environment}]) == "","synthetic free document profile")
	# One optimized record can contain solids on opposite sides of a new zone.
	var style := preload("res://scripts/regional_style.gd")
	var building := {"id":"classified","footprint":[[2000,2000],[3000,2000],[3000,3000],[2000,3000]],"base_cm":0,"height_cm":500,"roof":"flat","material":"concrete","usage":"residential","style_id":"building/cycladic/detached/whitewash","parts":[{"footprint":[[6000,2000],[7000,2000],[7000,3000],[6000,3000]]}]}
	var attribution := {"source":"synthetic regional","license":"MIT","notice":JSON.stringify({"adapter":"mapeditor-regional-v1","objects":[{"record_ids":["classified"],"evidence":{"architecture":"context:profile","material":"context:profile"}}]})}
	var install_error: String = ui.store.apply_command("Synthetic classified solids",[{"field":"buildings","id":"classified","before":null,"after":building},{"field":"attributions","id":ui.store.record_id("attributions",attribution),"before":null,"after":attribution}])
	check(install_error == "","install classified synthetic solids: "+install_error)
	var original_profile: Dictionary = ui.store.document.environment.duplicate(true)
	var changed_profile: Dictionary = original_profile.duplicate(true)
	changed_profile.regions = [{"id":"new-farm","concept":"countryside","architecture":"farm","polygon":[[1500,1500],[3500,1500],[3500,3500],[1500,3500]]}]
	var changed := style.patches(ui.store,original_profile,changed_profile)
	changed.append({"field":"environment","before":original_profile,"after":changed_profile})
	var style_error: String = ui.store.apply_command("Change regional architecture",changed)
	check(style_error == "","apply region style and split grouped solids atomically: "+style_error)
	check(ui.store.document.buildings.size() == 2 and ui.store.document.buildings.any(func(b):return b.style_id == "building/farm/detached/wood") and ui.store.document.buildings.any(func(b):return b.style_id == "building/cycladic/detached/whitewash"),"zone boundary keeps both individual footprints and styles")
	check(ui.store.undo() == "" and ui.store.document.buildings.size() == 1 and ui.store.document.buildings[0].parts.size() == 1,"one undo restores grouped solids and original style")
	ui.queue_free()
	for frame in 6: await process_frame
	print("environment_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
