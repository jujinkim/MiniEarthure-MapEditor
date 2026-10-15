extends Node
## Shared work plane and generation-bound 3D input. Geometry remains MapKit-owned.
const I18N := preload("./locale_text.gd")
const PREVIEW := preload("res://addons/mapkit/godot/track_authoring_preview.gd")
var editor: Control
var height := 0.0
var manual := false
var label: Label
var ground: CheckButton
var plane: MeshInstance3D
var session := -1
var drive_pick := false
var drive_point: Dictionary = {}

func build(owner: Control, parent: Control) -> void:
	editor = owner
	var row := HFlowContainer.new()
	parent.add_child(row)
	label = Label.new()
	row.add_child(label)
	ground = CheckButton.new()
	ground.text = I18N.t("Fit to ground")
	ground.button_pressed = true
	ground.toggled.connect(func(on: bool):
		manual = not on
		var placement: Node = editor.track_workbench.placement
		placement.manual_height = manual
		placement.height = height
		if placement.last_screen != null: placement.update_pointer(placement.last_screen)
		refresh())
	row.add_child(ground)
	for item in [["height_up", "Raise work height", "PageUp", 1.0], ["height_down", "Lower work height", "PageDown", -1.0], ["height_up_fine", "Raise work height precisely", "Shift+PageUp", 0.1], ["height_down_fine", "Lower work height precisely", "Shift+PageDown", -0.1]]:
		editor.commands.register("Edit", item[1], change_height.bind(item[3]), item[2], {"id":"edit."+item[0],"icon":"up" if item[3]>0 else "down"})
	editor.commands.register("Edit", "Confirm edit", confirm, "Enter", {"id":"edit.confirm", "menu":false,"icon":"check"})
	plane = MeshInstance3D.new()
	plane.name = "WorkPlane"
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for i in range(-20,21,2):
		for point in [Vector3(i,0,-20),Vector3(i,0,20),Vector3(-20,0,i),Vector3(20,0,i)]: mesh.surface_add_vertex(point)
	mesh.surface_end()
	plane.mesh = mesh
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.3,0.65,0.8,0.35)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	plane.material_override = material
	editor.preview_world.add_child(plane)
	editor.store.changed.connect(document_changed)
	refresh()

func document_changed() -> void:
	if session != editor.store.session_id:
		session = editor.store.session_id
		height = 0.0
		manual = false
		drive_point = {}
	drive_pick = false
	refresh()

func change_height(delta: float) -> void:
	var bench: Node = editor.track_workbench
	var placement: Node = bench.placement
	if placement.port_locked():
		editor._status(I18N.t("Connection height is locked. Use a slope piece or choose Free placement."))
		return
	if editor.tool_group == "course" and editor.course_tools.adjust_height(delta):
		height = float(editor.course_tools.gates[editor.course_tools.selected].position_cm[1])/100
	elif editor.tool_group == "roads" and bench.road_tools.selected != "":
		bench.road_tools.change_height(delta)
		height = float(bench.road_tools.design.control_points[bench.road_tools.point_index][1])/100.0
	elif editor.scenery != null and editor.scenery.adjust_height(delta):
		height = editor.scenery.current_height()
	else:
		if placement.tool != "": height = placement.height
		height = snappedf(height+delta,0.01)
		placement.height = height
		placement.manual_height = true
		if placement.moving_index >= 0: placement.moved = true
		if placement.last_screen != null: placement.update_pointer(placement.last_screen)
		elif placement.last_point != null: placement.preview_at(placement.last_point)
	manual = true
	refresh()

func refresh() -> void:
	if not is_instance_valid(label): return
	var placement: Node = editor.track_workbench.placement
	var locked: bool = placement.port_locked()
	var current: float = placement.height if placement.tool != "" else height
	if locked and not placement.candidate.is_empty(): current = float(placement.candidate.item.position_cm[1])/100.0
	label.text = I18N.t("Work height %.2f m · Horizontal plane") % current
	if locked: label.text += " · " + I18N.t("Port locked")
	ground.set_pressed_no_signal(not manual)
	ground.disabled = locked
	plane.visible = manual and not locked and editor.preview_dock.visible
	plane.position = Vector3(editor.preview_camera.target.x,current,editor.preview_camera.target.z)

func confirm() -> void:
	var placement: Node = editor.track_workbench.placement
	if placement.moving_index >= 0:
		placement.commit_move()
		placement.cancel()
	elif placement.tool != "": placement.commit()
	elif editor.track_workbench.road_tools.has_draft(): editor.track_workbench.road_tools.commit_direct()
	elif editor.scenery != null and not editor.scenery.candidate.is_empty(): editor.scenery.commit()
	elif editor.course_tools != null: editor.course_tools.confirm_move()
	refresh()

func surface(screen: Vector2, roads_only := false) -> Dictionary:
	var bench: Node = editor.track_workbench
	var road: Dictionary = bench.road_tools.raycast(screen,roads_only)
	var track: Dictionary = bench.placement._surface_at(screen)
	if int(track.get("piece",-1)) >= 0 and track.distance < road.distance:
		var sample: Dictionary = editor.store.track_pieces()[track.piece].path[track.sample]
		return {"point":PREVIEW.point(sample.position_cm),"surface":"assembled-road-%d" % track.piece,"piece":track.piece,"sample":track.sample,"distance":track.distance}
	if road.has("point"):
		return {"point":road.point,"surface":road.road if road.road != "" else "terrain","road":road.road,"sample":road.sample,"distance":road.distance}
	return {}

func pick_drive() -> void:
	editor._cancel_editing()
	drive_pick = true
	editor.drive_dialog.hide()
	editor._status(I18N.t("Click a driving surface to choose the test start."))

func input(event: InputEvent) -> bool:
	if not drive_pick or editor.busy or editor.store.editing_locked() or editor._popup_open(editor): return false
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var hit := surface(event.position)
		if hit.is_empty(): return true
		drive_point = {"position_cm":[roundi(hit.point.x*100),roundi(hit.point.y*100),roundi(-hit.point.z*100)],"surface_id":hit.surface}
		drive_pick = false
		editor._test_drive()
		return true
	return false

func cancel() -> void:
	drive_pick = false
	refresh()
