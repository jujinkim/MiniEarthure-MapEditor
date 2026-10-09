extends SceneTree
## Short synthetic input → installed 32 m meshes; no driving/device acceptance.
const TERRAIN := preload("res://scripts/terrain_tools.gd")
var failed := false
func _initialize() -> void: run.call_deferred()
func check(value: bool,label: String) -> void:
	if not value: failed=true;push_error(label)
func settle(road: RefCounted,revision: int) -> void:
	var deadline := Time.get_ticks_msec()+10000
	while road.environment_terrain_revision<revision and Time.get_ticks_msec()<deadline: await process_frame
	check(road.environment_terrain_revision>=revision,"input revision reached installed meshes")
func run() -> void:
	var ui: Control=load("res://main.tscn").instantiate();root.add_child(ui);await process_frame
	ui.store.new_track(true)
	check(ui.store.apply_command("Fixture",[{"field":"bounds","before":ui.store.document.bounds,"after":{"min":[0,0],"max":[9600,9600]}},{"field":"cell_size_cm","before":ui.store.document.cell_size_cm,"after":3200}])=="","fixture setup")
	ui.set_tool_workspace("landscape")
	ui.preview_camera.frame(Vector3(48,0,-48),64)
	var road: RefCounted=ui.track_workbench.road_tools
	road.request_cell(Vector2i(1,1));await settle(road,ui.store.terrain_revision)
	var terrain := TERRAIN.new();terrain.store=ui.store
	check(terrain.begin(Vector2(4800,4800),{"mode":"raise","radius_cm":1600})=="","timed brush starts")
	# The editor ticks its own pointer brush only; this fixture supplies deterministic time.
	var times: Array[float]=[]
	for i in 30:
		var start := Time.get_ticks_usec()
		check(terrain.step(Vector2(4800+i*5,4800),1.0/30)=="","synthetic input")
		await settle(road,ui.store.terrain_revision)
		times.append(float(Time.get_ticks_usec()-start)/1000)
	var elapsed: float=times.reduce(func(a,b):return a+b,0.0)
	times.sort()
	var p95: float=times[int(ceil(times.size()*0.95))-1]
	var hz: float=times.size()*1000/elapsed
	print("terrain mesh p95_ms=",p95,"; updates_hz=",hz,"; scene_install_budget_usec=3000")
	check(p95<=50 and hz>=30,"short synthetic terrain target: p95 <= 50 ms and >= 30 Hz")
	terrain.cancel();ui.queue_free();await process_frame
	print("terrain_frame_validator: ","FAIL" if failed else "PASS");quit(1 if failed else 0)
