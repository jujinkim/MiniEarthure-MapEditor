extends SceneTree
## Fixed source/package views for local regional-map authoring verification.
## MAPEDITOR_REGION_CAPTURE_PLAN: JSON {source, output, views:[{name,target_cm,
## offset_m,size_m,cell_radius,near_radius}]}. It never edits the source map.
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
const FAR := preload("res://addons/mapkit/godot/distant_renderer.gd")
const CACHE := preload("res://addons/mapkit/godot/render_resource_cache.gd")
const QUALITY := preload("res://addons/mapkit/godot/display_quality.gd")
class Lease extends RefCounted:
	var held: Array = []
	func track(value: Object) -> void: held.append(value)
var failed := false
func _initialize() -> void: run.call_deferred()
func check(ok: bool, label: String) -> bool:
	if not ok: failed = true; push_error(label)
	return ok
func run() -> void:
	if not check(DisplayServer.get_name() != "headless", "fixed captures require a rendered process"): quit(1); return
	var plan: Variant = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("MAPEDITOR_REGION_CAPTURE_PLAN")))
	if not check(plan is Dictionary and plan.get("views") is Array and not plan.views.is_empty(), "capture plan"): quit(1); return
	root.size = Vector2i(1280,960)
	QUALITY.current = QUALITY.profile(1)
	var native: RefCounted = ClassDB.instantiate("MapKitBridge")
	var source: String = plan.source
	var opened: Dictionary = JSON.parse_string(native.open_package(source) if source.ends_with(".memap") else native.open_project(source))
	if not check(opened.get("ok",false), "open regional source: "+str(opened.get("error",{}))): quit(1); return
	var document: Dictionary = JSON.parse_string(native.document_json()).data
	DirAccess.make_dir_recursive_absolute(plan.output)
	for view: Dictionary in plan.views:
		await capture(native,document,view,plan.output)
	print("capture_regional_map: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)

func capture(native: RefCounted, document: Dictionary, view: Dictionary, output: String) -> void:
	var point: Array = view.target_cm.duplicate()
	if not check(point.size() == 3 and point[1] != null,"explicit target height"): return
	var target := RENDER.scene_position(point)
	var world := Node3D.new();root.add_child(world)
	var atmosphere := WorldEnvironment.new();atmosphere.environment = Environment.new()
	atmosphere.environment.background_mode = Environment.BG_COLOR
	atmosphere.environment.background_color = Color("c7d3db")
	atmosphere.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	atmosphere.environment.ambient_light_color = Color.WHITE
	atmosphere.environment.ambient_light_energy = .35
	world.add_child(atmosphere)
	var light := DirectionalLight3D.new();world.add_child(light)
	light.rotation_degrees = Vector3(-50,-30,0);light.shadow_enabled = true;light.light_energy = .7
	var camera := Camera3D.new();world.add_child(camera)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL;camera.size = float(view.size_m)
	camera.far = 5000
	camera.position = target + Vector3(view.offset_m[0],view.offset_m[1],view.offset_m[2])
	camera.look_at(target);camera.current = true
	var label := Label.new();label.text = str(view.name);label.position = Vector2(16,12)
	label.add_theme_font_size_override("font_size",24);root.add_child(label)
	var cache := CACHE.new();cache.quality_profile = QUALITY.current
	cache.environment_profile = document.get("environment",{})
	var size := int(document.cell_size_cm)
	var nx := int((document.bounds.max[0]-document.bounds.min[0])/size)
	var ny := int((document.bounds.max[1]-document.bounds.min[1])/size)
	var cx := floori((float(point[0])-document.bounds.min[0])/size)
	var cy := floori((float(point[2])-document.bounds.min[1])/size)
	var radius := clampi(int(view.get("cell_radius",2)),0,7)
	var near_radius := clampi(int(view.get("near_radius",0)),-1,2)
	var jobs: Array = []
	var far_jobs: Array = []
	for y in range(maxi(0,cy-radius),mini(ny,cy+radius+1)):
		for x in range(maxi(0,cx-radius),mini(nx,cx+radius+1)):
			if maxi(absi(x-cx),absi(y-cy)) <= near_radius:
				var generated: Dictionary = native.generate_chunk_packed(x,y)
				if not check(generated.get("ok",false),"near cell "+str([x,y])+": "+str(generated.get("error",{}))): continue
				var decorated: Dictionary = native.with_presentation(generated.data)
				if not check(decorated.get("ok",false),"presentation "+str(decorated.get("error",{}))): continue
				var data: Dictionary = decorated.data.chunk
				data.render_batches = RENDER.PLAN.prepare_batches(RENDER.DATA.view(data))
				var job := RENDER.begin(data,world,Callable(),RENDER.PLAN.estimate(RENDER.DATA.view(data),0),cache)
				var steps := 0
				while not RENDER.advance(job) and steps < 100000:
					steps += 1
					if steps % 32 == 0: await process_frame
				check(job.error.is_empty() and steps < 100000,"near rendering "+str(job.error))
				jobs.append(job)
			else:
				var generated: Dictionary = native.generate_far_chunk(x,y)
				if not check(generated.get("ok",false),"far cell "+str([x,y])+": "+str(generated.get("error",{}))): continue
				var job := FAR.begin(generated.data,world,Lease.new(),cache)
				var steps := 0
				while not FAR.advance(job) and steps < 100000:
					steps += 1
					if steps % 32 == 0: await process_frame
				check(job.done and not job.cancelled,"far rendering")
				job.root.visible = true;far_jobs.append(job)
	for frame in 6: await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(output.path_join(str(view.name)+".png")) == OK,"save fixed view")
	print("REGIONAL_CAPTURE ",view.name," target=",point," near=",jobs.size()," far=",far_jobs.size())
	for job: Dictionary in jobs: RENDER.cancel(job)
	for job: Dictionary in far_jobs: FAR.cancel(job)
	jobs.clear();far_jobs.clear()
	world.queue_free();label.queue_free();cache.shutdown()
	for frame in 3: await process_frame
