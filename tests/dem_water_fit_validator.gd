extends SceneTree
## Imported city water fitted to a two-cell DEM: a gentle west cell and a
## steep east cell, a lake of two touching pieces, a stream of two touching
## pieces on the slope and a pond beside a ground road.
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const PNG := preload("res://scripts/terrain_png.gd")
const FIT := preload("res://scripts/dem_water_fit.gd")
const LAYER := "w"
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func prefix() -> String: return "import-" + LAYER.repeat(32) + "-"
func terrain(i: int, _j: int) -> int: return 1000 + i * 2 if i <= 32 else 1064 + (i - 32) * 20
func body(name: String, x0: int, z0: int, x1: int, z1: int) -> Dictionary:
	return {"id":prefix() + name, "polygon":[[x0, z0], [x1, z0], [x1, z1], [x0, z1]], "islands":[], "surface_cm":3, "bottom_cm":-57, "flow_cm_s":[0, 0]}

func heightmaps() -> Dictionary:
	var records: Array = []
	var blobs := {}
	for cx in range(2):
		var heights := PackedInt64Array()
		for j in range(33):
			for i in range(33): heights.append(terrain(cx * 32 + i, j))
		var encoded := PNG.encode(heights, 33)
		var path := "editor/" + FILES.digest(encoded.bytes) + ".png"
		records.append({"cell":{"x":cx, "y":0}, "path":path, "spacing_cm":400, "offset_cm":encoded.offset_cm, "step_cm":1, "source_accuracy_cm":null})
		blobs[path] = encoded.bytes
	return {"records":records, "blobs":blobs}

func samples(store: RefCounted, dem: Dictionary, points: Array) -> Array:
	var native: RefCounted = store.working_snapshot().fork()
	var thin: Dictionary = store.document.duplicate(true)
	for field in ["nodes", "roads", "attributions", "water_bodies"]: thin[field] = []
	thin.heightmaps = dem.records
	JSON.parse_string(native.set_document(JSON.stringify(thin), store.project_path))
	JSON.parse_string(native.provide_resources(dem.blobs))
	return points.map(func(point: Vector2) -> int: return int(JSON.parse_string(native.height(point)).data.height))

func run() -> void:
	var store := STORE.new()
	store.new_document()
	var frame := {"mode":"wgs84-utm", "origin":[9.5, 55.5], "local_origin_m":[0.0, 0.0]}
	var notice := {"source":"synthetic OSM", "license":"CC0", "notice":JSON.stringify({"adapter":"osm-extract-v1", "layer_id":LAYER.repeat(32), "coordinates":frame, "authored_units":{"source_denominator":3}})}
	var setup: Array = [
		{"field":"bounds", "before":store.document.bounds.duplicate(true), "after":{"min":[0, 0], "max":[25600, 12800]}},
		{"field":"cell_size_cm", "before":store.document.cell_size_cm, "after":12800},
		{"field":"attributions", "id":store.record_id("attributions", notice), "before":null, "after":notice}]
	for node: Dictionary in [{"id":prefix() + "osm-ground-node-n", "position":[12800, 0, 200], "level":0}, {"id":prefix() + "osm-ground-node-s", "position":[12800, 0, 12600], "level":0}]:
		setup.append({"field":"nodes", "id":node.id, "before":null, "after":node})
	setup.append({"field":"roads", "id":prefix() + "road", "before":null, "after":{"id":prefix() + "road", "from":prefix() + "osm-ground-node-n", "to":prefix() + "osm-ground-node-s",
		"points":[[12800, 0, 200], [12800, 0, 12600]], "widths_cm":[300], "surfaces":["asphalt"], "kind":"ground", "clearance_cm":null, "sidewalk_cm":0}})
	var bodies := [body("lake-a", 2000, 2000, 6000, 6000), body("lake-b", 6000, 2000, 9000, 6000),
		body("stream-c", 14000, 8000, 20000, 9200), body("stream-d", 20000, 8000, 25000, 9200), body("pond", 11400, 9000, 12500, 11000)]
	for item: Dictionary in bodies: setup.append({"field":"water_bodies", "id":item.id, "before":null, "after":item})
	check(store.apply_command("synthetic city water", setup) == "", "synthetic city with water")
	check(store.save_project(ProjectSettings.globalize_path("user://water-fit")) == "", "save isolated project")
	var dem := heightmaps()
	var options := {"coordinates":frame, "cell":[0, 0], "cell_count":[2, 1], "osm_denominator":3.0}
	var fit: Dictionary = FIT.prepare(store, dem.records, dem.blobs, {}, options)
	check(not fit.has("error"), "water fit succeeds: " + str(fit.get("error", "")))
	if fit.has("error"): return finish()
	var receipt: Dictionary = fit.receipt
	check(receipt.pieces == 5 and receipt.levels == 4 and receipt.estimated, "a lake shares one level; the steep stream pieces and the pond keep their own: " + JSON.stringify(receipt))
	var surface := {}
	for patch: Dictionary in fit.patches:
		check(FIT.valid_patch(patch, FIT.index(store.document)), "patch passes the transfer guard: " + patch.id)
		surface[patch.id.trim_prefix(prefix())] = int(patch.after.surface_cm)
	check(surface.get("lake-a") == surface.get("lake-b") and surface.get("lake-a", 0) > 1000, "touching lake pieces share one surface: " + str(surface))
	check(surface.get("stream-d", 0) - surface.get("stream-c", 0) > 100, "a stream on a slope steps down by piece: " + str(surface))
	# Carved terrain: inside the lake below its level; beside the road unchanged.
	var after := {"records":[], "blobs":{}}
	for record: Dictionary in dem.records:
		var cell := Vector2i(record.cell.x, record.cell.y)
		var item: Dictionary = record.duplicate(true)
		var bytes: PackedByteArray = dem.blobs[record.path]
		if fit.fitted.has(cell):
			item.path = fit.fitted[cell].path; item.offset_cm = fit.fitted[cell].offset_cm; item.step_cm = fit.fitted[cell].step_cm
			bytes = fit.fitted[cell].bytes
		after.records.append(item); after.blobs[item.path] = bytes
	var before_heights := samples(store, dem, [Vector2(4000, 4000), Vector2(12400, 10000)])
	var after_heights := samples(store, after, [Vector2(4000, 4000), Vector2(12400, 10000)])
	check(after_heights[0] <= surface.get("lake-a", 0) - FIT.SURFACE_CM - FIT.CARVE_CM, "the lake bed sinks below its surface: %s → %s" % [before_heights[0], after_heights[0]])
	check(after_heights[1] == before_heights[1], "a sample within one spacing of the road keeps the road's terrain")
	check(receipt.kept_by_roads > 0 and receipt.carved_samples > 0, "carving and road protection are disclosed")
	var heightmap_patches: Array = []
	for record: Dictionary in after.records: heightmap_patches.append({"field":"heightmaps", "id":store.record_id("heightmaps", record), "before":null, "after":record})
	var accepted := FILES.apply(store, "DEM", heightmap_patches + fit.patches, after.blobs, [Vector2i(0, 0), Vector2i(1, 0)], true)
	check(accepted == "", "fitted terrain, road and water pass native generation: " + accepted)
	var moved: Dictionary = fit.patches[0].duplicate(true)
	moved.after.polygon[0][0] += 1
	check(not FIT.valid_patch(moved, FIT.index(store.document)), "a horizontal water change is rejected")
	var shallow: Dictionary = fit.patches[0].duplicate(true)
	shallow.after.bottom_cm += 1
	check(not FIT.valid_patch(shallow, FIT.index(store.document)), "a changed depth is rejected")
	var none := STORE.new()
	none.new_document()
	check(FIT.prepare(none, dem.records, dem.blobs, {}, options).patches.is_empty(), "maps without imported water are unchanged")
	finish()

func finish() -> void:
	print("dem_water_fit_validator: ", "PASS" if failures.is_empty() else failures, "; checks=", checks)
	quit(0 if failures.is_empty() else 1)
