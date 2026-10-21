extends SceneTree
## Estimated bridge/tunnel fitting on a sloped, creased two-cell DEM.
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const PNG := preload("res://scripts/terrain_png.gd")
const FIT := preload("res://scripts/dem_structure_fit.gd")
const LAYER := "c"
var failures: Array[String] = []
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func prefix() -> String: return "import-" + LAYER.repeat(32) + "-"
func node(name: String, x: int, z: int) -> Dictionary: return {"id":prefix() + "osm-ground-node-" + name, "position":[x, 0, z], "level":0}
func road(id: String, from: String, to: String, points: Array, kind := "ground", clearance: Variant = null) -> Dictionary:
	var widths: Array = []
	var surfaces: Array = []
	for i in range(points.size() - 1):
		widths.append(300); surfaces.append("asphalt")
	return {"id":prefix() + id, "from":prefix() + "osm-ground-node-" + from, "to":prefix() + "osm-ground-node-" + to, "points":points, "widths_cm":widths, "surfaces":surfaces, "kind":kind, "clearance_cm":clearance, "sidewalk_cm":null}
## 1 m level lead, then an 8 % ramp to the deck or tunnel floor.
func ramp(depth: int) -> int: return ceili(absi(depth) / 0.08)
func structure(z: int, depth: int, x := 4000) -> Array:
	var r := ramp(depth)
	return [[x,0,z],[x+100,0,z],[x+100+r,depth,z],[x+15900-r,depth,z],[x+15900,0,z],[x+16000,0,z]]
## Sloped DSM with a checkerboard crease, a 1 m hump where the ground roads
## pass under the deck (cut at every scale) and a 1 m dip where one passes over
## the tunnel (filled); shared cell edges use one formula.
func terrain(i: int, j: int, spike := 0) -> int:
	var hump := 100 if i >= 27 and i <= 31 and j >= 14 and j <= 18 else (-100 if i >= 28 and i <= 32 and j >= 24 and j <= 26 else 0)
	return 3000 + i * 12 + j * 8 + 40 * ((i + j) % 2) + hump + (spike if i == 25 and j == 16 else 0)

func heightmaps(spike := 0) -> Dictionary:
	var records: Array = []
	var blobs := {}
	for cx in range(4):
		var heights := PackedInt64Array()
		for j in range(33):
			for i in range(33): heights.append(terrain(cx * 32 + i, j, spike))
		var encoded := PNG.encode(heights, 33)
		var path := "editor/" + FILES.digest(encoded.bytes) + ".png"
		records.append({"cell":{"x":cx, "y":0}, "path":path, "spacing_cm":400, "offset_cm":encoded.offset_cm, "step_cm":1, "source_accuracy_cm":null})
		blobs[path] = encoded.bytes
	return {"records":records, "blobs":blobs}

func patches(store: RefCounted, records: Array) -> Array:
	var result: Array = []
	for record: Dictionary in records: result.append({"field":"heightmaps", "id":store.record_id("heightmaps", record), "before":null, "after":record})
	return result

func fitted(dem: Dictionary, fit: Dictionary) -> Dictionary:
	var records: Array = []
	var blobs := {}
	for record: Dictionary in dem.records:
		var cell := Vector2i(record.cell.x, record.cell.y)
		var after: Dictionary = record.duplicate(true)
		var bytes: PackedByteArray = dem.blobs[record.path]
		if fit.fitted.has(cell):
			after.path = fit.fitted[cell].path; after.offset_cm = fit.fitted[cell].offset_cm; after.step_cm = fit.fitted[cell].step_cm
			bytes = fit.fitted[cell].bytes
		records.append(after); blobs[after.path] = bytes
	return {"records":records, "blobs":blobs}

func sample(store: RefCounted, dem: Dictionary, point: Vector2) -> int:
	return samples(store, dem, [point])[0]

func samples(store: RefCounted, dem: Dictionary, points: Array) -> Array:
	var native: RefCounted = store.working_snapshot().fork()
	var thin: Dictionary = store.document.duplicate(true)
	for field in ["nodes", "roads", "attributions"]: thin[field] = []
	thin.heightmaps = dem.records
	JSON.parse_string(native.set_document(JSON.stringify(thin), store.project_path))
	JSON.parse_string(native.provide_resources(dem.blobs))
	return points.map(func(point: Vector2) -> int: return int(JSON.parse_string(native.height(point)).data.height))

## DEM samples (400 cm grid) at the corners of squares within 150 cm (half the
## road width) of both the structure segment a-b and the ground segment c-d.
func shared_corners(a: Vector2, b: Vector2, c: Vector2, d: Vector2) -> Array:
	var keys := {}
	for j in range(32):
		for i in range(128):
			var box := Rect2(Vector2(i * 400, j * 400), Vector2(400, 400))
			if FIT._box_distance(box, a, b) <= 150.0 and FIT._box_distance(box, c, d) <= 150.0:
				for corner in [Vector2(i, j), Vector2(i + 1, j), Vector2(i, j + 1), Vector2(i + 1, j + 1)]: keys[corner * 400] = true
	return keys.keys()

func run() -> void:
	check(FIT.separation_cm(8) == 63 and FIT.max_edit_cm(8) == 800 and FIT.separation_cm(3) == 167 and FIT.max_edit_cm(3) == 2133, "5 m separation and 64 m edit bound follow the map scale")
	# The 1:3 city default, then the 1:8 map with every refusal case.
	if case(3): case(8)
	finish()

## Estimator heights at 1:D: 6 m decks and 4.5 m tunnel clearance.
func case(denominator: int) -> bool:
	var deck_cm := roundi(600.0 / denominator)
	var clearance_cm := roundi(450.0 / denominator)
	var separation: int = FIT.separation_cm(denominator)
	var store := STORE.new()
	store.new_document()
	var frame := {"mode":"wgs84-utm", "origin":[9.5, 55.5], "local_origin_m":[0.0, 0.0]}
	var notice := {"source":"synthetic OSM", "license":"CC0", "notice":JSON.stringify({"adapter":"osm-extract-v1", "layer_id":LAYER.repeat(32), "coordinates":frame.merged({"osm_estimated_structures":[prefix() + "bridge", prefix() + "tunnel", prefix() + "bridge2"]}), "authored_units":{"source_denominator":denominator}})}
	var setup: Array = [
		{"field":"bounds", "before":store.document.bounds.duplicate(true), "after":{"min":[0, 0], "max":[51200, 12800]}},
		{"field":"cell_size_cm", "before":store.document.cell_size_cm, "after":12800},
		{"field":"attributions", "id":store.record_id("attributions", notice), "before":null, "after":notice}]
	for item: Dictionary in [node("w", 1000, 6400), node("a", 4000, 6400), node("b", 20000, 6400), node("c", 23000, 6400), node("d", 39000, 6400), node("e", 40000, 6400), node("n", 12000, 1000), node("s", 12000, 12000),
			node("tw", 1000, 10000), node("ta", 4000, 10000), node("tb", 20000, 10000), node("te", 24000, 10000), node("dn", 8000, 1500), node("ds", 16100, 12300)]:
		setup.append({"field":"nodes", "id":item.id, "before":null, "after":item})
	for item: Dictionary in [road("west", "w", "a", [[1000,0,6400],[4000,0,6400]]), road("bridge", "a", "b", structure(6400, deck_cm), "bridge"),
			road("bridge2", "c", "d", structure(6400, deck_cm, 23000), "bridge"), road("east", "d", "e", [[39000,0,6400],[40000,0,6400]]),
			road("cross", "n", "s", [[12000,0,1000],[12000,0,12000]]), road("tunnel_west", "tw", "ta", [[1000,0,10000],[4000,0,10000]]),
			road("tunnel", "ta", "tb", structure(10000, -deck_cm), "tunnel", clearance_cm), road("tunnel_east", "tb", "te", [[20000,0,10000],[24000,0,10000]]),
			# Two anchors of different levels joined by one ground segment, and an
			# oblique road under the deck and over the tunnel.
			road("link", "b", "c", [[20000,0,6400],[23000,0,6400]]), road("diagonal", "dn", "ds", [[8000,0,1500],[16100,0,12300]])]:
		setup.append({"field":"roads", "id":item.id, "before":null, "after":item})
	check(store.apply_command("synthetic city", setup) == "", "synthetic estimated city 1:%d" % denominator)
	check(store.save_project(ProjectSettings.globalize_path("user://structure-fit-%d" % denominator)) == "", "save isolated project")
	var cells: Array = [Vector2i(0, 0), Vector2i(1, 0), Vector2i(2, 0), Vector2i(3, 0)]
	check(FILES.apply(store, "flat", [], {}, cells, true) == "", "estimated structures pass on flat terrain")
	var dem := heightmaps()
	var unfitted := FILES.apply(store, "DEM", patches(store, dem.records), dem.blobs, cells, true)
	check(unfitted.contains("must match terrain"), "unfitted DEM fails the 1 cm apron rule: " + unfitted)
	var options := {"coordinates":frame, "cell":[0, 0], "cell_count":[4, 1]}
	if denominator != 1: options.osm_denominator = float(denominator)
	var fit: Dictionary = FIT.prepare(store, dem.records, dem.blobs, options)
	check(not fit.has("error"), "fit succeeds at 1:%d: %s" % [denominator, str(fit.get("error", ""))])
	if fit.has("error"): return false
	var unscaled := options.duplicate(true); unscaled.erase("osm_denominator")
	check(str(FIT.prepare(store, dem.records, dem.blobs, unscaled).get("error", "")).contains("DEM map scale differs"), "a DEM reviewed at another scale refuses")
	var receipt: Dictionary = fit.receipt
	check(receipt.anchors == 6 and receipt.structures == 3 and receipt.crossings == 4, "six anchors, three structures, four crossings: " + JSON.stringify(receipt))
	check(receipt.edited_samples > 0 and receipt.fitted_cells >= 3 and receipt.estimated, "pads span all cells and are disclosed")
	var after := fitted(dem, fit)
	var accepted := FILES.apply(store, "DEM", patches(store, after.records) + fit.patches, after.blobs, cells, true)
	check(accepted == "", "fitted DEM, roads and nodes pass native generation and seams: " + accepted)
	var lifted := {}
	for patch: Dictionary in fit.patches:
		if patch.field == "roads": lifted[patch.id] = patch.after
	check(lifted.has(prefix() + "bridge") and lifted.has(prefix() + "tunnel"), "both structures rebased")
	if lifted.has(prefix() + "bridge") and lifted.has(prefix() + "tunnel"):
		var r := ramp(deck_cm)
		var a: Dictionary = lifted[prefix() + "bridge"]
		var tunnel: Dictionary = lifted[prefix() + "tunnel"]
		var level := func(road: Dictionary, x: float) -> float: return lerpf(road.points[2][1], road.points[3][1], (x - 4100 - r) / (15800.0 - 2 * r))
		check(receipt.clamped > 0 and receipt.filled > 0, "the hump is cut and the dip filled: " + JSON.stringify(receipt))
		# Every sample under the deck where a ground road (straight or oblique)
		# passes keeps 5 m at 1:D; the deck slope over one square allows 15 cm.
		var deck_a := Vector2(4100 + r, 6400)
		var deck_b := Vector2(19900 - r, 6400)
		var under: Array = shared_corners(deck_a, deck_b, Vector2(12000, 1000), Vector2(12000, 12000)) + shared_corners(deck_a, deck_b, Vector2(8000, 1500), Vector2(16100, 12300))
		var heights := samples(store, after, under)
		var worst := -INF
		for k in range(under.size()): worst = maxf(worst, heights[k] - (level.call(a, under[k].x) - separation))
		check(under.size() >= 12 and worst <= 15.0, "1:%d ground under the deck keeps %d cm (5 m): %d samples, worst excess %.1f cm" % [denominator, separation, under.size(), worst])
		var over: Array = shared_corners(Vector2(4100 + r, 10000), Vector2(19900 - r, 10000), Vector2(12000, 1000), Vector2(12000, 12000))
		heights = samples(store, after, over)
		var lowest := INF
		for k in range(over.size()): lowest = minf(lowest, heights[k] - (level.call(tunnel, over[k].x) + clearance_cm + FIT.COVER_CM))
		check(over.size() >= 6 and lowest >= -1.0, "1:%d ground road over the tunnel stays above its %d cm ceiling: %d samples, lowest margin %.1f cm" % [denominator, clearance_cm, over.size(), lowest])
		check(a.points[0][1] == a.points[1][1] and a.points[4][1] == a.points[5][1], "level leads stay level")
		var raised := false
		for patch: Dictionary in fit.patches:
			if patch.field == "nodes" and patch.id == prefix() + "osm-ground-node-w": raised = int(patch.after.position[1]) == int(a.points[0][1])
		check(raised, "a plain far junction rises with its anchor instead of shortening the arm")
		var link: Dictionary = lifted.get(prefix() + "link", {})
		check(link.get("points", []).size() == 4 and int(link.points[0][1]) != int(link.points[3][1]) and int(link.points[0][1]) == int(link.points[1][1]) and int(link.points[2][1]) == int(link.points[3][1]), "a segment between two anchors gets one level vertex per end")
	# Fitting the fitted map again changes nothing.
	var again := STORE.new()
	again.document = store.document.duplicate(true)
	again.project_path = store.project_path
	check(again._apply(again.document, fit.patches, false) == "", "apply fitted roads")
	var repeat: Dictionary = FIT.prepare(again, after.records, after.blobs, options)
	check(not repeat.has("error") and repeat.patches.is_empty() and repeat.receipt.edited_samples == 0, "fit is idempotent: " + JSON.stringify(repeat.get("receipt", repeat.get("error", ""))))
	# A DSM spike of about 11 m under the deck: beyond the 64 m bound at 1:8
	# (800 cm), within it at 1:3 (2133 cm).
	var spiked := heightmaps(1200)
	var tall: Dictionary = FIT.prepare(store, spiked.records, spiked.blobs, options)
	if denominator == 8: check(str(tall.get("error", "")).contains("terrain edit beyond the bound"), "edit bound refuses at 1:8: " + str(tall.get("error", "")))
	else: check(not tall.has("error") and tall.receipt.max_cut_cm > FIT.max_edit_cm(8), "the same spike stays within the bound at 1:%d: %s" % [denominator, str(tall.get("error", tall.get("receipt", {}).get("max_cut_cm")))])
	if denominator != 8: return true
	# A city with estimated structures is not imported onto an existing DEM.
	var city := preload("res://scripts/import_layer.gd").new()
	city.value = {"adapter":"osm-extract-v1", "coordinates":{"osm_city":{"scale_denominator":denominator}, "osm_estimated_structures":[prefix() + "bridge"]}, "patches":[]}
	var terrain_map := STORE.new()
	terrain_map.document = store.document.duplicate(true)
	terrain_map.document.heightmaps = after.records
	check(city.validate_for(terrain_map).contains("Adopt this city on flat terrain first"), "city onto a DEM map explains the order")
	# Anchors outside the reviewed cells refuse the whole fit.
	var partial: Dictionary = FIT.prepare(store, [dem.records[0]], dem.blobs, {"coordinates":frame, "cell":[0, 0], "cell_count":[1, 1], "osm_denominator":8.0})
	check(str(partial.get("error", "")).contains("anchor outside the DEM"), "partial DEM refuses: " + str(partial.get("error", "")))
	var moved := frame.duplicate(true); moved.origin[0] += 0.001
	check(str(FIT.prepare(store, dem.records, dem.blobs, {"coordinates":moved, "cell":[0, 0], "cell_count":[4, 1], "osm_denominator":8.0}).get("error", "")).contains("Projection"), "frame mismatch refuses")
	# Transfer guard: only heights of existing imported records.
	var index := FIT.index(store.document)
	var patch: Dictionary = fit.patches[0]
	var guarded := true
	var inserted := false
	for each: Dictionary in fit.patches:
		guarded = guarded and FIT.valid_patch(each, index)
		if each.field == "roads" and each.after.points.size() != each.before.points.size(): inserted = true
	check(guarded and inserted, "every fit patch, including inserted level vertices, passes the transfer guard")
	var shifted: Dictionary = patch.duplicate(true)
	if shifted.field == "roads": shifted.after.points[1][0] += 1
	else: shifted.after.position[0] += 1
	check(not FIT.valid_patch(shifted, index), "horizontal change rejected")
	var extra: Dictionary = patch.duplicate(true)
	if extra.field == "roads": extra.after.points.append(extra.after.points[-1].duplicate())
	else: extra.after.level = 1
	check(not FIT.valid_patch(extra, index), "extra vertex or field change rejected")
	var foreign: Dictionary = patch.duplicate(true); foreign.id = "manual"; foreign.before.id = "manual"; foreign.after.id = "manual"
	check(not FIT.valid_patch(foreign, index), "record outside the document rejected")
	return true

func finish() -> void:
	print("dem_structure_fit_validator: ", "PASS" if failures.is_empty() else failures, "; checks=", checks)
	quit(0 if failures.is_empty() else 1)
