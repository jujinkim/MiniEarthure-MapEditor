extends SceneTree
## Actual common sky pixels must remain continuous across the horizon.
const ENV := preload("res://addons/mapkit/godot/environment_renderer.gd")
func _initialize() -> void:run.call_deferred()
func run() -> void:
	root.size=Vector2i(320,200)
	var scene:=Node3D.new();root.add_child(scene)
	var world:=WorldEnvironment.new();world.environment=Environment.new();scene.add_child(world)
	var sun:=DirectionalLight3D.new();scene.add_child(sun)
	var environment:=ENV.new();scene.add_child(environment);environment.configure(world.environment,sun,false)
	world.environment.fog_enabled=false
	var camera:=Camera3D.new();scene.add_child(camera);camera.current=true;camera.fov=60
	environment.sky_material.set_shader_parameter("cloud_cover",0.0)
	environment.sky_material.set_shader_parameter("sun_direction",Vector3(0,1,0))
	for daylight in [0.0,1.0]:
		environment.sky_material.set_shader_parameter("daylight",daylight)
		for frame in 8:await process_frame
		await RenderingServer.frame_post_draw
		var bitmap:=root.get_texture().get_image();var maximum:=0.0
		for x in [60,100,140,180,220,260]:
			var a:=bitmap.get_pixel(x,97);var b:=bitmap.get_pixel(x,102)
			maximum=maxf(maximum,maxf(absf(a.r-b.r),maxf(absf(a.g-b.g),absf(a.b-b.b))))
		print("SKY_HORIZON daylight=",daylight," delta=",maximum)
		if maximum>.035:push_error("sky horizon colour discontinuity");quit(1);return
	scene.queue_free();environment=null
	for frame in 4:await process_frame
	print("sky_horizon_validator: PASS (day/night actual horizon pixels)");quit(0)
