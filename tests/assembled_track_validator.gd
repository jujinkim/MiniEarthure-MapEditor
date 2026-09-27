extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const PANEL := preload("res://scripts/track_settings_panel.gd")
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failures.append(label); push_error(label)
func run() -> void:
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
	var current := ProjectSettings.globalize_path("user://track-project")
	check(store.save_project(current)=="","generated project saved")
	var reopened := STORE.new()
	check(reopened.open_project(current)=="" and reopened.document.assembled_track==store.document.assembled_track,"seed settings placements round trip")
	var panel := PANEL.new()
	root.add_child(panel)
	panel.restore(reopened.document.assembled_track.settings)
	check(JSON.parse_string(JSON.stringify(panel.settings()))==JSON.parse_string(JSON.stringify(settings)),"generator controls restore settings")
	panel.free()
	print("assembled_track_validator: ","PASS" if failures.is_empty() else str(failures))
	quit(0 if failures.is_empty() else 1)
