extends SceneTree
## City parts: strict v1 files, built-ins placed with free rotation in one
## MapKit-validated Undo, 1:D scaling, replace-mode cuts, mouth joining (road
## ends and road splits), capture back to a part, the user library and the
## city-mode Parts group.
const SCRATCH := preload("res://tests/validator_scratch.gd")
const STORE := preload("res://scripts/document_store.gd")
const PARTS := preload("res://scripts/city_parts.gd")
const AUTHOR := preload("res://scripts/authoring_tools.gd")
const CANVAS := preload("res://scripts/map_canvas.gd")
const UNITS := preload("res://scripts/import_units.gd")
var scratch: String = SCRATCH.fresh(get_script().resource_path.get_file().get_basename())
var failures: Array[String] = []
var store: RefCounted
var canvas: Control
var author: RefCounted

func _finalize() -> void: SCRATCH.remove(scratch)

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error(message)

func _initialize() -> void: run.call_deferred()

func fresh(denominator := 1) -> void:
	store.new_track(true)
	if denominator == 1: return
	var notice := JSON.stringify({"adapter": "osm-extract-v1", "authored_units": {"metres_per_unit": 1, "source_denominator": denominator, "profile": UNITS.profile(denominator)}})
	var credit := {"source": "Synthetic OSM#layer", "license": "ODbL-1.0", "notice": notice}
	check(store.apply_command("Credit", [{"field": "attributions", "id": store.record_id("attributions", credit), "before": null, "after": credit}]) == "", "fixture 1:%d credit" % denominator)

func road(id: String, a: Array, b: Array, middle: Array = []) -> String:
	var patches: Array = []
	for end: Array in [[id + "-a", a], [id + "-b", b]]:
		patches.append({"field": "nodes", "id": end[0], "before": null, "after": {"id": end[0], "position": end[1], "level": 0}})
	var points: Array = [a] + middle + [b]
	var widths: Array = []
	var surfaces: Array = []
	for _i in points.size() - 1:
		widths.append(700)
		surfaces.append("asphalt")
	patches.append({"field": "roads", "id": id, "before": null, "after": {"id": id, "from": id + "-a", "to": id + "-b", "points": points, "widths_cm": widths, "surfaces": surfaces, "kind": "ground", "clearance_cm": null, "sidewalk_cm": null}})
	return author.apply("Fixture road", patches, true)

func place(part: Dictionary, at: Vector2, angle: float, replace := false, instance := "a1b2c3d4") -> Dictionary:
	var plan := PARTS.plan_place(store.document, part, at, angle, {"replace": replace, "instance": instance, "ground_cm": 0})
	if plan.has("error"): return plan
	var failure: String = author.apply("Place city part", plan.patches, true)
	if failure != "": return {"error": failure}
	return plan

func record(field: String, id: String) -> Dictionary:
	for item: Dictionary in store.document.get(field, []):
		if str(item.id) == id: return PARTS._ints(item)
	return {}

func run() -> void:
	store = STORE.new()
	canvas = CANVAS.new()
	canvas.store = store
	author = AUTHOR.new()
	author.configure(store, canvas)
	var listed := PARTS.list(PARTS.BUILTIN_DIR)
	check(listed.errors.is_empty() and listed.parts.size() == 9, "built-in parts load: %s" % str(listed.errors))
	var builtins := {}
	for entry: Dictionary in listed.parts:
		builtins[entry.part.id] = entry.part
		check(entry.part.license == "MIT" and entry.part.attributions.is_empty(), "built-in %s is in-house MIT" % entry.part.id)
	# Every built-in places at map scales 1:1–1:8 and free angles as one
	# validated Undo and undoes cleanly.
	for id: String in builtins:
		for denominator in [1, 3, 5, 8]:
			for angle in [0.0, 15.0, 45.0, 60.0]:
				fresh(denominator)
				var empty: String = store._signature(store.document)
				var undo_before: int = store.undo_stack.size()
				var plan := place(builtins[id], Vector2(51200, 51200), angle)
				check(not plan.has("error"), "place %s at 1:%d %.1f°: %s" % [id, denominator, angle, plan.get("error", "")])
				if plan.has("error"): continue
				check(store.undo_stack.size() == undo_before + 1 and not plan.selection.is_empty(), "%s is one Undo with a selection" % id)
				for key: String in plan.selection: check(key.get_slice("/", 1).begins_with("part-a1b2c3d4-"), "%s namespaced: %s" % [id, key])
				check(store.undo() == "" and store._signature(store.document) == empty, "%s undo restores the map" % id)
	# Free rotation: placements turn by the angle, gable roofs flatten off right angles.
	fresh()
	var plan := place(builtins["low-rise-block"], Vector2(51200, 51200), 37.5)
	check(record("buildings", "part-a1b2c3d4-house-1").get("roof") == "flat", "rotated gable becomes flat")
	fresh()
	plan = place(builtins["low-rise-block"], Vector2(51200, 51200), 90.0)
	check(record("buildings", "part-a1b2c3d4-house-1").get("roof") == "gable", "right-angle gable stays gable")
	fresh()
	plan = place(builtins["crossroads"], Vector2(51200, 51200), 100.0)
	var light := record("placements", "part-a1b2c3d4-light-2")
	check(int(light.get("quarter_turns", -1)) == 2 and int(light.get("yaw_offset_mdeg", 0)) == 10000, "placement yaw follows the part: %s" % str(light))
	var east := record("nodes", "part-a1b2c3d4-east")
	var expected := Vector2(3000, 0).rotated(deg_to_rad(100.0)) + Vector2(51200, 51200)
	check(not east.is_empty() and east.position[0] == roundi(expected.x) and east.position[2] == roundi(expected.y), "mouth node rotates counter-clockwise: %s" % str(east))
	# Replace mode cuts a crossing street at the footprint and joins both mouths to the cut ends.
	fresh()
	check(road("street", [21200, 0, 51200], [81200, 0, 51200]) == "", "fixture street")
	plan = place(builtins["crossroads"], Vector2(51200, 51200), 0.0, true)
	check(not plan.has("error") and int(plan.get("joined", 0)) == 2, "replace joins the cut street: %s" % str(plan.get("error", plan.get("joined"))))
	var street := record("roads", "street")
	check(not street.is_empty() and street.points[-1] == [48200, 0, 51200], "street cut at the footprint edge: %s" % str(street.get("points")))
	var west := record("roads", "part-a1b2c3d4-road-west")
	check(west.get("to") == street.get("to") and str(street.get("to")).begins_with("part-a1b2c3d4-cut-node-"), "west mouth joined the cut end")
	check(record("nodes", "part-a1b2c3d4-west").is_empty() and record("nodes", "street-b").get("id") == "street-b", "joined mouth node replaced; far end kept")
	check(store.undo_stack.size() == 2 and store.undo() == "" and record("roads", "street").points.size() == 2, "replace is one Undo")
	# Grade-separated roads pass over the part whole and are never join targets.
	fresh()
	check(road("street", [21200, 0, 51200], [81200, 0, 51200]) == "", "fixture street")
	var tunnel_patches: Array = []
	for end: Array in [["tunnel-a", [41200, -1200, 51200]], ["tunnel-b", [61200, -1200, 51200]]]:
		tunnel_patches.append({"field": "nodes", "id": end[0], "before": null, "after": {"id": end[0], "position": end[1], "level": -1}})
	tunnel_patches.append({"field": "roads", "id": "tunnel", "before": null, "after": {"id": "tunnel", "from": "tunnel-a", "to": "tunnel-b", "points": [[41200, -1200, 51200], [61200, -1200, 51200]], "widths_cm": [700], "surfaces": ["asphalt"], "kind": "tunnel", "clearance_cm": 500, "sidewalk_cm": null}})
	var tunnel_failure: String = author.apply("Fixture tunnel", tunnel_patches, true)
	if tunnel_failure == "":
		plan = place(builtins["crossroads"], Vector2(51200, 51200), 0.0, true)
		check(not plan.has("error") and record("roads", "tunnel").points.size() == 2 and str(record("roads", "part-a1b2c3d4-road-east").get("to")).begins_with("part-a1b2c3d4-cut-node-"), "tunnel kept whole, mouths join the street: %s" % str(plan.get("error", "")))
	else:
		print("tunnel fixture skipped by MapKit: ", tunnel_failure)
	# Replace keeps zone exclusions outside the footprint, clipped at its edge.
	fresh()
	var forest := {"id": "forest", "polygon": [[30000, 30000], [72000, 30000], [72000, 72000], [30000, 72000]], "kind": "forest", "spacing_cm": 800, "density_per_mille": 500, "exclusions": [[[56000, 49000], [60000, 49000], [60000, 53000], [56000, 53000]], [[50000, 44000], [54000, 44000], [54000, 48000], [50000, 48000]]]}
	check(author.apply("Fixture forest", [{"field": "zones", "id": "forest", "before": null, "after": forest}]) == "", "fixture forest")
	plan = place(builtins["plaza"], Vector2(51200, 51200), 0.0, true)
	var excluded := 0.0
	for zone: Dictionary in store.document.zones:
		for ring: Array in zone.get("exclusions", []): excluded += absf(PARTS._area(PARTS._packed(ring)))
	check(not plan.has("error") and is_equal_approx(excluded, 4000.0 * 4000.0 + 4000.0 * 3200.0), "exclusions kept and clipped: %f %s" % [excluded, str(plan.get("error", ""))])
	# Without replace, a mouth joins a nearby free end with a short connector.
	fresh()
	check(road("spur", [54500, 0, 51200], [70000, 0, 51200]) == "", "fixture spur")
	plan = place(builtins["t-junction"], Vector2(51200, 51200), 0.0)
	var joined_east := record("roads", "part-a1b2c3d4-road-east")
	check(int(plan.get("joined", 0)) == 1 and joined_east.get("to") == "spur-a" and joined_east.points[-1] == [54500, 0, 51200] and joined_east.points.size() == 3, "free end join: %s" % str(joined_east.get("points")))
	# ...or splits a passing road when no end is near.
	fresh()
	check(road("avenue", [21200, 0, 47700], [81200, 0, 47700]) == "", "fixture avenue")
	plan = place(builtins["t-junction"], Vector2(51200, 51200), 0.0)
	var head := record("roads", "avenue")
	var tail := record("roads", "part-a1b2c3d4-join-road-1")
	var south := record("roads", "part-a1b2c3d4-road-south")
	check(int(plan.get("joined", 0)) == 1 and head.get("to") == "part-a1b2c3d4-join-node-1" and tail.get("from") == head.get("to") and south.get("to") == head.get("to"), "road split join: %s / %s" % [str(head.get("points")), str(south.get("points"))])
	# Real-data maps at 1:3 divide the real-scale part by three.
	fresh()
	var notice := JSON.stringify({"adapter": "osm-extract-v1", "authored_units": {"metres_per_unit": 1, "source_denominator": 3, "profile": UNITS.profile(3)}})
	var credit := {"source": "Synthetic OSM#layer", "license": "ODbL-1.0", "notice": notice}
	check(store.apply_command("Credit", [{"field": "attributions", "id": store.record_id("attributions", credit), "before": null, "after": credit}]) == "", "fixture 1:3 credit")
	plan = place(builtins["crossroads"], Vector2(51200, 51200), 0.0)
	var arm := record("roads", "part-a1b2c3d4-road-east")
	check(not plan.has("error") and arm.get("widths_cm") == [233] and arm.points[-1] == [52200, 0, 51200], "1:3 scale: %s" % str(arm))
	# Capture: selected records become a real-scale part with mouths and inherited credits.
	var captured := PARTS.capture(store.document, plan.selection, "My crossing")
	check(captured.has("part"), "capture: %s" % captured.get("error", ""))
	if captured.has("part"):
		var part: Dictionary = captured.part
		check(part.mouths.size() == 4 and part.attributions == [{"source": "Synthetic OSM", "license": "ODbL-1.0", "notice": ""}] and part.license == PARTS.USER_LICENSE, "captured mouths and credits: %s" % str(part.mouths))
		var captured_road: Dictionary = part.records.roads[0]
		check(captured_road.widths_cm == [699] and absi(int(captured_road.points[-1][0]) - int(captured_road.points[0][0])) + absi(int(captured_road.points[-1][2]) - int(captured_road.points[0][2])) == 3000, "captured back to real scale: %s" % str(captured_road))
		PARTS.user_dir_override = scratch.path_join("parts")
		var saved := PARTS.save_user(part)
		check(saved.has("path") and PARTS.save_user(part).has("error"), "save once, never overwrite: %s" % str(saved))
		check(PARTS.list(PARTS.user_dir()).parts.size() == 1, "user library lists the part")
		if saved.has("path"):
			check(PARTS.rename_user(saved.path, "Renamed crossing") == "" and PARTS.read(saved.path).part.name == "Renamed crossing", "rename keeps the file")
			fresh()
			plan = place(PARTS.read(saved.path).part, Vector2(51200, 51200), 45.0, false, "feedbeef")
			check(not plan.has("error") and store.document.attributions.size() == 1 and store.document.attributions[0].source == "Synthetic OSM" and UNITS.osm_scale(store.document).denominator == 0, "placing a user part merges its credits: %s" % str(plan.get("error", "")))
			check(PARTS.delete_user(saved.path) == "" and PARTS.list(PARTS.user_dir()).parts.is_empty(), "delete removes the part")
		PARTS.user_dir_override = ""
	check(PARTS.capture(store.document, [], "x").has("error"), "empty selection is refused")
	# Strict v1 reader.
	var source: Dictionary = builtins["crossroads"].duplicate(true)
	var no_height: Dictionary = builtins["plaza"].records.duplicate(true)
	no_height.buildings[0].erase("height_cm")
	var spaced := [{"source": "S", "license": "L", "notice": "  " + notice}]
	for broken: Dictionary in [{"version": 2}, {"extra": 1}, {"format": "other"}, {"mouths": [{"node": "centre", "heading_deg": 0, "width_cm": 700}]}, {"records": {"water_bodies": []}}, {"records": no_height}, {"attributions": spaced}]:
		var bad := source.duplicate(true)
		bad.merge(broken, true)
		check(PARTS.parse(JSON.stringify(bad)).has("error"), "rejects " + str(broken))
	var broken_path := scratch.path_join("broken.json")
	var broken_file := FileAccess.open(broken_path, FileAccess.WRITE)
	broken_file.store_string("{")
	broken_file.close()
	check(PARTS.read(broken_path).get("error", "").begins_with("broken.json: "), "read errors name the file")
	# A colliding instance is refused rather than overwriting records.
	fresh()
	place(builtins["plaza"], Vector2(51200, 51200), 0.0)
	check(PARTS.plan_place(store.document, builtins["plaza"], Vector2(20000, 20000), 0.0, {"instance": "a1b2c3d4"}).has("error"), "instance collision refused")
	canvas.free()
	await ui_checks()
	print("city_parts_validator: ", "PASS" if failures.is_empty() else str(failures))
	quit(0 if failures.is_empty() else 1)

func ui_checks() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	root.add_child(ui)
	for _i in 4: await process_frame
	ui.store.new_track(true)
	ui.set_editor_mode("city")
	ui.show_tool_group("parts")
	await process_frame
	var panel: Control = ui.parts_panel
	check(panel.visible and not ui.city_panel.visible and ui.tool_workspace == "landscape", "Parts group shows the parts panel")
	check(panel.builtin_list.item_count == 9, "panel lists the built-in parts")
	panel.builtin_list.item_clicked.emit(0, Vector2.ZERO, MOUSE_BUTTON_LEFT)
	check(ui.canvas.tool == "Part" and ui.canvas.visible, "choosing a part arms plan placement")
	panel.rotate_by(15.0)
	check(is_equal_approx(panel.angle.value, 15.0), "rotation steps the angle")
	var before: int = ui.store.undo_stack.size()
	panel.place(Vector2(51200, 51200))
	check(ui.store.undo_stack.size() == before + 1 and not ui.canvas.selected.is_empty() and ui.canvas.tool == "Part", "click places one Undo and stays armed: %d→%d, %d selected, %s, %s" % [before, ui.store.undo_stack.size(), ui.canvas.selected.size(), ui.canvas.tool, ui.status_label.text])
	ui._cancel_editing()
	check(ui.canvas.tool == "Select", "Escape leaves part placement")
	# Rename and Delete act on the clicked user part, through their dialogs.
	PARTS.user_dir_override = scratch.path_join("ui-parts")
	var mine: Dictionary = panel.builtins[0].part.duplicate(true)
	mine.id = "user-probe"
	var saved := PARTS.save_user(mine)
	panel.refresh()
	panel.user_list.item_clicked.emit(0, Vector2.ZERO, MOUSE_BUTTON_LEFT)
	check(ui.canvas.tool == "Part" and not panel.chosen_user.is_empty(), "clicking a user part arms it and chooses it")
	panel._rename()
	panel.name_field.text = "Probe renamed"
	panel.name_dialog.confirmed.emit()
	panel.name_dialog.hide()
	check(saved.has("path") and PARTS.read(saved.get("path", "")).get("part", {}).get("name") == "Probe renamed", "rename through the dialog")
	panel.user_list.item_clicked.emit(0, Vector2.ZERO, MOUSE_BUTTON_LEFT)
	panel._confirm_delete()
	panel.delete_dialog.confirmed.emit()
	panel.delete_dialog.hide()
	check(not FileAccess.file_exists(saved.get("path", "")) and panel.user_list.item_count == 0, "delete through the dialog")
	PARTS.user_dir_override = ""
	# A saved custom key that a later default reuses keeps working.
	var config := ConfigFile.new()
	config.set_value("commands", "bindings", {"tool.forest": [KEY_E]})
	config.save(ui.commands.settings_path)
	ui.commands.load_settings()
	check(ui.commands.keys_for("tool.forest") == [KEY_E] and ui.commands.keys_for("parts.rotate_right").is_empty(), "saved shortcuts win over the new default: %s" % str(ui.commands.bindings))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(ui.commands.settings_path))
	ui.commands.load_settings()
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
