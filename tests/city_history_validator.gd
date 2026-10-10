extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const CODEC := preload("res://scripts/history_codec.gd")
var failures: Array[String] = []
func check(value: bool, message: String) -> void:
	if not value: failures.append(message); push_error(message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var store := STORE.new()
	store.new_track(true)
	var before: Dictionary = store.document.duplicate(true)
	var patches: Array = []
	for i in range(6000):
		var id := "city-building-%d" % i
		var x := 100+(i%100)*100
		var y := 100+(i/100)*100
		var record := {"id":id,"footprint":[[x,y],[x+40,y],[x+40,y+40],[x,y+40]],"base_cm":0,"height_cm":100,"usage":"residential","material":"concrete","roof":"flat"}
		patches.append({"field":"buildings","id":id,"before":null,"after":record})
	var last: Dictionary = patches[-1].after.duplicate(true)
	var changed := last.duplicate(true)
	changed.height_cm = 120
	patches.append({"field":"buildings","id":last.id,"before":last,"after":changed})
	patches.append({"field":"buildings","id":last.id,"before":changed,"after":null})
	patches.append({"field":"buildings","id":last.id,"before":null,"after":changed})
	var failure: String = store.apply_command("City batch",patches)
	check(failure=="","large indexed batch: "+failure)
	if failure != "": quit(1); return
	check(store.document.buildings.size()==6000 and store._get_value(store.document,"buildings",last.id).height_cm==120,"mixed add/update/remove retains last memento")
	check(store.undo_stack.size()==1 and store.undo_stack[0].has("packed_patches") and store.history_bytes < CODEC.THRESHOLD,"large city command retained compressed as one Undo")
	var after: Dictionary = store.document.duplicate(true)
	check(store.undo()=="" and store._signature(store.document)==store._signature(before),"compressed city Undo restores exact original")
	check(store.redo()=="" and store._signature(store.document)==store._signature(after),"compressed city Redo restores exact accepted geometry")
	var project := ProjectSettings.globalize_path("user://city-history")
	check(store.save_project(project)=="","save keeps compressed history readable")
	after = store.document.duplicate(true)
	var bad: Dictionary = store.undo_stack[0].duplicate(true)
	bad.expanded_bytes = CODEC.TEXT_LIMIT+1
	check(store._prepare_history(bad,true).has("error") and store.document==after,"expanded budget rejects before mutation")
	bad = store.undo_stack[0].duplicate(true)
	bad.digest = "0".repeat(64)
	check(store._prepare_history(bad,true).has("error") and store.document==after,"corrupt compressed command cannot change state")
	var original_height: Variant = store.document.buildings[0].height_cm
	store.document.buildings[0].height_cm = 999
	check(store.undo()!="" and store.undo_stack.size()==1,"stale compressed multi-record Undo is atomic")
	store.document.buildings[0].height_cm = original_height
	var duplicate: Dictionary = before.duplicate(true)
	duplicate.buildings = [last,last.duplicate(true)]
	check(store._apply(duplicate,[{"field":"buildings","id":last.id,"before":last,"after":changed}],false)!="","duplicate identity never resolves to an arbitrary record")
	print("city_history_validator: ","PASS" if failures.is_empty() else str(failures))
	quit(0 if failures.is_empty() else 1)
