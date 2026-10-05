extends SceneTree
const PANEL := preload("res://scripts/track_settings_panel.gd")
var failed := false
func check(ok:bool,label:String) -> void:
	if not ok: failed=true;push_error(label)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	seed(373)
	var expected := randi()
	seed(373)
	var panel := PANEL.new()
	root.add_child(panel)
	check(panel.catalogue_ready and panel.seed_input.text==str(expected),"new panel initializes exactly one random seed")
	check(int(panel._defaults.seed)==1,"MapKit default remains one")
	panel.seed_input.text="731"
	var settings: Dictionary=panel.settings()
	panel.set_busy(true);panel.cancelled.emit();panel.set_busy(false)
	panel.show_result({"estimated_msec":60000,"length_cm":54000,"settings":settings})
	check(panel.settings()==settings,"busy/cancel/result preserves inputs")
	panel.restore(settings)
	check(panel.seed_input.text=="731","explicit restoration preserves seed")
	check(panel.time_input.item_count==6,"six named times")
	panel.time_input.value=12.6
	check(panel.time_input.value==12.6 and panel.settings().time_minutes==756,"authored minutes preserved")
	panel.time_input.value=23.8
	check(panel.time_input.value==23.8 and panel.settings().time_minutes==1428,"late authored minutes preserved")
	for index in 6:
		panel.time_input.select(index);panel.time_input.item_selected.emit(index)
		check(panel.settings().time_minutes==[540,720,1020,1080,1260,360][index],"preset numeric time")
	panel.queue_free();await process_frame
	print("track_settings_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
