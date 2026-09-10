extends RefCounted
## Authoring adapter: one solid, round wall encoded as an ordinary MapKit prism.
## Integer vertices are the source of truth for rendering, collision and saves.
const SEGMENTS := 48

static func footprint(center: Vector2, radius_cm: int, phase: float = 0.0) -> Array:
	var points: Array = []
	for i in range(SEGMENTS):
		var angle := phase + TAU * i / SEGMENTS
		points.append([roundi(center.x + radius_cm * cos(angle)), roundi(center.y + radius_cm * sin(angle))])
	return points

static func create(id: String, center: Vector2, radius_cm: int, base_cm: int, height_cm: int, material: String = "concrete") -> Dictionary:
	return {"id": id, "footprint": footprint(center, radius_cm), "base_cm": base_cm,
		"height_cm": height_cm, "usage": "industrial", "material": material, "roof": "flat"}

static func dimensions(record: Dictionary) -> Dictionary:
	var points: Array = record.get("footprint", [])
	if points.size() != SEGMENTS or record.get("roof") != "flat" or not record.get("holes", []).is_empty() or not record.get("entrances", []).is_empty(): return {}
	var center := Vector2.ZERO
	for point: Array in points: center += Vector2(point[0], point[1])
	center = (center / SEGMENTS).round()
	var first := Vector2(points[0][0], points[0][1]) - center
	var radius := roundi(first.length())
	if radius < 25: return {}
	var phase := first.angle()
	# Accept winding reversal after a mirror and arbitrary phase after rotation.
	var second := Vector2(points[1][0], points[1][1]) - center
	var direction := 1 if first.cross(second) > 0 else -1
	for i in range(SEGMENTS):
		var expected := center + Vector2.from_angle(phase + direction * TAU * i / SEGMENTS) * radius
		if expected.distance_to(Vector2(points[i][0], points[i][1])) > 2.0: return {}
	return {"center": center, "radius_cm": radius, "phase": phase, "direction": direction}
