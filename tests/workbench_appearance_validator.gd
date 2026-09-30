extends SceneTree
## Synthetic control rendering, independent of OS input or an authored document.
const STYLE := preload("res://scripts/workbench_style.gd")
var surface: SubViewport
var button: Button
func _initialize() -> void: run.call_deferred()
func settle() -> void:
	for _i in 3: await process_frame
	await RenderingServer.frame_post_draw
func motion(position: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = position
	surface.push_input(event)
func press(down: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = Vector2(40, 40)
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = down
	surface.push_input(event)
func run() -> void:
	assert(DisplayServer.get_name() != "headless", "This is a rendered control regression")
	surface = SubViewport.new()
	surface.size = Vector2i(96, 112)
	surface.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(surface)
	var panel := Panel.new()
	panel.size = Vector2(96, 112)
	panel.add_theme_stylebox_override("panel", STYLE.box(STYLE.PANEL))
	panel.theme = STYLE.create_theme()
	surface.add_child(panel)
	button = STYLE.button(panel, "Save project", func(): pass, "Save the map.", "save")
	button.position = Vector2(22, 16)
	button.size = Vector2(52, 52)
	var label := Label.new()
	label.position = Vector2(4, 80)
	label.size.x = 88
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	panel.add_child(label)
	var sheet := Image.create(96 * 6, 112, false, Image.FORMAT_RGBA8)
	var states := ["Normal", "Hover", "Pressed", "Selected", "Disabled", "Focus"]
	var modes := [BaseButton.DRAW_NORMAL, BaseButton.DRAW_HOVER, BaseButton.DRAW_PRESSED, BaseButton.DRAW_PRESSED, BaseButton.DRAW_DISABLED, BaseButton.DRAW_NORMAL]
	for i in states.size():
		label.text = states[i]
		match i:
			0: motion(Vector2(90, 100))
			1: motion(Vector2(40, 40))
			2: press(true)
			3:
				press(false)
				motion(Vector2(90, 100))
				button.toggle_mode = true
				button.set_pressed_no_signal(true)
			4:
				button.set_pressed_no_signal(false)
				button.release_focus()
				button.disabled = true
			5:
				button.disabled = false
				button.toggle_mode = false
				button.grab_focus()
		await settle()
		assert(button.get_draw_mode() == modes[i], states[i] + " uses the real control state")
		if i == 5: assert(button.has_focus())
		var with_icon := surface.get_texture().get_image()
		sheet.blit_rect(with_icon, Rect2i(0, 0, 96, 112), Vector2i(i * 96, 0))
		var texture: Texture2D = button.icon
		button.icon = null
		await settle()
		var without_icon := surface.get_texture().get_image()
		var changed := 0
		for y in range(24, 60):
			for x in range(30, 66):
				var a := with_icon.get_pixel(x, y)
				var b := without_icon.get_pixel(x, y)
				if absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > 0.03: changed += 1
		assert(changed >= 30, states[i] + " must visibly render icon pixels, including disabled controls")
		button.icon = texture
	var capture := OS.get_environment("MAPEDITOR_CONTROL_CAPTURE")
	if not capture.is_empty(): assert(sheet.save_png(capture) == OK)
	surface.queue_free()
	for _i in 3: await process_frame
	print("workbench_appearance_validator: PASS (6 rendered icon states)")
	quit()
