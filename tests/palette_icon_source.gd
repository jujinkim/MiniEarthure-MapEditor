extends SceneTree
## Development-only input for original static SVG tile artwork; no user map IO.
func _initialize() -> void:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var catalogue: Dictionary = JSON.parse_string(bridge.track_catalogue()).data
	var paths := {}
	for entry: Dictionary in catalogue.entries:
		var width := 400 if entry.widths_cm.any(func(value): return int(value) == 400) else int(entry.widths_cm[0])
		var item := {"id":"icon", "preset":entry.id, "position_cm":[0,0,0], "rotation_mdeg":[0,0,0], "width_cm":width, "entry_width_cm":width, "exit_width_cm":width, "control_points":[]}
		if entry.id in ["free_curve", "flight_curve"]: item.control_points = [[0,0,0], [0,0,600], [600,0,1200], [1200,0,1200]]
		var result: Dictionary = JSON.parse_string(bridge.track_instance(JSON.stringify(item)))
		assert(result.ok)
		paths[entry.id] = result.data.path
	var output := OS.get_environment("MAPEDITOR_ICON_SOURCE")
	assert(output != "")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(paths))
	file.close()
	print("palette_icon_source: PASS")
	quit()
