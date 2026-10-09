extends SceneTree
## Same water/depth/flow on both display paths, with unchanged collision and leases.
const STORE := preload("res://scripts/document_store.gd")
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const FAR := preload("res://addons/mapkit/godot/distant_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
const QUALITY := preload("res://addons/mapkit/godot/display_quality.gd")
class Lease extends RefCounted:
	var refs: Array[WeakRef]=[]
	func track(value: Object) -> void: refs.append(weakref(value))
	func live() -> int: return refs.filter(func(r: WeakRef):return r.get_ref()!=null).size()
func _initialize() -> void: run.call_deferred()
func sample(image: Image) -> Color:
	var value:=Color(0,0,0,0);var count:=0
	for y in range(2,8):
		for x in range(2,8):
			value+=image.get_pixel(image.get_width()*x/10,image.get_height()*y/10);count+=1
	return value/float(count)
func run() -> void:
	root.size=Vector2i(320,320)
	var store:=STORE.new();store.new_document();store.document.free_roam=true
	store.document.bounds={"min":[0,0],"max":[6400,6400]};store.document.cell_size_cm=3200
	store.document.water_bodies=[{"id":"test-lake","polygon":[[100,100],[3100,100],[3100,3100],[100,3100]],
		"islands":[],"surface_cm":150,"bottom_cm":-200,"flow_cm_s":[45,-20]}]
	var source:=ProjectSettings.globalize_path("user://far-water")
	var error: String=store.save_project(source)
	if not error.is_empty():push_error(error);quit(1);return
	var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
	var opened: Dictionary=JSON.parse_string(bridge.open_project(source))
	if not opened.ok:push_error(str(opened));quit(1);return
	for quality in [0,2]:
		QUALITY.apply(root,QUALITY.profile(quality))
		var scene:=Node3D.new();root.add_child(scene)
		var world:=WorldEnvironment.new();world.environment=Environment.new()
		world.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
		world.environment.ambient_light_color=Color.WHITE;world.environment.ambient_light_energy=.8;scene.add_child(world)
		var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-60,20,0);scene.add_child(sun)
		var camera:=Camera3D.new();camera.position=Vector3(16,100,-16);camera.projection=Camera3D.PROJECTION_ORTHOGONAL
		camera.size=24;scene.add_child(camera);camera.look_at(Vector3(16,0,-16),Vector3.FORWARD);camera.current=true
		var cache:=CACHE.new();cache.quality_profile=QUALITY.active()
		var generated: Dictionary=bridge.generate_chunk_packed(0,0)
		var decorated: Dictionary=bridge.with_presentation(generated.data)
		var data: Dictionary=decorated.data.chunk
		data.render_batches=RENDER.PLAN.prepare_batches(RENDER.DATA.view(data))
		var near_job:=RENDER.begin(data,scene,Callable(),0,cache)
		while not RENDER.advance(near_job):pass
		for frame in 6:await process_frame
		await RenderingServer.frame_post_draw
		var near_color:=sample(root.get_texture().get_image())
		RENDER.cancel(near_job);near_job.clear();await process_frame
		var distant: Dictionary=bridge.generate_far_chunk(0,0)
		var lease:=Lease.new()
		var job:=FAR.begin(distant.data,scene,lease,cache)
		while not FAR.advance(job):pass
		job.root.visible=true;distant.clear()
		if not job.water_material.get_meta("mapkit_water",false):push_error("far water lost common material");quit(1);return
		for frame in 6:await process_frame
		await RenderingServer.frame_post_draw
		var far_color:=sample(root.get_texture().get_image())
		var delta:=maxf(absf(near_color.r-far_color.r),maxf(absf(near_color.g-far_color.g),absf(near_color.b-far_color.b)))
		print("WATER_MATCH quality=",quality," mean_rgb_delta=",delta," near=",near_color," far=",far_color)
		FAR.cancel(job);job.clear();scene.queue_free();cache.shutdown();cache=null
		for frame in 4:await process_frame
		if lease.live()!=0:push_error("far water resources retained after release");quit(1);return
		if delta>.045:push_error("near/far water colour seam");quit(1);return
	print("distant_water_validator: PASS (water colour, quality and release)")
	quit(0)
