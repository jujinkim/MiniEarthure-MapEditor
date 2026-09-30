extends SceneTree
## Runs in the disposable asset fixture owned by test_workbench_icons.py.
const STYLE := preload("res://scripts/workbench_style.gd")
func _initialize() -> void:
	var mode := OS.get_environment("MAPEDITOR_ICON_FIXTURE")
	assert(mode in ["cold", "stale", "imported", "packed", "missing", "damaged"])
	if mode in ["missing", "damaged"]:
		var button := Button.new()
		STYLE.decorate(button, "Save project", "Save the map.", "save")
		assert(button.icon == null and button.text == "Save project")
		assert(not STYLE.textures.has("save"), "Failed icons must remain retryable")
		if FileAccess.file_exists("res://ui/icons/save.svg.import"):
			assert(DirAccess.remove_absolute("res://ui/icons/save.svg.import") == OK)
		var file := FileAccess.open("res://ui/icons/save.svg", FileAccess.WRITE)
		file.store_string('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect x="4" y="4" width="24" height="24" fill="#245edb"/></svg>')
		file.close()
		STYLE.decorate(button, "Save project", "Save the map.", "save")
		assert(button.icon != null and button.text.is_empty(), "Repaired resource retries successfully")
		button.free()
	else:
		assert(STYLE.ICON_NAMES.size() == 118)
		for id: String in STYLE.ICON_NAMES:
			assert(STYLE.icon_name(id) == id, "Stable icon IDs do not depend on loose files")
			var texture: Texture2D = STYLE.icon(id)
			assert(texture != null and texture.get_size() == Vector2(32, 32), id)
			assert(STYLE.icon(id) == texture, "Successful textures are cached")
			assert(texture is ImageTexture if mode in ["cold", "stale"] else texture is CompressedTexture2D)
			var pixels := texture.get_image()
			var visible := 0
			for y in 32:
				for x in 32:
					if pixels.get_pixel(x, y).a > 0.2: visible += 1
			assert(visible >= 15, "Icon has actual artwork: " + id)
			if mode == "packed": assert(not FileAccess.file_exists("res://ui/icons/" + id + ".svg"))
	var theme := STYLE.create_theme()
	assert(theme.default_font_size == 14)
	assert(theme.get_stylebox("normal", "Button") is StyleBoxTexture)
	print("workbench_icon_validator: PASS (", mode, ")")
	quit()
