extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const LAYER := preload("res://scripts/import_layer.gd")
var checks := 0
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok: push_error(message); quit(1); assert(ok, message)
func _initialize() -> void: run.call_deferred()
func run() -> void:
	var store := STORE.new()
	store.new_document()
	var layer := LAYER.new()
	# Captured metric source; ordinary custom records use the same authoring API.
	var building := {"id":"import-"+"a".repeat(32)+"-building", "footprint":[[800,800],[2400,800],[2400,2400],[800,2400]],"base_cm":80,"height_cm":800,"usage":"residential","material":"brick","roof":"flat"}
	layer.value = {"adapter":"osm-extract-v1","coordinates":{},"layer_id":"a".repeat(32),"source":{"name":"synthetic","license":"MIT"},"patches":[{"field":"buildings","id":building.id,"before":null,"after":building}]}
	var captured := layer.value.duplicate(true)
	check(layer.adopt(store) == "", "OSM adopts actual metres")
	check(store.document.buildings[0].height_cm == 100 and int(store.document.buildings[0].footprint[0][0]) in [100,300] and int(store.document.buildings[0].footprint[0][1]) in [100,300], "source lengths and heights scale once")
	check(layer.value == captured, "source receipt remains immutable")
	check(store.undo() == "" and store.document.buildings.is_empty(), "undo removes only new layer")
	check(store.redo() == "", "redo restores already converted records")
	var authored: Dictionary = store.document.duplicate(true)
	var path := ProjectSettings.globalize_path("user://unit-roundtrip")
	check(store.save_project(path) == "" and store.open_project(path) == "", "save and reopen")
	check(store.document.buildings == authored.buildings, "reopen never scales custom source")
	var package := path + ".memap"
	check(JSON.parse_string(store.bridge.export_project(path,package)).ok, "export authored metres")
	check(JSON.parse_string(store.bridge.open_package(package)).ok, "open metric package")
	var window: Dictionary = JSON.parse_string(store.bridge.cell_window(100,100))
	check(window.ok and window.data.world_scale == 1.0, "one authored metre is one scene metre")
	var generated: Dictionary = JSON.parse_string(store.bridge.generate_chunk(0,0))
	check(generated.ok, "native generation accepts metric geometry")
	store.new_document()
	layer.value.adapter = "geojson-v1"
	check(layer.adopt(store) == "" and store.document.buildings[0].height_cm == 800, "custom GeoJSON retains 1:1 dimensions")
	check(preload("res://scripts/import_units.gd").dem_denominator(authored) == 8, "DEM aligns with adopted OSM scale")
	check(preload("res://scripts/import_units.gd").dem_denominator(store.document) == 1, "custom DEM is unscaled")
	var units := preload("res://scripts/import_units.gd")
	var road := {"id":"road","kind":"ground","from":"a","to":"b","points":[[80,0,80],[81,0,81],[160,0,160],[161,0,161]],"widths_cm":[160,160,160],"surfaces":["asphalt","asphalt","asphalt"]}
	var source := [{"field":"roads","after":road}]
	var scaled: Dictionary = units.osm_patches(source,true)[0].after
	check(scaled.points==[[10,0,10],[20,0,20]] and scaled.widths_cm==[20] and scaled.from=="a" and scaled.to=="b","city removes only consecutive quantized duplicates, preserving endpoints and material")
	check(road.points.size()==4 and units.osm_patches(source)[0].after.points.size()==4,"city cleanup never changes raw source or exact mode")
	road.surfaces[1]="concrete"
	check(units.osm_patches(source,true)[0].after.points.size()==4,"material boundary cannot be silently removed")
	check(units._ring_duplicates([[0,0],[0,0],[1,0],[1,1],[0,1]])==[[0,0],[1,0],[1,1],[0,1]],"adjacent polygon duplicates retain the same mathematical footprint")
	check(units._ring_duplicates([[0,0],[0,0],[1,0]]).size()==3,"collapsed courtyard stays invalid rather than silently filling")
	print("import_units_validator: PASS (",checks,")")
	quit(0)
