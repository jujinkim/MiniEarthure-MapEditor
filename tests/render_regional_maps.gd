extends SceneTree
## Offline actual package render, no game driving or user acceptance automation.
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
func _initialize() -> void: run.call_deferred()
func run() -> void:
	root.size=Vector2i(1120,760)
	var source := OS.get_environment("REGIONAL_SOURCE")
	var output := OS.get_environment("REGIONAL_DESTINATION")
	for id: String in ["haeon","belmont","nord","safra","red-wadi","kanupi","bansai"]:
		var meta: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(source.path_join(id+"/region.json")))
		var bridge: RefCounted=ClassDB.instantiate("MapKitBridge")
		var opened: Dictionary=JSON.parse_string(bridge.open_package(source.path_join(id+".memap")))
		if not opened.get("ok",false): push_error(str(opened));quit(1);return
		var world:=Node3D.new();root.add_child(world)
		var environment:=WorldEnvironment.new();environment.environment=Environment.new()
		environment.environment.background_mode=Environment.BG_COLOR
		environment.environment.background_color=Color("b7d0d4")
		environment.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color=Color("e3e8e2")
		environment.environment.ambient_light_energy=.35
		world.add_child(environment)
		var sun:=DirectionalLight3D.new();sun.rotation_degrees=Vector3(-55,-35,0);sun.light_energy=.85;sun.shadow_enabled=true;world.add_child(sun)
		var cache:=CACHE.new()
		var jobs:Array=[]
		var combined:Dictionary={"cell":{"x":0,"y":0},"triangles":[],"objects":[],"building_prisms":[],"asset_convexes":[]}
		var seen:Dictionary={}
		var presentation:Dictionary={}
		for y in int(meta.size[1])/16:
			for x in int(meta.size[0])/16:
				var generated:Dictionary=JSON.parse_string(bridge.generate_chunk(x,y))
				if not generated.get("ok",false):push_error(str(generated));quit(1);return
				var chunk:Dictionary=generated.data.chunk
				var packed:Dictionary=bridge.generate_chunk_packed(x,y)
				var decorated:Dictionary=bridge.with_presentation(packed.data)
				var part:Dictionary=decorated.data.chunk.presentation
				if presentation.is_empty():presentation=part.duplicate(true)
				else:
					presentation.assets.merge(part.assets)
					presentation.get("road_styles",{}).merge(part.get("road_styles",{}))
					presentation.hidden_proxies.append_array(part.hidden_proxies)
				combined.triangles.append_array(chunk.triangles)
				for object:Dictionary in chunk.objects:
					if not seen.has(object.id):combined.objects.append(object);seen[object.id]=true
			await process_frame
		combined.presentation=presentation
		combined.triangles.sort_custom(func(a:Dictionary,b:Dictionary):return str(a.surface)<str(b.surface))
		var job:=RENDER.begin(combined,world,Callable(),0,cache)
		while not RENDER.advance(job):pass
		if not job.error.is_empty():push_error(str(job.error));quit(1);return
		jobs.append(job)
		var camera:=Camera3D.new();world.add_child(camera);camera.current=true
		camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=meta.size[0]*1.13
		var center:=Vector3(meta.size[0]/2.0,0,-meta.size[1]/2.0)
		camera.position=center+Vector3(100,330,220);camera.look_at(center)
		await process_frame;await RenderingServer.frame_post_draw
		var directory:=output.path_join(id);DirAccess.make_dir_recursive_absolute(directory)
		root.get_texture().get_image().save_png(directory.path_join("overview.png"))
		camera.projection=Camera3D.PROJECTION_PERSPECTIVE;camera.fov=62
		camera.position=Vector3(meta.start.x_cm/100.0,3.5,-meta.start.y_cm/100.0)
		camera.rotation=Vector3(-.06,meta.start.heading_radians,0)
		await process_frame;await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(directory.path_join("ground.png"))
		print("REGIONAL_RENDERED ",id," cells=",jobs.size()," shared_bytes=",cache.bytes())
		for item:Dictionary in jobs:RENDER.dispose(item)
		world.queue_free();jobs.clear();combined.clear();job.clear();cache.shutdown();await process_frame;await process_frame
	print("render_regional_maps: PASS");quit()
