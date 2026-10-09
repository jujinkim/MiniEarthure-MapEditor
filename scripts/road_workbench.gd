extends RefCounted
## Ordinary roads share native surface frames, attachments and command history.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
const I18N := preload("./locale_text.gd")
const RENDER:=preload("res://addons/mapkit/godot/chunk_renderer.gd")
var bench: Node
var selected := ""
var selection: ItemList
var paths := {}
var epoch := -1
var session := -1
var controls: Array[SpinBox] = []
var design := {}
var width: SpinBox
var point_index := 0
var environment: Node3D
var environment_job: RefCounted
var environment_cell := Vector2i(-1,-1)
var camera_cell := Vector2i(-1,-1)
var requested := {}
var triangles: Array = []
var environment_epoch := -1
var environment_session := -1
var ray_bounds := AABB()
var guides: MeshInstance3D
var issue_marker: MeshInstance3D
var rendered := {}
var render_pending := {}
var render_jobs: Array = []

func build(parent: Node) -> void:
	selection = ItemList.new()
	selection.custom_minimum_size.y = 70
	selection.tooltip_text = I18N.t("Ordinary roads · Select to edit curve, height and width")
	parent.add_child(selection)
	selection.item_selected.connect(func(index: int): select(str(selection.get_item_metadata(index))))

func refresh() -> void:
	var store: RefCounted = bench.editor.store
	if epoch == store.command_epoch and session == store.session_id: return
	var replaced: bool = session != store.session_id
	epoch = store.command_epoch
	session = store.session_id
	paths.clear()
	selection.clear()
	for road: Dictionary in store.document.get("roads",[]):
		selection.add_item(str(road.id))
		selection.set_item_metadata(selection.item_count-1,road.id)
		if road.has("design"):
			var result: Dictionary=JSON.parse_string(store.bridge.road_surface_path(JSON.stringify(road)))
			if result.ok: paths[road.id]=result.data
	if selected not in paths: selected=""
	if replaced:
		selected=""
		triangles.clear()
		clear_environment()
		if is_instance_valid(environment): environment.queue_free()
		environment=null
		environment_cell=Vector2i(-1,-1)
		camera_cell=Vector2i(-1,-1)
		clear_guides()
		if is_instance_valid(issue_marker):issue_marker.queue_free()
	var d: Dictionary=store.document
	var assembly: Dictionary=d.assembled_track if d.get("assembled_track") is Dictionary else {}
	if not d.get("heightmaps",[]).is_empty() or not d.get("roads",[]).is_empty() or (assembly.get("authoring") is Dictionary and assembly.authoring.get("terrain_integration",false)):
		var point: Array = d.roads[0].points[0] if not d.get("roads",[]).is_empty() else [d.bounds.min[0],0,d.bounds.min[1]]
		if not replaced and environment_cell.x>=0: request_cell(environment_cell)
		else: focus_point(PREVIEW.point(point))

func select(id: String) -> void:
	bench.cancel_interaction(false)
	bench.selected=-1
	bench.selection.deselect_all()
	selected=id
	point_index=0
	bench._properties()
	if paths.has(id):
		var point:=PREVIEW.point(paths[id][0].position_cm)
		bench.editor.preview_camera.frame(point,48)
		focus_point(point)
	bench.editor.commands.refresh_buttons()

func terrain_policy_control(parent: Node, value: String, changed: Callable) -> void:
	var picker:=OptionButton.new()
	var values: Array[String]=["auto_fit","preserve","elevated"]
	for name: String in ["Fit surrounding terrain","Keep original terrain","Elevated / supported"]: picker.add_item(I18N.t(name))
	picker.select(maxi(0,values.find(value)))
	parent.add_child(picker)
	picker.item_selected.connect(func(index: int): changed.call(values[index]))

func properties(parent: Node) -> void:
	var record: Dictionary={}
	for road: Dictionary in bench.editor.store.document.roads:
		if road.id==selected: record=road;break
	if record.is_empty(): return
	var result: Dictionary=JSON.parse_string(bench.editor.store.bridge.road_design(JSON.stringify(record)))
	if not result.ok: bench.editor._status(bench.editor.store.reason(result));return
	design=result.data
	bench.editor._label(parent,selected)
	bench.editor._label(parent,I18N.t("Cubic controls · Shared nodes move connected road ends"))
	width=bench._spin(parent,"Road width (m)",float(record.widths_cm[0])/100,1,100)
	terrain_policy_control(parent,design.terrain_policy,func(value: String): design.terrain_policy=value)
	var shoulder: SpinBox=bench._spin(parent,"Shoulder (m)",float(design.shoulder_cm)/100,0,50)
	shoulder.value_changed.connect(func(value: float): design.shoulder_cm=roundi(value*100))
	var picker:=OptionButton.new()
	for i in design.control_points.size(): picker.add_item(I18N.t("Anchor " if i%3==0 else "Handle ")+str(i),i)
	point_index=clampi(point_index,0,design.control_points.size()-1)
	draw_guides()
	picker.select(point_index)
	parent.add_child(picker)
	controls.clear()
	for j in 3: controls.append(bench._spin(parent,["X (m)","Height (m)","Z (m)"][j],float(design.control_points[point_index][j])/100))
	picker.item_selected.connect(func(index: int):
		capture_point()
		point_index=index
		for j in 3: controls[j].set_value_no_signal(float(design.control_points[index][j])/100)
		draw_guides())
	bench._button(parent,"Apply road alignment",func():
		capture_point()
		var failure: String=bench.editor.store.edit_road(selected,design,roundi(width.value*100))
		if failure!="": bench.editor._status(I18N.diagnostic(failure)))
	for item: Dictionary in bench.editor.store.document.get("surface_attachments",[]):
		if item.surface.surface_id!=selected: continue
		bench._button(parent,I18N.t("Remove ")+I18N.t(bench.piece_name(item.kind)),func():
			var items: Array=bench.editor.store.document.surface_attachments.filter(func(a):return a.id!=item.id)
			var failure: String=bench.editor.store.edit_surface_attachments(items)
			if failure!="":bench.editor._status(failure))

func capture_point() -> void:
	var old: Array=design.control_points[point_index].duplicate()
	var point: Array=[]
	for control: SpinBox in controls:point.append(roundi(control.value*100))
	design.control_points[point_index]=point
	# Moving an anchor carries its handles; moving a handle mirrors its partner
	# about the shared anchor, retaining a continuous tangent and elevation.
	if point_index%3==0:
		for at in [point_index-1,point_index+1]:
			if at<0 or at>=design.control_points.size():continue
			for j in 3:design.control_points[at][j]+=point[j]-old[j]
	else:
		var anchor:=point_index-1 if point_index%3==1 else point_index+1
		var opposite:=2*anchor-point_index
		if opposite>=0 and opposite<design.control_points.size():
			for j in 3:design.control_points[opposite][j]=2*design.control_points[anchor][j]-point[j]
	draw_guides()

func clear_guides() -> void:
	if is_instance_valid(guides):guides.queue_free()
	guides=null

func draw_guides() -> void:
	clear_guides()
	if selected.is_empty() or design.is_empty():return
	guides=MeshInstance3D.new()
	var mesh:=ImmediateMesh.new()
	var material:=StandardMaterial3D.new()
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo=true
	material.no_depth_test=true
	mesh.surface_begin(Mesh.PRIMITIVE_LINES,material)
	for i in design.control_points.size():
		var point:=PREVIEW.point(design.control_points[i])
		mesh.surface_set_color(Color("ffbc40") if i==point_index else Color("65c7ed"))
		for axis in [Vector3.RIGHT,Vector3.UP,Vector3.BACK]:
			mesh.surface_add_vertex(point-axis*0.45);mesh.surface_add_vertex(point+axis*0.45)
		if i>0:
			mesh.surface_add_vertex(PREVIEW.point(design.control_points[i-1]));mesh.surface_add_vertex(point)
	mesh.surface_end();guides.mesh=mesh
	bench.editor.preview_world.add_child(guides)

func show_issue(text: String) -> void:
	if not (text.contains("E_TRACK_ENVIRONMENT") or text.contains("E_TRACK_SUPPORT") or text.contains("E_ROAD_ENVIRONMENT") or text.contains("E_ROAD_INTERSECTION")):return
	var pattern:=RegEx.new()
	pattern.compile("at \\[(-?[0-9]+), ?(-?[0-9]+), ?(-?[0-9]+)\\]")
	var found:=pattern.search(text)
	if found==null:return
	if is_instance_valid(issue_marker):issue_marker.queue_free()
	issue_marker=MeshInstance3D.new()
	var sphere:=SphereMesh.new();sphere.radius=0.8;sphere.height=1.6
	var material:=StandardMaterial3D.new();material.albedo_color=Color("ff384e");material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	sphere.material=material;issue_marker.mesh=sphere
	issue_marker.position=PREVIEW.point([int(found.get_string(1)),int(found.get_string(2)),int(found.get_string(3))])
	bench.editor.preview_world.add_child(issue_marker)
	bench.editor.preview_camera.frame(issue_marker.position,32);focus_point(issue_marker.position)

func connect_track(port: Dictionary, curve: bool) -> void:
	if bench.selected<0:return
	var next: Dictionary=bench.source.duplicate(true)
	var target_id: String=next.instances[bench.selected].id
	if curve:
		var a: Dictionary=port.sample
		var b: Dictionary=bench.editor.store.track_pieces()[bench.selected].path[0]
		var reach:=maxf(400,PREVIEW.point(a.position_cm).distance_to(PREVIEW.point(b.position_cm))*50)
		var p1: Array=[];var p2: Array=[]
		for j in 3:
			p1.append(roundi(a.position_cm[j]+a.forward[j]*reach/1000000))
			p2.append(roundi(b.position_cm[j]-b.forward[j]*reach/1000000))
		var id: String="road-link-"+Crypto.new().generate_random_bytes(4).hex_encode()
		next.instances.append({"id":id,"preset":"free_curve","position_cm":[0,0,0],"rotation_mdeg":[0,0,0],"width_cm":400,"entry_width_cm":int(a.lateral_cm)*2,"exit_width_cm":int(b.lateral_cm)*2,"control_points":[a.position_cm,p1,p2,b.position_cm]})
		next.connections.append({"from":id,"to":target_id})
		target_id=id
	next["road_connections"]=next.get("road_connections",[]).filter(func(c):return c.instance!=target_id)
	next.road_connections.append({"road":port.road,"start":port.start,"instance":target_id})
	bench._commit(next,next.instances.size()-1 if curve else bench.selected)

func ports() -> Array:
	var out: Array=[]
	for id: String in paths:
		for start in [false,true]:
			var sample: Dictionary=(paths[id][0] if start else paths[id].back()).duplicate(true)
			if start:
				for j in 3:sample.forward[j]=-sample.forward[j]
				if sample.get("ribbon_cm") is Array:sample.ribbon_cm.reverse()
			out.append({"road":id,"start":start,"sample":sample})
	return out

func station(id: String, sample: int) -> int:
	var distance:=0.0
	for i in range(1,sample+1):distance+=PREVIEW.point(paths[id][i].position_cm).distance_to(PREVIEW.point(paths[id][i-1].position_cm))*100
	return roundi(distance)

func focus_point(point: Vector3) -> void:
	var d: Dictionary=bench.editor.store.document
	request_cell(Vector2i(floori((point.x*100-d.bounds.min[0])/3200),floori((-point.z*100-d.bounds.min[1])/3200)))

func request_cell(cell: Vector2i) -> void:
	var store: RefCounted=bench.editor.store
	camera_cell=cell
	requested={"cell":cell,"epoch":store.command_epoch,"session":store.session_id}
	if environment_job!=null:
		if environment_job.request==requested:return
		environment_job.cancel()
		return
	_launch_environment()

func _launch_environment() -> void:
	if requested.is_empty():return
	environment_job=preload("./road_preview_job.gd").new()
	var failure: Error=environment_job.start(bench.editor.store,requested)
	if failure!=OK:environment_job=null;bench.editor._status(error_string(failure))

func poll() -> void:
	if bench.active and (not paths.is_empty() or not bench.editor.store.document.get("heightmaps",[]).is_empty()):
		var d: Dictionary=bench.editor.store.document
		var point: Vector3=bench.editor.preview_camera.target
		var cell:=Vector2i(floori((point.x*100-d.bounds.min[0])/3200),floori((-point.z*100-d.bounds.min[1])/3200))
		if cell!=camera_cell:request_cell(cell)
	if not render_pending.is_empty():
		if render_pending.request.epoch!=bench.editor.store.command_epoch or render_pending.request.session!=bench.editor.store.session_id:
			clear_pending()
		else:
			var deadline:=Time.get_ticks_usec()+3000
			while not render_jobs.is_empty() and Time.get_ticks_usec()<deadline:
				if RENDER.advance(render_jobs[0]):
					var done: Dictionary=render_jobs.pop_front()
					if not done.error.is_empty():
						bench.editor._status(str(done.error));clear_pending();return
			if render_jobs.is_empty():
				for cell: Vector2i in rendered:
					if not render_pending.cells.has(cell) or rendered[cell]!=render_pending.cells[cell]:RENDER.cancel(rendered[cell].job)
				rendered=render_pending.cells
				for cell: Vector2i in rendered:rendered[cell].job.root.visible=true
				triangles=render_pending.triangles
				environment_epoch=render_pending.request.epoch;environment_session=render_pending.request.session;environment_cell=render_pending.request.cell
				render_pending={}
	if environment_job==null or environment_job.is_alive():return
	var job: RefCounted=environment_job
	var result: Dictionary=job.finish()
	environment_job=null
	var store: RefCounted=bench.editor.store
	if job.request!=requested:
		_launch_environment();return
	if job.request.epoch!=store.command_epoch or job.request.session!=store.session_id:return
	requested={}
	if result.has("error"):
		bench.editor._status(result.error);return
	if not is_instance_valid(environment):
		environment=Node3D.new();environment.name="RoadTerrainPreview";bench.editor.preview_world.add_child(environment)
	clear_pending()
	render_pending={"cells":{},"triangles":result.triangles,"request":job.request}
	for cell: Dictionary in result.chunks:
		if rendered.has(cell.cell) and rendered[cell.cell].hash==cell.hash:
			render_pending.cells[cell.cell]=rendered[cell.cell];continue
		var display: Dictionary=RENDER.begin(cell.chunk,environment)
		display.root.visible=false
		render_jobs.append(display)
		render_pending.cells[cell.cell]={"hash":cell.hash,"job":display}

func raycast(screen: Vector2, roads_only := false) -> Dictionary:
	var camera: Camera3D=bench.editor.preview_camera.camera
	var origin:=camera.project_ray_origin(screen)
	var ray:=camera.project_ray_normal(screen)
	var best: Dictionary={"distance":INF,"road":"","sample":-1}
	if environment_epoch!=bench.editor.store.command_epoch or environment_session!=bench.editor.store.session_id:return best
	for t: Dictionary in triangles:
		if roads_only and not paths.has(t.object_id):continue
		if not t.spawnable:continue
		var hit: Variant=bench.placement._surface_triangle(origin,ray,PREVIEW.point(t.vertices[0]),PREVIEW.point(t.vertices[1]),PREVIEW.point(t.vertices[2]))
		if not hit is Vector3 or origin.distance_to(hit)>=best.distance:continue
		best={"distance":origin.distance_to(hit),"point":hit,"road":"","sample":-1}
		if paths.has(t.object_id):
			best.road=t.object_id
			var nearest:=INF
			for i in paths[t.object_id].size():
				var gap: float=hit.distance_squared_to(PREVIEW.point(paths[t.object_id][i].position_cm))
				if gap<nearest:nearest=gap;best.sample=i
	return best

func shutdown() -> void:
	if environment_job!=null:environment_job.shutdown();environment_job=null
	clear_environment()

func clear_pending() -> void:
	for cell: Vector2i in render_pending.get("cells",{}):
		if not rendered.has(cell) or rendered[cell]!=render_pending.cells[cell]:RENDER.cancel(render_pending.cells[cell].job)
	render_jobs.clear();render_pending={}

func clear_environment() -> void:
	clear_pending()
	for cell: Vector2i in rendered:RENDER.cancel(rendered[cell].job)
	rendered.clear()

func duplicate_road() -> void:
	var store: RefCounted=bench.editor.store
	var next: Dictionary=store.document.duplicate(true)
	for road: Dictionary in store.document.roads:
		if road.id!=selected:continue
		var copy: Dictionary=road.duplicate(true)
		copy.id="road-"+Crypto.new().generate_random_bytes(5).hex_encode()
		copy.from=copy.id+"-from";copy.to=copy.id+"-to"
		for point: Array in copy.points:point[0]+=2000
		if copy.has("design"):
			for point: Array in copy.design.control_points:point[0]+=2000
		next.roads.append(copy)
		next.nodes.append({"id":copy.from,"position":copy.points[0],"level":0})
		next.nodes.append({"id":copy.to,"position":copy.points.back(),"level":0})
		var failure: String=store.apply_command("Duplicate road",store.document_patches(next))
		if failure!="":bench.editor._status(failure)
		else:select(copy.id)
		return

func delete_road() -> void:
	var store: RefCounted=bench.editor.store
	var d: Dictionary=store.document
	var assembly: Dictionary=d.assembled_track if d.get("assembled_track") is Dictionary else {}
	# A connected port or attachment is an explicit dependency: preserve it and
	# explain which source must be detached instead of silently deleting it.
	if d.get("surface_attachments",[]).any(func(a):return a.surface.surface_id==selected) or (assembly.authoring.get("road_connections",[]) if assembly.get("authoring") is Dictionary else []).any(func(c):return c.road==selected):
		bench.editor._status(I18N.t("Detach this road's surface tools and track ports before deleting it."));return
	var next: Dictionary=d.duplicate(true)
	next.roads=next.roads.filter(func(r):return r.id!=selected)
	var failure: String=store.apply_command("Remove road and restore original terrain",store.document_patches(next))
	if failure!="":bench.editor._status(failure)
	else:selected="";bench.refresh()
