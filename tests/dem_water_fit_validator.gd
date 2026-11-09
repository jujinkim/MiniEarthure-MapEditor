extends SceneTree
## Imported city water fitted to a two-cell DEM: a gentle west cell and a
## steep east cell, a lake of two touching pieces with a 400 cm inlet and a
## 200 cm creek, a wide stream of two touching pieces on the slope, a narrow
## brook on the slope, a narrow sloped stream around an island and a pond beside
## a ground road. Levels sit 8 cm under a low shore height; the brook is cut
## into stretches with their own levels, the stream with an island is not; the
## DEM itself is never carved (MapKit sinks the basins). A second fit of the
## fitted map changes nothing.
const SCRATCH := preload("res://tests/validator_scratch.gd")
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const PNG := preload("res://scripts/terrain_png.gd")
const FIT := preload("res://scripts/dem_water_fit.gd")
const LAYER := "w"
var failures: Array[String] = []
var checks := 0
var scratch := ""
func _finalize() -> void: SCRATCH.remove(scratch)
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
	scratch = SCRATCH.fresh("dem_water_fit_validator")
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
		body("stream-c", 14000, 8000, 20000, 9200), body("stream-d", 20000, 8000, 25000, 9200), body("pond", 11400, 9000, 12500, 11000),
		body("brook", 14010, 4000, 24010, 4150), body("inlet", 9000, 3000, 11000, 3500), body("creek", 9000, 5000, 10000, 5200)]
	var isle := body("isle", 14010, 6000, 24010, 6300)
	isle.islands = [[[15000, 6100], [15100, 6100], [15100, 6200], [15000, 6200]]]
	bodies.append(isle)
	for item: Dictionary in bodies: setup.append({"field":"water_bodies", "id":item.id, "before":null, "after":item})
	check(store.apply_command("synthetic city water", setup) == "", "synthetic city with water")
	check(store.save_project(scratch.path_join("water-fit")) == "", "save isolated project")
	var dem := heightmaps()
	var options := {"coordinates":frame, "cell":[0, 0], "cell_count":[2, 1], "osm_denominator":3.0}
	var fit: Dictionary = FIT.prepare(store, dem.records, dem.blobs, {}, options)
	check(not fit.has("error"), "water fit succeeds: " + str(fit.get("error", "")))
	if fit.has("error"): return finish()
	var receipt: Dictionary = fit.receipt
	check(receipt.pieces == 9 and receipt.cut_pieces == 1 and receipt.levels > 8 and receipt.estimated and receipt.stretch_drop_cm == FIT.STRETCH_DROP_CM
		and receipt.stretches >= 10 and receipt.added_bodies > 0,
		"a lake shares one level; the steep stream pieces and the pond keep their own; the brook is cut: " + JSON.stringify(receipt))
	var surface := {}
	for patch: Dictionary in fit.patches:
		check(FIT.valid_patch(patch, FIT.index(store.document)), "patch passes the transfer guard: " + patch.id)
		surface[patch.id.trim_prefix(prefix())] = int(patch.after.surface_cm)
	# The brook: one body keeps its ID, the other stretches are added, all
	# inside its outline, covering it exactly, stepping up the slope.
	var brook: Array = fit.patches.filter(func(p: Dictionary) -> bool: return p.id.trim_prefix(prefix()).begins_with("brook"))
	check(brook.size() == receipt.added_bodies + 1 and brook.size() >= 10 and brook.filter(func(p: Dictionary) -> bool: return p.before == null).size() == receipt.added_bodies,
		"the brook becomes stretches: %d bodies, receipt %s" % [brook.size(), JSON.stringify(receipt)])
	var area := 0.0
	var steps: Array = []
	for patch: Dictionary in brook:
		area += FIT._area(FIT._polygon(patch.after))
		var xs: Array = patch.after.polygon.map(func(p: Array) -> int: return p[0])
		steps.append([xs.min(), int(patch.after.surface_cm), xs.max()])
	steps.sort()
	check(absf(area - 10000.0 * 150.0) < 1.0, "the stretches cover the brook exactly: %f" % area)
	var climbing := true
	var seams := true
	for k in range(1, steps.size()):
		climbing = climbing and steps[k][1] > steps[k - 1][1]
		seams = seams and steps[k][0] == steps[k - 1][2] and posmod(steps[k][0] - 200, 400) == 0
	check(climbing and seams and steps[-1][1] - steps[0][1] > 300, "stretches step up the slope at seams half a DEM spacing off the samples: " + str(steps))
	check(steps.all(func(s: Array) -> bool: return s[2] - s[0] <= 400 * FIT.MAX_STRETCH_SPACINGS), "a stretch spans at most four DEM spacings: " + str(steps))
	check(surface.get("lake-a") == surface.get("lake-b") and surface.get("lake-a", 0) > 1000, "touching lake pieces share one surface: " + str(surface))
	# A 400 cm inlet (wider than two MapKit banks) joins the lake level within
	# LEVEL_RANGE_CM; a 200 cm creek whose shore lies over STRETCH_RANGE_CM above
	# it keeps its own level (it could not sink its bed that far).
	check(surface.get("inlet") == surface.get("lake-a"), "a wide inlet keeps the lake level: " + str(surface))
	check(surface.get("creek", 0) > surface.get("lake-a", 0) + FIT.STRETCH_RANGE_CM, "a tight creek high above the lake keeps its own level: " + str(surface))
	var isles: Array = fit.patches.filter(func(p: Dictionary) -> bool: return p.id.trim_prefix(prefix()).begins_with("isle"))
	var stored: Dictionary = FIT.index(store.document).get(prefix() + "isle", {})
	check(isles.size() == 1 and isles[0].before != null and isles[0].after.polygon == stored.polygon and isles[0].after.islands == stored.islands and stored.islands.size() == 1,
		"a sloped stream around an island changes only its level: " + str(isles.size()))
	check(surface.get("stream-d", 0) - surface.get("stream-c", 0) > 100, "a stream on a slope steps down by piece: " + str(surface))
	# The lake level is its lowest shore sample minus 8 cm.
	var shore := samples(store, dem, [Vector2(2000, 2000), Vector2(6000, 2000), Vector2(6000, 6000), Vector2(2000, 6000),
		Vector2(9000, 2000), Vector2(9000, 6000)])
	var lowest: int = shore.min()
	check(surface.get("lake-a") == lowest + FIT.SURFACE_CM and FIT.SURFACE_CM < 0, "the lake surface lies below its lowest shore: %s vs %s" % [surface, shore])
	for patch: Dictionary in fit.patches:
		check(int(patch.after.surface_cm) - int(patch.after.bottom_cm) == FIT.DEPTH_CM, "every fitted body keeps its depth: " + patch.id)
		# The water never floats: every shore vertex and edge midpoint lies at
		# least 8 cm above the fitted surface.
		var ring: Array = patch.after.polygon
		var points: Array = []
		for k in range(ring.size()):
			var a := Vector2(ring[k][0], ring[k][1])
			var b := Vector2(ring[(k + 1) % ring.size()][0], ring[(k + 1) % ring.size()][1])
			points.append(a); points.append((a + b) / 2)
		var banks := samples(store, dem, points)
		check(banks.min() >= int(patch.after.surface_cm) - FIT.SURFACE_CM, "%s lies below every sampled bank: %d vs %s" % [patch.id, patch.after.surface_cm, banks])
	# The terrain itself is not carved; ground roads need no protection.
	check(fit.fitted.is_empty() and FIT.CARVE_CM == 0, "no DEM cell changes")
	check(receipt.carved_samples == 0 and receipt.max_carve_cm == 0 and receipt.kept_by_roads == 0 and receipt.level == "lowest-shore-sample", "the receipt discloses no carving")
	var after := {"records":[], "blobs":{}}
	for record: Dictionary in dem.records:
		var cell := Vector2i(record.cell.x, record.cell.y)
		var item: Dictionary = record.duplicate(true)
		var bytes: PackedByteArray = dem.blobs[record.path]
		if fit.fitted.has(cell):
			item.path = fit.fitted[cell].path; item.offset_cm = fit.fitted[cell].offset_cm; item.step_cm = fit.fitted[cell].step_cm
			bytes = fit.fitted[cell].bytes
		after.records.append(item); after.blobs[item.path] = bytes
	check(samples(store, after, [Vector2(4000, 4000), Vector2(12400, 10000)]) == samples(store, dem, [Vector2(4000, 4000), Vector2(12400, 10000)]),
		"terrain inside the lake and beside the road is unchanged")
	var heightmap_patches: Array = []
	for record: Dictionary in after.records: heightmap_patches.append({"field":"heightmaps", "id":store.record_id("heightmaps", record), "before":null, "after":record})
	var accepted := FILES.apply(store, "DEM", heightmap_patches + fit.patches, after.blobs, [Vector2i(0, 0), Vector2i(1, 0)], true)
	check(accepted == "", "terrain, road and fitted water pass native generation (with basins): " + accepted)
	# A second fit of the adopted map cuts nothing again and changes no level.
	check(FILES.apply(store, "DEM", heightmap_patches + fit.patches, after.blobs, [Vector2i(0, 0), Vector2i(1, 0)]) == "", "the fit is adopted")
	var again: Dictionary = FIT.prepare(store, after.records, after.blobs, {}, options)
	check(not again.has("error") and again.receipt.cut_pieces == 0 and again.receipt.added_bodies == 0 and again.patches.is_empty(),
		"a second fit changes nothing: %s %s" % [again.get("error", ""), JSON.stringify(again.get("receipt", {}))])
	for patch: Dictionary in again.get("patches", []):
		check(patch.before != null and FIT.valid_patch(patch, FIT.index(store.document)), "a refit only changes levels: " + patch.id)
	# Stretch grids: whole DEM spacings, halved down to a quarter on steep
	# pieces, their lines off the samples.
	var grids := FIT.new()
	grids._spacing = 400
	grids._min = Vector2i(0, 0)
	check([grids._grid(0.01, 30), grids._grid(0.05, 30), grids._grid(0.1, 30), grids._grid(0.3, 30), grids._grid(2.0, 30)] == [1600, 400, 200, 100, 100], "stretch grids follow the slope")
	check(grids._origin(400) == Vector2(200, 200) and grids._origin(1600) == Vector2(200, 200) and grids._origin(200) == Vector2(100, 100) and grids._origin(100) == Vector2(50, 50),
		"stretch grid lines lie off the DEM samples")
	# A stream along a grid line splits lengthwise; the halves share one run of
	# seams much longer than the stream is wide (they keep one level), also
	# where a finer grid cuts the run into short pairs. Crosswise seams stay
	# as short as the stream is wide.
	for expected: Array in [[400, 8, 4], [100, 45, 30]]:
		var grid: int = expected[0]
		var origin := Vector2.ONE * float(grid / 2)
		var along := FIT._cut(PackedVector2Array([Vector2(1000, 2130), Vector2(2400, 2130), Vector2(2400, 2280), Vector2(1000, 2280)]), origin, grid)
		var shared := FIT._shared(along, origin, grid)
		var long := shared.filter(func(p: Array) -> bool: return p[0] > FIT.LENGTHWISE_WIDTHS * 150)
		check(along.size() == expected[1] and long.size() == expected[2] and long.all(func(p: Array) -> bool: return p[0] == 1400.0)
			and shared.all(func(p: Array) -> bool: return p[0] == 1400.0 or p[0] == 150.0), "lengthwise halves share a long run (grid %d): %s" % [grid, shared])
	var level_only: Dictionary = fit.patches.filter(func(p: Dictionary) -> bool: return p.id == prefix() + "lake-a")[0]
	var moved: Dictionary = level_only.duplicate(true)
	moved.after.polygon[1][0] += 50
	check(not FIT.valid_patch(moved, FIT.index(store.document)), "water moved out of its outline is rejected")
	var added: Dictionary = brook.filter(func(p: Dictionary) -> bool: return p.before == null)[0]
	for mutation in range(4):
		var bad: Dictionary = added.duplicate(true)
		match mutation:
			0: bad.after.polygon[0][1] -= 500
			1: bad.id = bad.id.replace("-s", "-x"); bad.after.id = bad.id
			2: bad.id = prefix() + "nowhere-s1"; bad.after.id = bad.id
			3: bad.after.flow_cm_s = [10, 0]
		check(not FIT.valid_patch(bad, FIT.index(store.document)), "an invalid stretch is rejected (%d)" % mutation)
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
