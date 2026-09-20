extends SceneTree
const RENDER := preload("res://addons/mapkit/godot/chunk_renderer.gd")
func _initialize() -> void:
	var ordinary:=RENDER.material_color("grass")
	for climate:String in ["polar","arid","tropical"]:
		var presentation:Dictionary={"environment_json":JSON.stringify({"climate":climate})}
		assert(RENDER.ground_color("grass",presentation)!=ordinary)
		assert(RENDER.ground_color("asphalt",presentation)==RENDER.material_color("asphalt"))
		assert(RENDER.ground_color("dirt",presentation)==RENDER.material_color("dirt"))
	assert(RENDER.ground_color("grass",{})==ordinary)
	print("regional_palette_validator: PASS");quit()
