extends SceneTree
const PANEL := preload("res://scripts/generation_panel.gd")
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool, label: String) -> void:
	if not value: failures.append(label);push_error(label)
func run() -> void:
	var panel := PANEL.new();root.add_child(panel)
	var owner := Control.new();root.add_child(owner);panel.build(owner)
	var preview: Control=panel.preview
	preview.document={"bounds":{"min":[0,0],"max":[25600,25600]},"roads":[{"id":"r","points":[[0,0,12800],[25600,0,12800]],"widths_cm":[600]}],"placements":[],"water_bodies":[]}
	var boundary := {"polygon":[[1000,1000],[10000,1000],[10000,10000],[1000,10000]],"holes":[[[2000,2000],[4000,2000],[4000,4000],[2000,4000]]]}
	preview.composition={"districts":[{"id":"centre","landuse":"residential","anchor":[60,60],"density":[.4,.9],"boundaries":[boundary]}],"road_hierarchy":{"r":"main"},"sites":[{"boundaries":[boundary],"entrances":[boundary]}],"protected":[{"boundaries":[boundary]}]}
	preview.diagnostics=[{"district":"centre","position_cm":[6000,6000],"error":"Blocked entrance"}]
	panel.popup_centered();preview.queue_redraw();await process_frame;await process_frame
	check(preview.project_point.is_valid(),"composition projects into the preview")
	check(preview._get_tooltip(preview.project_point.call([6000,6000])).contains("centre"),"diagnostic points retain their district and reason")
	check(preview.layers.size()==5,"district/road/parcel/protection/diagnostic overlays")
	check(panel.apply_button.disabled,"unvalidated preview cannot apply")
	for key: String in preview.layers:
		preview.layers[key]=false
	preview.queue_redraw();await process_frame
	panel.queue_free();owner.queue_free();await process_frame
	print("environment_preview_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
