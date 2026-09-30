extends RefCounted
## Source launch from Client does not run Godot's import scan. Register the
## installed extension before any document store or private worker is created.
const EXTENSION := "res://addons/mapkit/mapkit.gdextension"
const REQUIRED_METHODS := ["validate_document", "track_catalogue", "track_authoring_source", "compile_track_source", "track_instance", "snap_track_instance", "generate_track"]

static func ensure_loaded() -> String:
	if not GDExtensionManager.is_extension_loaded(EXTENSION):
		var status := GDExtensionManager.load_extension(EXTENSION)
		if status not in [GDExtensionManager.LOAD_STATUS_OK, GDExtensionManager.LOAD_STATUS_ALREADY_LOADED]:
			return "Cannot load the MapKit extension (status %d): %s" % [status, EXTENSION]
	if not ClassDB.can_instantiate(&"MapKitBridge"):
		return "The loaded MapKit extension does not provide MapKitBridge."
	if not ClassDB.can_instantiate(&"MapKitWorkToken"):
		return "The loaded MapKit extension does not provide MapKitWorkToken."
	for method: String in REQUIRED_METHODS:
		if not ClassDB.class_has_method(&"MapKitBridge", method):
			return "The loaded MapKit extension is missing the required method: " + method
	var bridge: RefCounted = ClassDB.instantiate(&"MapKitBridge")
	var result: Variant = JSON.parse_string(bridge.call("track_catalogue"))
	if not result is Dictionary or result.get("ok") != true or not result.get("data") is Dictionary:
		return "MapKit did not return a valid track catalogue."
	var catalogue: Dictionary = result.data
	if not catalogue.get("entries") is Array or not catalogue.get("obstacle_kinds") is Array or not catalogue.get("selection_ids") is Array or not catalogue.get("defaults") is Dictionary or not catalogue.get("duration_options") is Dictionary:
		return "The MapKit track catalogue does not match this editor."
	return ""
