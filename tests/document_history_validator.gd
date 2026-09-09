extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const CANVAS := preload("res://scripts/map_canvas.gd")
var failures: Array[String] = []
var checks := 0

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func building(id: String) -> Dictionary:
	return {"id": id, "footprint": [[1000,1000],[3000,1000],[3000,3000],[1000,3000]],
		"base_cm": 0, "height_cm": 1200, "usage": "residential", "material": "concrete", "roof": "flat"}

func patch(field: String, id: String, before: Variant, after: Variant) -> Dictionary:
	return {"field": field, "id": id, "before": before, "after": after}

func state(store: RefCounted) -> String:
	return JSON.stringify([store.document, store.undo_stack, store.redo_stack, store.history_bytes, store.dirty, store.project_path])

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var store := STORE.new()
	store.new_document()
	var original := building("a")
	var other := building("b")
	check(store.apply_command("Two objects", [patch("buildings", "a", null, original), patch("buildings", "b", null, other)]) == "", "multi-record command accepted")
	original.height_cm = 9999
	check(store.document.buildings[0].height_cm == 1200, "caller mutation cannot alter document/memento")
	var bytes := store.history_bytes
	check(store.undo() == "" and store.document.buildings.is_empty(), "whole command undo")
	check(store.history_bytes == bytes and store.redo_stack.size() == 1, "redo mementos remain charged")
	check(store.redo() == "" and store.document.buildings.size() == 2, "whole command redo")
	check(store.history_bytes == bytes, "history transfer does not double-charge")
	var base := ProjectSettings.globalize_path("user://history-project")
	check(store.save_project(base) == "" and not store.dirty, "savepoint recorded")
	var a: Dictionary = store.document.buildings[0].duplicate(true)
	var edited := a.duplicate(true)
	edited.height_cm = 1500
	check(store.apply_command("Height", [patch("buildings", "a", a, edited)]) == "" and store.dirty, "edit leaves savepoint")
	check(store.undo() == "" and not store.dirty, "undo reaches saved content")
	var no_op := state(store)
	check(store.apply_command("No change", [patch("buildings", "a", a, a)]) == "" and state(store) == no_op, "no-op retains redo, dirty and timestamp")
	check(store.apply_command("Empty", []) == "" and state(store) == no_op, "empty operation has no history entry")
	check(store.redo() == "" and store.dirty, "redo restores unsaved edit")
	# A failure after the first reversed patch must not partly mutate live state.
	check(store.undo() == "", "return to multi-record entry")
	store.document.buildings[0].height_cm = 1300
	var stale := state(store)
	check(store.undo() != "" and state(store) == stale, "stale multi-record undo is atomic and retains history")
	store.document.buildings[0].height_cm = 1200
	check(store.undo() == "", "restored precondition permits undo")
	store.document.buildings.append(building("b"))
	stale = state(store)
	check(store.redo() != "" and state(store) == stale, "stale multi-record redo is atomic")
	store.document.buildings.clear()
	check(store.redo() == "", "redo recovers after stale state removed")
	var invalid := building("a")
	invalid.height_cm = -1
	stale = state(store)
	check(store.apply_command("Invalid", [patch("buildings", "a", building("a"), invalid)]) != "" and state(store) == stale, "native invalid command leaves all state intact")
	check(store.apply_command("Wrong ID", [patch("buildings", "wrong", null, building("c"))]) != "" and state(store) == stale, "IDs cannot escape their memento key")
	check(store.apply_command("Malformed", [42]) != "" and state(store) == stale, "malformed patch fails without script error")
	check(store.apply_command("Root alias", [patch("seed", "alias", 42, 43)]) != "" and state(store) == stale, "scalar fields cannot acquire duplicate memento identities")
	check(store.apply_command("Partial", [patch("buildings", "c", null, building("c")), patch("unknown", "x", null, {})]) != "" and state(store) == stale, "partial command failure preserves document")
	# A stroke can update a touched region repeatedly without publishing samples.
	check(store.begin_gesture("Stroke") == "", "begin grouped gesture")
	var untouched := state(store)
	for height in range(1201, 1301):
		var before := building("a")
		before.height_cm = height - 1
		var after := before.duplicate(true)
		after.height_cm = height
		check(store.stage_patches([patch("buildings", "a", before, after)]) == "", "stage sample " + str(height))
	check(store._gesture.patches.size() == 1 and state(store) == untouched, "100 samples retain one changed-region memento, no Scene/document changes")
	check(store.autosave() == "", "autosave during gesture captures committed state")
	var recovered := STORE.new()
	check(recovered.recover(store.recovery_path()) == "" and recovered.document.buildings[0].height_cm == 1200, "recovery excludes unfinished gesture")
	check(store.save_project(base) != "" and store.undo() != "", "save/history cannot cut across gesture")
	var count := store.undo_stack.size()
	check(store.commit_gesture() == "" and store.undo_stack.size() == count + 1 and store.redo_stack.is_empty(), "one stroke commits once and discards redo branch")
	check(store.undo() == "" and store.document.buildings[0].height_cm == 1200, "stroke undo restores first memento")
	check(store.redo() == "" and store.document.buildings[0].height_cm == 1300, "stroke redo restores final sample")
	check(store.save_project(base) == "", "save after gesture undo/redo")
	check(recovered.open_project(base) == "" and recovered.document == store.document, "exact full document save/reopen")
	check(store.begin_gesture("Cancel") == "", "begin cancelled gesture")
	var cancelled := state(store)
	check(store.stage_patches([patch("terrain_base_cm", "", 0, 100)]) == "", "stage scalar map field")
	store.cancel_gesture()
	check(state(store) == cancelled and not store.has_gesture(), "cancel leaves committed content/history unchanged")
	check(store.begin_gesture("Bad stroke") == "", "begin invalid stroke")
	check(store.stage_patches([patch("terrain_base_cm", "", 0, 20)]) == "", "valid staged prefix")
	var staged := JSON.stringify(store._gesture)
	check(store.stage_patches([patch("terrain_base_cm", "", 20, 30), {"field": "bad"}]) != "" and JSON.stringify(store._gesture) == staged, "failed sample batch retains previous staged memento")
	store.document.seed = 43
	check(store.commit_gesture() != "", "stale gesture cannot commit to externally changed document")
	store.cancel_gesture()
	store.document.seed = 42
	check(store.begin_gesture("Old document") == "", "start before replacement")
	store.new_document()
	check(not store.has_gesture() and store.commit_gesture() != "", "replacement invalidates old gesture")
	# Count and serialized-byte caps, redo branching, oversize transactional rejection.
	for i in range(205):
		check(store.apply_command("Seed", [patch("seed", "", store.document.seed, i)]) == "", "bounded command " + str(i))
	check(store.undo_stack.size() == STORE.HISTORY_COMMANDS, "oldest commands evicted at count cap")
	bytes = store.history_bytes
	for _i in 200:
		check(store.undo() == "", "bounded history undo")
	check(store.history_bytes == bytes and store.redo_stack.size() == 200, "all-redo history remains fully charged")
	check(store.apply_command("Branch", [patch("seed", "", store.document.seed, 999)]) == "" and store.redo_stack.is_empty(), "new branch releases all redo bytes")
	check(store.history_bytes == store.undo_stack[0].bytes, "branch accounting equals retained entry")
	var large_label := "m".repeat(8 * 1024 * 1024)
	check(store.apply_command(large_label, [patch("seed", "", 999, 1000)]) == "", "large bounded memento accepted")
	check(store.apply_command(large_label, [patch("seed", "", 1000, 1001)]) == "", "large command evicts oldest for byte cap")
	check(store.undo_stack.size() == 1 and store.history_bytes <= STORE.HISTORY_BYTES, "shared byte budget enforced")
	stale = state(store)
	check(store.apply_command(large_label + large_label, [patch("seed", "", 1001, 1002)]) != "" and state(store) == stale, "oversize command preserves state and history")
	store.new_document()
	check(store.history_bytes == 0 and store.undo_stack.is_empty() and store.redo_stack.is_empty(), "replacement releases both histories")
	check(store.apply_command("Explicit recipe", [patch("recipe_version", "", 1, 3)]) == "", "explicit recipe change uses command")
	var repetition := {"id":"line", "asset_id":"builtin:fence", "points":[[1000,0,1000],[2000,0,1000]], "spacing_cm":200}
	check(store.apply_command("Repeat", [patch("repetitions", "line", null, repetition)]) == "", "optional repetition field is command-owned")
	check(store.undo() == "" and store.document.get("repetitions", []).is_empty(), "optional field undo handles canonical omission")
	check(store.redo() == "" and store.document.repetitions.size() == 1, "optional field redo")
	var attribution_a := {"source":"same source", "license":"MIT", "notice":"A"}
	var attribution_b := {"source":"same source", "license":"MIT", "notice":"B"}
	check(store.apply_command("Licenses", [patch("attributions", store.record_id("attributions", attribution_a), null, attribution_a), patch("attributions", store.record_id("attributions", attribution_b), null, attribution_b)]) == "", "same-source distinct notices have distinct identities")
	check(store.undo() == "" and store.document.attributions.is_empty(), "both notices undo without ambiguity")
	check(store.redo() == "" and store.document.attributions.size() == 2, "both notices redo")
	store.document.attributions.append(attribution_b.duplicate(true))
	stale = state(store)
	check(store.undo() != "" and state(store) == stale, "identical duplicate identity fails without choosing a user record")
	await canvas_gestures()
	print("document_history_validator: %s (%d assertions)" % ["PASS" if failures.is_empty() else str(failures), checks])
	quit(0 if failures.is_empty() else 1)

func canvas_gestures() -> void:
	var ui: Node = load("res://main.tscn").instantiate()
	root.add_child(ui)
	await process_frame
	var store: RefCounted = ui.store
	check(store.apply_command("Building", [patch("buildings", "a", null, building("a"))]) == "", "UI fixture")
	var canvas: Control = ui.canvas
	var original: Dictionary = store.document.duplicate(true)
	var count: int = store.undo_stack.size()
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = canvas.screen([2000,2000])
	canvas._gui_input(press)
	for i in range(1, 21):
		var motion := InputEventMouseMotion.new()
		motion.position = canvas.screen([2000 + i * 100,2000])
		motion.button_mask = MOUSE_BUTTON_MASK_LEFT
		canvas._gui_input(motion)
	check(store.document == original and store.undo_stack.size() == count, "drag motion changes view only")
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	canvas._gui_input(release)
	check(store.undo_stack.size() == count + 1 and store.document.buildings[0].footprint[0][0] == 3000, "mouse release creates one movement command")
	ui._history(false)
	check(store.document.buildings[0].footprint[0][0] == 1000, "UI undo returns pre-drag geometry")
	canvas._gui_input(press)
	var escape := InputEventKey.new()
	escape.keycode = KEY_ESCAPE
	escape.pressed = true
	ui._unhandled_key_input(escape)
	canvas._gui_input(release)
	check(not store.has_gesture() and not canvas.dragging and store.document.buildings[0].footprint[0][0] == 1000, "Escape discards drag without later release mutation")
	canvas._gui_input(press)
	canvas.tool = "Building"
	check(not store.has_gesture() and not canvas.dragging, "tool change cancels gesture")
	canvas.tool = "Select"
	canvas._gui_input(press)
	canvas._notification(Node.NOTIFICATION_WM_WINDOW_FOCUS_OUT)
	check(not store.has_gesture() and not canvas.dragging, "focus loss cancels gesture")
	canvas._gui_input(press)
	ui._new()
	if ui.unsaved_dialog.visible:
		ui.unsaved_dialog.hide()
		ui._continue_document_action()
	canvas._gui_input(release)
	check(store.document.buildings.is_empty() and store.undo_stack.is_empty(), "old mouse release cannot edit replacement document")
	ui.store.dirty = false
	ui.queue_free()
	await process_frame
