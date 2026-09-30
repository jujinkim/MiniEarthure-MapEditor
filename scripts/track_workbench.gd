extends Node
## Commands edit public authoring source; the native compiler owns every derived frame.
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var editor: Control
var palette: VBoxContainer
var properties: VBoxContainer
var report: Label
var selection: ItemList
var catalogue: Dictionary
var source: Dictionary={}
var selected := -1
var route_index := 0
var snap: CheckButton
var active := false
var view: Node3D
var controls: Array[SpinBox]=[]
var port_widths: Array[SpinBox]=[]
var width: OptionButton
var target: OptionButton
var sample_input: SpinBox
var action_height: SpinBox
var landing_target: OptionButton
var landing_sample: SpinBox
var route_input: LineEdit
var drag_start: Variant=null
var drag_source: Dictionary={}
var drag_epoch := -1
var updating := false

func build(owner: Control) -> void:
	editor=owner
	catalogue=JSON.parse_string(editor.store.bridge.track_catalogue()).data
	palette=VBoxContainer.new()
	palette.size_flags_vertical=Control.SIZE_EXPAND_FILL
	editor.left_dock.add_child(palette)
	var title:=Label.new()
	title.text="트랙 조각"
	palette.add_child(title)
	var tabs:=TabContainer.new()
	tabs.custom_minimum_size=Vector2(240,150)
	palette.add_child(tabs)
	for category: String in ["driving","gimmick","action"]:
		var scroll:=ScrollContainer.new()
		scroll.name={"driving":"주행","gimmick":"기믹","action":"액션"}[category]
		tabs.add_child(scroll)
		var list:=VBoxContainer.new()
		scroll.add_child(list)
		for entry: Dictionary in catalogue.entries:
			if entry.category!=category: continue
			_button(list,entry.id,add_piece.bind(entry.id))
		if category=="gimmick":
			for kind: String in catalogue.obstacle_kinds: _button(list,kind,add_obstacle.bind(kind))
	_button(palette,"지그재그 + 점프 지름길 조합",func(): var result: Dictionary=JSON.parse_string(editor.store.bridge.track_shortcut_source()); _commit(result.data))
	selection=ItemList.new()
	selection.custom_minimum_size.y=60
	selection.size_flags_vertical=Control.SIZE_EXPAND_FILL
	palette.add_child(selection)
	selection.item_selected.connect(func(index: int): selected=index; _properties(); _draw())
	snap=CheckButton.new()
	snap.text="포트 스냅"
	snap.button_pressed=true
	palette.add_child(snap)
	_button(palette,"선택 조각 보기",frame_selection)
	_button(palette,"복제",duplicate_piece)
	_button(palette,"삭제",delete_piece)
	properties=VBoxContainer.new()
	properties.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	editor.properties.get_parent().add_child(properties)
	report=editor.validation_label
	report.max_lines_visible=3

func refresh() -> void:
	if updating: return
	active=not editor.store.document.get("free_roam",false)
	palette.visible=active
	properties.visible=active
	report.visible=true
	editor.author_panel.visible=not active
	editor.full_generation.visible=not active
	editor.regional_grouping.visible=not active
	editor.preview_dock.get_child(0).visible=not active
	if active:
		editor.selection_label.text="3D 트랙 작업 공간 · 보조 평면도"
		editor.tool_hint.text="왼쪽 조각 선택 · 왼쪽 드래그 이동 · 오른쪽 드래그 회전 · 휠 확대 · 속성에서 고도/곡선 조절"
		editor.status_label.text="조각을 추가하거나 Seed Track으로 시작하세요." if source.get("instances",[]).is_empty() else "저장 가능한 저작 원본 · 실행 내보내기는 연결·코스 검사 후 가능"
	for child in editor.left_dock.get_children():
		if child!=palette: child.visible=not active
	editor.properties.visible=not active
	editor.apply_button.visible=not active
	if not active:
		if editor.store.document.has("assembled_track"): _draw()
		elif is_instance_valid(view): view.queue_free()
		return
	source=editor.store.track_source()
	selection.clear()
	for i: Dictionary in source.instances: selection.add_item(i.id+" · "+i.preset)
	selected=mini(selected,source.instances.size()-1)
	if selected>=0: selection.select(selected)
	_properties()
	var a: Dictionary=editor.store.document.get("assembled_track",{})
	var issues: Array=a.get("issues",[])
	report.text="연결·코스 검사: "+("실행 형상 준비 · 수동 코스는 플레이어 완주 검증 필요" if issues.is_empty() and not a.is_empty() else " / ".join(issues))
	_draw()

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var b:=Button.new()
	b.text=text
	b.pressed.connect(callback)
	parent.add_child(b)
	return b

func _spin(parent: Node, label: String, value: float, low := -100000.0, high := 100000.0, step := 0.01) -> SpinBox:
	var s:=SpinBox.new()
	s.prefix=label+" "
	s.min_value=low
	s.max_value=high
	s.step=step
	s.value=value
	parent.add_child(s)
	return s

func _properties() -> void:
	for child in properties.get_children(): child.queue_free(); properties.remove_child(child)
	controls.clear()
	port_widths.clear()
	var policy:=CheckButton.new()
	policy.text="자유주행 편집으로 전환"
	properties.add_child(policy)
	policy.toggled.connect(func(value: bool): var failure: String=editor.store.set_free_roam(value); if failure!="": editor._status(failure))
	var circuit:=CheckButton.new()
	circuit.text="순환 코스"
	circuit.button_pressed=source.settings.circuit
	properties.add_child(circuit)
	circuit.toggled.connect(func(value: bool): var next:=source.duplicate(true); next.settings.circuit=value; _commit(next))
	var routes:=OptionButton.new()
	for path: Dictionary in source.paths: routes.add_item(path.id)
	route_index=clampi(route_index,0,maxi(0,source.paths.size()-1))
	if routes.item_count>0: routes.select(route_index)
	routes.item_selected.connect(func(index: int): route_index=index; _properties())
	properties.add_child(routes)
	_button(properties,"대체 경로 추가",func(): var next:=source.duplicate(true); next.paths.append({"id":"대체 %d" % next.paths.size(),"pieces":[]}); route_index=next.paths.size()-1; _commit(next))
	route_input=LineEdit.new()
	route_input.placeholder_text="경로 조각 ID 순서 (쉼표 구분)"
	if not source.paths.is_empty(): route_input.text=", ".join(source.paths[route_index].pieces)
	properties.add_child(route_input)
	_button(properties,"경로 순서 적용",_set_route)
	_button(properties,"선택 조각을 경로 끝에 추가",func():
		if selected<0: return
		var next:=source.duplicate(true)
		if next.paths.is_empty(): next.paths=[{"id":"base","pieces":[]}]
		var id: String=next.instances[selected].id
		if not next.paths[route_index].pieces.has(id): next.paths[route_index].pieces.append(id)
		_commit(next))
	_button(properties,"선택 조각을 경로에서 제외",func():
		if selected<0 or source.paths.is_empty(): return
		var next:=source.duplicate(true)
		next.paths[route_index].pieces.erase(next.instances[selected].id)
		_commit(next))
	for n in source.checkpoints.size():
		var cp: Dictionary=source.checkpoints[n]
		_button(properties,"CP %d · %s / %d 삭제" % [n,cp.piece,int(cp.sample)],func(): var next:=source.duplicate(true); next.checkpoints.remove_at(n); _commit(next))
	for n in source.actions.size():
		_button(properties,"액션 %s 삭제" % source.actions[n].id,func(): var next:=source.duplicate(true); next.actions.remove_at(n); _commit(next))
	if selected<0: return
	var item: Dictionary=source.instances[selected]
	for j in 3: controls.append(_spin(properties,["X (m)","고도 (m)","Z (m)"][j],float(item.position_cm[j])/100.0))
	for j in 3: controls.append(_spin(properties,["기울기 X°","회전 Y°","기울기 Z°"][j],float(item.rotation_mdeg[j])/1000.0,-360.0,360.0,0.1))
	width=OptionButton.new()
	for entry: Dictionary in catalogue.entries:
		if entry.id!=item.preset: continue
		for w in entry.widths_cm:
			width.add_item("폭 %dm" % (float(w)/100.0),int(w))
			if int(w)==int(item.width_cm): width.select(width.item_count-1)
	properties.add_child(width)
	port_widths.append(_spin(properties,"입구 폭 (m)",float(item.entry_width_cm)/100.0,2.0,12.0))
	port_widths.append(_spin(properties,"출구 폭 (m)",float(item.exit_width_cm)/100.0,2.0,12.0))
	_button(properties,"위치·회전·폭 적용",apply_properties)
	if item.preset in ["free_curve","flight_curve"]:
		for n in item.control_points.size():
			for j in 3: controls.append(_spin(properties,"제어점 %d %s" % [n,["X","Y","Z"][j]],float(item.control_points[n][j])/100.0))
		_button(properties,"곡선 제어점 적용",apply_properties)
	target=OptionButton.new()
	for i in source.instances.size():
		if i!=selected: target.add_item(source.instances[i].id,i)
	properties.add_child(target)
	_button(properties,"대상 출구에 스냅·연결",snap_to_target)
	_button(properties,"선택 출구 → 대상 입구 자유 연결",connect_curve)
	var piece: Dictionary=editor.store.document.assembled_track.pieces[selected]
	sample_input=_spin(properties,"경로 지점",0,0,piece.path.size()-1,1)
	_button(properties,"출발 체크포인트",checkpoint.bind(true))
	_button(properties,"도착 / 공통 체크포인트",checkpoint.bind(false))
	action_height=_spin(properties,"점프 높이 (m)",2.0,0.5,10.0,0.1)
	landing_target=OptionButton.new()
	landing_target.add_item("연속 노면 점프",-2)
	for i in source.instances.size(): landing_target.add_item("착지 · "+source.instances[i].id,i)
	properties.add_child(landing_target)
	landing_sample=_spin(properties,"착지 지점",0,0,1024,1)
	for kind: String in ["jump_panel","acceleration_panel","boost_chain","air_ring"]:
		_button(properties,kind+" 배치",add_action.bind(kind))

func _commit(next: Dictionary) -> void:
	var failure: String=editor.store.edit_track(next)
	if failure!="": editor._status(failure)

func add_piece(preset: String) -> void:
	var next:=source.duplicate(true)
	var widths: Array=[]
	for entry: Dictionary in catalogue.entries:
		if entry.id==preset: widths=entry.widths_cm
	var w:=400 if widths.has(400) else int(widths[0])
	var id: String="p-"+Crypto.new().generate_random_bytes(4).hex_encode()
	var item: Dictionary={"id":id,"preset":preset,"position_cm":[0,0,0],"rotation_mdeg":[0,0,0],"width_cm":w,"entry_width_cm":w,"exit_width_cm":w,"control_points":[]}
	if preset in ["free_curve","flight_curve"]: item.control_points=[[0,0,0],[0,0,600],[600,0,1200],[1200,0,1200]]
	if selected>=0 and snap.button_pressed:
		var result: Dictionary=JSON.parse_string(editor.store.bridge.snap_track_instance(JSON.stringify(item),JSON.stringify(next.instances[selected])))
		if not result.ok: editor._status(result.error.message); return
		item=result.data
		next.connections.append({"from":next.instances[selected].id,"to":id})
	if next.paths.is_empty(): next.paths=[{"id":"base","pieces":[]}]
	next.paths[route_index].pieces.append(id)
	next.instances.append(item)
	selected=next.instances.size()-1
	_commit(next)

func apply_properties() -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var item: Dictionary=next.instances[selected]
	for j in 3: item.position_cm[j]=roundi(controls[j].value*100.0)
	for j in 3: item.rotation_mdeg[j]=roundi(controls[j+3].value*1000.0)
	item.width_cm=width.get_selected_id()
	item.entry_width_cm=roundi(port_widths[0].value*100.0)
	item.exit_width_cm=roundi(port_widths[1].value*100.0)
	for n in item.control_points.size():
		for j in 3: item.control_points[n][j]=roundi(controls[6+n*3+j].value*100.0)
	_commit(next)

func duplicate_piece() -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var item: Dictionary=next.instances[selected].duplicate(true)
	item.id="p-"+Crypto.new().generate_random_bytes(4).hex_encode()
	item.position_cm[0]+=int(item.width_cm)+200
	next.instances.append(item)
	selected=next.instances.size()-1
	_commit(next)

func delete_piece() -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var id: String=next.instances[selected].id
	next.instances.remove_at(selected)
	next.connections=next.connections.filter(func(c): return c.from!=id and c.to!=id)
	next.checkpoints=next.checkpoints.filter(func(c): return c.piece!=id)
	next.attachments=next.attachments.filter(func(c): return c.piece!=id)
	next.actions=next.actions.filter(func(c): return c.piece!=id and (c.landing==null or c.landing.piece!=id))
	for path: Dictionary in next.paths: path.pieces.erase(id)
	selected=-1
	_commit(next)

func snap_to_target() -> void:
	if selected<0 or target.item_count==0: return
	var next:=source.duplicate(true)
	var other: Dictionary=next.instances[target.get_selected_id()]
	var result: Dictionary=JSON.parse_string(editor.store.bridge.snap_track_instance(JSON.stringify(next.instances[selected]),JSON.stringify(other)))
	if not result.ok: editor._status(result.error.message); return
	next.instances[selected]=result.data
	next.connections.append({"from":other.id,"to":result.data.id})
	_commit(next)

func connect_curve() -> void:
	if selected<0 or target.item_count==0: return
	var next:=source.duplicate(true)
	var other:=target.get_selected_id()
	var a: Dictionary=editor.store.document.assembled_track.pieces[selected].path.back()
	var b: Dictionary=editor.store.document.assembled_track.pieces[other].path[0]
	var reach:=maxf(400.0,PREVIEW.point(a.position_cm).distance_to(PREVIEW.point(b.position_cm))*50.0)
	var p1: Array=[]
	var p2: Array=[]
	for j in 3:
		p1.append(roundi(float(a.position_cm[j])+float(a.forward[j])*reach/1000000.0))
		p2.append(roundi(float(b.position_cm[j])-float(b.forward[j])*reach/1000000.0))
	var id: String="c-"+Crypto.new().generate_random_bytes(4).hex_encode()
	next.instances.append({"id":id,"preset":"free_curve","position_cm":[0,0,0],"rotation_mdeg":[0,0,0],"width_cm":400,"entry_width_cm":int(a.lateral_cm)*2,"exit_width_cm":int(b.lateral_cm)*2,"control_points":[a.position_cm,p1,p2,b.position_cm]})
	next.connections=next.connections.filter(func(c): return not (c.from==next.instances[selected].id and c.to==next.instances[other].id))
	next.connections.append({"from":next.instances[selected].id,"to":id})
	next.connections.append({"from":id,"to":next.instances[other].id})
	if not next.paths.is_empty():
		var path: Array=next.paths[route_index].pieces
		var at:=path.find(next.instances[selected].id)
		path.insert(at+1,id)
		if not path.has(next.instances[other].id): path.insert(at+2,next.instances[other].id)
	selected=next.instances.size()-1
	_commit(next)

func _set_route() -> void:
	var next:=source.duplicate(true)
	if next.paths.is_empty(): next.paths=[{"id":"base","pieces":[]}]
	var ids: Array=[]
	for id: String in route_input.text.split(",",false): ids.append(id.strip_edges())
	next.paths[route_index].pieces=ids
	_commit(next)

func checkpoint(start: bool) -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	var cp: Dictionary={"piece":next.instances[selected].id,"sample":int(sample_input.value)}
	if start:
		if next.checkpoints.is_empty(): next.checkpoints.append(cp)
		else: next.checkpoints[0]=cp
	else: next.checkpoints.append(cp)
	_commit(next)

func add_action(kind: String) -> void:
	if selected<0: return
	var next:=source.duplicate(true)
	next.actions.append({"id":"a-"+Crypto.new().generate_random_bytes(4).hex_encode(),"kind":kind,"piece":next.instances[selected].id,"sample":int(sample_input.value),"height_cm":roundi(action_height.value*100.0),"landing":null if landing_target.get_selected_id()<0 else {"piece":next.instances[landing_target.get_selected_id()].id,"sample":int(landing_sample.value)}})
	_commit(next)

func _draw() -> void:
	if is_instance_valid(view): view.queue_free()
	var a: Dictionary=editor.store.document.get("assembled_track",{})
	if a.is_empty(): return
	view=PREVIEW.create(editor.store.document,selected)
	# View-only grid supplies orientation for an empty draft; it is not map geometry.
	var mesh:=ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	mesh.surface_set_color(Color("35434a"))
	for station in range(-50,51,5):
		mesh.surface_add_vertex(Vector3(station,-0.05,-50)); mesh.surface_add_vertex(Vector3(station,-0.05,50))
		mesh.surface_add_vertex(Vector3(-50,-0.05,station)); mesh.surface_add_vertex(Vector3(50,-0.05,station))
	mesh.surface_end()
	var grid:=MeshInstance3D.new()
	grid.mesh=mesh
	var material:=StandardMaterial3D.new()
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo=true
	grid.material_override=material
	view.add_child(grid)
	editor.preview_world.add_child(view)
	if editor.preview_camera.camera.position==Vector3.ZERO: editor.preview_camera.frame(Vector3.ZERO,80.0)

func input(event: InputEvent) -> bool:
	if not active: return false
	var camera: Camera3D=editor.preview_camera.camera
	if event is InputEventMouseButton and event.button_index==MOUSE_BUTTON_LEFT:
		if event.pressed:
			var nearest:=18.0
			var index:=-1
			var a: Dictionary=editor.store.document.get("assembled_track",{})
			for i in a.get("pieces",[]).size():
				for p: Dictionary in a.pieces[i].path:
					var point:=PREVIEW.point(p.position_cm)
					if camera.is_position_behind(point): continue
					var d:=camera.unproject_position(point).distance_to(event.position)
					if d<nearest: nearest=d; index=i
			selected=index
			if selected>=0:
				selection.select(selected)
				_properties()
				_draw()
				drag_source=source.duplicate(true)
				drag_epoch=editor.store.command_epoch
				drag_start=_plane_point(event.position,float(source.instances[selected].position_cm[1])*0.01)
			return true
		elif drag_start!=null:
			var end: Variant=_plane_point(event.position,float(drag_source.instances[selected].position_cm[1])*0.01)
			if end!=null and end.distance_to(drag_start)>0.01:
				var delta: Vector3=end-drag_start
				var item: Dictionary=drag_source.instances[selected]
				item.position_cm[0]+=roundi(delta.x*100.0)
				item.position_cm[2]-=roundi(delta.z*100.0)
				if snap.button_pressed:
					var current: Dictionary=JSON.parse_string(editor.store.bridge.track_instance(JSON.stringify(item)))
					var nearest:=3.0
					var found:=-1
					if current.ok:
						for i in drag_source.instances.size():
							if i==selected: continue
							var candidate: Dictionary=editor.store.document.assembled_track.pieces[i]
							var distance: float=PREVIEW.point(current.data.path[0].position_cm).distance_to(PREVIEW.point(candidate.path.back().position_cm))
							if distance<nearest: nearest=distance; found=i
					if found>=0:
						var result: Dictionary=JSON.parse_string(editor.store.bridge.snap_track_instance(JSON.stringify(item),JSON.stringify(drag_source.instances[found])))
						if result.ok:
							drag_source.instances[selected]=result.data
							var edge: Dictionary={"from":drag_source.instances[found].id,"to":item.id}
							if not drag_source.connections.has(edge): drag_source.connections.append(edge)
				var failure: String=editor.store.edit_track(drag_source,drag_epoch)
				if failure!="": editor._status(failure)
			drag_start=null
			return true
	return false

func _plane_point(point: Vector2, height: float) -> Variant:
	var camera: Camera3D=editor.preview_camera.camera
	return Plane(Vector3.UP,height).intersects_ray(camera.project_ray_origin(point),camera.project_ray_normal(point))

func add_obstacle(kind: String) -> void:
	if selected<0: editor._status("장애물을 배치할 도로를 선택하세요"); return
	var next:=source.duplicate(true)
	var piece: Dictionary=editor.store.document.assembled_track.pieces[selected]
	var station:=0.0
	for i in range(1,int(sample_input.value)+1): station+=PREVIEW.point(piece.path[i].position_cm).distance_to(PREVIEW.point(piece.path[i-1].position_cm))*100.0
	next.attachments.append({"kind":kind,"piece":source.instances[selected].id,"path":"main","station_cm":roundi(station),"side":1})
	_commit(next)

func frame_selection() -> void:
	if selected<0: editor.preview_camera.frame(Vector3.ZERO,80.0); return
	var piece: Dictionary=editor.store.document.assembled_track.pieces[selected]
	var center:=Vector3.ZERO
	for point: Dictionary in piece.path: center+=PREVIEW.point(point.position_cm)
	center/=piece.path.size()
	var radius:=8.0
	for point: Dictionary in piece.path: radius=maxf(radius,center.distance_to(PREVIEW.point(point.position_cm))*2.0)
	editor.preview_camera.frame(center,radius)
