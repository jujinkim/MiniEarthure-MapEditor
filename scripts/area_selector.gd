extends Control
const I18N := preload("./locale_text.gd")
## Offline WGS84 diagram, not a basemap or a source coverage claim.
signal bounds_selected(bounds: Array)
signal center_selected(point: Vector2)
var places: Array = []
var center := Vector2(INF, INF)
var bounds: Array = [0.0, 0.0, 0.001, 0.001]
var envelope := Rect2(-0.001, -0.001, 0.003, 0.003)
var anchor := Vector2.ZERO
var dragging := false
var cursor := Vector2.ZERO

func _ready() -> void:
	custom_minimum_size = Vector2(640, maxf(custom_minimum_size.y,150))
	clip_contents = true
	mouse_default_cursor_shape = Control.CURSOR_CROSS
	toggle_fit()

func set_bounds(value: Array) -> void:
	bounds = value.duplicate()
	queue_redraw()

func set_places(value: Array) -> void:
	places = value.duplicate(true)
	queue_redraw()

func toggle_fit() -> void:
	if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]: return
	var span := Vector2(bounds[2]-bounds[0], bounds[3]-bounds[1])
	var midpoint := Vector2((bounds[0]+bounds[2])*0.5, (bounds[1]+bounds[3])*0.5)
	# Equirectangular boundary preview with local latitude correction, not a basemap.
	var ratio := maxf(size.x,1.0)/maxf(size.y,1.0)/maxf(cos(deg_to_rad(midpoint.y)),0.1)
	span = Vector2(maxf(span.x,span.y*ratio), maxf(span.y,span.x/ratio))*1.2
	envelope = Rect2(midpoint-span*0.5,span).intersection(Rect2(-180,-80,360,164))
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
			if screen(anchor).distance_to(event.position) > 5:
				bounds_selected.emit([minf(anchor.x,end.x),minf(anchor.y,end.y),maxf(anchor.x,end.x),maxf(anchor.y,end.y)])
			else:
				center = end
				center_selected.emit(end)
		queue_redraw()
		accept_event()

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO,size),Color("192b37"))
	for i in range(1,4):
		draw_line(Vector2(size.x*i/4.0,0),Vector2(size.x*i/4.0,size.y),Color("36505e"))
		draw_line(Vector2(0,size.y*i/4.0),Vector2(size.x,size.y*i/4.0),Color("36505e"))
	var occupied: Array[Rect2] = []
	for place: Dictionary in places:
		if place.get("issue", "") != "": continue
		for line: Array in place.outlines:
			var path := PackedVector2Array()
			for point: Array in line: path.append(screen(Vector2(point[0],point[1])))
			if path.size() > 1: draw_polyline(path,Color("cedba0"),1.5,true)
		var b: Array = place.bbox
		var point := screen(Vector2((b[0]+b[2])*0.5,(b[1]+b[3])*0.5))
		var label: String = str(place.name).left(40)
		var label_size := get_theme_default_font().get_string_size(label,HORIZONTAL_ALIGNMENT_LEFT,-1,14)
		var rect := Rect2(point+Vector2(5,-16),label_size+Vector2(8,4))
		if not Rect2(Vector2.ZERO,size).encloses(rect) or occupied.any(func(r): return r.intersects(rect)): continue
		occupied.append(rect)
		draw_rect(rect,Color(0.04,0.1,0.13,0.9))
		draw_string(get_theme_default_font(),point+Vector2(9,-1),label,HORIZONTAL_ALIGNMENT_LEFT,-1,14,Color.WHITE)
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
	if center.is_finite():
		var at := screen(center)
		draw_circle(at,5,Color("ffc363"))
		draw_line(at-Vector2(9,0),at+Vector2(9,0),Color("ffc363"))
		draw_line(at-Vector2(0,9),at+Vector2(0,9),Color("ffc363"))
	draw_string(get_theme_default_font(),Vector2(8,20),"N ↑   W ←    %s · click origin / drag crop" % ("Local PBF boundaries" if not places.is_empty() else "Coordinate diagram"),HORIZONTAL_ALIGNMENT_LEFT,-1,14,Color.WHITE)
