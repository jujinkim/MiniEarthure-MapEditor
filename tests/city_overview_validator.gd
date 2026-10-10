extends SceneTree
const CANVAS := preload("res://scripts/map_canvas.gd")
var failures: Array[String]=[]
var checks:=0
func _initialize() -> void: run.call_deferred()
func check(ok: bool,message: String) -> void:
	checks+=1
	if not ok: failures.append(message);push_error(message)
func run() -> void:
	var canvas:=CANVAS.new()
	canvas.size=Vector2(100,150)
	var batches: Dictionary={}
	var color:=Color(0.2,0.3,0.4,0.5)
	var polygon:=PackedVector2Array([Vector2(10,10),Vector2(12,10),Vector2(12,12),Vector2(10,12)])
	for i in range(1000): canvas._overview_add(batches,"buildings",polygon,color)
	check(batches.size()==1 and batches[color].size()==8000,"one style batches a thousand independent closed footprints")
	var original: Array=batches[color].duplicate()
	canvas._overview_add(batches,"nodes",PackedVector2Array([Vector2(15,15)]),color)
	canvas._overview_add(batches,"pois",PackedVector2Array([Vector2(15,15)]),color)
	canvas._overview_add(batches,"roads",PackedVector2Array([Vector2(-10,-10),Vector2(-5,-5)]),color)
	check(batches[color]==original,"hidden handles, separately rendered POIs and offscreen roads do not add draw calls")
	var road:=PackedVector2Array([Vector2(-10,20),Vector2(20,20),Vector2(20,25)])
	canvas._overview_add(batches,"roads",road,color)
	check(batches[color].slice(8000)==[road[0],road[1],road[1],road[2]],"crossing viewport keeps independent road segments without closing its ends")
	canvas._overview_add(batches,"roads",road,Color(color,0.2))
	check(batches.size()==2,"layer opacity remains a separate style")
	check(polygon.size()==4 and road.size()==3,"source geometry unchanged")
	canvas.free()
	print("city_overview_validator: ","PASS" if failures.is_empty() else failures,"; checks=",checks)
	quit(0 if failures.is_empty() else 1)
