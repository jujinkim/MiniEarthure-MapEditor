extends RefCounted
## Source coordinates stay in provenance. Only newly adopted OSM records scale.
const OSM_DENOMINATOR := 8

static func osm_patches(source: Array, city := false) -> Array:
	var result := source.duplicate(true)
	for patch: Dictionary in result:
		var record: Dictionary = patch.after
		for key in ["position", "points", "footprint", "polygon", "exclusions", "entrances", "courtyards", "holes"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["widths_cm"]:
			if record.has(key): record[key] = _coordinates(record[key])
		for key in ["height_cm", "base_cm", "clearance_cm", "sidewalk_cm", "spacing_cm"]:
			if record.get(key) != null: record[key] = roundi(float(record[key]) / OSM_DENOMINATOR)
		if city:
			# Scaling to whole game centimetres can collapse adjacent source
			# vertices. Remove only exact duplicates, never a road endpoint,
			# vertical step, material boundary or nonempty courtyard.
			if patch.field == "roads" and record.kind == "ground": _road_duplicates(record)
			for key in ["footprint","polygon"]:
				if record.has(key): record[key] = _ring_duplicates(record[key])
			for key in ["courtyards","holes","exclusions"]:
				if record.has(key):
					for i in range(record[key].size()): record[key][i] = _ring_duplicates(record[key][i])
	return result

## A 1:8 road narrower than this cannot carry the ~61 cm car with any margin.
const ROAD_WIDTH_FLOOR_CM := 150
const BUILDING_MARGIN_CM := 20
const EDGE_BUCKET_CM := 1000

## Widens adopted roads to the floor per segment, stopping each side at the nearest
## building edge or courtyard wall (including sidewalk and margin). Already wider segments and the
## listed pedestrian roads (paths, footways, cycleways) never change.
static func widen_roads(patches: Array, existing_buildings: Array, pedestrian: Array = []) -> void:
	var walking := {}
	for id: String in pedestrian: walking[id] = true
	var buckets := {}
	var rings: Array = []
	var records: Array = existing_buildings.duplicate()
	for patch: Dictionary in patches:
		if patch.field == "buildings" and patch.after is Dictionary: records.append(patch.after)
	# Courtyard walls bound a road inside the courtyard like outer walls.
	for building: Dictionary in records:
		rings.append(building.footprint)
		rings.append_array(building.get("holes", []))
	var edges: Array = []
	for ring: Array in rings:
		for i in ring.size():
			var a := Vector2(ring[i][0],ring[i][1])
			var b := Vector2(ring[(i+1)%ring.size()][0],ring[(i+1)%ring.size()][1])
			var index := edges.size()
			edges.append([a,b])
			for x in range(floori(minf(a.x,b.x)/EDGE_BUCKET_CM),floori(maxf(a.x,b.x)/EDGE_BUCKET_CM)+1):
				for y in range(floori(minf(a.y,b.y)/EDGE_BUCKET_CM),floori(maxf(a.y,b.y)/EDGE_BUCKET_CM)+1):
					buckets.get_or_add(Vector2i(x,y),[]).append(index)
	for patch: Dictionary in patches:
		if patch.field != "roads" or not patch.after is Dictionary or walking.has(patch.get("id", "")): continue
		var road: Dictionary = patch.after
		var sidewalk := float(road.get("sidewalk_cm",0) if road.get("sidewalk_cm") != null else 0)
		for s in road.widths_cm.size():
			if int(road.widths_cm[s]) >= ROAD_WIDTH_FLOOR_CM: continue
			var p := Vector2(road.points[s][0],road.points[s][2])
			var q := Vector2(road.points[s+1][0],road.points[s+1][2])
			var reach := ROAD_WIDTH_FLOOR_CM/2.0+sidewalk+BUILDING_MARGIN_CM
			var nearest := INF
			var seen := {}
			for x in range(floori((minf(p.x,q.x)-reach)/EDGE_BUCKET_CM),floori((maxf(p.x,q.x)+reach)/EDGE_BUCKET_CM)+1):
				for y in range(floori((minf(p.y,q.y)-reach)/EDGE_BUCKET_CM),floori((maxf(p.y,q.y)+reach)/EDGE_BUCKET_CM)+1):
					for index: int in buckets.get(Vector2i(x,y),[]):
						if seen.has(index): continue
						seen[index] = true
						nearest = minf(nearest,_segment_gap(p,q,edges[index][0],edges[index][1]))
			var half := minf(ROAD_WIDTH_FLOOR_CM/2.0,nearest-sidewalk-BUILDING_MARGIN_CM)
			road.widths_cm[s] = maxi(int(road.widths_cm[s]),floori(half*2))

## Ordinary source junctions the road planner cannot build (for example a way that
## doubles back) become separate road ends at the same position, as before source
## junctions were kept. Only ground junction nodes added by this import change;
## explicit structural junctions still fail review. Returns the separated count.
static func separate_junctions(patches: Array, store: RefCounted) -> int:
	var separated := 0
	for _round in 3:
		var staged: Dictionary = store._candidate_for_patches(patches)
		if staged.has("error"): return separated
		var found: Dictionary = JSON.parse_string(store.bridge.unbuildable_junctions(JSON.stringify(staged.candidate)))
		if not found.get("ok", false) or found.data.nodes.is_empty(): return separated
		var failing := {}
		for id: String in found.data.nodes: failing[id] = true
		var added := {}
		for patch: Dictionary in patches:
			# Only ordinary source junctions; explicit structural junctions keep their rules.
			if patch.field == "nodes" and patch.before == null and failing.has(patch.id) and str(patch.id).contains("-osm-ground-node-"): added[patch.id] = patch
		if added.is_empty(): return separated
		var arms := {}
		for patch: Dictionary in patches:
			if patch.field != "roads" or not patch.after is Dictionary: continue
			for end in ["from", "to"]:
				var id: String = patch.after[end]
				if not added.has(id): continue
				var k: int = arms.get(id, 0)
				arms[id] = k + 1
				var node: Dictionary = added[id].after.duplicate(true)
				node.id = "%s-arm-%d" % [id, k]
				patch.after[end] = node.id
				patches.append({"field":"nodes", "id":node.id, "before":null, "after":node})
		for id: String in added:
			patches.erase(added[id])
			separated += 1
	return separated

static func _segment_gap(a: Vector2, b: Vector2, c: Vector2, d: Vector2) -> float:
	if Geometry2D.segment_intersects_segment(a,b,c,d) != null: return 0.0
	return minf(minf(Geometry2D.get_closest_point_to_segment(a,c,d).distance_to(a),Geometry2D.get_closest_point_to_segment(b,c,d).distance_to(b)),
		minf(Geometry2D.get_closest_point_to_segment(c,a,b).distance_to(c),Geometry2D.get_closest_point_to_segment(d,a,b).distance_to(d)))

static func _ring_duplicates(source: Array) -> Array:
	var result: Array = []
	for point: Variant in source:
		if result.is_empty() or result[-1] != point: result.append(point)
	if result.size() > 1 and result[0] == result[-1]: result.pop_back()
	return result if result.size() >= 3 else source

static func _road_duplicates(record: Dictionary) -> void:
	var retained: Array[int] = [0]
	for i in range(1,record.points.size()-1):
		if record.points[i] != record.points[retained[-1]] and record.points[i] != record.points[i+1]: retained.append(i)
	retained.append(record.points.size()-1)
	if retained.size() == record.points.size(): return
	var points: Array = []
	var widths: Array = []
	var surfaces: Array = []
	for i in range(retained.size()):
		points.append(record.points[retained[i]])
		if i == retained.size()-1: break
		var first: int = retained[i]
		for edge in range(first,retained[i+1]):
			if record.widths_cm[edge] != record.widths_cm[first] or record.surfaces[edge] != record.surfaces[first]: return
		widths.append(record.widths_cm[first]); surfaces.append(record.surfaces[first])
	record.points = points
	record.widths_cm = widths
	record.surfaces = surfaces

static func _coordinates(value: Variant) -> Variant:
	if value is Array:
		var result := []
		for part in value: result.append(_coordinates(part))
		return result
	return roundi(float(value) / OSM_DENOMINATOR)

static func dem_denominator(document: Dictionary) -> int:
	for notice: Dictionary in document.get("attributions", []):
		var parser := JSON.new()
		if parser.parse(notice.get("notice", "")) != OK: continue
		var meta: Variant = parser.data
		if meta is Dictionary and meta.get("adapter") == "osm-extract-v1" and meta.get("authored_units", {}).get("source_denominator") == OSM_DENOMINATOR:
			return OSM_DENOMINATOR
	return 1
