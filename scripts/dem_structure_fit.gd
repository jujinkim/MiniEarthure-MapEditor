extends RefCounted
## Fits estimated city bridges/tunnels to a reviewed DEM (disclosed estimate).
## Each ground anchor gets a level terrain pad under its whole junction fan, the
## level leads and the anchor-side ground vertices take the pad height, and the
## estimated profile keeps its height above a base interpolated between anchors.
## Terrain is cut under bridge decks and filled above tunnels where ground roads
## cross. Explicit source-height structures are never changed.
const TYPES := preload("./import_layer.gd")
const GROUNDING := preload("./dem_building_grounding.gd")
const UNITS := preload("./import_units.gd")
const PROFILE := "osm-estimated-structure-dem-fit-v1"
## Junction mouths reach half the widest arm plus 2 m; fillets stay within the
## widest road width plus 224 cm (MapKit junction influence).
const FAN_MARGIN_CM := 224
const DECK_MARGIN_CM := 1
## Source metres, ÷D on a 1:D map: the estimator's crossing separation, and a
## DSM edit beyond 64 m (taller than most city buildings) refuses.
const SEPARATION_M := 5.0
const MAX_TERRAIN_EDIT_M := 64.0
const COVER_CM := 2
const MAX_EDITED_SAMPLES := 1000000
const MAX_REPORTED := 20
const MAX_ROUNDS := 32

static func estimated(document: Dictionary) -> Dictionary:
	var result := {}
	for attribution: Dictionary in document.attributions:
		var parser := JSON.new()
		if parser.parse(attribution.notice) != OK or parser.data is not Dictionary: continue
		var meta: Dictionary = parser.data
		if meta.get("adapter") != "osm-extract-v1" or meta.get("coordinates") is not Dictionary: continue
		var list: Variant = meta.coordinates.get("osm_estimated_structures", [])
		if list is not Array: continue
		for id: Variant in list:
			if id is String: result[id] = true
	return result

static func prepare(store: RefCounted, records: Array, blobs: Dictionary, options: Dictionary) -> Dictionary:
	var document: Dictionary = store.document
	var listed := estimated(document)
	var roads := {}
	var structures := {}
	for road: Dictionary in document.roads:
		roads[road.id] = road
		if listed.has(road.id) and road.kind in ["bridge", "tunnel"]: structures[road.id] = road
	if structures.is_empty(): return {"patches":[], "fitted":{}, "receipt":{}}
	# DSM heights and structures share the map's one OSM scale 1:D.
	var scale := UNITS.osm_scale(document)
	if scale.has("error"): return {"error":scale.error}
	var denominator := int(scale.denominator)
	if denominator < 1 or int(options.get("osm_denominator", 1)) != denominator: return {"error":"DEM map scale differs from the city map scale; review the DEM again."}
	var frames := GROUNDING.layers(document)
	for id: String in structures:
		var prefix := id.left(40)
		if not frames.has(prefix): return {"error":"Estimated structures lack their imported coordinate frame."}
		for key in ["mode","origin","local_origin_m"]:
			if frames[prefix].get(key) != options.coordinates.get(key): return {"error":"Projection origin conflicts with active imported height data."}
	var spacing := int(records[0].spacing_cm)
	for record: Dictionary in records:
		if int(record.spacing_cm) != spacing: return {"error":"DEM structure fitting needs one terrain spacing."}
	# Cells this DEM replaces do not count; the ones it keeps share the view.
	var replaced := {}
	for record: Dictionary in records: replaced[Vector2i(int(record.cell.x), int(record.cell.y))] = true
	for existing: Dictionary in document.heightmaps:
		if not replaced.has(Vector2i(int(existing.cell.x), int(existing.cell.y))) and int(existing.spacing_cm) != spacing: return {"error":"DEM structure fitting needs one terrain spacing."}
	var nodes := {}
	for node: Dictionary in document.nodes: nodes[node.id] = node
	var incident := {}
	for road: Dictionary in document.roads:
		for end in ["from", "to"]:
			if not incident.has(road[end]): incident[road[end]] = []
			incident[road[end]].append(road)
	var fit := new()
	fit._separation_cm = separation_cm(denominator)
	fit._max_edit_cm = max_edit_cm(denominator)
	return fit._run(store, records, blobs, options, roads, structures, nodes, incident)

static func separation_cm(denominator: int) -> int: return ceili(SEPARATION_M * 100.0 / denominator)
static func max_edit_cm(denominator: int) -> int: return floori(MAX_TERRAIN_EDIT_M * 100.0 / denominator)

var _separation_cm := 0
var _max_edit_cm := 0
var _store: RefCounted
var _native: RefCounted
var _min: Vector2i
var _spacing := 0
var _samples := {}
var _pad := {}
var _pad_of := {}
var _floor := {}
var _ceiling := {}
var _failures := {}
var _counts := {}
var _source := {}

func _fail(reason: String, item: String) -> void:
	_counts[reason] = _counts.get(reason, 0) + 1
	if not _failures.has(reason): _failures[reason] = []
	if _failures[reason].size() < MAX_REPORTED: _failures[reason].append(item)

func _sample(key: Vector2i) -> int:
	if not _samples.has(key):
		var result: Dictionary = JSON.parse_string(_native.height(Vector2(_min.x + key.x * _spacing, _min.y + key.y * _spacing)))
		if not result.ok:
			_fail("terrain sample unavailable", str(key))
			return 0
		_samples[key] = int(result.data.height)
	return _samples[key]

## Segments bucketed by plan cell for crossing queries.
const BUCKET_CM := 2000
static func _buckets(segments: Array) -> Dictionary:
	var result := {}
	for index in range(segments.size()):
		var a: Vector2 = segments[index][2]
		var b: Vector2 = segments[index][3]
		for y in range(floori(minf(a.y, b.y) / BUCKET_CM), floori(maxf(a.y, b.y) / BUCKET_CM) + 1):
			for x in range(floori(minf(a.x, b.x) / BUCKET_CM), floori(maxf(a.x, b.x) / BUCKET_CM) + 1):
				var key := Vector2i(x, y)
				if not result.has(key): result[key] = []
				result[key].append(index)
	return result

static func _near(buckets: Dictionary, a: Vector2, b: Vector2) -> Array:
	var found := {}
	for y in range(floori(minf(a.y, b.y) / BUCKET_CM), floori(maxf(a.y, b.y) / BUCKET_CM) + 1):
		for x in range(floori(minf(a.x, b.x) / BUCKET_CM), floori(maxf(a.x, b.x) / BUCKET_CM) + 1):
			for index: int in buckets.get(Vector2i(x, y), []): found[index] = true
	return found.keys()

## A crossing is a proper plan intersection, not two segments touching at an end.
static func _cross(a: Vector2, b: Vector2, c: Vector2, d: Vector2) -> Variant:
	var hit: Variant = Geometry2D.segment_intersects_segment(a, b, c, d)
	if hit == null: return null
	for end: Vector2 in [a, b, c, d]:
		if end.distance_to(hit) < 1.0: return null
	return hit

## Sample corners of every terrain square within `radius` of the segment a-b.
func _squares(a: Vector2, b: Vector2, radius: float) -> Array:
	return _corners(_cells(a, b, radius))

## Lowest and highest deck over a terrain square (x = min, y = max).
func _span(square: Vector2i, pa: Vector2, pb: Vector2, ya: float, yb: float) -> Vector2:
	var length_squared := pa.distance_squared_to(pb)
	var low := INF
	var high := -INF
	for corner: Vector2i in [square, square + Vector2i(1, 0), square + Vector2i(0, 1), square + Vector2i(1, 1)]:
		var point := Vector2(_min.x + corner.x * _spacing, _min.y + corner.y * _spacing)
		var t := 0.0 if length_squared == 0.0 else clampf((point - pa).dot(pb - pa) / length_squared, 0.0, 1.0)
		var deck := lerpf(ya, yb, t)
		low = minf(low, deck); high = maxf(high, deck)
	return Vector2(low, high)

static func _corners(squares: Dictionary) -> Array:
	var keys := {}
	for square: Vector2i in squares:
		for corner in [square, square + Vector2i(1, 0), square + Vector2i(0, 1), square + Vector2i(1, 1)]: keys[corner] = true
	return keys.keys()

## Terrain squares (by lower-left sample) within `radius` of the segment a-b.
func _cells(a: Vector2, b: Vector2, radius: float) -> Dictionary:
	var keys := {}
	var low := Vector2(minf(a.x, b.x), minf(a.y, b.y)) - Vector2(radius, radius)
	var high := Vector2(maxf(a.x, b.x), maxf(a.y, b.y)) + Vector2(radius, radius)
	var i0 := floori((low.x - _min.x) / _spacing)
	var j0 := floori((low.y - _min.y) / _spacing)
	var i1 := floori((high.x - _min.x) / _spacing)
	var j1 := floori((high.y - _min.y) / _spacing)
	for j in range(j0, j1 + 1):
		for i in range(i0, i1 + 1):
			var box := Rect2(Vector2(_min.x + i * _spacing, _min.y + j * _spacing), Vector2(_spacing, _spacing))
			if _box_distance(box, a, b) <= radius: keys[Vector2i(i, j)] = true
	return keys

static func _xz(point: Array) -> Vector2: return Vector2(point[0], point[2])

## Exact distance between an axis-aligned square and the segment a-b.
static func _box_distance(box: Rect2, a: Vector2, b: Vector2) -> float:
	if box.has_point(a) or box.has_point(b): return 0.0
	var corners := [box.position, box.position + Vector2(box.size.x, 0), box.end, box.position + Vector2(0, box.size.y)]
	var best := INF
	for k in range(4):
		var c: Vector2 = corners[k]
		var d: Vector2 = corners[(k + 1) % 4]
		if Geometry2D.segment_intersects_segment(a, b, c, d) != null: return 0.0
		best = minf(best, Geometry2D.get_closest_point_to_segment(c, a, b).distance_to(c))
	for end: Vector2 in [a, b]:
		var nearest := Vector2(clampf(end.x, box.position.x, box.end.x), clampf(end.y, box.position.y, box.end.y))
		best = minf(best, nearest.distance_to(end))
	return best

func _run(store: RefCounted, records: Array, blobs: Dictionary, options: Dictionary, roads: Dictionary, structures: Dictionary, nodes: Dictionary, incident: Dictionary) -> Dictionary:
	_store = store
	var document: Dictionary = store.document
	_spacing = int(records[0].spacing_cm)
	_min = Vector2i(int(document.bounds.min[0]), int(document.bounds.min[1]))
	var size := int(document.cell_size_cm)
	var low := Vector2(_min.x + options.cell[0] * size, _min.y + options.cell[1] * size)
	var high := low + Vector2(options.cell_count[0] * size, options.cell_count[1] * size)
	# The thin view samples the exact MapKit terrain of the reviewed DEM.
	_native = store.working_snapshot().fork()
	var thin: Dictionary = document.duplicate(true)
	for field in ["nodes","roads","buildings","zones","placements","assets","attributions","pois","surface_areas","water_bodies","gimmicks"]:
		if thin.has(field): thin[field] = []
	thin.erase("assembled_track")
	var others: Array = []
	for existing: Dictionary in document.heightmaps:
		var covered := false
		for record: Dictionary in records:
			if record.cell.x == existing.cell.x and record.cell.y == existing.cell.y: covered = true
		if not covered: others.append(existing)
	thin.heightmaps = records + others
	var resources := blobs.duplicate()
	for existing: Dictionary in others:
		var payload := preload("./authoring_files.gd").read(store.project_path.path_join(existing.path))
		if payload.has("error"): return {"error":payload.error}
		resources[existing.path] = payload.bytes
	var result: Dictionary = JSON.parse_string(_native.set_document(JSON.stringify(thin), store.project_path))
	if not result.ok: return {"error":store.reason(result)}
	result = JSON.parse_string(_native.provide_resources(resources))
	if not result.ok: return {"error":store.reason(result)}
	var widest := 0
	for road: Dictionary in document.roads:
		for width: int in road.widths_cm: widest = maxi(widest, width)
	# Anchors: structure ends joined to other roads, or open ends.
	var anchors := {}
	for id: String in structures:
		var road: Dictionary = structures[id]
		if road.get("design") != null: _fail("designed structure", id)
		for end in ["from", "to"]:
			var node_id: String = road[end]
			if node_id.contains("-osm-node-"): _fail("explicit-height joint", id)
			var other := false
			for joined: Dictionary in incident.get(node_id, []):
				if not structures.has(joined.id): other = true
			if other or incident.get(node_id, []).size() == 1: anchors[node_id] = true
	for node_id: String in anchors:
		var position := _xz(nodes[node_id].position)
		if position.x < low.x or position.y < low.y or position.x > high.x or position.y > high.y: _fail("anchor outside the DEM", node_id)
	if not _failures.is_empty(): return _refuse()
	# Pads: every terrain square under the junction fan becomes level.
	var pads := {}
	var arm_radius := {}
	for node_id: String in anchors:
		var centre := _xz(nodes[node_id].position)
		var arms: Array = []
		var local := 0
		for road: Dictionary in incident[node_id]:
			var first: bool = road.from == node_id
			var next: Array = road.points[1 if first else road.points.size() - 2]
			arms.append([(_xz(next) - centre).normalized(), road.widths_cm[0 if first else road.widths_cm.size() - 1] * 0.5])
			local = maxi(local, road.widths_cm[0 if first else road.widths_cm.size() - 1])
		# Mouths reach half the widest arm plus 2 m along each arm and half a
		# width sideways; fillet corners lie where two arms' edges meet.
		var radius := 2.0
		for arm: Array in arms: radius = maxf(radius, Vector2(local * 0.5 + 200.0, arm[1]).length() + 2.0)
		for i in range(arms.size()):
			for j in range(i + 1, arms.size()):
				var angle := absf(arms[i][0].angle_to(arms[j][0]))
				if angle > 0.01: radius = maxf(radius, maxf(arms[i][1], arms[j][1]) / sin(angle * 0.5) + 2.0)
		radius = minf(radius, float(widest + FAN_MARGIN_CM))
		pads[node_id] = _squares(centre, centre, radius)
		arm_radius[node_id] = local * 0.5
	# Overlapping pads share one level.
	var group := {}
	for node_id: String in anchors: group[node_id] = node_id
	var owner := {}
	for node_id: String in pads:
		for key: Vector2i in pads[node_id]:
			if owner.has(key): _union(group, owner[key], node_id)
			else: owner[key] = node_id
	var members := {}
	for node_id: String in anchors:
		var root := _find(group, node_id)
		if not members.has(root): members[root] = []
		members[root].append(node_id)
	var level := {}
	var pad_keys := {}
	for root: String in members:
		var heights: Array = []
		var keys := {}
		for node_id: String in members[root]:
			for key: Vector2i in pads[node_id]: keys[key] = true
		for key: Vector2i in keys: heights.append(_sample(key))
		heights.sort()
		var h: int = heights[heights.size() / 2] if not heights.is_empty() else 0
		for node_id: String in members[root]: level[node_id] = h
		pad_keys[root] = keys.keys()
		for key: Vector2i in keys:
			_pad[key] = h
			_pad_of[key] = root
	if not _failures.is_empty(): return _refuse()
	# Vertex graph of the estimated structures; endpoints merge at nodes.
	var vertex := {}
	var position := {}
	var height := {}
	var edges := {}
	for id: String in structures:
		var road: Dictionary = structures[id]
		for i in range(road.points.size()):
			var key: String = road.from if i == 0 else (road.to if i == road.points.size() - 1 else id + "#" + str(i))
			vertex[id + "@" + str(i)] = key
			position[key] = _xz(road.points[i])
			height[key] = int(road.points[i][1])
			if not edges.has(key): edges[key] = []
		for i in range(road.points.size() - 1):
			var a: String = vertex[id + "@" + str(i)]
			var b: String = vertex[id + "@" + str(i + 1)]
			var length: float = position[a].distance_to(position[b])
			edges[a].append([b, length]); edges[b].append([a, length])
	# Level leads keep their anchor's height; the rest interpolates by path
	# distance from every anchor's lead (linear between two anchors).
	var lead_of := {}
	var weights := {}
	for node_id: String in anchors:
		var lead := {node_id: true}
		var queue: Array = [node_id]
		while not queue.is_empty():
			var current: String = queue.pop_back()
			for edge: Array in edges[current]:
				if not lead.has(edge[0]) and height[edge[0]] == height[node_id] and not anchors.has(edge[0]):
					lead[edge[0]] = true
					queue.append(edge[0])
		for key: String in lead:
			if lead_of.has(key) and _find(group, lead_of[key]) != _find(group, node_id): _fail("leads of different levels meet", key)
			lead_of[key] = node_id
		var distances := _distances(edges, lead.keys(), anchors)
		for key: String in distances:
			if not weights.has(key): weights[key] = []
			weights[key].append([node_id, 1.0 / maxf(distances[key], 1.0)])
	var old_base := {}
	for key: String in position:
		if lead_of.has(key):
			old_base[key] = height[lead_of[key]]
		elif not weights.has(key):
			_fail("structure without an anchor", key)
		else:
			old_base[key] = _weighted(weights[key], height)
	if not _failures.is_empty(): return _refuse()
	# A structure skips cuts only on its own anchors' pads (its level leads).
	var own := {}
	for id: String in structures:
		own[id] = {}
		var road: Dictionary = structures[id]
		for i in range(road.points.size()):
			var key: String = vertex[id + "@" + str(i)]
			if lead_of.has(key): own[id][_find(group, lead_of[key])] = true
			for entry: Array in weights.get(key, []): own[id][_find(group, entry[0])] = true
	var relative := {}
	for key: String in position: relative[key] = height[key] - old_base[key]
	var ground_segments: Array = []
	for road: Dictionary in document.roads:
		if structures.has(road.id) or road.kind != "ground": continue
		for i in range(road.points.size() - 1): ground_segments.append([road, i, _xz(road.points[i]), _xz(road.points[i + 1])])
	var ground_buckets := _buckets(ground_segments)
	# A pad level is free within the bounds its crossings put on its samples;
	# moving it moves the decks rebased on it, so repeat until it settles.
	var lifted := {}
	var report := {}
	var rounds := 0
	var history := {}
	while true:
		rounds += 1
		lifted = {}
		for key: String in position:
			var base: float = level[lead_of[key]] if lead_of.has(key) else _weighted(weights[key], level)
			lifted[key] = height[key] - roundi(old_base[key]) + roundi(base)
		report = _constrain(structures, vertex, position, lifted, relative, own, ground_segments, ground_buckets)
		# The last round only rebases; unresolved bounds refuse below.
		if rounds > MAX_ROUNDS: break
		var moved := false
		for root: String in members:
			var low_bound := -1000000
			var high_bound := 1000000
			for key: Vector2i in pad_keys[root]:
				low_bound = maxi(low_bound, _floor.get(key, -1000000))
				high_bound = mini(high_bound, _ceiling.get(key, 1000000))
			var h: int = level[members[root][0]]
			if low_bound > high_bound: continue
			var settled := clampi(h, low_bound, high_bound)
			if settled == h: continue
			# A bound on decks rebased on this pad moves with its level: solve
			# that line from the last two rounds instead of creeping towards it.
			var bound := high_bound if settled < h else low_bound
			if history.has(root) and history[root][0] != h:
				var slope := float(bound - history[root][1]) / float(h - history[root][0])
				if slope >= 0.0 and slope < 0.95:
					var solved := (bound - slope * h) / (1.0 - slope)
					settled = floori(solved) if settled < h else ceili(solved)
			history[root] = [h, bound]
			moved = true
			for node_id: String in members[root]: level[node_id] = settled
			for key: Vector2i in pad_keys[root]: _pad[key] = settled
		if not moved: break
	report.rounds = rounds
	# Anchor-side ground vertices take the pad level (their mouths interpolate
	# it). The far end of a two-point arm rises with it when it is an ordinary
	# ground junction; otherwise a level vertex is inserted far enough out to
	# keep the junction mouths where they were.
	var arms := {}
	for node_id: String in anchors:
		for road: Dictionary in incident[node_id]:
			if structures.has(road.id): continue
			if road.kind != "ground" or road.get("design") != null:
				_fail("structure joins a non-ground road", road.id)
				continue
			if not arms.has(road.id): arms[road.id] = {}
			arms[road.id]["from" if road.from == node_id else "to"] = node_id
	var claims := {}
	for id: String in arms:
		var road: Dictionary = roads[id]
		if road.points.size() != 2 or arms[id].size() != 1: continue
		var end: String = arms[id].keys()[0]
		var far: String = road.to if end == "from" else road.from
		var h: int = level[arms[id][end]]
		if anchors.has(far) or claims.get(far, h) != h: continue
		var plain := true
		for joined: Dictionary in incident[far]:
			if structures.has(joined.id) or joined.kind != "ground" or joined.get("design") != null: plain = false
		if plain: claims[far] = h
	var ground_roads := {}
	for id: String in arms: ground_roads[id] = true
	for node_id: String in claims:
		for road: Dictionary in incident[node_id]: ground_roads[road.id] = true
	# Estimated structures crossing each other keep their separation.
	var structure_segments: Array = []
	for id: String in structures:
		var road: Dictionary = structures[id]
		for i in range(road.points.size() - 1): structure_segments.append([road, i, _xz(road.points[i]), _xz(road.points[i + 1])])
	var structure_buckets := _buckets(structure_segments)
	for x in range(structure_segments.size()):
		var first: Dictionary = structure_segments[x][0]
		var i: int = structure_segments[x][1]
		for y: int in _near(structure_buckets, structure_segments[x][2], structure_segments[x][3]):
			if y <= x: continue
			var second: Dictionary = structure_segments[y][0]
			var j: int = structure_segments[y][1]
			var hit: Variant = _cross(structure_segments[x][2], structure_segments[x][3], structure_segments[y][2], structure_segments[y][3])
			if hit == null: continue
			var before := absf(_at(first, i, hit, height, vertex) - _at(second, j, hit, height, vertex))
			var after := absf(_at(first, i, hit, lifted, vertex) - _at(second, j, hit, lifted, vertex))
			if before >= 1.0 and after < minf(before, _separation_cm): _fail("crossing structures lose separation", first.id + " × " + second.id)
	var delta := PackedInt32Array()
	var changes := {"pad":[], "cut":[], "fill":[]}
	var keys := _pad.duplicate()
	keys.merge(_floor); keys.merge(_ceiling)
	for key: Vector2i in keys:
		var before := _sample(key)
		var after := before
		if _floor.has(key) and _ceiling.has(key) and _floor[key] > _ceiling[key]: _fail("cut and fill conflict", str(key))
		if _pad.has(key):
			after = _pad[key]
			if (_floor.has(key) and _floor[key] > after) or (_ceiling.has(key) and _ceiling[key] < after): _fail("crossing needs a pad sample", "%s at %s (pad %s level %d, bound %d..%d)" % [_source.get(key, ""), str(key), _pad_of[key].right(12), after, _floor.get(key, -1000000), _ceiling.get(key, 1000000)])
		else:
			if _ceiling.has(key): after = mini(after, _ceiling[key])
			if _floor.has(key): after = maxi(after, _floor[key])
		if before == after: continue
		var change := after - before
		if _pad_of.has(key):
			if absi(change) > report.max_pad_cm: report.max_pad_at = _pad_of[key]
			report.max_pad_cm = maxi(report.max_pad_cm, absi(change)); changes.pad.append(absi(change))
		elif change < 0:
			if -change > report.max_cut_cm: report.max_cut_at = _source.get(key, "")
			report.clamped += 1; report.max_cut_cm = maxi(report.max_cut_cm, -change); changes.cut.append(-change)
		else:
			if change > report.max_fill_cm: report.max_fill_at = _source.get(key, "")
			report.filled += 1; report.max_fill_cm = maxi(report.max_fill_cm, change); changes.fill.append(change)
		if absi(change) > _max_edit_cm: _fail("terrain edit beyond the bound", str(key))
		delta.append_array([key.x, key.y, before, after])
	if delta.size() / 4 > MAX_EDITED_SAMPLES: _fail("terrain edit count", str(delta.size() / 4))
	report.edited_samples = delta.size() / 4
	for kind: String in changes:
		var values: Array = changes[kind]
		values.sort()
		report["p50_%s_cm" % kind] = values[values.size() / 2] if not values.is_empty() else 0
		report["p95_%s_cm" % kind] = values[mini(values.size() - 1, values.size() * 95 / 100)] if not values.is_empty() else 0
	report.pads = members.size()
	report.anchors = anchors.size()
	report.structures = structures.size()
	if not _failures.is_empty(): return _refuse(report)
	result = JSON.parse_string(_native.apply_delta(delta, false))
	if not result.ok: return {"error":store.reason(result)}
	var materialized: Dictionary = _native.materialize()
	if not materialized.get("ok", false): return {"error":store.reason(materialized)}
	var canonical: Dictionary = JSON.parse_string(materialized.data.canonical)
	# Only cells sharing an edited sample take re-encoded payloads.
	var touched := {}
	var per_cell := int(store.document.cell_size_cm) / _spacing
	for row in range(0, delta.size(), 4):
		for y in range(maxi(0, floori((delta[row + 1] - 1) / float(per_cell))), delta[row + 1] / per_cell + 1):
			for x in range(maxi(0, floori((delta[row] - 1) / float(per_cell))), delta[row] / per_cell + 1): touched[Vector2i(x, y)] = true
	var fitted := {}
	for record: Dictionary in canonical.heightmaps:
		if materialized.data.blobs.has(record.path) and touched.has(Vector2i(int(record.cell.x), int(record.cell.y))):
			fitted[Vector2i(int(record.cell.x), int(record.cell.y))] = {"path":record.path, "offset_cm":int(record.offset_cm), "step_cm":int(record.step_cm), "bytes":materialized.data.blobs[record.path]}
	for cell: Vector2i in fitted:
		var inside := false
		for record: Dictionary in records:
			if int(record.cell.x) == cell.x and int(record.cell.y) == cell.y: inside = true
		if not inside: return {"error":"Structure fitting would change terrain outside this DEM."}
	var patches: Array = []
	for id: String in structures:
		var road: Dictionary = structures[id]
		var after: Dictionary = road.duplicate(true)
		for i in range(after.points.size()): after.points[i][1] = lifted[vertex[id + "@" + str(i)]]
		if not _same(road, after): patches.append({"field":"roads", "id":id, "before":road.duplicate(true), "after":after})
	for id: String in ground_roads:
		var road: Dictionary = roads[id]
		var after := _level_arm(road, arms.get(id, {}), level, claims, arm_radius)
		if not _same(road, after):
			patches.append({"field":"roads", "id":id, "before":road.duplicate(true), "after":after})
			if after.points.size() != road.points.size(): report.inserted_vertices = report.get("inserted_vertices", 0) + after.points.size() - road.points.size()
	var node_patches := {}
	for key: String in position:
		if nodes.has(key): node_patches[key] = lifted[key]
	for node_id: String in claims: node_patches[node_id] = claims[node_id]
	for node_id: String in node_patches:
		var node: Dictionary = nodes[node_id]
		if int(node.position[1]) == node_patches[node_id]: continue
		var after: Dictionary = node.duplicate(true)
		after.position[1] = node_patches[node_id]
		patches.append({"field":"nodes", "id":node_id, "before":node.duplicate(true), "after":after})
	report.profile = PROFILE
	report.estimated = true
	report.changed_roads = 0
	report.changed_nodes = 0
	for patch: Dictionary in patches:
		if patch.field == "roads": report.changed_roads += 1
		else: report.changed_nodes += 1
	report.fitted_cells = fitted.size()
	report.delta_sha256 = _digest(delta)
	return {"patches":patches, "fitted":fitted, "receipt":report}

static func _weighted(weights: Array, heights: Dictionary) -> float:
	var total := 0.0
	var sum := 0.0
	for entry: Array in weights:
		total += entry[1]; sum += entry[1] * heights[entry[0]]
	return sum / total

## Terrain bounds under decks, above tunnels and where ground roads cross.
## A ground road under a deck keeps 5 source metres, or the clearance it had
## on flat terrain where that was less; one over a tunnel keeps its cover.
func _constrain(structures: Dictionary, vertex: Dictionary, position: Dictionary, lifted: Dictionary, relative: Dictionary, own: Dictionary, ground_segments: Array, ground_buckets: Dictionary) -> Dictionary:
	_floor.clear(); _ceiling.clear(); _source.clear()
	var report := {"clamped":0, "filled":0, "open_cut_samples":0, "max_cut_cm":0, "max_fill_cm":0, "max_pad_cm":0, "max_grade_permille":0, "crossings":0}
	for id: String in structures:
		var road: Dictionary = structures[id]
		for i in range(road.points.size() - 1):
			var a: String = vertex[id + "@" + str(i)]
			var b: String = vertex[id + "@" + str(i + 1)]
			var pa: Vector2 = position[a]
			var pb: Vector2 = position[b]
			var length := pa.distance_to(pb)
			if length > 0.0: report.max_grade_permille = maxi(report.max_grade_permille, roundi(absf(lifted[b] - lifted[a]) * 1000.0 / length))
			var half: float = road.widths_cm[i] * 0.5
			var clearance := int(road.clearance_cm) if road.clearance_cm != null else 0
			# A square projects onto the centreline between its corners' projections,
			# so the deck over it is bounded by the deck at those four points.
			var under := _cells(pa, pb, half)
			for square: Vector2i in under:
				var span := _span(square, pa, pb, lifted[a], lifted[b])
				for key: Vector2i in _corners({square:true}):
					if _pad_of.has(key) and own[id].has(_pad_of[key]): continue
					if road.kind == "bridge": _limit(key, floori(span.x) - DECK_MARGIN_CM, id)
					elif _sample(key) <= ceili(span.y) + clearance: report.open_cut_samples += 1
			for index: int in _near(ground_buckets, pa, pb):
				var other: Dictionary = ground_segments[index][0]
				var j: int = ground_segments[index][1]
				if _cross(pa, pb, ground_segments[index][2], ground_segments[index][3]) != null: report.crossings += 1
				for square: Vector2i in _cells(ground_segments[index][2], ground_segments[index][3], other.widths_cm[j] * 0.5):
					if not under.has(square): continue
					var span := _span(square, pa, pb, lifted[a], lifted[b])
					var flat := _span(square, pa, pb, relative[a], relative[b])
					for key: Vector2i in _corners({square:true}):
						if _pad_of.has(key) and own[id].has(_pad_of[key]): continue
						if road.kind == "bridge":
							_limit(key, floori(span.x) - clampi(floori(flat.x), DECK_MARGIN_CM, _separation_cm), id + " × " + other.id)
						else:
							var cover := -(ceili(flat.y) + clearance)
							if cover > 0: _raise(key, ceili(span.y) + clearance + mini(cover, COVER_CM), id + " × " + other.id)
	return report

## Document numbers may be floats; heights compare by value.
static func _same(road: Dictionary, after: Dictionary) -> bool:
	if road.points.size() != after.points.size(): return false
	for i in range(road.points.size()):
		if int(road.points[i][1]) != int(after.points[i][1]): return false
	return true

## Ground road with its anchored ends, raised far ends and the vertices next
## to anchored ends at the pad levels; a missing neighbour is inserted.
static func _level_arm(road: Dictionary, anchored: Dictionary, level: Dictionary, claims: Dictionary, radius: Dictionary) -> Dictionary:
	var after: Dictionary = road.duplicate(true)
	var n: int = after.points.size()
	var fixed := {}
	for end in ["from", "to"]:
		var index := 0 if end == "from" else n - 1
		var h: Variant = level[anchored[end]] if anchored.has(end) else claims.get(road[end])
		if h == null: continue
		after.points[index][1] = h
		fixed[index] = h
	var inserts := {}
	for end: String in anchored:
		var h: int = level[anchored[end]]
		var next := 1 if end == "from" else n - 2
		var interior := next > 0 and next < n - 1
		if fixed.get(next, h) == h and (interior or fixed.has(next)):
			if interior:
				after.points[next][1] = h
				fixed[next] = h
			continue
		# Keep the mouth's centre and extension: the new first segment must be at
		# least radius/0.40 and (radius + 2 m)/0.45 long when the segment allows.
		var r: float = radius[anchored[end]]
		inserts[end] = maxf(r / 0.40, (r + 200.0) / 0.45)
	# Distances along the original end segments; on a two-point road both
	# inserted vertices share its one segment and stay apart.
	var shared := inserts.size() == 2 and n == 2
	var first_length := _xz(after.points[0]).distance_to(_xz(after.points[1]))
	var last_length := _xz(after.points[n - 2]).distance_to(_xz(after.points[n - 1]))
	var t_to := 1.0
	if inserts.has("to"):
		var distance: float = minf(inserts.to, last_length * 0.5 - 1.0 if shared else last_length * 0.9)
		t_to = 1.0 - distance / maxf(last_length, 1.0)
		_insert(after, n - 2, t_to, level[anchored.to], road.points[n - 2], road.points[n - 1])
	if inserts.has("from"):
		var distance: float = minf(inserts.from, first_length * 0.5 - 1.0 if shared else first_length * 0.9)
		var t: float = distance / maxf(first_length, 1.0)
		_insert(after, 0, t, level[anchored.from], road.points[0], road.points[1])
	return after

## The new vertex lies at `t` along the original segment a-b, so a second
## insert on a shared segment does not drift from it.
static func _insert(road: Dictionary, segment: int, t: float, height: int, a: Array, b: Array) -> void:
	road.points.insert(segment + 1, [roundi(lerpf(a[0], b[0], t)), height, roundi(lerpf(a[2], b[2], t))])
	road.widths_cm.insert(segment, road.widths_cm[segment])
	road.surfaces.insert(segment, road.surfaces[segment])

static func _digest(delta: PackedInt32Array) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	if not delta.is_empty(): context.update(delta.to_byte_array())
	return context.finish().hex_encode()

func _refuse(report: Dictionary = {}) -> Dictionary:
	var parts: Array = []
	for reason: String in _failures:
		parts.append("%s ×%d: %s" % [reason, _counts[reason], ", ".join(PackedStringArray(_failures[reason]))])
	return {"error":"Estimated structures cannot be fitted to this DEM; the map keeps its flat terrain. " + "; ".join(PackedStringArray(parts)), "failures":_counts, "receipt":report}

func _limit(key: Vector2i, value: int, source: String) -> void:
	if value < _ceiling.get(key, value + 1):
		_ceiling[key] = value; _source[key] = source

func _raise(key: Vector2i, value: int, source: String) -> void:
	if value > _floor.get(key, value - 1):
		_floor[key] = value; _source[key] = source

static func _at(road: Dictionary, i: int, hit: Vector2, heights: Dictionary, vertex: Dictionary) -> float:
	var a := _xz(road.points[i])
	var b := _xz(road.points[i + 1])
	var length := a.distance_to(b)
	var t := 0.0 if length == 0.0 else a.distance_to(hit) / length
	return lerpf(heights[vertex[road.id + "@" + str(i)]], heights[vertex[road.id + "@" + str(i + 1)]], t)

## Path distances from one anchor's lead; other anchors bound the search, so a
## base interpolates only between the anchors of its own structure.
static func _distances(edges: Dictionary, sources: Array, anchors: Dictionary) -> Dictionary:
	var best := {}
	var open: Array = []
	var start := {}
	for key: String in sources:
		best[key] = 0.0
		start[key] = true
		open.append([0.0, key])
	while not open.is_empty():
		var index := 0
		for i in range(1, open.size()):
			if open[i][0] < open[index][0]: index = i
		var current: Array = open[index]
		open.remove_at(index)
		if current[0] > best[current[1]]: continue
		if anchors.has(current[1]) and not start.has(current[1]): continue
		for edge: Array in edges[current[1]]:
			var d: float = current[0] + edge[1]
			if d < best.get(edge[0], INF):
				best[edge[0]] = d
				open.append([d, edge[0]])
	return best

static func _find(group: Dictionary, key: String) -> String:
	while group[key] != key:
		group[key] = group[group[key]]
		key = group[key]
	return key

static func _union(group: Dictionary, a: String, b: String) -> void:
	group[_find(group, a)] = _find(group, b)

## Transfer shape guard: only heights change, on records of this document
## (imported, or drawn roads joining an anchor).
static func index(document: Dictionary) -> Dictionary:
	var result := {"roads":{}, "nodes":{}}
	for field in ["roads", "nodes"]:
		for record: Dictionary in document[field]: result[field][record.id] = record
	return result

static func valid_patch(patch: Dictionary, records: Dictionary) -> bool:
	if patch.get("field") not in ["roads", "nodes"] or patch.get("before") is not Dictionary or patch.get("after") is not Dictionary: return false
	var before: Dictionary = patch.before
	var after: Dictionary = patch.after
	if before.get("id") != patch.get("id") or after.get("id") != patch.get("id"): return false
	if records[patch.field].get(patch.id) != before: return false
	if patch.field == "nodes":
		var moved := after.duplicate(true)
		moved.position = before.position
		return moved == before and after.position[0] == before.position[0] and after.position[2] == before.position[2] and TYPES._finite(after.position[1], -1000000, 1000000)
	var expected := after.duplicate(true)
	for key in ["points", "widths_cm", "surfaces"]: expected[key] = before[key]
	if expected != before: return false
	if after.points.size() == before.points.size():
		if after.widths_cm != before.widths_cm or after.surfaces != before.surfaces: return false
	elif before.kind != "ground" or after.points.size() > before.points.size() + 2: return false
	# Every original vertex keeps its plan position in order; inserted ones lie
	# on the original segment and repeat its width and surface.
	var j := 0
	for i in range(after.points.size()):
		var point: Array = after.points[i]
		if not TYPES._finite(point[1], -1000000, 1000000): return false
		# The segment of `before` that ends at, or contains, this vertex.
		var segment := j - 1
		if j < before.points.size() and point[0] == before.points[j][0] and point[2] == before.points[j][2]:
			j += 1
		elif j == 0 or j >= before.points.size():
			return false
		elif Geometry2D.get_closest_point_to_segment(_xz(point), _xz(before.points[j - 1]), _xz(before.points[j])).distance_to(_xz(point)) > 1.0:
			return false
		if i > 0 and (after.widths_cm[i - 1] != before.widths_cm[segment] or after.surfaces[i - 1] != before.surfaces[segment]): return false
	return j == before.points.size() and after.widths_cm.size() == after.points.size() - 1 and after.surfaces.size() == after.points.size() - 1

