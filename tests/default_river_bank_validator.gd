extends SceneTree
## Native final terrain, including road fitting, at the authored water boundary.
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); push_error(label)
func terrain_height(view: Dictionary, point: Vector2) -> float:
	# Spawn probes intentionally reject submerged terrain. Interpolate the actual
	# immutable terrain faces here, including the centimetres below the shore.
	var id: int=view.object_ids.find("terrain")
	for i in view.object_indices.size():
		if view.object_indices[i]!=id: continue
		var v: PackedInt64Array=view.vertices_cm.slice(i*9,i*9+9)
		var a:=Vector2(v[0],v[2]);var b:=Vector2(v[3],v[5]);var c:=Vector2(v[6],v[8])
		var denominator: float=(b-a).cross(c-a)
		if absf(denominator)<.001: continue
		var u: float=(point-a).cross(c-a)/denominator
		var w: float=(b-a).cross(point-a)/denominator
		if u>=-.00001 and w>=-.00001 and u+w<=1.00001: return v[1]*(1-u-w)+v[4]*u+v[7]*w
	return NAN
func run() -> void:
	var source := OS.get_environment("DEFAULT_WORLD_SOURCE")
	var document: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source.path_join("village/document.json")))
	var water: Dictionary=document.water_bodies.filter(func(w):return w.id=="willow-river")[0]
	var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(bridge.open_package(source.path_join("village.memap"))).ok,"open candidate")
	var samples := []
	for index in water.polygon.size():
		var a := Vector2(water.polygon[index][0],water.polygon[index][1])
		var raw: Array=water.polygon[(index+1)%water.polygon.size()]
		var b:=Vector2(raw[0],raw[1])
		if is_equal_approx(a.x,b.x): continue # Clipped end caps span the bed, not a bank.
		# Sample every bank cell and each bridge crossing on the current layout.
		for step in range(1,ceili(a.distance_to(b)/800.0)):
			samples.append(a.lerp(b,float(step)/ceili(a.distance_to(b)/800.0)))
	var cache := {}; var peak := 0
	for point: Vector2 in samples:
		var cell:=Vector2i(floori(point.x/3200),floori(point.y/3200))
		if not cache.has(cell):
			var built: Dictionary=bridge.generate_chunk_packed(cell.x,cell.y)
			check(built.ok,"shore cell generation "+str(cell))
			if not built.ok: continue
			cache[cell]=built.data.chunk.geometry.view()
		var height:=terrain_height(cache[cell],point)
		check(is_finite(height),"shore terrain face "+str(point))
		if is_finite(height):
			var error:=absi(roundi(height)-int(water.surface_cm))
			peak=maxi(peak,error)
			check(error<=22,"water joins final 2 m terrain within interpolation tolerance: "+str([point,error]))
	print("RIVER_BANK samples=",samples.size()," max_error_cm=",peak)
	cache.clear();bridge=null
	print("default_river_bank_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
