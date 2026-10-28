extends RefCounted
## Fits imported city water to a reviewed DEM (disclosed estimate). Connected
## water pieces whose shore heights stay within LEVEL_RANGE_CM share one level
## (a lake); other pieces keep their own (a sloping stream steps). The level is
## the median shore terrain; the surface lies SURFACE_CM above it and terrain
## samples inside sink CARVE_CM below it, except within one sample spacing of a
## ground road, whose surface follows the terrain.
const UNITS := preload("./import_units.gd")
const PROFILE := "osm-water-dem-fit-v1"
const SURFACE_CM := 3
const DEPTH_CM := 60
const CARVE_CM := 40
const LEVEL_RANGE_CM := 100
const MAX_EDIT_M := 64.0
const BUCKET_CM := 2000

var _native: RefCounted
var _min: Vector2i
var _spacing := 0
var _samples := {}
var _failed := 0

## `fitted` holds the structure-fitted cells ({cell: {path, offset_cm, step_cm,
## bytes}}); water fits on top of them. Returns {patches, fitted, receipt} or {error}.
static func prepare(store: RefCounted, records: Array, blobs: Dictionary, fitted: Dictionary, options: Dictionary) -> Dictionary:
	var bodies: Array = []
	for body: Dictionary in store.document.get("water_bodies", []):
		if str(body.id).begins_with("import-"): bodies.append(body)
	if bodies.is_empty(): return {"patches":[], "fitted":{}, "receipt":{}}
	var scale := UNITS.osm_scale(store.document)
	if scale.has("error"): return {"error":scale.error}
	var fit := new()
	return fit._run(store, records, blobs, fitted, options, bodies, int(scale.denominator))

## Imported water bodies by ID, for checking a returned patch.
static func index(document: Dictionary) -> Dictionary:
	var result := {}
	for body: Dictionary in document.get("water_bodies", []):
		if str(body.id).begins_with("import-"): result[body.id] = body
	return result

## A fit changes only the surface and bottom of an imported water body.
static func valid_patch(patch: Dictionary, bodies: Dictionary) -> bool:
	if patch.get("field") != "water_bodies" or patch.get("before") is not Dictionary or patch.get("after") is not Dictionary: return false
	var before: Dictionary = patch.before
	var after: Dictionary = patch.after
	if before.get("id") != patch.get("id") or bodies.get(patch.id) != before: return false
	var expected := after.duplicate(true)
	expected.surface_cm = before.surface_cm
	expected.bottom_cm = before.bottom_cm
	if expected != before: return false
	for key in ["surface_cm", "bottom_cm"]:
		if not (after[key] is int or after[key] is float) or after[key] != floor(after[key]) or absf(after[key]) > 1000000: return false
	return after.surface_cm - after.bottom_cm == DEPTH_CM

func _sample(key: Vector2i) -> int:
	if not _samples.has(key):
		var result: Dictionary = JSON.parse_string(_native.height(Vector2(_min.x + key.x * _spacing, _min.y + key.y * _spacing)))
		if not result.ok:
			_failed += 1
			return 0
		_samples[key] = int(result.data.height)
	return _samples[key]

func _height(point: Vector2) -> Variant:
	var result: Dictionary = JSON.parse_string(_native.height(point))
	return int(result.data.height) if result.ok else null

static func _polygon(body: Dictionary) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point: Array in body.polygon: result.append(Vector2(point[0], point[1]))
	return result

static func _find(group: Dictionary, key: int) -> int:
	while group[key] != key: key = group[key]
	return key

func _run(store: RefCounted, records: Array, blobs: Dictionary, fitted: Dictionary, options: Dictionary, bodies: Array, denominator: int) -> Dictionary:
	var document: Dictionary = store.document
	_spacing = int(records[0].spacing_cm)
	_min = Vector2i(int(document.bounds.min[0]), int(document.bounds.min[1]))
	var size := int(document.cell_size_cm)
	var low := Vector2(_min.x + options.cell[0] * size, _min.y + options.cell[1] * size)
	var high := low + Vector2(options.cell_count[0] * size, options.cell_count[1] * size)
	# The reviewed DEM cells, with structure-fitted payloads where present.
	var effective: Array = []
	var resources := blobs.duplicate()
	var covered := {}
	for record: Dictionary in records:
		var cell := Vector2i(int(record.cell.x), int(record.cell.y))
		covered[cell] = true
		if fitted.has(cell):
			var item: Dictionary = record.duplicate(true)
			item.path = fitted[cell].path
			item.offset_cm = fitted[cell].offset_cm
			item.step_cm = fitted[cell].step_cm
			resources[item.path] = fitted[cell].bytes
			effective.append(item)
		else: effective.append(record)
	var others: Array = []
	for existing: Dictionary in document.heightmaps:
		if not covered.has(Vector2i(int(existing.cell.x), int(existing.cell.y))): others.append(existing)
	for existing: Dictionary in others:
		var payload := preload("./authoring_files.gd").read(store.project_path.path_join(existing.path))
		if payload.has("error"): return {"error":payload.error}
		resources[existing.path] = payload.bytes
	_native = store.working_snapshot().fork()
	var thin: Dictionary = document.duplicate(true)
	for field in ["nodes","roads","buildings","zones","placements","assets","attributions","pois","surface_areas","water_bodies","gimmicks","barriers"]:
		if thin.has(field): thin[field] = []
	thin.erase("assembled_track")
	thin.heightmaps = effective + others
	var result: Dictionary = JSON.parse_string(_native.set_document(JSON.stringify(thin), store.project_path))
	if not result.ok: return {"error":store.reason(result)}
	result = JSON.parse_string(_native.provide_resources(resources))
	if not result.ok: return {"error":store.reason(result)}
	# Shore heights of every piece inside the DEM.
	var pieces: Array = []
	var report := {"profile":PROFILE, "estimated":true, "pieces":0, "outside":0, "levels":0, "carved_samples":0, "kept_by_roads":0, "max_carve_cm":0, "surface_cm":SURFACE_CM, "carve_cm":CARVE_CM}
	for body: Dictionary in bodies:
		var polygon := _polygon(body)
		var inside := true
		for point in polygon:
			if point.x < low.x or point.y < low.y or point.x > high.x or point.y > high.y: inside = false
		if not inside:
			report.outside += 1
			continue
		var heights: Array = []
		for point in polygon:
			var h: Variant = _height(point)
			if h == null: return {"error":"Water fitting could not sample the DEM terrain."}
			heights.append(h)
		heights.sort()
		var box := Rect2(polygon[0], Vector2.ZERO)
		for point in polygon: box = box.expand(point)
		pieces.append({"body":body, "polygon":polygon, "box":box, "heights":heights})
	report.pieces = pieces.size()
	if pieces.is_empty(): return {"patches":[], "fitted":{}, "receipt":report}
	# Connected pieces (touching within 2 cm) form groups.
	var group := {}
	for i in range(pieces.size()): group[i] = i
	for i in range(pieces.size()):
		for j in range(i + 1, pieces.size()):
			if not pieces[i].box.grow(2).intersects(pieces[j].box.grow(2)): continue
			var grown := Geometry2D.offset_polygon(pieces[i].polygon, 2.0)
			var touching := false
			for shape: PackedVector2Array in grown:
				if not Geometry2D.intersect_polygons(shape, pieces[j].polygon).is_empty(): touching = true
			if touching: group[_find(group, j)] = _find(group, i)
	var members := {}
	for i in range(pieces.size()):
		var root := _find(group, i)
		if not members.has(root): members[root] = []
		members[root].append(i)
	var level := {}
	for root: int in members:
		var all: Array = []
		for i: int in members[root]: all.append_array(pieces[i].heights)
		all.sort()
		if all[-1] - all[0] <= LEVEL_RANGE_CM:
			report.levels += 1
			for i: int in members[root]: level[i] = all[all.size() / 2]
		else:
			for i: int in members[root]:
				report.levels += 1
				level[i] = pieces[i].heights[pieces[i].heights.size() / 2]
	# Ground roads keep the terrain they follow within one sample spacing.
	var segments: Array = []
	var buckets := {}
	for road: Dictionary in document.roads:
		if road.kind != "ground": continue
		for i in range(road.points.size() - 1):
			var a := Vector2(road.points[i][0], road.points[i][2])
			var b := Vector2(road.points[i + 1][0], road.points[i + 1][2])
			var reach: float = road.widths_cm[i] * 0.5 + float(road.get("sidewalk_cm", 0) if road.get("sidewalk_cm") != null else 0) + _spacing
			var index := segments.size()
			segments.append([a, b, reach])
			var box := Rect2(a, Vector2.ZERO).expand(b).grow(reach)
			for x in range(floori(box.position.x / BUCKET_CM), floori(box.end.x / BUCKET_CM) + 1):
				for y in range(floori(box.position.y / BUCKET_CM), floori(box.end.y / BUCKET_CM) + 1):
					var bucket := Vector2i(x, y)
					if not buckets.has(bucket): buckets[bucket] = []
					buckets[bucket].append(index)
	var max_edit := floori(MAX_EDIT_M * 100.0 / denominator)
	var target := {}
	for i in range(pieces.size()):
		var piece: Dictionary = pieces[i]
		var box: Rect2 = piece.box
		var deepest: int = level[i] - CARVE_CM
		for ky in range(ceili((box.position.y - _min.y) / float(_spacing)), floori((box.end.y - _min.y) / float(_spacing)) + 1):
			for kx in range(ceili((box.position.x - _min.x) / float(_spacing)), floori((box.end.x - _min.x) / float(_spacing)) + 1):
				var key := Vector2i(kx, ky)
				var p := Vector2(_min.x + kx * _spacing, _min.y + ky * _spacing)
				if p.x < low.x or p.y < low.y or p.x > high.x or p.y > high.y: continue
				if not Geometry2D.is_point_in_polygon(p, piece.polygon): continue
				var near := false
				for index: int in buckets.get(Vector2i(floori(p.x / BUCKET_CM), floori(p.y / BUCKET_CM)), []):
					var s: Array = segments[index]
					if p.distance_to(Geometry2D.get_closest_point_to_segment(p, s[0], s[1])) < s[2]: near = true; break
				if near:
					report.kept_by_roads += 1
					continue
				var before := _sample(key)
				var after := maxi(mini(before, deepest), before - max_edit)
				if after < before: target[key] = mini(target.get(key, after), after)
	if _failed > 0: return {"error":"Water fitting could not sample the DEM terrain."}
	var delta := PackedInt32Array()
	for key: Vector2i in target:
		var before := _sample(key)
		report.max_carve_cm = maxi(report.max_carve_cm, before - target[key])
		delta.append_array([key.x, key.y, before, target[key]])
	report.carved_samples = delta.size() / 4
	var out_fitted := {}
	if not delta.is_empty():
		result = JSON.parse_string(_native.apply_delta(delta, false))
		if not result.ok: return {"error":store.reason(result)}
		var materialized: Dictionary = _native.materialize()
		if not materialized.get("ok", false): return {"error":store.reason(materialized)}
		var canonical: Dictionary = JSON.parse_string(materialized.data.canonical)
		var touched := {}
		var per_cell := size / _spacing
		for row in range(0, delta.size(), 4):
			for y in range(maxi(0, floori((delta[row + 1] - 1) / float(per_cell))), delta[row + 1] / per_cell + 1):
				for x in range(maxi(0, floori((delta[row] - 1) / float(per_cell))), delta[row] / per_cell + 1): touched[Vector2i(x, y)] = true
		for record: Dictionary in canonical.heightmaps:
			var cell := Vector2i(int(record.cell.x), int(record.cell.y))
			if materialized.data.blobs.has(record.path) and touched.has(cell):
				if not covered.has(cell): return {"error":"Water fitting would change terrain outside this DEM."}
				out_fitted[cell] = {"path":record.path, "offset_cm":int(record.offset_cm), "step_cm":int(record.step_cm), "bytes":materialized.data.blobs[record.path]}
	var patches: Array = []
	for i in range(pieces.size()):
		var body: Dictionary = pieces[i].body
		var after: Dictionary = body.duplicate(true)
		after.surface_cm = level[i] + SURFACE_CM
		after.bottom_cm = level[i] + SURFACE_CM - DEPTH_CM
		if after != body: patches.append({"field":"water_bodies", "id":body.id, "before":body.duplicate(true), "after":after})
	report.changed_water = patches.size()
	report.fitted_cells = out_fitted.size()
	return {"patches":patches, "fitted":out_fitted, "receipt":report}
