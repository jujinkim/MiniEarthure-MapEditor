extends RefCounted
## View-only orbit/pan state. Never changes the document or runs game physics.
var camera: Camera3D
var target := Vector3.ZERO
var distance := 80.0
var yaw := 0.66
var pitch := 0.77

func frame(center: Vector3, radius: float) -> void:
	target = center
	distance = clampf(radius, 0.5, 10000.0)
	apply()

func apply() -> void:
	if not is_instance_valid(camera): return
	camera.position = target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.far = maxf(2000, distance * 4)
	camera.look_at(target)

func input(event: InputEvent) -> bool:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			distance = clampf(distance * (0.85 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 0.85), 0.5, 10000.0)
			apply()
			return true
	if event is InputEventMouseMotion:
		if event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
			yaw -= event.relative.x * 0.006
			pitch = clampf(pitch + event.relative.y * 0.006, -1.45, 1.45)
		elif event.button_mask & MOUSE_BUTTON_MASK_MIDDLE:
			target += (-camera.basis.x * event.relative.x + camera.basis.y * event.relative.y) * distance * 0.0015
		else: return false
		apply()
		return true
	return false
