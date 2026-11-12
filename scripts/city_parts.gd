extends RefCounted
## City part files v1 and pure placement/capture planning over document
## dictionaries. MapKit validation and DocumentStore commit stay with the caller
## (one `authoring_tools.apply` = one Undo). Part records use MapDocument v1
## shapes in real-scale source centimetres around a local origin; a map at 1:D
## divides them by D, exactly like an OSM import.
const UNITS := preload("./import_units.gd")
const EDIT := preload("./workbench_edit.gd")
const I18N := preload("./locale_text.gd")
const FORMAT := "miniearthure-city-part"
const VERSION := 1
const FIELDS := ["nodes", "roads", "buildings", "zones", "surface_areas", "barriers", "placements"]
const KEYS := ["format", "version", "id", "name", "license", "attributions", "footprint", "mouths", "records"]
## Existing records a replacing part removes or cuts at its footprint edge.
const REPLACED := ["roads", "repetitions", "barriers", "buildings", "zones", "surface_areas", "placements", "pois"]
const BUILTIN_DIR := "res://parts"
const MAX_BYTES := 8 * 1024 * 1024
## Mouths join road ends (or roads) within 20 real metres of the mouth.
const JOIN_SOURCE_CM := 2000.0
## Cut pieces shorter than this (map cm) are dropped instead of kept as stubs.
const MIN_PIECE_CM := 50.0
const INVALID := "Invalid city part file: %s"
const TOO_SMALL := "The part is too small for this map scale."
const WRITE_FAILED := "Cannot write the part file: %s"
const USER_LICENSE := "LicenseRef-user"
static var user_dir_override := ""

static func user_dir() -> String:
	if user_dir_override != "": return user_dir_override
	return OS.get_system_dir(OS.SYSTEM_DIR_DOCUMENTS).path_join("MiniEarthure maps").path_join("parts")

static func _invalid(what: String) -> Dictionary:
	return {"error": I18N.t(INVALID) % what}

# ---------------------------------------------------------------- file format

static func _is_int(value: Variant) -> bool:
	return (value is int) or (value is float and is_finite(value) and value == floorf(value))

static func _ints(value: Variant) -> Variant:
	if value is float and value == floorf(value) and absf(value) < 9.0e15: return int(value)
	if value is Array:
		var result: Array = []
		for item: Variant in value: result.append(_ints(item))
		return result
	if value is Dictionary:
		var result := {}
		for key: Variant in value: result[key] = _ints(value[key])
		return result
	return value

static func _point_ok(value: Variant, size: int) -> bool:
	if value is not Array or value.size() != size: return false
	for item: Variant in value:
		if not _is_int(item) or absf(float(item)) > 1.0e8: return false
	return true

static func _ring_ok(value: Variant) -> bool:
	if value is not Array or value.size() < 3 or value.size() > 512: return false
	for point: Variant in value:
		if not _point_ok(point, 2): return false
	return absf(_area(_packed(value))) > 0.0

static func _rings_ok(value: Variant) -> bool:
	if value is not Array: return false
	for ring: Variant in value:
		if not _ring_ok(ring): return false
	return true

static func _local_id_ok(value: Variant) -> bool:
	if value is not String: return false
	var pattern := RegEx.create_from_string("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
	return pattern.search(value) != null

## Strict v1 reader: unknown keys, versions or malformed geometry are refused.
## MapKit validates the full record shapes when the part is placed.
static func parse(text: String) -> Dictionary:
	if text.length() > MAX_BYTES: return _invalid("size")
	var parser := JSON.new()
	if parser.parse(text) != OK or parser.data is not Dictionary: return _invalid("json")
	var part: Dictionary = _ints(parser.data)
	for key: Variant in part:
		if str(key) not in KEYS: return _invalid(str(key))
	for key: String in KEYS:
		if not part.has(key): return _invalid(key)
	if part.format != FORMAT: return _invalid("format")
	if part.version is not int or part.version != VERSION: return _invalid("version")
	if not RegEx.create_from_string("^[a-z0-9][a-z0-9-]{0,63}$").search(str(part.id)) or part.id is not String: return _invalid("id")
	for key in ["name", "license"]:
		if part[key] is not String or part[key].strip_edges() == "" or part[key].length() > 256: return _invalid(key)
	if part.attributions is not Array: return _invalid("attributions")
	for attribution: Variant in part.attributions:
		if attribution is not Dictionary or attribution.keys().size() != 3: return _invalid("attributions")
		for key in ["source", "license", "notice"]:
			if attribution.get(key) is not String: return _invalid("attributions")
		if attribution.source.strip_edges() == "" or attribution.license.strip_edges() == "": return _invalid("attributions")
		# Import metadata (adapter, 1:D provenance) belongs to the source map only.
		var meta: Variant = JSON.parse_string(attribution.notice.strip_edges()) if attribution.notice.strip_edges().begins_with("{") else null
		if meta is Dictionary: return _invalid("attributions")
	if not _ring_ok(part.footprint): return _invalid("footprint")
	if part.records is not Dictionary: return _invalid("records")
	var ids := {}
	var count := 0
	for field: Variant in part.records:
		if str(field) not in FIELDS or part.records[field] is not Array: return _invalid("records")
		for record: Variant in part.records[field]:
			if record is not Dictionary or not _local_id_ok(record.get("id")) or ids.has(record.id): return _invalid(str(field))
			ids[record.id] = field
			count += 1
			if not _record_ok(str(field), record): return _invalid(str(field) + "/" + str(record.id))
	if count == 0: return _invalid("records")
	var degree := {}
	for road: Dictionary in part.records.get("roads", []):
		for end in ["from", "to"]:
			if ids.get(road.get(end), "") != "nodes": return _invalid("roads/" + str(road.id))
			degree[road[end]] = int(degree.get(road[end], 0)) + 1
	if part.mouths is not Array: return _invalid("mouths")
	var mouths := {}
	for mouth: Variant in part.mouths:
		if mouth is not Dictionary or mouth.keys().size() != 3 or mouths.has(mouth.get("node")): return _invalid("mouths")
		if int(degree.get(mouth.get("node"), 0)) != 1: return _invalid("mouths")
		if not (mouth.get("heading_deg") is int or mouth.get("heading_deg") is float) or not is_finite(float(mouth.heading_deg)): return _invalid("mouths")
		if mouth.get("width_cm") is not int or mouth.width_cm < 20 or mouth.width_cm > 10000: return _invalid("mouths")
		mouths[mouth.node] = true
	return {"part": part}

## Integer fields: `required` must be present, `optional` may be absent or null.
static func _scalars_ok(record: Dictionary, required: Array, optional: Array = []) -> bool:
	for key: String in required:
		if record.get(key) is not int: return false
	for key: String in optional:
		if record.get(key) != null and record.get(key) is not int: return false
	return true

## The geometry and scalar fields `transform` reads; MapKit checks the rest.
static func _record_ok(field: String, record: Dictionary) -> bool:
	match field:
		"nodes": return _point_ok(record.get("position"), 3) and _scalars_ok(record, [], ["level"])
		"placements": return _point_ok(record.get("position"), 3) and record.get("asset_id") is String and _scalars_ok(record, ["quarter_turns"], ["yaw_offset_mdeg"])
		"roads":
			var points: Variant = record.get("points")
			if points is not Array or points.size() < 2: return false
			for point: Variant in points:
				if not _point_ok(point, 3): return false
			if record.get("widths_cm") is not Array or record.widths_cm.size() != points.size() - 1 or record.get("surfaces") is not Array or record.surfaces.size() != points.size() - 1: return false
			if not record.widths_cm.all(func(w: Variant) -> bool: return w is int) or not record.surfaces.all(func(s: Variant) -> bool: return s is String): return false
			if record.get("markings") != null and (record.markings is not Dictionary or not _scalars_ok(record.markings, [], ["lane_width_cm", "median_width_cm"])): return false
			return record.get("from") is String and record.get("to") is String and _scalars_ok(record, [], ["clearance_cm", "sidewalk_cm"])
		"buildings":
			if not _ring_ok(record.get("footprint")) or not _rings_ok(record.get("holes", [])) or not _rings_ok(record.get("entrances", [])): return false
			if record.get("parts", []) is not Array or not _scalars_ok(record, ["base_cm", "height_cm"]): return false
			for solid: Variant in record.get("parts", []):
				if solid is not Dictionary or not _ring_ok(solid.get("footprint")) or not _rings_ok(solid.get("holes", [])) or not _scalars_ok(solid, [], ["base_cm", "height_cm"]): return false
			return true
		"zones": return _ring_ok(record.get("polygon")) and _rings_ok(record.get("exclusions", [])) and _scalars_ok(record, ["spacing_cm"])
		"surface_areas": return _ring_ok(record.get("polygon"))
		"barriers":
			var line: Variant = record.get("line")
			if line is not Array or line.size() < 2: return false
			for point: Variant in line:
				if not _point_ok(point, 2): return false
			return _scalars_ok(record, ["height_cm", "thickness_cm"])
	return false

static func read(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return _invalid(path.get_file())
	if file.get_length() > MAX_BYTES: return _invalid(path.get_file())
	var result := parse(file.get_as_text())
	if result.has("part"): result.path = path
	else: result.error = path.get_file() + ": " + str(result.error)
	return result

## Every readable part in a folder, sorted by file name; unreadable files are
## reported, never silently skipped.
static func list(directory: String) -> Dictionary:
	var parts: Array = []
	var errors: Array = []
	if not DirAccess.dir_exists_absolute(directory): return {"parts": parts, "errors": errors}
	var names := Array(DirAccess.get_files_at(directory))
	names.sort()
	for name: String in names:
		if name.get_extension().to_lower() != "json": continue
		var result := read(directory.path_join(name))
		if result.has("part"): parts.append(result)
		else: errors.append(result.error)
	return {"parts": parts, "errors": errors}

## Writes and reads back a pending copy beside `path`; returns its path or "".
static func _pending(path: String, part: Dictionary) -> String:
	var pending := path + ".pending-" + Crypto.new().generate_random_bytes(6).hex_encode()
	var text := JSON.stringify(part, "\t") + "\n"
	var file := FileAccess.open(pending, FileAccess.WRITE)
	if file == null: return ""
	var stored := file.store_string(text) and file.get_error() == OK
	file.close()
	if not stored or FileAccess.get_file_as_string(pending) != text:
		DirAccess.remove_absolute(pending)
		return ""
	return pending

static func _write_new(path: String, part: Dictionary) -> String:
	var pending := _pending(path, part)
	if pending == "": return I18N.t(WRITE_FAILED) % path
	if FileAccess.file_exists(path) or DirAccess.rename_absolute(pending, path) != OK:
		DirAccess.remove_absolute(pending)
		return I18N.t(WRITE_FAILED) % path
	return ""

## Writes a new user part; an existing file is never overwritten.
static func save_user(part: Dictionary, directory: String = "") -> Dictionary:
	var folder := directory if directory != "" else user_dir()
	DirAccess.make_dir_recursive_absolute(folder)
	var checked := parse(JSON.stringify(part))
	if checked.has("error"): return checked
	var path := folder.path_join(str(part.id) + ".json")
	if FileAccess.file_exists(path): return {"error": I18N.t(WRITE_FAILED) % path}
	var failure := _write_new(path, checked.part)
	return {"error": failure} if failure != "" else {"path": path}

## Renames a user part in place (same file and ID).
static func rename_user(path: String, name: String) -> String:
	var current := read(path)
	if current.has("error"): return current.error
	var part: Dictionary = current.part
	part.name = name.strip_edges()
	if parse(JSON.stringify(part)).has("error"): return I18N.t(INVALID) % "name"
	# The verified copy replaces the file through a kept backup, so a failed
	# move can always restore the original.
	var pending := _pending(path, part)
	if pending == "": return I18N.t(WRITE_FAILED) % path
	var backup := path + ".previous-" + Crypto.new().generate_random_bytes(6).hex_encode()
	if DirAccess.rename_absolute(path, backup) != OK:
		DirAccess.remove_absolute(pending)
		return I18N.t(WRITE_FAILED) % path
	if DirAccess.rename_absolute(pending, path) != OK:
		if not FileAccess.file_exists(path): DirAccess.rename_absolute(backup, path)
		DirAccess.remove_absolute(pending)
		return I18N.t(WRITE_FAILED) % path
	DirAccess.remove_absolute(backup)
	return ""

static func delete_user(path: String) -> String:
	return "" if DirAccess.remove_absolute(path) == OK else I18N.t(WRITE_FAILED) % path

# ------------------------------------------------------------------ geometry

static func _packed(ring: Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point: Array in ring: result.append(Vector2(point[0], point[1]))
	return result

static func _area(ring: PackedVector2Array) -> float:
	var sum := 0.0
	for i in ring.size():
		var a := ring[i]
		var b := ring[(i + 1) % ring.size()]
		sum += a.x * b.y - b.x * a.y
	return sum / 2.0

static func _round_ring(ring: PackedVector2Array) -> Array:
	var result: Array = []
	for point in ring:
		var value := [roundi(point.x), roundi(point.y)]
		if result.is_empty() or result[-1] != value: result.append(value)
	while result.size() > 1 and result[0] == result[-1]: result.pop_back()
	return result

static func _plan(vertex: Array) -> Vector2:
	return Vector2(vertex[0], vertex[2]) if vertex.size() == 3 else Vector2(vertex[0], vertex[1])

static func _inside(point: Vector2, ring: PackedVector2Array) -> bool:
	return Geometry2D.is_point_in_polygon(point, ring)

static func _overlaps(ring: PackedVector2Array, footprint: PackedVector2Array) -> bool:
	return not Geometry2D.intersect_polygons(ring, footprint).is_empty()

## Polyline pieces outside `footprint`. Vertices are [x,y] or [x,h,y]; cut
## points interpolate height. Each piece keeps the source segment index of its
## segments and whether it starts/ends at the original line ends.
static func _outside_pieces(points: Array, footprint: PackedVector2Array) -> Dictionary:
	var pieces: Array = []
	var current: Dictionary = {}
	var cut := false
	for i in range(points.size() - 1):
		var a: Array = points[i]
		var b: Array = points[i + 1]
		var pa := _plan(a)
		var pb := _plan(b)
		var cuts: Array[float] = [0.0, 1.0]
		var length := pa.distance_to(pb)
		for j in footprint.size():
			var hit: Variant = Geometry2D.segment_intersects_segment(pa, pb, footprint[j], footprint[(j + 1) % footprint.size()])
			if hit != null and length > 0.0: cuts.append(clampf(pa.distance_to(hit) / length, 0.0, 1.0))
		cuts.sort()
		for k in range(cuts.size() - 1):
			var t0: float = cuts[k]
			var t1: float = cuts[k + 1]
			if t1 - t0 <= 0.000001: continue
			var outside := not _inside(pa.lerp(pb, (t0 + t1) / 2.0), footprint)
			if not outside:
				cut = true
				if not current.is_empty(): pieces.append(current)
				current = {}
				continue
			var start := _lerp_vertex(a, b, t0)
			var end := _lerp_vertex(b, a, 1.0 - t1) if t1 < 1.0 else b.duplicate()
			if current.is_empty():
				current = {"points": [start], "segments": [], "from_start": i == 0 and t0 == 0.0, "to_end": false}
			current.points.append(end)
			current.segments.append(i)
			current.to_end = i == points.size() - 2 and t1 == 1.0
	if not current.is_empty(): pieces.append(current)
	return {"cut": cut, "pieces": pieces}

static func _lerp_vertex(a: Array, b: Array, t: float) -> Array:
	if t <= 0.0: return a.duplicate()
	var result: Array = []
	for i in a.size(): result.append(roundi(lerpf(float(a[i]), float(b[i]), t)))
	return result

## Removes consecutive plan duplicates while keeping both exact end vertices.
static func _dedupe_line(points: Array, segments: Array) -> Dictionary:
	var kept: Array = [points[0]]
	var kept_segments: Array = []
	for i in range(1, points.size()):
		if _plan(points[i]) == _plan(kept[-1]):
			if i == points.size() - 1: kept[-1] = points[i]
			continue
		kept.append(points[i])
		kept_segments.append(segments[i - 1])
	if kept.size() >= 2 and _plan(kept[-1]) != _plan(points[-1]): kept[-1] = points[-1]
	return {"points": kept, "segments": kept_segments}

static func _line_length(points: Array) -> float:
	var total := 0.0
	for i in range(1, points.size()): total += _plan(points[i]).distance_to(_plan(points[i - 1]))
	return total

## Area minus footprint as hole-free rings. When the footprint lies wholly inside
## the area, the area is first split through the footprint's centre so no piece
## needs a hole (surface areas cannot hold one).
static func _subtract(ring: PackedVector2Array, footprint: PackedVector2Array) -> Array:
	var result := Geometry2D.clip_polygons(ring, footprint)
	if result.size() <= 1 or not _has_hole(result): return result
	var box := Rect2(ring[0], Vector2.ZERO)
	for point in ring: box = box.expand(point)
	for point in footprint: box = box.expand(point)
	box = box.grow(100.0)
	var middle := 0.0
	for point in footprint: middle += point.y / footprint.size()
	var pieces: Array = []
	for half: Rect2 in [Rect2(box.position, Vector2(box.size.x, middle - box.position.y)), Rect2(Vector2(box.position.x, middle), Vector2(box.size.x, box.end.y - middle))]:
		var rect := PackedVector2Array([half.position, Vector2(half.end.x, half.position.y), half.end, Vector2(half.position.x, half.end.y)])
		for side: PackedVector2Array in Geometry2D.intersect_polygons(ring, rect):
			for piece: PackedVector2Array in Geometry2D.clip_polygons(side, footprint): pieces.append(piece)
	return [] if _has_hole(pieces) else pieces

static func _has_hole(rings: Array) -> bool:
	if rings.size() < 2: return false
	var largest := 0
	for i in rings.size():
		if absf(_area(rings[i])) > absf(_area(rings[largest])): largest = i
	var outer := _area(rings[largest]) > 0.0
	for ring: PackedVector2Array in rings:
		if (_area(ring) > 0.0) != outer: return true
	return false

# ----------------------------------------------------------------- placement

## Part records transformed onto the map: rotate `angle_deg` counter-clockwise
## about the local origin, divide by D, translate to `origin` (map cm) and lift
## heights onto `ground_cm`. IDs gain `prefix`. Gable roofs that no longer sit
## on an axis-aligned rectangle become flat.
static func transform(part: Dictionary, origin: Vector2, angle_deg: float, denominator: int, ground_cm: int, prefix: String) -> Dictionary:
	var d := float(maxi(1, denominator))
	var radians := deg_to_rad(angle_deg)
	var remainder := fposmod(angle_deg, 90.0)
	var right_angle := remainder < 0.0001 or remainder > 89.9999
	var point := func(p: Array) -> Array:
		var v := Vector2(p[0], p[1]).rotated(radians) / d + origin
		return [roundi(v.x), roundi(v.y)]
	var vertex := func(p: Array) -> Array:
		var v := Vector2(p[0], p[2]).rotated(radians) / d + origin
		return [roundi(v.x), ground_cm + roundi(float(p[1]) / d), roundi(v.y)]
	var ring := func(r: Array) -> Array:
		var result: Array = []
		for p: Array in r:
			var value: Array = point.call(p)
			if result.is_empty() or result[-1] != value: result.append(value)
		while result.size() > 1 and result[0] == result[-1]: result.pop_back()
		return result
	var scaled := func(value: Variant, low: int, high: int) -> int:
		return clampi(roundi(float(value) / d), low, high)
	var out := {}
	for field in FIELDS: out[field] = []
	var records: Dictionary = part.records
	var positions := {}
	for node: Dictionary in records.get("nodes", []):
		var copy := node.duplicate(true)
		copy.id = prefix + str(node.id)
		copy.position = vertex.call(node.position)
		positions[node.id] = copy.position
		out.nodes.append(copy)
	for road: Dictionary in records.get("roads", []):
		var copy := road.duplicate(true)
		copy.id = prefix + str(road.id)
		copy.from = prefix + str(road.from)
		copy.to = prefix + str(road.to)
		copy.erase("design")
		var points: Array = []
		for p: Array in road.points: points.append(vertex.call(p))
		points[0] = positions[road.from]
		points[-1] = positions[road.to]
		var line := _dedupe_line(points, range(road.widths_cm.size()))
		if line.points.size() < 2: return {"error": I18N.t(TOO_SMALL)}
		copy.points = line.points
		copy.widths_cm = line.segments.map(func(i: int) -> int: return scaled.call(road.widths_cm[i], 20, 10000))
		copy.surfaces = line.segments.map(func(i: int) -> Variant: return road.surfaces[i])
		if road.get("clearance_cm") != null: copy.clearance_cm = scaled.call(road.clearance_cm, 20, 5000)
		if road.get("sidewalk_cm") != null and int(road.sidewalk_cm) > 0:
			var sidewalk: int = scaled.call(road.sidewalk_cm, 0, 1000)
			copy.sidewalk_cm = sidewalk if sidewalk >= 20 else null
		if copy.get("markings") is Dictionary:
			for key in ["lane_width_cm", "median_width_cm"]:
				if copy.markings.has(key) and int(copy.markings[key]) > 0: copy.markings[key] = scaled.call(copy.markings[key], 1, 1000)
		out.roads.append(copy)
	for building: Dictionary in records.get("buildings", []):
		var copy := building.duplicate(true)
		copy.id = prefix + str(building.id)
		copy.footprint = ring.call(building.footprint)
		for key in ["holes", "entrances"]:
			if copy.has(key): copy[key] = building[key].map(func(r: Array) -> Array: return ring.call(r))
		copy.base_cm = ground_cm + roundi(float(building.base_cm) / d)
		copy.height_cm = scaled.call(building.height_cm, 1, 100000)
		for i in copy.get("parts", []).size():
			var solid: Dictionary = copy.parts[i]
			var source: Dictionary = building.parts[i]
			solid.footprint = ring.call(source.footprint)
			if solid.has("holes"): solid.holes = source.holes.map(func(r: Array) -> Array: return ring.call(r))
			if solid.has("base_cm"): solid.base_cm = ground_cm + roundi(float(source.base_cm) / d)
			if solid.has("height_cm"): solid.height_cm = scaled.call(source.height_cm, 1, 100000)
		if str(copy.get("roof", "")) == "gable" and not right_angle: copy.roof = "flat"
		for r: Array in [copy.footprint] + copy.get("holes", []) + copy.get("entrances", []):
			if r.size() < 3: return {"error": I18N.t(TOO_SMALL)}
		out.buildings.append(copy)
	for field in ["zones", "surface_areas"]:
		for area: Dictionary in records.get(field, []):
			var copy := area.duplicate(true)
			copy.id = prefix + str(area.id)
			copy.polygon = ring.call(area.polygon)
			if copy.polygon.size() < 3: return {"error": I18N.t(TOO_SMALL)}
			if copy.has("exclusions"): copy.exclusions = area.exclusions.map(func(r: Array) -> Array: return ring.call(r))
			if copy.has("spacing_cm"): copy.spacing_cm = scaled.call(area.spacing_cm, 25, 100000)
			out[field].append(copy)
	for barrier: Dictionary in records.get("barriers", []):
		var copy := barrier.duplicate(true)
		copy.id = prefix + str(barrier.id)
		var line: Array = []
		for p: Array in barrier.line:
			var value: Array = point.call(p)
			if line.is_empty() or line[-1] != value: line.append(value)
		if line.size() < 2: return {"error": I18N.t(TOO_SMALL)}
		copy.line = line
		if copy.has("height_cm"): copy.height_cm = scaled.call(barrier.height_cm, 10, 1000)
		if copy.has("thickness_cm"): copy.thickness_cm = scaled.call(barrier.thickness_cm, 5, 100)
		out.barriers.append(copy)
	for placement: Dictionary in records.get("placements", []):
		var copy := placement.duplicate(true)
		copy.id = prefix + str(placement.id)
		copy.position = vertex.call(placement.position)
		var total := posmod(int(placement.get("quarter_turns", 0)) * 90000 + int(placement.get("yaw_offset_mdeg", 0)) + roundi(angle_deg * 1000.0), 360000)
		copy.quarter_turns = floori(total / 90000.0)
		copy.yaw_offset_mdeg = total - int(copy.quarter_turns) * 90000
		if copy.yaw_offset_mdeg == 0: copy.erase("yaw_offset_mdeg")
		out.placements.append(copy)
	var mouths: Array = []
	for mouth: Dictionary in part.mouths:
		mouths.append({"node": prefix + str(mouth.node), "heading_deg": float(mouth.heading_deg) + angle_deg})
	var footprint: Array = ring.call(part.footprint)
	if footprint.size() < 3: return {"error": I18N.t(TOO_SMALL)}
	return {"records": out, "mouths": mouths, "footprint": footprint}

static func _record_id(field: String, record: Dictionary) -> String:
	if field == "attributions": return JSON.stringify([record.get("source", ""), record.get("license", ""), record.get("notice", "")])
	return str(record.get("id", ""))

## Plans one part placement. Options: `replace` (remove or cut existing objects
## under the footprint), `instance` (hex namespace token), `ground_cm` (map
## height under the origin). Returns {patches, selection, joined, mouths} or
## {error}; the caller validates and commits the patches as one command.
static func plan_place(document: Dictionary, part: Dictionary, origin: Vector2, angle_deg: float, options: Dictionary = {}) -> Dictionary:
	var scale := UNITS.osm_scale(document)
	if scale.has("error"): return {"error": scale.error}
	var denominator := maxi(1, int(scale.denominator))
	var prefix := "part-" + str(options.get("instance", Crypto.new().generate_random_bytes(4).hex_encode())) + "-"
	var placed := transform(part, origin, angle_deg, denominator, int(options.get("ground_cm", document.get("terrain_base_cm", 0))), prefix)
	if placed.has("error"): return placed
	var used := {}
	for field in EDIT.FIELDS + ["assets"]:
		for record: Variant in document.get(field, []):
			if record is Dictionary: used[str(record.get("id", ""))] = true
	for field in FIELDS:
		for record: Dictionary in placed.records[field]:
			if used.has(record.id) or record.id.length() > 128: return _invalid("id")
	var work := {}
	for field in REPLACED + ["nodes", "attributions"]: work[field] = document.get(field, []).duplicate(true)
	if options.get("replace", false): _replace(work, _packed(placed.footprint), prefix)
	var own := {}
	for field in FIELDS:
		for record: Dictionary in placed.records[field]:
			work[field].append(record)
			own[record.id] = true
	var joined := _join(work, placed.mouths, JOIN_SOURCE_CM / denominator, prefix, own)
	var credits := {}
	for attribution: Dictionary in work.attributions: credits[_record_id("attributions", attribution)] = true
	for attribution: Dictionary in part.attributions:
		if not credits.has(_record_id("attributions", attribution)):
			work.attributions.append(attribution.duplicate(true))
			credits[_record_id("attributions", attribution)] = true
	var patches: Array = []
	var selection: Array = []
	for field: String in work:
		var before := {}
		for record: Dictionary in document.get(field, []): before[_record_id(field, record)] = record
		var after := {}
		for record: Dictionary in work[field]: after[_record_id(field, record)] = record
		for id: String in before:
			if not after.has(id): patches.append({"field": field, "id": id, "before": before[id], "after": null})
			elif JSON.stringify(after[id]) != JSON.stringify(before[id]): patches.append({"field": field, "id": id, "before": before[id], "after": after[id]})
		for id: String in after:
			if before.has(id): continue
			patches.append({"field": field, "id": id, "before": null, "after": after[id]})
			if own.has(id) and field != "nodes": selection.append(EDIT.key(field, id))
	return {"patches": patches, "selection": selection, "joined": joined, "mouths": placed.mouths.size(), "prefix": prefix}

## Replace mode: point objects and buildings under the footprint go; roads,
## repetitions and barriers are cut at its edge (new road ends get nodes that
## mouths can join); zones and surface areas lose the covered part.
static func _replace(work: Dictionary, footprint: PackedVector2Array, prefix: String) -> void:
	var counter := [0]
	var next_id := func(kind: String) -> String:
		counter[0] += 1
		return prefix + "cut-" + kind + "-" + str(counter[0])
	work.placements = work.placements.filter(func(r: Dictionary) -> bool: return not _inside(_plan(r.position), footprint))
	work.pois = work.pois.filter(func(r: Dictionary) -> bool: return not _inside(Vector2(r.position[0], r.position[1]), footprint))
	var buildings: Array = []
	for building: Dictionary in work.buildings:
		var covered := _overlaps(_packed(building.footprint), footprint)
		for solid: Dictionary in building.get("parts", []): covered = covered or _overlaps(_packed(solid.footprint), footprint)
		if not covered: buildings.append(building)
	work.buildings = buildings
	for field in ["zones", "surface_areas"]:
		var kept: Array = []
		for area: Dictionary in work[field]:
			var ring := _packed(area.polygon)
			if not _overlaps(ring, footprint):
				kept.append(area)
				continue
			var first := true
			for piece: PackedVector2Array in _subtract(ring, footprint):
				var polygon := _round_ring(piece)
				if polygon.size() < 3 or absf(_area(_packed(polygon))) < 100.0: continue
				var copy := area.duplicate(true)
				copy.polygon = polygon
				if not first: copy.id = next_id.call("area")
				first = false
				if copy.has("exclusions"):
					# Each exclusion keeps its part inside this piece and outside the footprint.
					var exclusions: Array = []
					for exclusion: Array in area.exclusions:
						for inside: PackedVector2Array in Geometry2D.intersect_polygons(_packed(exclusion), _packed(polygon)):
							var outside := Geometry2D.clip_polygons(inside, footprint)
							if _has_hole(outside): outside = [inside]
							for remainder: PackedVector2Array in outside:
								var rounded := _round_ring(remainder)
								if rounded.size() >= 3 and absf(_area(_packed(rounded))) >= 100.0: exclusions.append(rounded)
					copy.exclusions = exclusions
				kept.append(copy)
		work[field] = kept
	var barriers: Array = []
	for barrier: Dictionary in work.barriers:
		var clipped := _outside_pieces(barrier.line, footprint)
		if not clipped.cut:
			barriers.append(barrier)
			continue
		var first := true
		for piece: Dictionary in clipped.pieces:
			var line := _dedupe_line(piece.points, piece.segments)
			if line.points.size() < 2 or _line_length(line.points) < MIN_PIECE_CM: continue
			var copy := barrier.duplicate(true)
			copy.line = line.points
			if not first: copy.id = next_id.call("barrier")
			first = false
			barriers.append(copy)
	work.barriers = barriers
	var repetitions: Array = []
	for repetition: Dictionary in work.repetitions:
		var clipped := _outside_pieces(repetition.points, footprint)
		if not clipped.cut:
			repetitions.append(repetition)
			continue
		var first := true
		for piece: Dictionary in clipped.pieces:
			var line := _dedupe_line(piece.points, piece.segments)
			if line.points.size() < 2 or _line_length(line.points) < maxf(MIN_PIECE_CM, float(repetition.get("spacing_cm", 0))): continue
			var copy := repetition.duplicate(true)
			copy.points = line.points
			if not first: copy.id = next_id.call("repeat")
			first = false
			repetitions.append(copy)
	work.repetitions = repetitions
	var levels := {}
	for node: Dictionary in work.nodes: levels[node.id] = int(node.get("level", 0))
	var touched := {}
	var roads: Array = []
	for road: Dictionary in work.roads:
		# Bridges, elevated roads and tunnels pass over or under the part whole.
		var clipped := _outside_pieces(road.points, footprint) if str(road.get("kind", "ground")) == "ground" else {"cut": false}
		if not clipped.cut:
			roads.append(road)
			continue
		touched[road.from] = true
		touched[road.to] = true
		var first := true
		for piece: Dictionary in clipped.pieces:
			var line := _dedupe_line(piece.points, piece.segments)
			if line.points.size() < 2 or _line_length(line.points) < MIN_PIECE_CM: continue
			var copy := road.duplicate(true)
			copy.erase("design")
			copy.points = line.points
			copy.widths_cm = line.segments.map(func(i: int) -> Variant: return road.widths_cm[i])
			copy.surfaces = line.segments.map(func(i: int) -> Variant: return road.surfaces[i])
			if not first: copy.id = next_id.call("road")
			first = false
			for end: Array in [["from", piece.from_start, 0, "crosswalk_start"], ["to", piece.to_end, -1, "crosswalk_end"]]:
				if end[1]: continue
				var node_id: String = next_id.call("node")
				work.nodes.append({"id": node_id, "position": copy.points[end[2]], "level": int(levels.get(road[end[0]], 0))})
				copy[end[0]] = node_id
				if copy.get("markings") is Dictionary: copy.markings[end[3]] = false
			roads.append(copy)
	work.roads = roads
	var referenced := {}
	for road: Dictionary in work.roads:
		referenced[road.from] = true
		referenced[road.to] = true
	var nodes: Array = []
	for node: Dictionary in work.nodes:
		if referenced.has(node.id) or not (touched.has(node.id) or _inside(_plan(node.position), footprint)): nodes.append(node)
	work.nodes = nodes

## Joins each mouth to the nearest free road end, else to the nearest point of
## another road (splitting it), within `radius` map cm. The mouth road gains a
## short connector to the target; any angle is accepted. Returns joins made.
static func _join(work: Dictionary, mouths: Array, radius: float, prefix: String, own: Dictionary) -> int:
	var joined := 0
	var counter := [0]
	var nodes := {}
	for node: Dictionary in work.nodes: nodes[node.id] = node
	for mouth: Dictionary in mouths:
		var node: Dictionary = nodes[mouth.node]
		var at := _plan(node.position)
		# Only ground roads are joined; ties prefer the target nearest in height.
		var degree := {}
		var structure := {}
		for road: Dictionary in work.roads:
			for end in ["from", "to"]:
				degree[road[end]] = int(degree.get(road[end], 0)) + 1
				if str(road.get("kind", "ground")) != "ground": structure[road[end]] = true
		var target := ""
		var best := INF
		var height := float(node.position[1])
		for other: Dictionary in work.nodes:
			if own.has(other.id) or structure.has(other.id) or int(degree.get(other.id, 0)) != 1: continue
			var distance := at.distance_to(_plan(other.position))
			var score := distance + absf(float(other.position[1]) - height)
			if distance <= radius and score < best:
				best = score
				target = other.id
		if target == "":
			var split := {}
			best = radius
			for index in work.roads.size():
				var road: Dictionary = work.roads[index]
				if own.has(road.id) or str(road.get("kind", "ground")) != "ground": continue
				for i in range(road.points.size() - 1):
					var a := _plan(road.points[i])
					var b := _plan(road.points[i + 1])
					var closest := Geometry2D.get_closest_point_to_segment(at, a, b)
					var distance := at.distance_to(closest)
					if distance <= best:
						best = distance
						split = {"road": index, "segment": i, "t": a.distance_to(closest) / maxf(0.001, a.distance_to(b))}
			if split.is_empty(): continue
			counter[0] += 1
			target = _split(work, nodes, split, prefix + "join-node-" + str(counter[0]), prefix + "join-road-" + str(counter[0]))
			if target == "": continue
		var connect := _connect(work, mouth.node, nodes[target])
		if connect:
			work.nodes.erase(node)
			nodes.erase(mouth.node)
			joined += 1
	return joined

## Splits a road at a planned point, returning the node there (an existing end
## node when the point falls on one).
static func _split(work: Dictionary, nodes: Dictionary, split: Dictionary, node_id: String, tail_id: String) -> String:
	var road: Dictionary = work.roads[split.road]
	var i: int = split.segment
	var point := _lerp_vertex(road.points[i], road.points[i + 1], split.t)
	if _plan(point).distance_to(_plan(road.points[0])) < MIN_PIECE_CM: return road.from
	if _plan(point).distance_to(_plan(road.points[-1])) < MIN_PIECE_CM: return road.to
	var head_points: Array = road.points.slice(0, i + 1)
	var tail_points: Array = road.points.slice(i + 1)
	var head_segments: Array = range(i + 1)
	var tail_segments: Array = range(i, road.widths_cm.size())
	if _plan(point) == _plan(head_points[-1]):
		head_points.pop_back()
		head_segments.pop_back()
	if _plan(point) == _plan(tail_points[0]):
		tail_points.pop_front()
		tail_segments.pop_front()
	head_points.append(point)
	tail_points.push_front(point)
	if head_points.size() < 2 or tail_points.size() < 2: return ""
	var level := int(nodes[road.from].get("level", 0)) if nodes.has(road.from) else 0
	var node := {"id": node_id, "position": point, "level": level}
	work.nodes.append(node)
	nodes[node_id] = node
	var head := road.duplicate(true)
	head.erase("design")
	head.points = head_points
	head.widths_cm = head_segments.map(func(s: int) -> Variant: return road.widths_cm[s])
	head.surfaces = head_segments.map(func(s: int) -> Variant: return road.surfaces[s])
	head.to = node_id
	var tail := head.duplicate(true)
	tail.id = tail_id
	tail.points = tail_points
	tail.widths_cm = tail_segments.map(func(s: int) -> Variant: return road.widths_cm[s])
	tail.surfaces = tail_segments.map(func(s: int) -> Variant: return road.surfaces[s])
	tail.from = node_id
	tail.to = road.to
	if head.get("markings") is Dictionary:
		head.markings.crosswalk_end = false
		tail.markings = road.markings.duplicate(true)
		tail.markings.crosswalk_start = false
	work.roads[split.road] = head
	work.roads.append(tail)
	return node_id

## Rewires the one road at `mouth_id` onto `target`, adding a connector segment
## unless the target already coincides with the mouth.
static func _connect(work: Dictionary, mouth_id: String, target: Dictionary) -> bool:
	for index in work.roads.size():
		var road: Dictionary = work.roads[index]
		if mouth_id not in [road.from, road.to]: continue
		var copy := road.duplicate(true)
		var at_start: bool = road.from == mouth_id
		var points: Array = copy.points
		var end := 0 if at_start else points.size() - 1
		var neighbour := 1 if at_start else points.size() - 2
		if _plan(target.position) == _plan(points[neighbour]):
			points[end] = target.position.duplicate()
			points.remove_at(neighbour)
			copy.widths_cm.remove_at(0 if at_start else copy.widths_cm.size() - 1)
			copy.surfaces.remove_at(0 if at_start else copy.surfaces.size() - 1)
			if points.size() < 2: return false
		elif _plan(target.position).distance_to(_plan(points[end])) < 1.0:
			points[end] = target.position.duplicate()
		elif at_start:
			points.push_front(target.position.duplicate())
			copy.widths_cm.push_front(copy.widths_cm[0])
			copy.surfaces.push_front(copy.surfaces[0])
		else:
			points.append(target.position.duplicate())
			copy.widths_cm.append(copy.widths_cm[-1])
			copy.surfaces.append(copy.surfaces[-1])
		copy[("from" if at_start else "to")] = target.id
		work.roads[index] = copy
		return true
	return false

# ------------------------------------------------------------------- capture

## The map's source credits without import metadata: a notice can carry an
## adapter's 1:D provenance, which must never change another map's scale.
static func _credits(document: Dictionary) -> Array:
	var result: Array = []
	for attribution: Dictionary in document.get("attributions", []):
		var credit := {"source": str(attribution.source).get_slice("#", 0).strip_edges(), "license": str(attribution.license), "notice": ""}
		if credit.source == "": credit.source = str(attribution.source)
		if credit not in result: result.append(credit)
	return result

## Selected map records as a user part: local IDs, origin at the selection's
## centre, heights above its lowest point, multiplied back to real-scale source
## cm. Road ends used by only one selected road become mouths. When any record
## came from an import, regional source or another part, the map's source
## attributions are carried so placement keeps credits.
static func capture(document: Dictionary, keys: Array, name: String) -> Dictionary:
	var scale := UNITS.osm_scale(document)
	if scale.has("error"): return {"error": scale.error}
	var d := float(maxi(1, int(scale.denominator)))
	var chosen := {}
	for field in FIELDS: chosen[field] = []
	var sourced := false
	for entry in EDIT.entries(document):
		if entry.key not in keys or entry.field not in FIELDS or entry.field == "nodes": continue
		if entry.field == "placements" and not str(entry.record.asset_id).begins_with("builtin:"): continue
		chosen[entry.field].append(entry.record)
		var id := str(entry.record.id)
		if id.begins_with("import-") or id.begins_with("regional-") or id.begins_with("part-"): sourced = true
	var used := {}
	for road: Dictionary in chosen.roads:
		used[road.from] = true
		used[road.to] = true
	for node: Dictionary in document.get("nodes", []):
		if used.has(node.id): chosen.nodes.append(node)
	var points := PackedVector2Array()
	var heights: Array = []
	var margin := 100.0
	for field in FIELDS:
		for record: Dictionary in chosen[field]:
			for p in EDIT.points(field, record): points.append(p)
			if field == "roads":
				for p: Array in record.points: heights.append(int(p[1]))
				for width in record.widths_cm: margin = maxf(margin, float(width) / 2.0)
			elif field in ["nodes", "placements"]: heights.append(int(record.position[1]))
			elif field == "buildings": heights.append(int(record.base_cm))
	if points.is_empty(): return {"error": I18N.t("Select roads, buildings, areas or placements to save as a part.")}
	var box := Rect2(points[0], Vector2.ZERO)
	for p in points: box = box.expand(p)
	var origin := Vector2(roundi(box.get_center().x), roundi(box.get_center().y))
	var ground: int = heights.min() if not heights.is_empty() else 0
	var hull := Geometry2D.convex_hull(points)
	if hull.size() > 1 and hull[0] == hull[-1]: hull.remove_at(hull.size() - 1)
	# The footprint is the selection's convex hull grown past road edges; a
	# point-like or straight selection uses its grown bounding box.
	var grow_cm := margin + 100.0
	var grown: Array = Geometry2D.offset_polygon(hull, grow_cm, Geometry2D.JOIN_SQUARE) if hull.size() >= 3 and absf(_area(hull)) > 1.0 else []
	var wide := box.grow(grow_cm)
	var outline: PackedVector2Array = grown[0] if grown.size() == 1 else PackedVector2Array([wide.position, Vector2(wide.end.x, wide.position.y), wide.end, Vector2(wide.position.x, wide.end.y)])
	var point := func(p: Array) -> Array: return [roundi((float(p[0]) - origin.x) * d), roundi((float(p[1]) - origin.y) * d)]
	var vertex := func(p: Array) -> Array: return [roundi((float(p[0]) - origin.x) * d), roundi((float(p[1]) - ground) * d), roundi((float(p[2]) - origin.y) * d)]
	var ring := func(r: Array) -> Array: return r.map(func(p: Array) -> Array: return point.call(p))
	var grow := func(value: Variant) -> int: return roundi(float(value) * d)
	var local := {}
	var short := {"nodes": "node", "roads": "road", "buildings": "building", "zones": "zone", "surface_areas": "area", "barriers": "barrier", "placements": "place"}
	var records := {}
	for field in FIELDS:
		records[field] = []
		for record: Dictionary in chosen[field]:
			local[str(record.id)] = short[field] + "-" + str(records[field].size() + 1)
			var copy: Dictionary = record.duplicate(true)
			copy.id = local[str(record.id)]
			records[field].append(copy)
	for node: Dictionary in records.nodes: node.position = vertex.call(node.position)
	var degree := {}
	for road: Dictionary in records.roads:
		road.from = local[road.from]
		road.to = local[road.to]
		road.erase("design")
		road.points = road.points.map(func(p: Array) -> Array: return vertex.call(p))
		road.widths_cm = road.widths_cm.map(func(w: Variant) -> int: return grow.call(w))
		if road.get("clearance_cm") != null: road.clearance_cm = grow.call(road.clearance_cm)
		if road.get("sidewalk_cm") != null: road.sidewalk_cm = grow.call(road.sidewalk_cm)
		if road.get("markings") is Dictionary:
			for key in ["lane_width_cm", "median_width_cm"]:
				if road.markings.has(key): road.markings[key] = grow.call(road.markings[key])
		for end in ["from", "to"]: degree[road[end]] = int(degree.get(road[end], 0)) + 1
	for building: Dictionary in records.buildings:
		building.footprint = ring.call(building.footprint)
		for key in ["holes", "entrances"]:
			if building.has(key): building[key] = building[key].map(func(r: Array) -> Array: return ring.call(r))
		building.base_cm = roundi((float(building.base_cm) - ground) * d)
		building.height_cm = grow.call(building.height_cm)
		for solid: Dictionary in building.get("parts", []):
			solid.footprint = ring.call(solid.footprint)
			if solid.has("holes"): solid.holes = solid.holes.map(func(r: Array) -> Array: return ring.call(r))
			if solid.has("base_cm"): solid.base_cm = roundi((float(solid.base_cm) - ground) * d)
			if solid.has("height_cm"): solid.height_cm = grow.call(solid.height_cm)
	for field in ["zones", "surface_areas"]:
		for area: Dictionary in records[field]:
			area.polygon = ring.call(area.polygon)
			if area.has("exclusions"): area.exclusions = area.exclusions.map(func(r: Array) -> Array: return ring.call(r))
			if area.has("spacing_cm"): area.spacing_cm = grow.call(area.spacing_cm)
	for barrier: Dictionary in records.barriers:
		barrier.line = ring.call(barrier.line)
		for key in ["height_cm", "thickness_cm"]:
			if barrier.has(key): barrier[key] = grow.call(barrier[key])
	for placement: Dictionary in records.placements: placement.position = vertex.call(placement.position)
	var mouths: Array = []
	for road: Dictionary in records.roads:
		for end: Array in [["from", 0, 1, 0], ["to", -1, -2, -1]]:
			if int(degree.get(road[end[0]], 0)) != 1: continue
			var tip := _plan(road.points[end[1]])
			var back := _plan(road.points[end[2]])
			mouths.append({"node": road[end[0]], "heading_deg": snappedf(rad_to_deg((tip - back).angle()), 0.001), "width_cm": clampi(int(road.widths_cm[end[3]]), 20, 10000)})
	for field in FIELDS:
		if records[field].is_empty(): records.erase(field)
	var footprint: Array = []
	for p in outline: footprint.append(point.call([p.x, p.y]))
	var part := {"format": FORMAT, "version": VERSION, "id": "user-" + Crypto.new().generate_random_bytes(5).hex_encode(),
		"name": name, "license": USER_LICENSE, "attributions": _credits(document) if sourced else [],
		"footprint": _round_ring(_packed(footprint)), "mouths": mouths, "records": records}
	return parse(JSON.stringify(part))
