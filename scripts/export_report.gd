extends AcceptDialog
var summary: RichTextLabel
var overview: Control
var data := {}

func _ready() -> void:
	title = "Package validation and capacity"
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(650, 420)
	add_child(column)
	summary = RichTextLabel.new()
	summary.custom_minimum_size.y = 200
	summary.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(summary)
	overview = Control.new()
	overview.custom_minimum_size = Vector2(620, 190)
	overview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	overview.draw.connect(_draw_overview)
	column.add_child(overview)

func show_report(value: Dictionary) -> void:
	data = value
	summary.text = ("Validated files, seams, inventory and spatial index · %d cells / %d index references\n"
		+ "Compressed package: %d bytes\nBase including ZIP/manifest overhead: %d / %d bytes · %s\n"
		+ "User assets: %d compressed / %d expanded bytes\nBase data expanded: %d bytes · Total expanded: %d bytes\n"
		+ "Native validation estimate: %d bytes peak / %d retained (not measured RSS)\n"
		+ "Full 3D generation: %s · %.3f seconds\n"
		+ "Preview: 256 MiB work + 256 MiB / 4 cached cells; 8 ms/frame batch admission.\n"
		+ "2D overview: roads / buildings; source map and export ignore layer filters.") % [
		data.cell_count, data.index_references, data.package_bytes, data.base_package_bytes, data.base_target_bytes,
		"within 50 MB goal" if data.base_target_met else "over goal; reduce base data",
		data.user_asset_compressed_bytes, data.user_asset_bytes, data.base_data_bytes, data.expanded_bytes,
		data.validation_peak_bytes, data.retained_memory_bytes,
		"%d cells checked" % data.full_generation_cells if data.full_generation_cells > 0 else "not requested", data.seconds]
	overview.queue_redraw()
	popup_centered()

func _draw_overview() -> void:
	overview.draw_rect(Rect2(Vector2.ZERO, overview.size), Color("15181e"))
	if data.is_empty(): return
	var map: Dictionary = data.overview
	var low := Vector2(map.bounds.min[0], map.bounds.min[1])
	var span := Vector2(map.bounds.max[0], map.bounds.max[1]) - low
	var scale_factor := minf((overview.size.x - 20) / span.x, (overview.size.y - 20) / span.y)
	for building: Dictionary in map.buildings:
		for ring: Array in [building.footprint] + building.get("holes", []):
			var points := PackedVector2Array()
			for p: Array in ring: points.append(Vector2(10,10) + (Vector2(p[0], p[1]) - low) * scale_factor)
			points.append(points[0])
			overview.draw_polyline(points, Color("ffe14c"), 1.0)
	for road: Dictionary in map.roads:
		var points := PackedVector2Array()
		for p: Array in road.points: points.append(Vector2(10,10) + (Vector2(p[0], p[2]) - low) * scale_factor)
		overview.draw_polyline(points, Color("eeeeee"), 2.0)
