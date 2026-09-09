extends Control
## Offline WGS84 diagram, not a basemap or a source coverage claim.
signal bounds_selected(bounds: Array)
var bounds: Array = [0.0, 0.0, 0.001, 0.001]
var envelope := Rect2(-0.001, -0.001, 0.003, 0.003)
var anchor := Vector2.ZERO
var dragging := false
var cursor := Vector2.ZERO

func _ready() -> void:
	custom_minimum_size = Vector2(640, 150)
	mouse_default_cursor_shape = Control.CURSOR_CROSS
	toggle_fit()

func set_bounds(value: Array) -> void:
	bounds = value.duplicate()
	queue_redraw()

func toggle_fit() -> void:
	if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]: return
	var span := Vector2(bounds[2]-bounds[0], bounds[3]-bounds[1])
	envelope = Rect2(Vector2(bounds[0], bounds[1])-span*0.25, span*1.5).intersection(Rect2(-180,-80,360,164))
	queue_redraw()

func geographic(point: Vector2) -> Vector2:
	var uv := (point / size).clamp(Vector2.ZERO, Vector2.ONE)
	return envelope.position + Vector2(uv.x, 1.0-uv.y)*envelope.size

func screen(point: Vector2) -> Vector2:
	var uv := (point-envelope.position)/envelope.size
	return Vector2(uv.x, 1.0-uv.y)*size

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and dragging:
		cursor = geographic(event.position)
		queue_redraw()
		accept_event()
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			anchor = geographic(event.position)
			cursor = anchor
			dragging = true
		elif dragging:
			dragging = false
			var end := geographic(event.position)
			if anchor.distance_to(end) > 0.000002:
				bounds_selected.emit([minf(anchor.x,end.x),minf(anchor.y,end.y),maxf(anchor.x,end.x),maxf(anchor.y,end.y)])
		queue_redraw()
		accept_event()

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO,size),Color("192b37"))
	for i in range(1,4):
		draw_line(Vector2(size.x*i/4.0,0),Vector2(size.x*i/4.0,size.y),Color("36505e"))
		draw_line(Vector2(0,size.y*i/4.0),Vector2(size.x,size.y*i/4.0),Color("36505e"))
	if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
		var a := screen(Vector2(bounds[0],bounds[3]))
		var b := screen(Vector2(bounds[2],bounds[1]))
		var rectangle := Rect2(a,b-a).intersection(Rect2(Vector2.ZERO,size))
		draw_rect(rectangle,Color(0.25,0.75,0.8,0.25))
		draw_rect(rectangle,Color("62d8dc"),false,2)
	if dragging:
		var a := screen(anchor)
		var b := screen(cursor)
		draw_rect(Rect2(a,b-a).abs(),Color("ffffff"),false,2)
	draw_string(ThemeDB.fallback_font,Vector2(8,20),"N ↑   W ←    Offline coordinate diagram · drag to select",HORIZONTAL_ALIGNMENT_LEFT,-1,14,Color.WHITE)
