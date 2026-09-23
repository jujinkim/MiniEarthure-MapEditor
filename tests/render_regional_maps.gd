extends SceneTree
## Offline actual package render, no game driving or user acceptance automation.
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
func _initialize() -> void: run.call_deferred()
func run() -> void:
	root.size=Vector2i(1120,760)
	var source := OS.get_environment("REGIONAL_SOURCE")
	var output := OS.get_environment("REGIONAL_DESTINATION")
	var ids:=OS.get_environment("REGIONAL_IDS").split(",",false)
	if ids.is_empty():ids=PackedStringArray(["haeon","belmont","nord","safra","red-wadi","kanupi","bansai"])
	for id: String in ids:
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
		# Offline whole-map capture owns all district templates at once. Runtime
		# streaming/cache limits are unchanged and verified separately.
		cache.limit_bytes=512*1024*1024
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
				# Keep the per-triangle road styling aligned while merging cells.
				# Strip hidden proxy triangles before grouping visible materials.
				var road_keys:PackedStringArray=part.get("road_materials",PackedStringArray())
				for index in chunk.triangles.size():
					var triangle:Dictionary=chunk.triangles[index]
					if triangle.object_id in part.hidden_proxies:continue
					triangle["preview_key"]=road_keys[index] if index<road_keys.size() else ""
					combined.triangles.append(triangle)
				for object:Dictionary in chunk.objects:
					if not seen.has(object.id):combined.objects.append(object);seen[object.id]=true
			await process_frame
		combined.presentation=presentation
		combined.triangles.sort_custom(func(a:Dictionary,b:Dictionary):return (a.preview_key if not a.preview_key.is_empty() else str(a.surface))<(b.preview_key if not b.preview_key.is_empty() else str(b.surface)))
		presentation.road_materials=PackedStringArray()
		for triangle:Dictionary in combined.triangles:presentation.road_materials.append(triangle.preview_key)
		combined.presentation=presentation
		# Whole-map documentation is not a streaming cell. Coalesce each material
		# into one mesh so the capture does not consume one shader slot per 512
		# terrain triangles; product per-cell batching remains unchanged.
		var surfaces:Dictionary={}
		for index in combined.triangles.size():
			var key:String=RENDER.display_material_key(combined,index)
			if not surfaces.has(key):
				var surface:=SurfaceTool.new();surface.begin(Mesh.PRIMITIVE_TRIANGLES);surfaces[key]=surface
			var surface:SurfaceTool=surfaces[key]
			for vertex in [0,2,1]:
				var point:Vector3=RENDER.DATA.scene_vertex(combined,index,vertex)
				surface.set_uv(Vector2(point.x,point.z));surface.add_vertex(point)
		combined.render_batches=[]
		for key:String in surfaces:
			var surface:SurfaceTool=surfaces[key];surface.generate_normals()
			var arrays:Array=surface.commit_to_arrays()
			combined.render_batches.append({"key":key,"vertices":arrays[Mesh.ARRAY_VERTEX],"normals":arrays[Mesh.ARRAY_NORMAL],"uv":arrays[Mesh.ARRAY_TEX_UV]})
		var job:=RENDER.begin(combined,world,Callable(),0,cache)
		while not RENDER.advance(job):pass
		if not job.error.is_empty():push_error(str(job.error));quit(1);return
		print("REVIEW_GEOMETRY nodes=",job.root.get_child_count()," triangles=",combined.triangles.size()," objects=",combined.objects.size()," materials=",job.materials.size()," instances=",job.instances.size())
		jobs.append(job)
		var source_document: Dictionary = JSON.parse_string(bridge.document_json()).data
		for g: Dictionary in source_document.get("gimmicks", []):
			var structure := preload("res://addons/mapkit/godot/gimmick_geometry.gd").visual(g)
			structure.transform = preload("res://addons/mapkit/godot/gimmick_geometry.gd").pose(g,0)
			world.add_child(structure)
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
		for view:Dictionary in meta.get("review_views",[]):
			var p:Array=view.position_m;var t:Array=view.target_m
			camera.position=Vector3(p[0],p[1],-p[2]);camera.look_at(Vector3(t[0],t[1],-t[2]))
			await process_frame;await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(directory.path_join(str(view.name)+".png"))
			if view.name==meta.get("ground_view",""):root.get_texture().get_image().save_png(directory.path_join("ground.png"))
		print("REGIONAL_RENDERED ",id," cells=",jobs.size()," shared_bytes=",cache.bytes())
		for item:Dictionary in jobs:RENDER.dispose(item)
		world.queue_free();jobs.clear();combined.clear();job.clear();cache.shutdown();await process_frame;await process_frame
	print("render_regional_maps: PASS");quit()
