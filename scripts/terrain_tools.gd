extends RefCounted
## Heightmap import helpers shared by PNG and DEM adoption.
const PNG := preload("./terrain_png.gd")
const FILES := preload("./authoring_files.gd")
var store: RefCounted
var canvas: Control

func descriptor(cell: Vector2i) -> Dictionary:
	for record: Dictionary in store.document.heightmaps:
		if int(record.cell.x) == cell.x and int(record.cell.y) == cell.y: return record
	return {}

func _load(cell: Vector2i, _side: int, _expected: Dictionary = {}) -> Dictionary:
	var result: Dictionary = store.working_snapshot().tile(cell)
	return result.data if result.ok else {"error":store.reason(result)}

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
