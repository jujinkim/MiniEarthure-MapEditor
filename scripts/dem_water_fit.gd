extends RefCounted
## Fits imported city water to a reviewed DEM (disclosed estimate). A narrow
## piece (mean width under NARROW_CM, no islands, not already cut) whose shore
## heights span more than STRETCH_RANGE_CM is a sloped stream: it is cut into
## stretches on a square grid off the DEM samples, sized from the piece's slope
## so a stretch falls about STRETCH_DROP_CM (a quarter to four DEM spacings).
## Parts of one piece sharing a seam along the course (longer than twice the
## piece's mean width) and parts under SLIVER_CM2 stay together. Touching pieces
## and stretches then join levels, wide pieces (lakes) first, each most similar
## first, while the median shore height of every wide member stays within
## LEVEL_RANGE_CM of the joined level (a lake keeps one level; DSM shores rise
## over trees and buildings) and every shore height of a tight member (a
## stretch, or a piece narrower than TIGHT_CM) within STRETCH_RANGE_CM. A level is the
## lowest shore terrain height of its members, sampled at every polygon vertex
## and along every edge at the DEM spacing, so the surface, SURFACE_CM below it,
## lies under every sampled bank; the bottom lies DEPTH_CM below the surface. The stretches of one piece
## at one level are joined again; a piece left in several parts keeps its ID
## for the first and adds `<id>-s<k>` (the next free k) for the others.
## Terrain samples are not carved: MapKit sinks an earth basin under OSM-city
## water when it generates ground, with a lip at the upper surface where water
## of different levels meets.
const UNITS := preload("./import_units.gd")
const PROFILE := "osm-water-dem-fit-v1"
const SURFACE_CM := -8
const DEPTH_CM := 60
## DEM samples inside water are no longer lowered (MapKit basins give depth).
const CARVE_CM := 0
const LEVEL_RANGE_CM := 100
const NARROW_CM := 600
## Narrower than two MapKit banks (2 · 180 cm): such water cannot sink its bed
## far under its banks, so its shore stays within STRETCH_RANGE_CM of its level.
const TIGHT_CM := 360
const STRETCH_RANGE_CM := 30
const STRETCH_DROP_CM := 30
## Grid of a stretch: a quarter of a DEM spacing to four spacings.
const MAX_STRETCH_SPACINGS := 4
const MAX_STRETCH_HALVINGS := 2
## A seam between parts of one piece longer than this many piece mean widths
## runs along the course: those parts keep one level.
const LENGTHWISE_WIDTHS := 2.0
## Stretch parts under one map square metre join a neighbour of their piece.
const SLIVER_CM2 := 10000.0
const MAX_STRETCH_VERTICES := 256
## MapKit's document limit of water bodies.
const MAX_BODIES := 1024

var _native: RefCounted
var _min: Vector2i
var _spacing := 0

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

## A fit changes only the level of an imported water body, or cuts it into
## stretches: the body keeps its ID for one part and `<id>-s<k>` bodies are
## added for the others, each inside the original outline.
static func valid_patch(patch: Dictionary, bodies: Dictionary) -> bool:
	if patch.get("field") != "water_bodies" or patch.get("after") is not Dictionary or patch.get("id") is not String: return false
	var id: String = patch.id
	var after: Dictionary = patch.after
	var original: Dictionary = {}
	if patch.get("before") == null:
		var cut := id.rfind("-s")
		if cut < 0 or bodies.has(id): return false
		var k := id.substr(cut + 2)
		if not k.is_valid_int() or str(int(k)) != k or int(k) < 1 or int(k) > MAX_BODIES: return false
		original = bodies.get(id.left(cut), {})
		if original.is_empty(): return false
	elif patch.before is Dictionary and patch.before.get("id") == id and bodies.get(id) == patch.before:
		original = patch.before
	else: return false
	var expected := original.duplicate(true)
	expected.id = id
	for key in ["polygon", "surface_cm", "bottom_cm"]: expected[key] = after.get(key)
	if expected != after: return false
	for key in ["surface_cm", "bottom_cm"]:
		if not (after[key] is int or after[key] is float) or after[key] != floor(after[key]) or absf(after[key]) > 1000000: return false
	if after.surface_cm - after.bottom_cm != DEPTH_CM: return false
	if patch.get("before") != null and after.polygon == original.polygon: return true
	return _inside(after.polygon, original)

## Whether `ring` is a stretch ring inside or on the outline of `original`.
static func _inside(ring: Variant, original: Dictionary) -> bool:
	if ring is not Array or ring.size() < 3 or ring.size() > MAX_STRETCH_VERTICES or not original.get("islands", []).is_empty(): return false
	var outline := _polygon(original)
	for point: Variant in ring:
		if point is not Array or point.size() != 2 or point.any(func(v: Variant) -> bool: return not (v is int or v is float) or v != floor(v)): return false
		var p := Vector2(point[0], point[1])
		if Geometry2D.is_point_in_polygon(p, outline): continue
		var near := false
		for k in range(outline.size()):
			if p.distance_to(Geometry2D.get_closest_point_to_segment(p, outline[k], outline[(k + 1) % outline.size()])) <= 1.0:
				near = true
				break
		if not near: return false
	return true

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

## Sorted shore heights: every vertex, and points along each edge no farther
## apart than one DEM sample spacing. Null when the DEM cannot be sampled.
func _shore(polygon: PackedVector2Array) -> Variant:
	var heights: Array = []
	for k in range(polygon.size()):
		var a := polygon[k]
		var b := polygon[(k + 1) % polygon.size()]
		var steps := maxi(1, ceili(a.distance_to(b) / float(_spacing)))
		for step in range(steps):
			var h: Variant = _height(a.lerp(b, float(step) / steps))
			if h == null: return null
			heights.append(h)
	heights.sort()
	return heights

static func _area(polygon: PackedVector2Array) -> float:
	var twice := 0.0
	for k in range(polygon.size()):
		var a := polygon[k]
		var b := polygon[(k + 1) % polygon.size()]
		twice += float(a.x) * float(b.y) - float(b.x) * float(a.y)
	return absf(twice) / 2.0

## Exact turn of integer points `a → b → c` (positive left, zero collinear).
static func _turn(a: Vector2, b: Vector2, c: Vector2) -> int:
	return (int(b.x) - int(a.x)) * (int(c.y) - int(a.y)) - (int(b.y) - int(a.y)) * (int(c.x) - int(a.x))

static func _perimeter(polygon: PackedVector2Array) -> float:
	var length := 0.0
	for k in range(polygon.size()): length += polygon[k].distance_to(polygon[(k + 1) % polygon.size()])
	return length

## Integer ring without repeated or exactly collinear vertices.
static func _clean(polygon: PackedVector2Array) -> PackedVector2Array:
	var ring := PackedVector2Array()
	for point in polygon:
		var p := point.round()
		if ring.is_empty() or ring[-1] != p: ring.append(p)
	if ring.size() > 1 and ring[0] == ring[-1]: ring.remove_at(ring.size() - 1)
	var changed := true
	while changed and ring.size() > 3:
		changed = false
		for k in range(ring.size()):
			var a := ring[(k - 1 + ring.size()) % ring.size()]
			if _turn(a, ring[k], ring[(k + 1) % ring.size()]) == 0:
				ring.remove_at(k)
				changed = true
				break
	return ring

## A simple ring MapKit accepts: three or more distinct vertices, nonzero area
## and no touching or crossing edges.
static func _simple(ring: PackedVector2Array) -> bool:
	var n := ring.size()
	if n < 3 or n > MAX_STRETCH_VERTICES or _area(ring) == 0.0: return false
	var seen := {}
	for point in ring:
		if seen.has(point): return false
		seen[point] = true
	for i in range(n):
		for j in range(i + 1, n):
			if j == i + 1 or (i == 0 and j == n - 1): continue
			if Geometry2D.segment_intersects_segment(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n]) != null: return false
	return true

## Cuts `polygon` on the square grid of side `grid` through `origin`. Every
## crossing of a grid line becomes a vertex first (on the line, rounded along
## it), so neighbouring stretches share exact seams. Returns the parts, or []
## when the cut is not clean.
static func _cut(polygon: PackedVector2Array, origin: Vector2, grid: int) -> Array:
	var ring := PackedVector2Array()
	for k in range(polygon.size()):
		var a := polygon[k]
		var b := polygon[(k + 1) % polygon.size()]
		ring.append(a)
		var crossings: Array = []
		for axis in 2:
			if a[axis] == b[axis]: continue
			var low := minf(a[axis], b[axis])
			var high := maxf(a[axis], b[axis])
			for line in range(ceili((low - origin[axis]) / grid), floori((high - origin[axis]) / grid) + 1):
				var at := origin[axis] + line * grid
				if at <= low or at >= high: continue
				var t := (at - a[axis]) / (b[axis] - a[axis])
				var point := a.lerp(b, t)
				point[axis] = at
				point[1 - axis] = roundf(point[1 - axis])
				crossings.append([t, point])
		crossings.sort_custom(func(x: Array, y: Array) -> bool: return x[0] < y[0])
		for item: Array in crossings:
			if ring[-1] != item[1]: ring.append(item[1])
	var box := Rect2(ring[0], Vector2.ZERO)
	for point in ring: box = box.expand(point)
	var parts: Array = []
	var area := 0.0
	for gx in range(floori((box.position.x - origin.x) / grid), floori((box.end.x - origin.x) / grid) + 1):
		for gy in range(floori((box.position.y - origin.y) / grid), floori((box.end.y - origin.y) / grid) + 1):
			var low := origin + Vector2(gx, gy) * grid
			var square := PackedVector2Array([low, low + Vector2(grid, 0), low + Vector2(grid, grid), low + Vector2(0, grid)])
			var pieces := Geometry2D.intersect_polygons(ring, square)
			# A hole (opposite orientation) cannot be a stretch.
			for part: PackedVector2Array in pieces:
				if Geometry2D.is_polygon_clockwise(part) != Geometry2D.is_polygon_clockwise(pieces[0]): return []
			for part: PackedVector2Array in pieces:
				var clean := _clean(part)
				if clean.size() < 3 or _area(clean) == 0.0: continue
				if not _simple(clean): return []
				parts.append(clean)
				area += _area(clean)
	if parts.size() < 2 or absf(area - _area(polygon)) > 0.001 * _area(polygon) + 100.0: return []
	return parts

## Joins touching parts into simple rings; parts that do not join stay apart.
static func _join(parts: Array) -> Array:
	var joined: Array = []
	for part: PackedVector2Array in parts:
		var current := part
		var merged := true
		while merged:
			merged = false
			for i in range(joined.size()):
				var union := Geometry2D.merge_polygons(joined[i], current)
				if union.size() != 1: continue
				var clean := _clean(union[0])
				if not _simple(clean): continue
				joined.remove_at(i)
				current = clean
				merged = true
				break
		joined.append(current)
	return joined

static func _touching(a: PackedVector2Array, b: PackedVector2Array) -> bool:
	for shape: PackedVector2Array in Geometry2D.offset_polygon(a, 2.0):
		if not Geometry2D.intersect_polygons(shape, b).is_empty(): return true
	return false

func _run(store: RefCounted, records: Array, blobs: Dictionary, fitted: Dictionary, options: Dictionary, bodies: Array, _denominator: int) -> Dictionary:
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
	# The carve counters stay zero: no DEM sample is lowered.
	var report := {"profile":PROFILE, "estimated":true, "pieces":0, "outside":0, "levels":0, "carved_samples":0, "kept_by_roads":0, "max_carve_cm":0, "surface_cm":SURFACE_CM, "carve_cm":CARVE_CM, "level":"lowest-shore-sample",
		"stretch_range_cm":STRETCH_RANGE_CM, "stretch_drop_cm":0, "cut_pieces":0, "stretches":0, "added_bodies":0}
	# A body already cut (a stretch, or a piece with stretches) is refitted
	# whole, as a tight unit: a second fit only changes levels.
	var ids := {}
	for body: Dictionary in document.get("water_bodies", []): ids[str(body.id)] = true
	var family := {}
	for id: String in ids:
		var base := _stretch_base(id, ids)
		if base != "":
			family[id] = true
			family[base] = true
	for body: Dictionary in bodies:
		var polygon := _polygon(body)
		var inside := true
		for point in polygon:
			if point.x < low.x or point.y < low.y or point.x > high.x or point.y > high.y: inside = false
		if not inside:
			report.outside += 1
			continue
		var heights: Variant = _shore(polygon)
		if heights == null: return {"error":"Water fitting could not sample the DEM terrain."}
		var width := 2.0 * _area(polygon) / _perimeter(polygon)
		var cut := family.has(str(body.id))
		pieces.append({"body":body, "polygon":polygon, "heights":heights, "width":width,
			"narrow":width < NARROW_CM and not cut and body.get("islands", []).is_empty(), "tight":cut or width < TIGHT_CM})
	report.pieces = pieces.size()
	if pieces.is_empty(): return {"patches":[], "fitted":{}, "receipt":report}
	# Sloped narrow pieces become stretches; a larger drop per stretch is
	# tried when the cut would pass MapKit's body limit.
	var limit: int = MAX_BODIES - (document.get("water_bodies", []).size() - pieces.size())
	var drop := STRETCH_DROP_CM
	var parts := {}
	while true:
		parts = _stretches(pieces, drop)
		var count := pieces.size()
		for i: int in parts: count += parts[i].parts.size() - 1
		if count <= limit or drop == 0: break
		drop = drop * 2 if drop < STRETCH_DROP_CM * 8 else 0
	report.stretch_drop_cm = drop
	# Units: whole pieces and stretches, each with its shore heights.
	var units: Array = []
	for i in range(pieces.size()):
		if not parts.has(i):
			units.append({"piece":i, "polygon":pieces[i].polygon, "heights":pieces[i].heights, "tight":pieces[i].tight})
			continue
		report.cut_pieces += 1
		for part: PackedVector2Array in parts[i].parts:
			var heights: Variant = _shore(part)
			if heights == null: return {"error":"Water fitting could not sample the DEM terrain."}
			units.append({"piece":i, "polygon":part, "heights":heights, "tight":true})
	report.stretches = units.size() - (pieces.size() - parts.size())
	# Touching units (within 2 cm), found through a coarse grid of their bounds.
	var buckets := {}
	for i in range(units.size()):
		var box := Rect2(units[i].polygon[0], Vector2.ZERO)
		for point: Vector2 in units[i].polygon: box = box.expand(point)
		units[i].box = box.grow(2)
		for x in range(floori(units[i].box.position.x / 4096), floori(units[i].box.end.x / 4096) + 1):
			for y in range(floori(units[i].box.position.y / 4096), floori(units[i].box.end.y / 4096) + 1):
				var key := Vector2i(x, y)
				if not buckets.has(key): buckets[key] = []
				buckets[key].append(i)
	var pairs := {}
	for key: Vector2i in buckets:
		var list: Array = buckets[key]
		for a in range(list.size()):
			for b in range(a + 1, list.size()):
				var i: int = list[a]
				var j: int = list[b]
				var pair := Vector2i(mini(i, j), maxi(i, j))
				if pairs.has(pair) or not units[i].box.intersects(units[j].box): continue
				pairs[pair] = _touching(units[i].polygon, units[j].polygon)
	var edges: Array = []
	for pair: Vector2i in pairs:
		if pairs[pair]: edges.append([absi(int(units[pair.x].heights[0]) - int(units[pair.y].heights[0])), pair.x, pair.y])
	edges.sort_custom(_before)
	# Join levels, most similar first, while every wide member's median shore
	# height stays within LEVEL_RANGE_CM of the joined level and a tight
	# member's whole shore within STRETCH_RANGE_CM.
	var group := {}
	var lo := {}
	var wide_mid := {}
	var tight_hi := {}
	var area := {}
	for i in range(units.size()):
		group[i] = i
		lo[i] = int(units[i].heights[0])
		wide_mid[i] = -(1 << 40) if units[i].tight else int(units[i].heights[units[i].heights.size() / 2])
		tight_hi[i] = int(units[i].heights[-1]) if units[i].tight else -(1 << 40)
		area[i] = _area(units[i].polygon)
	var join := func(a: int, b: int) -> void:
		group[b] = a
		lo[a] = mini(lo[a], lo[b])
		wide_mid[a] = maxi(wide_mid[a], wide_mid[b])
		tight_hi[a] = maxi(tight_hi[a], tight_hi[b])
		area[a] += area[b]
	# Parts of a cut piece that share a seam along its course keep one level:
	# their levels would step across the stream.
	var first_unit := {}
	for i in range(units.size()):
		if not first_unit.has(units[i].piece): first_unit[units[i].piece] = i
	# Seam length shared by each pair of parts of one piece, by unit pair.
	var overlap := {}
	for piece: int in parts:
		var along: float = LENGTHWISE_WIDTHS * pieces[piece].width
		for pair: Array in _shared(parts[piece].parts, parts[piece].origin, parts[piece].grid):
			var x: int = first_unit[piece] + pair[1]
			var y: int = first_unit[piece] + pair[2]
			overlap[Vector2i(x, y)] = overlap.get(Vector2i(x, y), 0.0) + pair[3]
			if pair[0] <= along: continue
			var a := _find(group, x)
			var b := _find(group, y)
			if a != b: join.call(a, b)
	# A sliver part joins the neighbour of its piece it shares the longest seam
	# with (only touching ones when it shares none), preferring one that is no
	# sliver, until none is left alone.
	var slivers: Array = []
	for i in range(units.size()):
		if parts.has(units[i].piece) and area[i] < SLIVER_CM2: slivers.append([area[i], i])
	slivers.sort_custom(_before)
	var joined := true
	while joined:
		joined = false
		for sliver: Array in slivers:
			var i: int = sliver[1]
			var b := _find(group, i)
			if area[b] >= SLIVER_CM2: continue
			var best: Array = []
			for edge: Array in edges:
				if edge[1] != i and edge[2] != i: continue
				var other: int = edge[2] if edge[1] == i else edge[1]
				var a := _find(group, other)
				if units[other].piece != units[i].piece or a == b: continue
				var shared: float = overlap.get(Vector2i(mini(i, other), maxi(i, other)), 0.0)
				var rank := [0 if area[a] >= SLIVER_CM2 else 1, 0 if shared > 0.0 else 1, -shared, absi(lo[a] - lo[b]), other]
				if best.is_empty() or _before(rank, best): best = rank
			if best.is_empty(): continue
			join.call(_find(group, best[4]), b)
			joined = true
	# Lakes first (wide pieces only), so a tight neighbour joining one piece
	# cannot keep the others of its lake apart.
	for wide in [true, false]:
		for edge: Array in edges:
			if wide and (units[edge[1]].tight or units[edge[2]].tight): continue
			var a := _find(group, edge[1])
			var b := _find(group, edge[2])
			if a == b: continue
			var level := mini(lo[a], lo[b])
			if maxi(wide_mid[a], wide_mid[b]) - level <= LEVEL_RANGE_CM and maxi(tight_hi[a], tight_hi[b]) - level <= STRETCH_RANGE_CM: join.call(a, b)
	var levels := {}
	for i in range(units.size()): levels[_find(group, i)] = true
	report.levels = levels.size()
	# The bodies of each piece: its units joined per level.
	var by_piece := {}
	for i in range(units.size()):
		var root := _find(group, i)
		var piece: int = units[i].piece
		if not by_piece.has(piece): by_piece[piece] = {}
		if not by_piece[piece].has(root): by_piece[piece][root] = []
		by_piece[piece][root].append(units[i].polygon)
	var patches: Array = []
	for i in range(pieces.size()):
		var body: Dictionary = pieces[i].body
		var made: Array = []
		for root: int in by_piece[i]:
			var level: int = lo[root]
			for ring: PackedVector2Array in (_join(by_piece[i][root]) if parts.has(i) else by_piece[i][root]):
				var points: Array = []
				for point in ring: points.append([int(point.x), int(point.y)])
				var low_x: int = points.map(func(p: Array) -> int: return p[0]).min()
				var low_y: int = points.map(func(p: Array) -> int: return p[1]).min()
				made.append({"key":[low_x, low_y], "polygon":points, "level":level})
		made.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return _before(a.key, b.key))
		var suffix := 0
		for k in range(made.size()):
			var after: Dictionary = body.duplicate(true)
			if k > 0:
				suffix += 1
				while ids.has("%s-s%d" % [body.id, suffix]): suffix += 1
				after.id = "%s-s%d" % [body.id, suffix]
				ids[after.id] = true
			# A cut piece left whole keeps its outline.
			if made.size() > 1: after.polygon = made[k].polygon
			after.surface_cm = made[k].level + SURFACE_CM
			after.bottom_cm = made[k].level + SURFACE_CM - DEPTH_CM
			if k > 0:
				patches.append({"field":"water_bodies", "id":after.id, "before":null, "after":after})
				report.added_bodies += 1
			# A level already in place (stored numbers may be floats) is no change.
			elif made.size() == 1 and int(body.surface_cm) == after.surface_cm and int(body.bottom_cm) == after.bottom_cm and body.surface_cm == floor(body.surface_cm): continue
			elif after != body: patches.append({"field":"water_bodies", "id":body.id, "before":body.duplicate(true), "after":after})
	report.changed_water = patches.size()
	report.fitted_cells = 0
	return {"patches":patches, "fitted":{}, "receipt":report}

## Lexicographic order of number arrays.
static func _before(a: Array, b: Array) -> bool:
	for k in range(mini(a.size(), b.size())):
		if a[k] != b[k]: return a[k] < b[k]
	return a.size() < b.size()

## `<base>` when `id` is `<base>-s<k>` (k a positive integer) and `<base>` is
## in `ids`, otherwise "".
static func _stretch_base(id: String, ids: Dictionary) -> String:
	var cut := id.rfind("-s")
	if cut < 0: return ""
	var k := id.substr(cut + 2)
	if not k.is_valid_int() or str(int(k)) != k or int(k) < 1 or not ids.has(id.left(cut)): return ""
	return id.left(cut)

## Grid side of a stretch falling about `drop` cm at `slope` cm/cm: whole DEM
## spacings (one to four), or halved (down to a quarter) on steep pieces.
func _grid(slope: float, drop: int) -> int:
	var spacings := floori(drop / (slope * _spacing))
	if spacings >= 1: return _spacing * mini(spacings, MAX_STRETCH_SPACINGS)
	var grid := _spacing
	for k in MAX_STRETCH_HALVINGS:
		if slope * grid <= drop: break
		grid = maxi(2, grid / 4 * 2)
	return grid

## Origin of a stretch grid: its lines lie half a grid (or half a DEM spacing
## for whole spacings) off the DEM samples, so no seam lies on a sample line.
func _origin(grid: int) -> Vector2:
	return Vector2(_min) + Vector2.ONE * float(grid / 2 if grid < _spacing else _spacing / 2)

## Stretch parts of every sloped narrow piece at `drop` cm per stretch (none
## when `drop` is 0), by piece index: {parts, origin, grid}.
func _stretches(pieces: Array, drop: int) -> Dictionary:
	var result := {}
	if drop == 0: return result
	for i in range(pieces.size()):
		var piece: Dictionary = pieces[i]
		var fall: int = piece.heights[-1] - piece.heights[0]
		if not piece.narrow or fall <= STRETCH_RANGE_CM: continue
		var grid := _grid(fall / (_perimeter(piece.polygon) / 2.0), drop)
		var origin := _origin(grid)
		var cut := _cut(piece.polygon, origin, grid)
		if not cut.is_empty(): result[i] = {"parts":cut, "origin":origin, "grid":grid}
	return result

## [run length, i, j, length] for every pair of parts (indices into `parts`,
## i < j) sharing edges on a line of the cut grid: the length of the contiguous
## run of shared seams along that line holding theirs (a stream along a grid
## line shares one long run cut by the squares into short pairs) and their own.
static func _shared(parts: Array, origin: Vector2, grid: int) -> Array:
	var lines := {}
	for i in range(parts.size()):
		var ring: PackedVector2Array = parts[i]
		for k in range(ring.size()):
			var a := ring[k]
			var b := ring[(k + 1) % ring.size()]
			for axis in 2:
				if a[axis] != b[axis] or fposmod(a[axis] - origin[axis], float(grid)) != 0.0: continue
				var key := Vector2(axis, a[axis])
				if not lines.has(key): lines[key] = []
				lines[key].append([minf(a[1 - axis], b[1 - axis]), maxf(a[1 - axis], b[1 - axis]), i])
	var result: Array = []
	for key: Vector2 in lines:
		var spans: Array = lines[key]
		var shared: Array = []
		for x in range(spans.size()):
			for y in range(x + 1, spans.size()):
				if spans[x][2] == spans[y][2]: continue
				var from: float = maxf(spans[x][0], spans[y][0])
				var to: float = minf(spans[x][1], spans[y][1])
				if to > from: shared.append([from, to, mini(spans[x][2], spans[y][2]), maxi(spans[x][2], spans[y][2])])
		shared.sort_custom(_before)
		var run: Array = []
		var end := -INF
		for k in range(shared.size() + 1):
			if k == shared.size() or shared[k][0] > end:
				if not run.is_empty():
					var length: float = end - float(run[0][0])
					for item: Array in run: result.append([length, item[2], item[3], float(item[1]) - float(item[0])])
				run = []
				if k == shared.size(): break
			run.append(shared[k])
			end = maxf(end, shared[k][1]) if run.size() > 1 else shared[k][1]
	result.sort_custom(_before)
	return result
