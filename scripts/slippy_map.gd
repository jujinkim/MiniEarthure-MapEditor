extends Control
## Location picker over OpenStreetMap standard raster tiles (Web Mercator).
## Drag pans, the wheel or +/- zooms, a click places the pin. The chosen extent
## (circle or square around the pin) is drawn on top. Tile use follows the OSMF
## tile policy: an identified client, the attribution always visible, a disk
## cache, only visible tiles and no bulk prefetch. Without a network (or in a
## headless run) the grid and pin still work; coordinates stay exact.
const I18N := preload("./locale_text.gd")
const STYLE := preload("./workbench_style.gd")
signal pin_changed(point: Vector2)
const TILE_URL := "https://tile.openstreetmap.org/%d/%d/%d.png"
const USER_AGENT := "User-Agent: MiniEarthure-MapEditor/1 (location picker)"
const ATTRIBUTION := "© OpenStreetMap contributors"
const TILE := 256
const MIN_ZOOM := 2
const MAX_ZOOM := 19
const MAX_REQUESTS := 4
const MEMORY_TILES := 256
## Cached tiles are reused for at least this long before a refresh.
const CACHE_SECONDS := 14 * 24 * 3600
const CACHE_DIR := "user://map-tiles"

var center := Vector2(127.0, 37.5)
var zoom := 12
var pin := Vector2(INF, INF)
var radius_km := 2.0
var shape := "circle"
var network := true
var _textures := {}
var _order: Array[String] = []
var _pending := {}
var _failed := {}
var _idle: Array[HTTPRequest] = []
var _dragging := false
var _moved := false
var _press := Vector2.ZERO

func _ready() -> void:
	custom_minimum_size = Vector2(maxf(custom_minimum_size.x, 420), maxf(custom_minimum_size.y, 420))
	clip_contents = true
	mouse_default_cursor_shape = Control.CURSOR_CROSS
	focus_mode = Control.FOCUS_CLICK
	network = network and DisplayServer.get_name() != "headless"
	resized.connect(queue_redraw)
	var buttons := VBoxContainer.new()
	buttons.position = Vector2(8, 8)
	add_child(buttons)
	for step: int in [1, -1]:
		var button := STYLE.button(buttons, "Zoom in" if step > 0 else "Zoom out", func(): zoom_by(step, size * 0.5), "", "plus" if step > 0 else "minus")
		button.text = ""

## Centres the view on point (longitude, latitude), optionally changing zoom.
func show_point(point: Vector2, level := -1) -> void:
	center = Vector2(clampf(point.x, -180, 180), clampf(point.y, -85, 85))
	if level >= 0: zoom = clampi(level, MIN_ZOOM, MAX_ZOOM)
	queue_redraw()

## Places the pin without emitting pin_changed (for typed coordinates).
func set_pin(point: Vector2) -> void:
	pin = point
	queue_redraw()

func set_extent(value_km: float, value_shape: String) -> void:
	radius_km = value_km
	shape = value_shape
	queue_redraw()

## A zoom level that shows the whole extent with some surroundings.
func fit_extent() -> void:
	if not pin.is_finite(): return
	var side_m := radius_km * 2000.0 * 1.6
	var metres_per_pixel := side_m / maxf(minf(size.x, size.y), 1.0)
	var level := log(156543.03 * cos(deg_to_rad(pin.y)) / maxf(metres_per_pixel, 0.01)) / log(2.0)
	show_point(pin, clampi(int(floor(level)), MIN_ZOOM, MAX_ZOOM))

func zoom_by(step: int, around: Vector2) -> void:
	var before := to_world(around)
	zoom = clampi(zoom + step, MIN_ZOOM, MAX_ZOOM)
	# Keep the geographic point under the cursor in place.
	var shift := to_screen(before) - around
	center = _lonlat(_world(center) + shift)
	queue_redraw()

# Web Mercator: world pixels at the current zoom.
func _world(point: Vector2) -> Vector2:
	var n := TILE * pow(2.0, zoom)
	var lat := deg_to_rad(clampf(point.y, -85.0511, 85.0511))
	return Vector2((point.x + 180.0) / 360.0 * n, (1.0 - log(tan(lat) + 1.0 / cos(lat)) / PI) * 0.5 * n)

func _lonlat(world: Vector2) -> Vector2:
	var n := TILE * pow(2.0, zoom)
	var lon := world.x / n * 360.0 - 180.0
	var lat := rad_to_deg(atan(sinh(PI * (1.0 - 2.0 * world.y / n))))
	return Vector2(wrapf(lon, -180.0, 180.0), clampf(lat, -85.0, 85.0))

func to_screen(point: Vector2) -> Vector2:
	return _world(point) - _world(center) + size * 0.5

func to_world(screen: Vector2) -> Vector2:
	return _lonlat(_world(center) + screen - size * 0.5)

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed: zoom_by(1, event.position); accept_event()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed: zoom_by(-1, event.position); accept_event()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				_dragging = true
				_moved = false
				_press = event.position
			else:
				_dragging = false
				if not _moved:
					pin = to_world(event.position)
					pin_changed.emit(pin)
					queue_redraw()
			accept_event()
	elif event is InputEventMouseMotion and _dragging:
		if event.position.distance_to(_press) > 4: _moved = true
		if _moved:
			center = _lonlat(_world(center) - event.relative)
			queue_redraw()
		accept_event()

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("dfe3e6"))
	var origin := _world(center) - size * 0.5
	var count := int(pow(2.0, zoom))
	var first := Vector2i(floori(origin.x / TILE), floori(origin.y / TILE))
	var last := Vector2i(floori((origin.x + size.x) / TILE), floori((origin.y + size.y) / TILE))
	for ty in range(maxi(first.y, 0), mini(last.y, count - 1) + 1):
		for tx in range(first.x, last.x + 1):
			var at := Vector2(tx * TILE, ty * TILE) - origin
			var texture: Texture2D = _tile(zoom, posmod(tx, count), ty)
			if texture != null: draw_texture_rect(texture, Rect2(at, Vector2(TILE, TILE)), false)
			else: draw_rect(Rect2(at, Vector2(TILE, TILE)), Color(0, 0, 0, 0.08), false, 1.0)
	if pin.is_finite():
		var ring := extent_points(pin, radius_km, shape)
		var points := PackedVector2Array(ring.map(func(p): return to_screen(p)))
		draw_colored_polygon(points, Color(1.0, 0.55, 0.1, 0.16))
		points.append(points[0])
		draw_polyline(points, Color("e8590c"), 2.0, true)
		var at := to_screen(pin)
		draw_circle(at, 6.0, Color("e8590c"))
		draw_circle(at, 2.5, Color.WHITE)
	var font := get_theme_default_font()
	var text := ATTRIBUTION if network else ATTRIBUTION + " · " + I18N.t("map tiles offline")
	var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	var box := Rect2(size - Vector2(width + 12, 20), Vector2(width + 12, 20))
	draw_rect(box, Color(1, 1, 1, 0.82))
	draw_string(font, box.position + Vector2(6, 15), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("333333"))

## Ring (longitude, latitude) of the extent drawn around point: a geodesic-like
## circle or a north-aligned square with side 2·radius (display only; the
## importer builds the exact geometry).
static func extent_points(point: Vector2, value_km: float, value_shape: String) -> Array:
	var lat_deg := value_km * 1000.0 / 111320.0
	var lon_deg := lat_deg / maxf(cos(deg_to_rad(point.y)), 0.01)
	if value_shape == "square":
		return [point + Vector2(-lon_deg, -lat_deg), point + Vector2(lon_deg, -lat_deg), point + Vector2(lon_deg, lat_deg), point + Vector2(-lon_deg, lat_deg)]
	var ring: Array = []
	for i in 72:
		var angle := TAU * i / 72.0
		ring.append(point + Vector2(sin(angle) * lon_deg, cos(angle) * lat_deg))
	return ring

func _tile(z: int, x: int, y: int) -> Texture2D:
	var key := "%d/%d/%d" % [z, x, y]
	if _textures.has(key):
		_order.erase(key)
		_order.append(key)
		return _textures[key]
	var path := "%s/%s.png" % [CACHE_DIR, key]
	var fresh := FileAccess.file_exists(path) and Time.get_unix_time_from_system() - FileAccess.get_modified_time(path) < CACHE_SECONDS
	if FileAccess.file_exists(path) and (fresh or not network or _failed.has(key)):
		var image := Image.load_from_file(ProjectSettings.globalize_path(path))
		if image != null and not image.is_empty():
			_remember(key, ImageTexture.create_from_image(image))
			return _textures[key]
	if network and not _pending.has(key) and not _failed.has(key) and _pending.size() < MAX_REQUESTS: _request(key, z, x, y)
	return null

func _remember(key: String, texture: Texture2D) -> void:
	_textures[key] = texture
	_order.append(key)
	while _order.size() > MEMORY_TILES: _textures.erase(_order.pop_front())

func _request(key: String, z: int, x: int, y: int) -> void:
	var http: HTTPRequest = _idle.pop_back() if not _idle.is_empty() else HTTPRequest.new()
	if http.get_parent() == null:
		http.timeout = 20.0
		add_child(http)
	_pending[key] = http
	for connection: Dictionary in http.request_completed.get_connections(): http.request_completed.disconnect(connection.callable)
	http.request_completed.connect(_received.bind(key, http))
	if http.request(TILE_URL % [z, x, y], PackedStringArray([USER_AGENT])) != OK:
		_pending.erase(key)
		_failed[key] = true
		_idle.append(http)

func _received(outcome: int, code: int, _headers: PackedStringArray, body: PackedByteArray, key: String, http: HTTPRequest) -> void:
	_pending.erase(key)
	_idle.append(http)
	var image := Image.new()
	if outcome != HTTPRequest.RESULT_SUCCESS or code != 200 or image.load_png_from_buffer(body) != OK:
		_failed[key] = true
		queue_redraw()
		return
	var path := "%s/%s.png" % [CACHE_DIR, key]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	var file := FileAccess.open(path + ".part", FileAccess.WRITE)
	if file != null:
		file.store_buffer(body)
		file.close()
		DirAccess.rename_absolute(ProjectSettings.globalize_path(path + ".part"), ProjectSettings.globalize_path(path))
	_remember(key, ImageTexture.create_from_image(image))
	queue_redraw()
