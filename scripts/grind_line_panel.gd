extends Window
const I18N := preload("./locale_text.gd")
## Independent line authoring uses the same cancellable source transaction as roads.
var bench: Node
var list: ItemList
var points: TextEdit
var identifier: LineEdit
var width: SpinBox
var up: LineEdit
var start_links: LineEdit
var end_links: LineEdit
var status: Label
var selected := -1

func open(owner: Node) -> void:
	bench=owner
	title=I18N.t("Grind Lines")
	size=Vector2i(640,600)
	var box:=VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.offset_left=16; box.offset_right=-16; box.offset_top=16; box.offset_bottom=-16
	add_child(box)
	list=ItemList.new()
	list.custom_minimum_size.y=110
	box.add_child(list)
	list.item_selected.connect(select)
	var tools:=HBoxContainer.new(); box.add_child(tools)
	_button(tools,"Add air line",add_line.bind(false))
	_button(tools,"Add on selected fence",add_line.bind(true))
	_button(tools,"Delete",remove_line)
	identifier=_field(box,"Line ID (up to 32 UTF-8 bytes)")
	_label(box,"Path points in cm · one x, y, z per row · 2 points: straight; 4, 7, …: cubic curve")
	points=TextEdit.new(); points.custom_minimum_size.y=150; points.size_flags_vertical=Control.SIZE_EXPAND_FILL; box.add_child(points)
	up=_field(box,"Up frame (x, y, z; unit vector)")
	_label(box,"Capture width (cm)")
	width=SpinBox.new(); width.min_value=5; width.max_value=100; width.value=30; box.add_child(width)
	start_links=_field(box,"Start connections · comma-separated line ID:start or line ID:end")
	end_links=_field(box,"End connections · comma-separated line ID:start or line ID:end")
	_button(box,"Apply line",apply_line)
	status=Label.new(); status.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART; box.add_child(status)
	close_requested.connect(queue_free)
	bench.editor.store.track_edit_finished.connect(_finished)
	refresh()
	popup_centered()

func _label(parent: Node,text: String) -> void:
	var label:=Label.new(); label.text=text; parent.add_child(label)
func _field(parent: Node,text: String) -> LineEdit:
	_label(parent,text)
	var field:=LineEdit.new(); parent.add_child(field); return field
func _button(parent: Node,text: String,action: Callable) -> void:
	var button:=Button.new();button.text=text;button.pressed.connect(action);parent.add_child(button)
func refresh() -> void:
	list.clear()
	for line: Dictionary in bench.source.get("grind_lines",[]): list.add_item(line.id)
	if list.item_count>0: select(clampi(selected,0,list.item_count-1))
	else: selected=-1
func _finished(error: String) -> void:
	status.text=I18N.diagnostic(error) if error!="" else I18N.t("Line saved · Undo/Redo and package save retain the source.")
	if error=="": refresh.call_deferred()
func select(index: int) -> void:
	selected=index; list.select(index)
	var line: Dictionary=bench.source.grind_lines[index]
	identifier.text=line.id
	var rows:=PackedStringArray()
	for p: Array in line.control_points: rows.append("%d, %d, %d" % p)
	points.text="\n".join(rows)
	up.text="%.6f, %.6f, %.6f" % [line.up[0]*0.000001,line.up[1]*0.000001,line.up[2]*0.000001]
	width.value=line.capture_width_cm
	for pair in [[start_links,line.start_connections],[end_links,line.end_connections]]:
		var links:=PackedStringArray()
		for link: Dictionary in pair[1]: links.append(link.line+(":end" if link.end else ":start"))
		pair[0].text=", ".join(links)
func add_line(fence: bool) -> void:
	var next: Dictionary=bench.source.duplicate(true)
	var lines: Array=next.get_or_add("grind_lines",[])
	var cp: Array=[[0,100,0],[0,100,800]];var normal: Array=[0,1000000,0]
	if fence:
		if bench.selected<0: status.text=I18N.t("Select a road piece before placing a fence line.");return
		var path: Array=bench.editor.store.document.assembled_track.pieces[bench.selected].path
		if path.is_empty() or path.any(func(sample: Dictionary):return sample.mode in ["flight","loop","cylinder","halfpipe"]):
			status.text=I18N.t("This piece has no ordinary side fence.");return
		cp=fence_points(path);normal=path[0].normal
	var suffix:=lines.size()+1
	while lines.any(func(l: Dictionary):return l.id=="grind-%d"%suffix): suffix+=1
	lines.append({"id":"grind-%d"%suffix,"control_points":cp,"up":normal,"capture_width_cm":30,"start_connections":[],"end_connections":[]})
	selected=lines.size()-1
	bench._commit(next)
func remove_line() -> void:
	if selected<0 or selected>=bench.source.get("grind_lines",[]).size():return
	var next: Dictionary=bench.source.duplicate(true)
	var id: String=next.grind_lines[selected].id
	next.grind_lines.remove_at(selected)
	for line: Dictionary in next.grind_lines:
		for key in ["start_connections","end_connections"]: line[key]=line[key].filter(func(link: Dictionary):return link.line!=id)
	bench._commit(next)
func _vector(text: String) -> Array:
	var fields:=text.strip_edges().split(",")
	if fields.size()!=3:return []
	var result:=[]
	for field: String in fields:
		if not field.strip_edges().is_valid_float() or not is_finite(float(field)):return []
		result.append(float(field))
	return result
func _links(text: String) -> Variant:
	var result:=[]
	if text.strip_edges()=="":return result
	for field: String in text.split(","):
		var parts:=field.strip_edges().rsplit(":",true,1)
		if parts.size()!=2 or parts[1] not in ["start","end"]:return null
		result.append({"line":parts[0],"end":parts[1]=="end"})
	return result
func apply_line() -> void:
	if selected<0 or selected>=bench.source.get("grind_lines",[]).size():return
	var cp:=[]
	for row: String in points.text.split("\n",false):
		var v:=_vector(row)
		if v.is_empty():status.text=I18N.t("Each path point needs three finite coordinates.");return
		cp.append([roundi(v[0]),roundi(v[1]),roundi(v[2])])
	var n:=_vector(up.text)
	var starts: Variant=_links(start_links.text);var ends: Variant=_links(end_links.text)
	if n.is_empty() or starts==null or ends==null:status.text=I18N.t("Check the up vector and endpoint connections.");return
	var next: Dictionary=bench.source.duplicate(true)
	var old: String=next.grind_lines[selected].id
	next.grind_lines[selected]={"id":identifier.text.strip_edges(),"control_points":cp,"up":[roundi(n[0]*1e6),roundi(n[1]*1e6),roundi(n[2]*1e6)],"capture_width_cm":int(width.value),"start_connections":starts,"end_connections":ends}
	for line: Dictionary in next.grind_lines:
		for key in ["start_connections","end_connections"]:
			for link: Dictionary in line[key]:
				if link.line==old:link.line=identifier.text.strip_edges()
	bench._commit(next)

static func fence_points(path: Array) -> Array:
	var points: Array[Vector3]=[]
	for s: Dictionary in path:
		var n:=Vector3(s.normal[0],s.normal[1],s.normal[2])*0.000001
		var f:=Vector3(s.forward[0],s.forward[1],s.forward[2])*0.000001
		points.append(Vector3(s.position_cm[0],s.position_cm[1],s.position_cm[2])+n*61.0+n.cross(f)*float(s.lateral_cm))
	var encode:=func(v: Vector3):return [roundi(v.x),roundi(v.y),roundi(v.z)]
	if points.size()==2:return [encode.call(points[0]),encode.call(points[1])]
	var spans:=mini(16,points.size()-1)
	var result: Array=[encode.call(points[0])]
	for i in spans:
		var a:=roundi(float(i)*(points.size()-1)/spans)
		var b:=roundi(float(i+1)*(points.size()-1)/spans)
		var tangent_a: Vector3=(points[mini(a+1,points.size()-1)]-points[maxi(0,a-1)]).normalized()
		var tangent_b: Vector3=(points[mini(b+1,points.size()-1)]-points[maxi(0,b-1)]).normalized()
		var arm:=points[a].distance_to(points[b])/3.0
		result.append(encode.call(points[a]+tangent_a*arm))
		result.append(encode.call(points[b]-tangent_b*arm))
		result.append(encode.call(points[b]))
	return result
