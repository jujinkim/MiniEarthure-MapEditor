extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const PANEL := preload("res://scripts/track_settings_panel.gd")
class MissingGroupsPanel extends "res://scripts/track_settings_panel.gd":
	func _load_catalogue() -> Dictionary:
		var catalogue := super._load_catalogue()
		catalogue.erase("selection_groups")
		return catalogue

var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failures.append(label); push_error(label)
func run() -> void:
	var mismatched := MissingGroupsPanel.new()
	root.add_child(mismatched)
	check(not mismatched.catalogue_ready and mismatched.selections.is_empty(), "mismatched native catalogue disables generation")
	check(mismatched.note.text.contains("다시 실행"), "mismatched native catalogue shows restart guidance")
	check(mismatched.settings().is_empty(), "mismatched catalogue cannot submit settings")
	mismatched.restore({})
	mismatched.free()
	var store := STORE.new()
	store.new_document()
	var old_path := ProjectSettings.globalize_path("user://original")
	check(store.save_project(old_path)=="","original save")
	var original_bytes := FileAccess.get_file_as_bytes(old_path.path_join("document.json"))
	check(store.apply_command("Seed",[{"field":"seed","id":"","before":store.document.seed,"after":113}])=="","unsaved source")
	var recovery := store.recovery_path()
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var settings: Dictionary = JSON.parse_string(bridge.track_catalogue()).data.defaults
	settings.seed=42
	var generated: Dictionary = JSON.parse_string(bridge.generate_track(JSON.stringify(settings),ProjectSettings.globalize_path("user://generated.memap")))
	check(generated.ok,"generation")
	for g: Dictionary in generated.data.document.gimmicks:
		if not g.has("track"): continue
		var bounds: Dictionary = JSON.parse_string(bridge.special_track_bounds(JSON.stringify(g.track)))
		check(bounds.ok,"native shared track bounds")
		for axis in 3:
			check(g.safety_min_cm[axis]<=g.position[axis]-bounds.data.radius_cm and g.safety_max_cm[axis]>=g.position[axis]+bounds.data.radius_cm,"swept source envelope")
	check(store.open_generated(generated.data.document)=="" and store.project_path=="" and store.dirty,"new unsaved document")
	check(FileAccess.get_file_as_bytes(old_path.path_join("document.json"))==original_bytes,"original file preserved")
	var recovered := STORE.new()
	check(recovered.recover(recovery)=="" and recovered.document.seed==113,"unsaved source retained in recovery")
	check(not store.document.free_roam,"generated maps default to normal finish presentation")
	var original_course: String = store.document.courses[0].course_id
	check(store.set_free_roam(true)=="" and store.document.free_roam,"generated finish policy edit")
	check(store.document.courses[0].course_id!=original_course,"course rebound to updated content hash")
	check(store.undo()=="" and not store.document.free_roam and store.document.courses[0].course_id==original_course,"policy and course hash undo together")
	check(store.redo()=="" and store.document.free_roam,"policy redo")
	check(store.autosave()=="","policy recovery snapshot saved")
	var recovered_policy := STORE.new()
	var recovery_error := recovered_policy.recover(store.recovery_path())
	check(recovery_error=="" and recovered_policy.document.free_roam,"recovery includes policy: "+recovery_error)
	var current := ProjectSettings.globalize_path("user://track-project")
	check(store.save_project(current)=="","generated project saved")
	var reopened := STORE.new()
	check(reopened.open_project(current)=="" and reopened.document.assembled_track==store.document.assembled_track,"seed settings placements round trip")
	check(reopened.document.free_roam,"saved policy retained")
	var panel := PANEL.new()
	root.add_child(panel)
	check(panel.catalogue_ready and panel.selections.has("cylinder") and not panel.selections.has("cylinder_curve"), "current catalogue exposes one cylinder family")
	panel.restore(reopened.document.assembled_track.settings)
	check(JSON.parse_string(JSON.stringify(panel.settings()))==JSON.parse_string(JSON.stringify(settings)),"generator controls restore settings")
	check(panel.selections.has("sprint_lane"),"32m sprint selection")
	check(not panel.selections.has("slope_up") and not panel.selections.has("curve_left_down"),"ordinary grades are not gimmick choices")
	panel.show_result(reopened.document.assembled_track)
	check(panel.note.text.contains("일반도로 직선") and panel.note.text.contains("예상"),"actual duration and ordinary distance ratio")
	check(panel.note.text.contains("길이") and panel.note.text.contains("초과") and not panel.note.text.contains("목표"),"length and overrun shown without ratio target")
	panel.free()
	print("assembled_track_validator: ","PASS" if failures.is_empty() else str(failures))
	quit(0 if failures.is_empty() else 1)
