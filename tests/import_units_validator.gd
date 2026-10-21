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
	# Map scale 1:D read back from provenance: exactly the stored value, never guessed.
	var notice := func(unit: Dictionary) -> Dictionary: return {"source":"osm","license":"ODbL","notice":JSON.stringify({"adapter":"osm-extract-v1","authored_units":unit})}
	for d in [8, 3]:
		var stored := {"attributions":[notice.call({"source_denominator":d,"profile":units.profile(d)}),notice.call({"source_denominator":float(d)})]}
		check(units.dem_denominator(stored) == d and units.osm_scale(stored).denominator == d, "DEM/CSV read the stored 1:%d" % d)
	check(units.profile(8) == "osm-import-1to8-v1" and units.profile(3) == "osm-import-1to3-v1", "1:8 keeps its original profile id")
	check(units.dem_denominator(authored) == 8 and authored.attributions.any(func(a): return a.notice.contains("\"source_denominator\":8}") and a.notice.contains("osm-import-1to8-v1")), "existing 1:8 provenance reads back 8")
	for bad: Dictionary in [{"source_denominator":9}, {"source_denominator":2.5}, {"source_denominator":"3"}, {}, {"source_denominator":3,"profile":"osm-import-1to8-v1"}]:
		var unknown := {"attributions":[notice.call(bad)]}
		check(units.dem_denominator(unknown) == 0 and units.osm_scale(unknown).has("error"), "unknown OSM scale is an error, never 1: %s" % JSON.stringify(bad))
	var mixed := {"attributions":[notice.call({"source_denominator":8}),notice.call({"source_denominator":3})]}
	check(units.dem_denominator(mixed) == 0 and str(units.osm_scale(mixed).get("error","")).contains("different map scales"), "mixed OSM scales are rejected")
	check(units.osm_scale({"attributions":[]}).denominator == 0 and units.dem_denominator({"attributions":[]}) == 1, "a map without OSM is 1:1 for DEM/CSV")
	var third: Dictionary = units.osm_patches([{"field":"buildings","after":building.duplicate(true)}],true,0,3)[0].after
	check(third.height_cm == 267 and third.base_cm == 27 and third.footprint[0] == [267,267], "1:3 adoption divides source centimetres by three")
	var city_layer := LAYER.new()
	city_layer.value = {"adapter":"osm-extract-v1","coordinates":{"osm_city":{"scale_denominator":3.0}},"layer_id":"b".repeat(32),"source":{"name":"synthetic","license":"MIT"},"patches":[{"field":"buildings","id":building.id,"before":null,"after":building}]}
	store.new_document()
	var city_patches: Array = city_layer.patches(store)
	var notice_text: String = city_patches.filter(func(p): return p.field == "attributions")[0].after.notice
	var units_notice: Dictionary = JSON.parse_string(notice_text).authored_units
	check(city_layer.osm_denominator() == 3 and notice_text.contains("\"source_denominator\":3}") and units_notice.profile == "osm-import-1to3-v1", "a 1:3 city layer writes D=3 and its profile")
	check(city_patches.filter(func(p): return p.field == "buildings")[0].after.height_cm == 267, "a 1:3 city layer adopts at 1:3")
	store.document.attributions.append(notice.call({"source_denominator":8,"profile":units.profile(8)}))
	check(city_layer.validate_for(store).contains("already uses OSM scale 1:8"), "a second OSM scale cannot be adopted into the same map")
	store.new_document()
	var road := {"id":"road","kind":"ground","from":"a","to":"b","points":[[80,0,80],[81,0,81],[160,0,160],[161,0,161]],"widths_cm":[160,160,160],"surfaces":["asphalt","asphalt","asphalt"]}
	var source := [{"field":"roads","after":road}]
	var scaled: Dictionary = units.osm_patches(source,true)[0].after
	check(scaled.points==[[10,0,10],[20,0,20]] and scaled.widths_cm==[20] and scaled.from=="a" and scaled.to=="b","city removes only consecutive quantized duplicates, preserving endpoints and material")
	check(road.points.size()==4 and units.osm_patches(source)[0].after.points.size()==4,"city cleanup never changes raw source or exact mode")
	road.surfaces[1]="concrete"
	check(units.osm_patches(source,true)[0].after.points.size()==4,"material boundary cannot be silently removed")
	var planes := [{"field":"nodes","id":"import-x-osm-ground-node-1","after":{"id":"import-x-osm-ground-node-1","position":[80,0,80],"level":0}},
		{"field":"roads","id":"import-x-1","after":{"id":"import-x-1","kind":"bridge","from":"import-x-osm-ground-node-1","to":"import-x-1-to","points":[[80,0,80],[160,4800,80]],"widths_cm":[800],"surfaces":["asphalt"]}},
		{"field":"roads","id":"import-x-2","after":{"id":"import-x-2","kind":"bridge","from":"import-x-osm-node-5","to":"import-x-osm-node-6","points":[[80,800,80],[160,800,80]],"widths_cm":[800],"surfaces":["asphalt"]}}]
	var placed: Array = units.osm_patches(planes,true,-2000)
	check(placed[0].after.position[1]==-2000 and placed[1].after.points[0][1]==-2000 and placed[1].after.points[1][1]==-1400,"city plane heights follow the map terrain base")
	check(placed[2].after.points[0][1]==100,"explicit source-height structures keep their vertical frame")
	check(units._ring_duplicates([[0,0],[0,0],[1,0],[1,1],[0,1]])==[[0,0],[1,0],[1,1],[0,1]],"adjacent polygon duplicates retain the same mathematical footprint")
	check(units._ring_duplicates([[0,0],[0,0],[1,0]]).size()==3,"collapsed courtyard stays invalid rather than silently filling")
	var narrow := [{"field":"roads","after":{"id":"n","kind":"ground","from":"a","to":"b","points":[[0,0,0],[1000,0,0],[2000,0,0]],"widths_cm":[75,200],"surfaces":["asphalt","asphalt"],"sidewalk_cm":null}},
		{"field":"buildings","after":{"id":"near","footprint":[[1200,60],[1800,60],[1800,400],[1200,400]]}}]
	units.widen_roads(narrow,[])
	check(narrow[0].after.widths_cm == [150,200],"narrow 1:8 road widens to the 150 cm floor; wider segments unchanged")
	narrow[0].after.widths_cm = [75,75]
	units.widen_roads(narrow,[])
	check(narrow[0].after.widths_cm == [150,80],"widening stops 20 cm before a building edge")
	units.widen_roads(narrow,[{"id":"old","footprint":[[0,-50],[1000,-50],[1000,-500],[0,-500]]}])
	check(narrow[0].after.widths_cm == [150,80],"existing buildings never shrink an already widened road")
	narrow[0].after.widths_cm = [75,75]
	units.widen_roads(narrow,[{"id":"old","footprint":[[0,-50],[1000,-50],[1000,-500],[0,-500]]}])
	check(narrow[0].after.widths_cm == [75,75],"existing map buildings also limit widening without narrowing")
	var courtyard := [{"field":"roads","after":{"id":"c","kind":"ground","from":"a","to":"b","points":[[100,0,500],[900,0,500]],"widths_cm":[40],"surfaces":["asphalt"],"sidewalk_cm":null}},
		{"field":"buildings","after":{"id":"yard","footprint":[[-500,-500],[1500,-500],[1500,1500],[-500,1500]],"holes":[[[0,450],[0,560],[1000,560],[1000,450]]]}}]
	units.widen_roads(courtyard,[])
	check(courtyard[0].after.widths_cm == [60],"a road inside a courtyard stops 20 cm before its walls")
	var walking := [{"field":"roads","id":"path","after":{"id":"path","kind":"ground","from":"a","to":"b","points":[[0,0,3000],[1000,0,3000]],"widths_cm":[20],"surfaces":["asphalt"],"sidewalk_cm":null}}]
	units.widen_roads(walking,[],["path"])
	check(walking[0].after.widths_cm == [20],"listed pedestrian roads keep their estimated width")
	# City building parts and barriers scale once at 1:D; parts bound widening too.
	var parted := {"id":"p","footprint":[[0,0],[300,0],[300,300],[0,300]],"base_cm":0,"height_cm":900,"usage":"residential","material":"concrete","roof":"flat",
		"parts":[{"footprint":[[600,0],[900,0],[900,300],[600,300],[600,300]],"height_cm":3000},{"footprint":[[1200,0],[1500,0],[1500,300],[1200,300]],"base_cm":30}]}
	var barrier := {"id":"f","kind":"fence","line":[[0,600],[3,600],[1200,600],[1200,600],[0,600]],"height_cm":120,"thickness_cm":15}
	var adopted: Array = units.osm_patches([{"field":"buildings","after":parted},{"field":"barriers","after":barrier}],true,-2000,3)
	var solid: Dictionary = adopted[0].after
	check(solid.footprint[1] == [100,0] and solid.parts[0].footprint == [[200,0],[300,0],[300,100],[200,100]] and solid.parts[0].height_cm == 1000 and solid.parts[1].base_cm == 10 and solid.height_cm == 300,"building parts scale like their record, quantized duplicates removed")
	check(adopted[1].after.line == [[0,200],[1,200],[400,200],[0,200]] and adopted[1].after.height_cm == 40 and adopted[1].after.thickness_cm == 5,"barrier lines, heights and thicknesses scale once; a closed line keeps its repeat")
	var between := [{"field":"roads","after":{"id":"r","kind":"ground","from":"a","to":"b","points":[[0,0,450],[600,0,450]],"widths_cm":[40],"surfaces":["asphalt"],"sidewalk_cm":0}},
		{"field":"buildings","after":{"id":"two","footprint":[[0,-500],[100,-500],[100,-600],[0,-600]],"parts":[{"footprint":[[0,400],[600,400],[600,300],[0,300]]}]}}]
	units.widen_roads(between,[])
	check(between[0].after.widths_cm == [60],"a building part limits widening like a footprint")
	var paved: Array = city_layer.patches(store).filter(func(p): return p.field == "ground_surface")
	check(paved.size() == 1 and paved[0].before == null and paved[0].after == "concrete","a city layer paves a map without a ground surface")
	store.document.ground_surface = "gravel"
	city_layer.limit_warnings = []
	check(city_layer.patches(store).filter(func(p): return p.field == "ground_surface").is_empty() and city_layer.limit_warnings.any(func(e): return e.code == "city_ground_surface"),"another ground surface is kept with a warning")
	store.document.erase("ground_surface")
	print("import_units_validator: PASS (",checks,")")
	quit(0)
