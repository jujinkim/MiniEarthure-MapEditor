extends AcceptDialog
## Shared new-region / semantic infill workflow. Preview and apply are separate.
const JOB := preload("./generation_native_job.gd")
const I18N := preload("./locale_text.gd")
const IDS := ["village","neon-harbor","deep-forest","red-canyon","snow-mountain","machine-factory","sky-park"]
const NAMES := ["Village Driving Park","Neon Harbor","Deep Forest","Red Canyon","Snow Mountain","Machine Factory","Sky Amusement Park"]
const SIZES := [Vector2i(1120,960),Vector2i(1920,1280),Vector2i(1760,1760),Vector2i(2400,1200),Vector2i(1600,2080),Vector2i(1440,1440),Vector2i(1920,1600)]
var editor: Control
var job: RefCounted
var generation_mode := "new"
var themes: OptionButton
var seed: SpinBox
var density: SpinBox
var profile: OptionButton
var coordinates: Array[SpinBox] = []
var message: RichTextLabel
var preview: Control
var destination: LineEdit
var generate_button: Button
var apply_button: Button
var cancel_button: Button
var submitted_settings := ""

class PlanPreview extends Control:
	var document := {}
	var composition := {}
	var diagnostics: Array = []
	var layers := {"districts":true,"roads":true,"parcels":true,"protected":true,"diagnostics":true}
	var project_point: Callable
	func _rings(boundaries: Array, project: Callable, color: Color, filled: bool = false) -> void:
		for boundary: Dictionary in boundaries:
			var points := PackedVector2Array()
			for p: Array in boundary.polygon: points.append(project.call(p))
			if points.size()<3: continue
			if filled: draw_colored_polygon(points,Color(color,color.a*.22))
			points.append(points[0]);draw_polyline(points,color,1,true)
			for hole: Array in boundary.get("holes",[]):
				var ring := PackedVector2Array()
				for p: Array in hole: ring.append(project.call(p))
				if ring.size()>2: ring.append(ring[0]);draw_polyline(ring,color,1,true)
	func _get_tooltip(at_position: Vector2) -> String:
		if not project_point.is_valid(): return ""
		for issue: Dictionary in diagnostics:
			if issue.has("position_cm") and at_position.distance_to(project_point.call(issue.position_cm))<12:
				return str(issue.get("district",issue.get("id","")))+"\n"+I18N.diagnostic(str(issue.get("error",issue.get("warning",""))))
		return ""
	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO,size),Color("202a25"))
		if document.is_empty(): return
		var bounds: Dictionary = document.bounds
		var origin := Vector2(bounds.min[0],bounds.min[1])
		var extent := Vector2(bounds.max[0],bounds.max[1])-origin
		var scale := minf((size.x-16)/extent.x,(size.y-16)/extent.y)
		var project := func(p): return Vector2(8,8)+(Vector2(p[0],p[1])-origin)*scale
		project_point=project
		if layers.districts:
			for district: Dictionary in composition.get("districts",[]):
				var colors := {"residential":Color("76bc82"),"commercial":Color("e6be6c"),"industrial":Color("a5a0d0"),"recreation_ground":Color("ef98b1"),"farmland":Color("ada95e")}
				var color: Color=colors.get(district.landuse,Color("659b7d"))
				_rings(district.boundaries,project,color,true)
				var anchor: Array=district.anchor
				var caption: String=str(district.id)+" · %d–%d%%"%[roundi(district.density[0]*100),roundi(district.density[1]*100)]
				draw_string(ThemeDB.fallback_font,project.call([anchor[0]*100,anchor[1]*100]),caption,HORIZONTAL_ALIGNMENT_LEFT,-1,11,color)
		for water: Dictionary in document.get("water_bodies",[]):
			var points := PackedVector2Array()
			for p: Array in water.polygon: points.append(project.call(p))
			if points.size()>2: draw_colored_polygon(points,Color("387eaa"))
		for road: Dictionary in document.get("roads",[]):
			if not layers.roads: continue
			var points := PackedVector2Array()
			for p: Array in road.points: points.append(project.call([p[0],p[2]]))
			var role: String=composition.get("road_hierarchy",{}).get(road.id,"")
			var color := Color("f5cc69") if role in ["arterial","main"] else Color("8dbdd0") if role in ["connector","access","promenade"] else Color("acada2")
			if points.size()>1: draw_polyline(points,color,maxf(1,float(road.widths_cm[0])*scale),true)
		if layers.parcels:
			for site: Dictionary in composition.get("sites",[]):
				_rings(site.get("boundaries",[]),project,Color("d5ba88"))
				_rings(site.get("entrances",[]),project,Color("f3a951"),true)
		if layers.protected:
			for region: Dictionary in composition.get("protected",[]):
				_rings(region.boundaries,project,Color("e77686"),true)
		for placement: Dictionary in document.get("placements",[]):
			var p: Array = placement.position
			var color := Color("75a560") if "canopy" in placement.asset_id or "pine" in placement.asset_id or "grove" in placement.asset_id else Color("e0b36b")
			draw_circle(project.call([p[0],p[2]]),1.8,color)
		if layers.diagnostics:
			for issue: Dictionary in diagnostics:
				if not issue.has("position_cm") or not issue.has("error"): continue
				var p: Vector2=project.call(issue.position_cm)
				draw_circle(p,5,Color("f16262"),false,2,true)
				draw_line(p-Vector2(3,3),p+Vector2(3,3),Color("f16262"),2,true)

func build(owner: Control) -> void:
	editor = owner
	title = I18N.t("Environment generation")
	min_size = Vector2i(760,700)
	get_ok_button().text = I18N.t("Close")
	var column := VBoxContainer.new()
	add_child(column)
	var row := HBoxContainer.new()
	column.add_child(row)
	themes = OptionButton.new()
	for name: String in NAMES: themes.add_item(I18N.t(name))
	row.add_child(themes)
	seed = _number(row,"Seed",9026,0,9007199254740990)
	density = _number(row,"Density",1,.1,2,.1)
	profile = OptionButton.new()
	for pixels: int in [128,256,512]: profile.add_item(str(pixels)+" px",pixels)
	profile.select(1)
	row.add_child(profile)
	var area := HBoxContainer.new()
	column.add_child(area)
	for label: String in ["Min X (m)","Min Y (m)","Max X (m)","Max Y (m)"]:
		coordinates.append(_number(area,label,0,-100000,100000))
	destination = LineEdit.new()
	destination.placeholder_text = I18N.t("New project directory (absolute path)")
	column.add_child(destination)
	preview = PlanPreview.new()
	preview.custom_minimum_size = Vector2(700,300)
	column.add_child(preview)
	var layers := HFlowContainer.new()
	column.add_child(layers)
	for entry: Array in [["districts","Districts and density"],["roads","Road hierarchy"],["parcels","Parcels and entrances"],["protected","Protected areas"],["diagnostics","Diagnostics"]]:
		var toggle := CheckButton.new();toggle.text=I18N.t(entry[1]);toggle.button_pressed=true
		var key: String=entry[0]
		toggle.toggled.connect(func(enabled): preview.layers[key]=enabled;preview.queue_redraw())
		layers.add_child(toggle)
	message = RichTextLabel.new()
	message.custom_minimum_size = Vector2(700,130)
	column.add_child(message)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	generate_button = _button(actions,"Preview composition",generate_preview)
	apply_button = _button(actions,"Apply environment",apply_result)
	apply_button.disabled = true
	cancel_button = _button(actions,"Cancel generation",discard)
	themes.item_selected.connect(func(_index):
		if generation_mode == "new": _default_size()
		invalidate())
	for control: SpinBox in coordinates+[seed,density]: control.value_changed.connect(func(_value): invalidate())
	profile.item_selected.connect(func(_index): invalidate())
	visibility_changed.connect(func():
		if not visible: discard())

func _number(parent: Node, label: String, value: float, minimum: float, maximum: float, step: float = 1) -> SpinBox:
	var column := VBoxContainer.new(); parent.add_child(column)
	var caption := Label.new(); caption.text = I18N.t(label); column.add_child(caption)
	var number := SpinBox.new(); number.min_value=minimum; number.max_value=maximum; number.step=step; number.value=value
	number.custom_minimum_size.x=145; column.add_child(number)
	return number

func _button(parent: Node, label: String, callback: Callable) -> Button:
	var button := Button.new(); button.text=I18N.t(label); button.pressed.connect(callback); parent.add_child(button)
	return button

func open_mode(value: String) -> void:
	if editor.store.editing_locked(): return
	discard()
	generation_mode=value
	destination.visible=generation_mode=="new"
	if generation_mode=="new": _default_size()
	else:
		var bounds: Dictionary=editor.store.document.bounds
		var low := Vector2(bounds.min[0],bounds.min[1])
		var high := Vector2(bounds.max[0],bounds.max[1])
		var selected_points: Array[Vector2]=[]
		for entry: Dictionary in editor.canvas.EDIT.entries(editor.store.document):
			if entry.key in editor.canvas.selected: selected_points.append_array(editor.canvas.EDIT.points(entry.field,entry.record))
		if not selected_points.is_empty():
			var a: Vector2=selected_points[0];var b: Vector2=a
			for p: Vector2 in selected_points: a=a.min(p);b=b.max(p)
			low=low.max(a-Vector2(3200,3200));high=high.min(b+Vector2(3200,3200))
		for i in range(4): coordinates[i].set_value_no_signal([low.x,low.y,high.x,high.y][i]/100.0)
	message.text=I18N.t("Choose theme, seed and bounds, then preview. Generated scenery is an estimated game environment. Existing and manually edited objects are protected.")
	preview.document={};preview.composition={};preview.diagnostics=[];preview.queue_redraw()
	popup_centered()

func _default_size() -> void:
	var size_m: Vector2i=SIZES[themes.selected]
	for i in range(4): coordinates[i].set_value_no_signal([0,0,size_m.x,size_m.y][i])

func settings() -> Dictionary:
	var bounds := []
	for coordinate: SpinBox in coordinates: bounds.append(roundi(coordinate.value*100))
	return {"mode":generation_mode,"theme":IDS[themes.selected],"seed":int(seed.value),"bounds_cm":bounds,"density":density.value,"texture_profile":profile.get_selected_id()}

func invalidate() -> void:
	apply_button.disabled=true
	if job != null: job.cancel()

func generate_preview() -> void:
	discard()
	job=JOB.new()
	submitted_settings=JSON.stringify(settings())
	var failure: String=job.start_generation(editor.store,settings(),editor.import_python.text.strip_edges())
	if failure != "": message.text=I18N.diagnostic(failure);discard();return
	generate_button.disabled=true
	message.text=I18N.t("Generating terrain, districts and scenery…")

func _process(_delta: float) -> void:
	if job==null: return
	if not job.matches(editor.store) or JSON.stringify(settings()) != submitted_settings: job.cancel()
	if not job.done:
		job.poll()
		return
	generate_button.disabled=false
	if job.cancelled:
		message.text=I18N.t("Generation cancelled. Current document retained.")
		discard();return
	if not job.result.get("ok",false) or job.bundle.is_empty():
		message.text=I18N.diagnostic(str(job.result.get("error",job.result)))
		discard();return
	if job.has_meta("displayed"): return
	job.set_meta("displayed",true)
	var report: Dictionary=job.bundle.report.diagnostics
	var candidate: Dictionary=job.bundle.snapshot.get("document",job._prepared.get("candidate",{}))
	preview.document=candidate;preview.composition=report.get("composition",{});preview.diagnostics=report.get("stages",[]);preview.queue_redraw()
	message.text=I18N.t("Preview ready")+"\n"+I18N.t("Facilities")+": "+str(report.facilities)+" · "+I18N.t("Objects")+": "+str(report.counts.placements)+"\n"+I18N.t("Undo size")+": %.2f MiB"%(float(report.history_bytes)/1048576.0)
	var metrics: Dictionary=report.get("metrics",{})
	if not metrics.is_empty(): message.text+="\n"+I18N.t("Core %.1f%% · Natural %.1f%% · Junctions %d")%[float(metrics.core_land_fraction)*100,float(metrics.natural_land_fraction)*100,int(metrics.road_graph.junctions)]
	for error: String in report.errors: message.text+="\n"+I18N.diagnostic(error)
	if generation_mode=="fill": message.text+="\n"+I18N.t("Apply is one Undo. Reduce the area if it exceeds 16 MiB.")
	apply_button.disabled=not report.errors.is_empty()

func apply_result() -> void:
	if job==null or JSON.stringify(settings())!=submitted_settings: return
	var target := destination.text.strip_edges()
	var failure: String=job.commit(editor.store,target)
	if failure!="": message.text=I18N.diagnostic(failure);return
	discard()
	hide()
	if generation_mode=="new": editor._request_document_action("open",target)
	else: editor._status(I18N.t("Environment applied. Undo restores the previous area."))

func discard() -> void:
	apply_button.disabled=true
	generate_button.disabled=false
	if job==null: return
	job.shutdown()
	job.cleanup()
	job=null

func _exit_tree() -> void: discard()
