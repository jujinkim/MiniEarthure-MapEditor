extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value,message)
func run() -> void:
	var source := OS.get_environment("MAPEDITOR_SCHOOL_ROOT")
	check(not source.is_empty(),"explicit synthetic project")
	var store := STORE.new()
	var before := FileAccess.get_sha256(source.path_join("document.json"))
	check(store.open_project(source)=="","Editor opens the complete town")
	var saved := ProjectSettings.globalize_path("user://school-saved")
	check(store.save_project(saved)=="","Editor Save As copies static models")
	check(store.open_project(saved)=="","Editor saved project reopens")
	var output := ProjectSettings.globalize_path("user://school-export.memap")
	var packed: Dictionary = JSON.parse_string(store.bridge.export_project(saved,output))
	check(packed.ok,"native export: "+str(packed))
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(bridge.open_package(output)).ok,"exported package opens")
	var hashes := {}
	# Full 432-cell generation is retained by check_driving_school.py. Exercise
	# the binding on each district and both kart courses here, sharing one import.
	for row: Array in [[1,1],[7,2],[1,4],[2,5],[3,6],[4,6],[2,7],[1,8],[4,10],[7,6],[7,7],[8,6],[10,8],[10,10],[7,10],[12,3],[17,3],[23,3],[24,3],[29,4],[35,10]]:
		var x: int = row[0]
		var y: int = row[1]
		var generated: Dictionary = bridge.generate_chunk_packed(x,y)
		check(generated.ok,"cell %d/%d: %s" % [x,y,str(generated.get("error",""))])
		hashes["%d/%d" % [x,y]] = generated.data.generated_sha256
		await process_frame
		print("school binding cell: ",x,"/",y)
	var itinerary: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(source.path_join("driving.json")))
	for location: Dictionary in itinerary.locations:
		var p: Array = location.position_cm
		var probe: Dictionary = JSON.parse_string(bridge.surface_probe(p[0],p[2],location.surface_id))
		check(probe.ok,"advertised spawn "+str(location.id)+": "+str(probe))
		check(absf(probe.data.position_cm[1]-p[1])<=1,"exact spawn height "+str(location.id))
	# Probe every interior segment of the relocated grades and widened roads.
	for road: Dictionary in store.document.roads:
		if road.id not in ["license-hill","license-t-parking-bay","two-km-straight","kart-freeway-climb","kart-freeway-descent","kart-finger-bridge-in","kart-finger-bridge-out"]: continue
		for i in range(road.points.size()-1):
			var a: Array = road.points[i]
			var b: Array = road.points[i+1]
			# The short parking spur starts inside the wider approach's apron.
			var fraction := 0.8 if road.id=="license-t-parking-bay" else 0.5
			var x := roundi(lerpf(a[0],b[0],fraction))
			var y := roundi(lerpf(a[2],b[2],fraction))
			var result: Dictionary = JSON.parse_string(bridge.surface_probe(x,y,road.id))
			check(result.ok,"course support "+road.id+": "+str(result))
			check(absf(result.data.position_cm[1]-(a[1]+b[1])/2.0)<=2,"course support height "+road.id)
	check(FileAccess.get_sha256(source.path_join("document.json"))==before,"original project retained")
	var report := FileAccess.open(OS.get_environment("MAPEDITOR_SCHOOL_REPORT"),FileAccess.WRITE)
	check(report!=null,"report path")
	report.store_string(JSON.stringify({"source_sha256":before,"inspection":packed.data,"generated_cells":hashes,"checks":checks},"  ")+"\n")
	print("driving_school_validator: PASS (",checks," checks)")
	quit(0)
