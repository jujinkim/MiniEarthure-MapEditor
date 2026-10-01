extends AcceptDialog
const I18N := preload("./locale_text.gd")
var summary: RichTextLabel
var overview: Control
var data := {}

func _ready() -> void:
	title = I18N.t("Package validation and capacity")
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
	summary.text = (I18N.t("Validated files, seams, inventory and spatial index · %d cells / %d index references\n")
		+ I18N.t("Compressed package: %d bytes\nBase including ZIP/manifest overhead: %d / %d bytes · %s\n")
		+ I18N.t("User assets: %d compressed / %d expanded bytes\nBase data expanded: %d bytes · Total expanded: %d bytes\n")
		+ I18N.t("Native validation estimate: %d bytes peak / %d retained (not measured RSS)\n")
		+ I18N.t("Full 3D generation: %s · %.3f seconds\n")
		+ I18N.t("Preview: 256 MiB work + 256 MiB / 4 cached cells; 8 ms/frame batch admission.\n")
		+ I18N.t("2D overview: roads / buildings; source map and export ignore layer filters.")) % [
		data.cell_count, data.index_references, data.package_bytes, data.base_package_bytes, data.base_target_bytes,
		I18N.t("within 50 MB goal") if data.base_target_met else I18N.t("over goal; reduce base data"),
		data.user_asset_compressed_bytes, data.user_asset_bytes, data.base_data_bytes, data.expanded_bytes,
		data.validation_peak_bytes, data.retained_memory_bytes,
		I18N.t("%d cells checked") % data.full_generation_cells if data.full_generation_cells > 0 else I18N.t("not requested"), data.seconds]
	if data.get("format") == "mkregions":
		summary.text = (I18N.t("Indexed regional map · complete source audit · %d execution cells\n")
			+ I18N.t("Complete transfer: %d / 50,000,000 bytes · %s\n")
			+ I18N.t("Shared user assets: %d compressed / %d expanded bytes\n")
			+ I18N.t("All expanded records (including regional source copies): %d bytes\n")
			+ I18N.t("Audit allowance: %d bytes · retained index/overview: %d bytes\n")
			+ I18N.t("Largest regional validation allowance: %d bytes (generation is additional)\n")
			+ I18N.t("%.3f seconds · Logical allowances are separate from measured RSS.")) % [
			data.cell_count,data.package_bytes,I18N.t("within goal") if data.base_target_met else I18N.t("over goal"),
			data.user_asset_compressed_bytes,data.user_asset_bytes,data.expanded_bytes,
			data.validation_peak_bytes,data.retained_memory_bytes,data.source_peak_bytes,data.seconds]
	for key: String in data.get("chunk_costs",{}):
		var row: Dictionary = data.chunk_costs[key]
		summary.text += I18N.t("\nCell %s: %d objects / %d triangles / %d prisms / %d convexes · display %.1f MiB · work %.1f MiB estimated · %s") % [key,row.objects,row.triangles,row.building_prisms,row.asset_convexes,float(row.presentation_bytes)/1048576.0,float(row.work_bytes)/1048576.0,row.warning]
		var delay: Dictionary = data.get("preview_delays",{}).get(key,{})
		if delay.get("signature","") == row.signature: summary.text += I18N.t(" · measured preview %.2fs") % delay.seconds
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
