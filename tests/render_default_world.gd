extends SceneTree
## Fixed, bounded art-review captures using the product's common render paths.
## No driving, runtime scheduling, collision or acceptance simulation.
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const FAR := preload("res://addons/mapkit/godot/distant_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
const QUALITY := preload("res://addons/mapkit/godot/display_quality.gd")
const ENVIRONMENT := preload("res://addons/mapkit/godot/environment_renderer.gd")
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")

class Lease extends RefCounted:
	var references: Array[WeakRef] = []
	func track(value: Object) -> void: references.append(weakref(value))
	func seal() -> void: pass
	func live() -> int: return references.filter(func(ref: WeakRef): return ref.get_ref()!=null).size()

class StillSky extends RefCounted:
	var profile: Dictionary
	var config: Dictionary
	var seconds := 14.0*3600.0
	var wet := 0.0
	var snow := 0.0
	var seed := 10092026
	var elapsed := 0.0
	var previous_weather := "clear"
	var weather := "clear"
	func blend() -> float: return 1.0
	func celestial() -> Dictionary: return PROFILE.celestial(seconds,config)

func _initialize() -> void: run.call_deferred()
func scene_point(point: Array) -> Vector3: return Vector3(point[0],point[1],-point[2])
func require(result: Dictionary, label: String) -> bool:
	if result.get("ok",false): return true
	push_error(label+": "+str(result));quit(1);return false

func visible_cell(camera: Camera3D, x: int, y: int, eye: Vector3, heights: Array) -> bool:
	if Vector2(x*32+16,y*32+16).distance_to(Vector2(eye.x,-eye.z))<48: return true
	# Frustum culling only reduces offline work; include vertical and visual
	# margins, so trees/buildings anchored just outside a cell remain visible.
	var bounds := AABB(Vector3(x*32-18,float(heights[0]),-(y+1)*32-18),Vector3(68,float(heights[1])-float(heights[0]),68))
	for plane: Plane in camera.get_frustum():
		var all_outside := true
		for corner in 8:
			if not plane.is_point_over(bounds.get_endpoint(corner)):
				all_outside=false;break
		if all_outside: return false
	return true

func percentile(values: Array, fraction: float) -> float:
	if values.is_empty(): return 0.0
	var sorted := values.duplicate();sorted.sort()
	return float(sorted[mini(sorted.size()-1,floori(sorted.size()*fraction))])

func run() -> void:
	root.size=Vector2i(1440,900)
	var source := OS.get_environment("DEFAULT_WORLD_SOURCE")
	var output := OS.get_environment("DEFAULT_WORLD_OUTPUT")
	var id := OS.get_environment("DEFAULT_WORLD_THEME")
	if id.is_empty(): id="village"
	var wanted := OS.get_environment("DEFAULT_WORLD_VIEWS").split(",",false)
	var meta: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source.path_join(id+"/region.json")))
	var doc: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source.path_join(id+"/document.json")))
	var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
	if not require(JSON.parse_string(bridge.open_package(source.path_join(id+".memap"))),"open"): return
	DirAccess.make_dir_recursive_absolute(output)
	var results: Array=[]
	var views: Array=meta.review_views.duplicate(true)
	if OS.get_environment("DEFAULT_WORLD_LOD_COMPARISON")=="1":
		# One fixed dense street, one normal pass and one authored-far pass.
		# This measures display work only; it is not a device/FPS acceptance run.
		var dense: Dictionary=views[0]
		for view: Dictionary in views:
			if view.name=="day-street":dense=view
		views=[dense,dense.duplicate(true)]
		views[1].name=str(dense.name)+"-authored-far-comparison"
		views[1]["force_distant"]=true
	var revisit := OS.get_environment("DEFAULT_WORLD_REVISIT")=="1"
	var shared_cache: RefCounted
	if revisit:
		views=views.filter(func(v):return wanted.is_empty() or v.name in wanted)
		var repeated: Array=[]
		for view: Dictionary in views:
			repeated.append(view)
			var second:=view.duplicate(true);second.name=str(view.name)+"-revisit";repeated.append(second)
		views=repeated;wanted=PackedStringArray()
	for view: Dictionary in views:
		if not wanted.is_empty() and view.name not in wanted: continue
		var override:=OS.get_environment("DEFAULT_WORLD_QUALITY")
		if not override.is_empty(): view.quality=int(override)
		QUALITY.apply(root,QUALITY.profile(int(view.quality)))
		var scene:=Node3D.new();root.add_child(scene)
		var atmosphere:=WorldEnvironment.new();atmosphere.environment=Environment.new();scene.add_child(atmosphere)
		var sun:=DirectionalLight3D.new();scene.add_child(sun)
		var environment:=ENVIRONMENT.new();scene.add_child(environment)
		environment.configure(atmosphere.environment,sun,false)
		environment.set_display_distance(float(view.view_distance_m))
		environment.apply_display_quality(QUALITY.active())
		var camera:=Camera3D.new();scene.add_child(camera);camera.current=true;camera.fov=68
		camera.near=.1;camera.far=float(view.view_distance_m)+80
		if view.get("projection","")=="orthogonal":
			camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=float(view.size_m)
		camera.position=scene_point(view.position_m);camera.look_at(scene_point(view.target_m))
		var state:=StillSky.new();state.profile=doc.environment;state.config=doc.environment.duplicate(true)
		state.config.merge({"intensity":.3,"aurora_probability":0.0,"celestial_mode":"simple"})
		state.seconds=float(view.get("time_minutes",doc.environment.start_minutes))*60
		var cache: RefCounted=shared_cache if shared_cache!=null else CACHE.new()
		if revisit: shared_cache=cache
		cache.environment_profile=state.profile
		cache.quality_profile=QUALITY.active()
		var leases: Array[Lease]=[]
		var jobs: Array[Dictionary]=[]
		var cell_times: Array=[]
		var near_count:=0;var far_count:=0;var near_triangles:=0;var far_triangles:=0
		var maximum_far_cell:=0;var started:=Time.get_ticks_msec()
		var window: Dictionary=JSON.parse_string(bridge.cell_window(roundi(camera.position.x*100),roundi(-camera.position.z*100)))
		if not require(window,"cell window"): return
		var margin: float=float(window.data.visual_margin_cm)*.01
		for y in ceili(float(meta.size[1])/32.0):
			for x in ceili(float(meta.size[0])/32.0):
				var distance:=Vector2(x*32+16,y*32+16).distance_to(Vector2(camera.position.x,-camera.position.z))
				if distance-32*.707107>float(view.view_distance_m): continue
				if not visible_cell(camera,x,y,camera.position,meta.get("display_height_range_m",[-6,80])): continue
				var cell_started:=Time.get_ticks_usec()
				# Same 128m detail radius, 16m prefetch and visual margin as the
				# current display streamer. No altered execution-cell budgets.
				if not view.get("force_distant",false) and maxf(0.0,distance-32*.707107-margin)<=128+16:
					var generated: Dictionary=bridge.generate_chunk_packed(x,y)
					if not require(generated,"near %d,%d"%[x,y]): return
					var decorated: Dictionary=bridge.with_presentation(generated.data)
					if not require(decorated,"presentation"): return
					var data: Dictionary=decorated.data.chunk
					var render_view: Dictionary=RENDER.DATA.view(data)
					near_triangles+=RENDER.DATA.count(render_view)
					data.render_batches=RENDER.PLAN.prepare_batches(render_view)
					var job:=RENDER.begin(data,scene,Callable(),0,cache)
					while not RENDER.advance(job): pass
					if not job.error.is_empty(): push_error(str(job.error));quit(1);return
					jobs.append(job);near_count+=1
				else:
					var generated: Dictionary=bridge.generate_far_chunk(x,y)
					if not require(generated,"far %d,%d"%[x,y]): return
					var lease:=Lease.new();leases.append(lease)
					var job:=FAR.begin(generated.data,scene,lease,cache)
					job["distant"]=true
					while not FAR.advance(job): pass
					job.root.visible=true;jobs.append(job)
					far_count+=1;far_triangles+=int(generated.data.triangles)
					maximum_far_cell=maxi(maximum_far_cell,int(generated.data.retained_bytes)+int(generated.data.display_bytes))
				cell_times.append(float(Time.get_ticks_usec()-cell_started)/1000.0)
				if (near_count+far_count)%40==0:
					print("REVIEW_PROGRESS ",view.name," cells=",near_count+far_count)
					await process_frame
		var preparation_ms:=Time.get_ticks_msec()-started
		environment.update_environment(state,camera.position,[],cache,true)
		environment.update_dynamic_lights(camera.position,[])
		for frame in 12: await process_frame
		var frame_times: Array=[]
		var last:=Time.get_ticks_usec()
		for frame in 120:
			await process_frame
			var now:=Time.get_ticks_usec();frame_times.append(float(now-last)/1000.0);last=now
		await RenderingServer.frame_post_draw
		var frame_stats: Dictionary={"objects":RenderingServer.viewport_get_render_info(root.get_viewport_rid(),RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,RenderingServer.VIEWPORT_RENDER_INFO_OBJECTS_IN_FRAME),
			"primitives":RenderingServer.viewport_get_render_info(root.get_viewport_rid(),RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME),
			"draw_calls":RenderingServer.viewport_get_render_info(root.get_viewport_rid(),RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME)}
		var file:=output.path_join(id+"-"+str(view.name)+".png")
		if root.get_texture().get_image().save_png(file)!=OK: push_error("capture failed");quit(1);return
		var report: Dictionary={"package_sha256":FileAccess.get_sha256(source.path_join(id+".memap")),"view":view,"near_cells":near_count,"far_cells":far_count,"near_collision_triangles":near_triangles,
			"far_display_triangles":far_triangles,"largest_far_cell_bytes":maximum_far_cell,"shared_cache_bytes":cache.bytes(),
			"render":frame_stats,"preparation_ms":preparation_ms,"image":file,
			"cell_prepare_p95_ms":percentile(cell_times,.95),"cell_prepare_p99_ms":percentile(cell_times,.99),
			"frame_p95_ms":percentile(frame_times,.95),"frame_p99_ms":percentile(frame_times,.99),
			"static_memory_bytes":Performance.get_monitor(Performance.MEMORY_STATIC),"video_memory_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
			"cache":cache.diagnostics(),"attachment":RENDER.diagnostics(),"device":RenderingServer.get_video_adapter_name(),"resolution":[1440,900]}
		results.append(report);print("REVIEW_CAPTURE ",JSON.stringify(report))
		for job: Dictionary in jobs:
			if job.get("distant",false): FAR.cancel(job)
			else: RENDER.cancel(job)
		jobs.clear();scene.queue_free()
		if not revisit: cache.shutdown()
		environment=null;cache=null
		for frame in 4: await process_frame
		for lease: Lease in leases:
			if lease.live()!=0: push_error("far resource ownership retained after release");quit(1);return
		leases.clear()
	if shared_cache!=null: shared_cache.shutdown();shared_cache=null
	var report_file:=FileAccess.open(output.path_join(id+"-render-report.json"),FileAccess.WRITE)
	report_file.store_string(JSON.stringify(results,"\t"));report_file.close()
	print("render_default_world: PASS (fixed common-renderer views; user art review pending)")
	quit(0)
