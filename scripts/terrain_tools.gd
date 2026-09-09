extends RefCounted
const PNG := preload("./terrain_png.gd")
const FILES := preload("./authoring_files.gd")
const MAX_SAMPLES := 1000000
const MAX_TILES := 16
var store: RefCounted
var canvas: Control
var stroke: Array[Vector2] = []
var signature := ""
var settings := {}
var active := false

func begin(point: Vector2, options: Dictionary) -> String:
	cancel()
	if canvas != null and not canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true): return "Show and unlock the terrain layer before authoring."
	if store.project_path.is_empty(): return "Save the project before painting terrain."
	var spacing := int(options.spacing_cm)
	if spacing < 200 or int(store.document.cell_size_cm) % spacing != 0: return "Grid spacing must divide the cell size and be at least 2 m."
	for descriptor: Dictionary in store.document.heightmaps:
		if int(descriptor.spacing_cm) != spacing: return "Choose the existing heightmap spacing; resampling is an explicit import operation."
	var failure: String = store.begin_gesture("Terrain stroke")
	if failure != "": return failure
	signature = store._signature(store.document)
	settings = options.duplicate(true)
	stroke.append(point.round())
	active = true
	return ""

func sample(point: Vector2) -> String:
	if not active: return ""
	if stroke.size() >= 2048: return "Terrain stroke exceeds 2048 points; release and start another stroke."
	if stroke.back().distance_to(point) >= 1: stroke.append(point.round())
	return ""

func cancel() -> void:
	if active and store != null: store.cancel_gesture()
	active = false
	stroke.clear()

func finish() -> String:
	if not active: return ""
	if store._signature(store.document) != signature or not store.has_gesture():
		cancel()
		return "Terrain stroke is stale; nothing was changed."
	var plan := _plan()
	cancel()
	if plan.has("error"): return plan.error
	return FILES.apply(store, "Terrain " + str(settings.mode), plan.patches, plan.blobs, plan.get("cells", []))

func descriptor(cell: Vector2i) -> Dictionary:
	for record: Dictionary in store.document.heightmaps:
		if int(record.cell.x) == cell.x and int(record.cell.y) == cell.y: return record
	return {}

func _load(cell: Vector2i, side: int) -> Dictionary:
	var record := descriptor(cell)
	if record.is_empty():
		var heights := PackedInt64Array()
		heights.resize(side * side)
		heights.fill(int(store.document.terrain_base_cm))
		return {"heights": heights}
	var source := FILES.read(store.project_path.path_join(record.path), PNG.MAX_BYTES)
	if source.has("error"): return source
	return PNG.decode(source.bytes, side, int(record.offset_cm), int(record.step_cm))

func _plan() -> Dictionary:
	var doc: Dictionary = store.document
	var cell_size := int(doc.cell_size_cm)
	var spacing := int(settings.spacing_cm)
	var side := cell_size / spacing + 1
	var radius := float(settings.radius_cm)
	if radius < spacing or radius > cell_size * 2: return {"error": "Brush radius must be at least one sample and at most two cells."}
	var area := Rect2(stroke[0], Vector2.ZERO)
	for point in stroke: area = area.expand(point)
	area = area.grow(radius)
	var origin := Vector2(doc.bounds.min[0], doc.bounds.min[1])
	var count := Vector2i(ceili(float(doc.bounds.max[0] - doc.bounds.min[0]) / cell_size), ceili(float(doc.bounds.max[1] - doc.bounds.min[1]) / cell_size))
	# Closed boundaries include BOTH owners. Identical world samples get identical edits.
	var first := Vector2i(floori((area.position.x - origin.x - 1) / cell_size), floori((area.position.y - origin.y - 1) / cell_size)).max(Vector2i.ZERO)
	var last := Vector2i(floori((area.end.x - origin.x) / cell_size), floori((area.end.y - origin.y) / cell_size)).min(count - Vector2i.ONE)
	var tiles := (last.x - first.x + 1) * (last.y - first.y + 1)
	if first.x > last.x or first.y > last.y: return {"error": "Brush is outside map bounds."}
	if tiles > MAX_TILES or tiles * side * side > MAX_SAMPLES or tiles * side * side * stroke.size() > 8000000: return {"error": "Brush exceeds the 16 tile / one million sample operation budget; use a smaller stroke."}
	var patches: Array = []
	var blobs := {}
	var loaded := {}
	for cy in range(first.y, last.y + 1):
		for cx in range(first.x, last.x + 1):
			var cell := Vector2i(cx, cy)
			var source := _load(cell, side)
			if source.has("error"): return source
			loaded[cell] = source.heights
	for cell: Vector2i in loaded:
		var heights: PackedInt64Array = loaded[cell].duplicate()
		var changed := false
		for y in range(side):
			for x in range(side):
				var position := origin + Vector2(cell.x * cell_size + x * spacing, cell.y * cell_size + y * spacing)
				var distance := position.distance_to(stroke[0])
				for i in range(stroke.size() - 1): distance = minf(distance, position.distance_to(Geometry2D.get_closest_point_to_segment(position, stroke[i], stroke[i + 1])))
				if distance >= radius: continue
				var weight := 1.0 - distance / radius
				var index := y * side + x
				var before := heights[index]
				var target := before
				match str(settings.mode):
					"raise": target += int(settings.amount_cm)
					"lower": target -= int(settings.amount_cm)
					"flatten": target = int(settings.target_cm)
					"smooth":
						var sum := 0
						for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
							var global_sample: Vector2i = Vector2i(cell.x * (side - 1) + x, cell.y * (side - 1) + y) + offset
							var neighbor := Vector2i(clampi(global_sample.x / (side - 1), 0, count.x - 1), clampi(global_sample.y / (side - 1), 0, count.y - 1))
							if not loaded.has(neighbor):
								# Smooth uses flat terrain outside the touched tile set only when no raster exists.
								if not descriptor(neighbor).is_empty(): return {"error": "Smooth needs neighboring raster context; extend the stroke radius to include that tile."}
								sum += int(doc.terrain_base_cm)
							else:
								var nx := clampi(global_sample.x - neighbor.x * (side - 1), 0, side - 1)
								var ny := clampi(global_sample.y - neighbor.y * (side - 1), 0, side - 1)
								sum += int(loaded[neighbor][ny * side + nx])
						target = roundi(float(sum) / 4)
					_: return {"error": "Unknown terrain brush mode."}
				heights[index] = roundi(lerpf(before, target, weight))
				changed = changed or heights[index] != before
		if not changed: continue
		var encoded := PNG.encode(heights, side)
		if encoded.has("error"): return encoded
		var before := descriptor(cell)
		var after := before.duplicate(true) if not before.is_empty() else {"cell": {"x": cell.x, "y": cell.y}, "spacing_cm": spacing, "source_accuracy_cm": null}
		after.path = "editor/" + FILES.digest(encoded.bytes) + ".png"
		after.offset_cm = encoded.offset_cm
		after.step_cm = encoded.step_cm
		blobs[after.path] = encoded.bytes
		patches.append({"field": "heightmaps", "id": store.record_id("heightmaps", after), "before": null if before.is_empty() else before, "after": after})
	return {"patches": patches, "blobs": blobs, "cells": loaded.keys() if not doc.roads.is_empty() else []}

func import_png(path: String, cell: Vector2i, spacing: int, offset: int, step: int, accuracy: int, attribution: Dictionary) -> String:
	if canvas != null and not canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true): return "Show and unlock the terrain layer before importing."
	var source := FILES.read(path, PNG.MAX_BYTES)
	if source.has("error"): return source.error
	if spacing < 200 or int(store.document.cell_size_cm) % spacing != 0: return "Invalid full-cell grid spacing."
	var decoded := PNG.decode(source.bytes, int(store.document.cell_size_cm) / spacing + 1, offset, step)
	if decoded.has("error"): return decoded.error
	var before := descriptor(cell)
	var record := {"cell": {"x": cell.x, "y": cell.y}, "path": "editor/" + FILES.digest(source.bytes) + ".png", "spacing_cm": spacing, "offset_cm": offset, "step_cm": step, "source_accuracy_cm": accuracy if accuracy > 0 else null}
	var patches: Array = [{"field": "heightmaps", "id": store.record_id("heightmaps", record), "before": null if before.is_empty() else before, "after": record}]
	var key: String = store.record_id("attributions", attribution)
	if store._get_value(store.document, "attributions", key) == null: patches.append({"field": "attributions", "id": key, "before": null, "after": attribution})
	return FILES.apply(store, "Import heightmap", patches, {record.path: source.bytes}, [cell] if not store.document.roads.is_empty() else [])
