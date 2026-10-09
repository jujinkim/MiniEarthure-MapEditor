extends RefCounted
## Timed in-memory brush session. finish records a command; only Save encodes PNG.
const PNG := preload("./terrain_png.gd")
const FILES := preload("./authoring_files.gd")
const MAX_SAMPLES := 1000000
var store: RefCounted
var canvas: Control
var stroke: Array[Vector2] = []
var settings := {}
var active := false
var point := Vector2.ZERO
var last_usec := 0
var session := -1
var epoch := -1
var working: RefCounted

func begin(at: Vector2, options: Dictionary) -> String:
	cancel()
	if canvas != null and not canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true): return "Show and unlock the terrain layer before authoring."
	var failure: String = store.begin_gesture("Terrain stroke")
	if failure != "": return failure
	working = store.working_snapshot()
	settings = {"mode":options.get("mode","raise"),"radius_cm":options.get("radius_cm",1600),
		"rate_cm_s":options.get("rate_cm_s",200),"steepness":options.get("steepness",0.5),
		"strength":options.get("strength",0.5),"target_cm":options.get("target_cm",0) if options.get("numeric_target",false) else null}
	var result: Dictionary = JSON.parse_string(working.begin_brush(at, JSON.stringify(settings)))
	if not result.ok:
		store.cancel_gesture()
		return store.reason(result)
	point = at
	stroke = [at]
	last_usec = Time.get_ticks_usec()
	session = store.session_id
	epoch = store.command_epoch
	active = true
	store.active_terrain = self
	return ""

func step(at: Vector2, seconds: float) -> String:
	if not active: return ""
	if store.session_id != session or store.command_epoch != epoch:
		cancel()
		return "Terrain stroke is stale; nothing was changed."
	var result: Dictionary = working.step_brush(at, seconds)
	if not result.ok:
		var failure: String = store.reason(result)
		cancel()
		return failure
	point = at
	stroke = [at]
	if not result.data.cells.is_empty(): store.terrain_preview(Array(result.data.cells))
	return ""

func sample(at: Vector2) -> String:
	var now := Time.get_ticks_usec()
	var failure := step(at, maxf(0, now-last_usec)/1000000.0)
	last_usec = now
	return failure

func tick() -> String: return sample(point) if active else ""
func preview() -> RefCounted: return working.fork()

func cancel() -> void:
	if active and store != null:
		working.cancel_brush()
		store.cancel_gesture()
		store.active_terrain = null
		store.dirty = store._signature(store.document) != store._saved_signature or working.has_changes()
		store.dirty_changed.emit()
		store.terrain_revision += 1
		store.terrain_preview_changed.emit([])
	active = false
	stroke.clear()

func finish() -> String:
	if not active: return ""
	var failure := tick()
	if failure != "": return failure
	var delta: PackedInt32Array = working.finish_brush()
	active = false
	stroke.clear()
	store.active_terrain = null
	store.cancel_gesture()
	if delta.is_empty(): return store.install_terrain_command(delta, store.document.get("water_bodies", []))
	if not store.document.get("water_bodies", []).is_empty() or not store.document.get("roads",[]).is_empty() or store.document.get("assembled_track") is Dictionary:
		failure = store.start_water(Vector2.ZERO, false, true, delta)
	else: failure = store.install_terrain_command(delta, [])
	if failure != "":
		working.apply_delta(delta, true)
		store.dirty = store._signature(store.document) != store._saved_signature or working.has_changes()
		store.dirty_changed.emit()
		store.terrain_revision += 1
		store.terrain_preview_changed.emit([])
	return failure

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
