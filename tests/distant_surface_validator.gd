extends SceneTree
## Same terrain, fixed camera/lighting: near and far must not create cell tint seams.
const STORE := preload("res://scripts/document_store.gd")
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const FAR := preload("res://addons/mapkit/godot/distant_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")
class Lease extends RefCounted:
	func track(_value: Object) -> void: pass
func _initialize() -> void: run.call_deferred()
func run() -> void:
	root.size=Vector2i(320,320)
	var store:=STORE.new();store.new_document()
	store.document.free_roam=true
	store.document.bounds={"min":[0,0],"max":[6400,6400]}
	store.document.cell_size_cm=3200
	store.document.environment=PROFILE.defaults()
	store.document.environment.ground_color=[117,140,88]
	var source:=ProjectSettings.globalize_path("user://surface-match")
	var error: String=store.save_project(source)
	if not error.is_empty(): push_error(error);quit(1);return
	var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
	var opened: Dictionary=JSON.parse_string(bridge.open_project(source))
	if not opened.ok: push_error(str(opened));quit(1);return
	var scene:=Node3D.new();root.add_child(scene)
	var world:=WorldEnvironment.new();world.environment=Environment.new()
	world.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color=Color.WHITE;world.environment.ambient_light_energy=0.8
	scene.add_child(world)
	var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-60,20,0);scene.add_child(sun)
	var camera:=Camera3D.new();camera.position=Vector3(16,100,-16);camera.projection=Camera3D.PROJECTION_ORTHOGONAL
	camera.size=24;scene.add_child(camera);camera.look_at(Vector3(16,0,-16),Vector3.FORWARD);camera.current=true
	var cache:=CACHE.new();cache.environment_profile=store.document.environment
	var generated: Dictionary=bridge.generate_chunk_packed(0,0)
	var decorated: Dictionary=bridge.with_presentation(generated.data)
	var data: Dictionary=decorated.data.chunk
	data.render_batches=RENDER.PLAN.prepare_batches(RENDER.DATA.view(data))
	var job:=RENDER.begin(data,scene,Callable(),0,cache)
	while not RENDER.advance(job): pass
	for frame in 6: await process_frame
	await RenderingServer.frame_post_draw
	var near_image:=root.get_texture().get_image()
	RENDER.cancel(job)
	await process_frame
	var distant: Dictionary=bridge.generate_far_chunk(0,0)
	var far_job:=FAR.begin(distant.data,scene,Lease.new(),cache)
	while not FAR.advance(far_job): pass
	far_job.root.visible=true
	for frame in 6: await process_frame
	await RenderingServer.frame_post_draw
	var far_image:=root.get_texture().get_image()
	var maximum:=0.0
	for y in range(40,280,40):
		for x in range(40,280,40):
			var a:=near_image.get_pixel(x,y);var b:=far_image.get_pixel(x,y)
			maximum=maxf(maximum,maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b))))
	print("SURFACE_MATCH max_rgb_delta=",maximum," near=",near_image.get_pixel(160,160)," far=",far_image.get_pixel(160,160))
	FAR.cancel(far_job);scene.queue_free();cache.shutdown()
	for frame in 3: await process_frame
	if maximum>0.02: push_error("Near/far terrain colour discontinuity");quit(1);return
	print("distant_surface_validator: PASS")
	quit(0)
