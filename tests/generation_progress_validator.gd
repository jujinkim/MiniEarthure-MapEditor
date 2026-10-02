extends SceneTree
const JOB:=preload("res://addons/mapkit/godot/track_job.gd")
const PANEL:=preload("res://scripts/track_settings_panel.gd")
const STORE:=preload("res://scripts/document_store.gd")
var failures:Array[String]=[]
func check(ok:bool,label:String)->void:
	if not ok:failures.append(label);push_error(label)
func _initialize()->void:run.call_deferred()
func run()->void:
	var panel:=PANEL.new();root.add_child(panel)
	panel.set_busy(true);panel.update_progress({"stage":"searching"})
	check(panel.generate.disabled and panel.progress.fraction()<0,"busy generator blocks duplicates and shows unknown search")
	var job:=JOB.new();root.add_child(job)
	var states:Array=[];var results:Array=[]
	job.progressed.connect(func(request:int,value:Dictionary):states.append([request,value]);panel.update_progress(value))
	job.completed.connect(func(request:int,value:Dictionary):results.append([request,value]))
	var settings:Dictionary=panel.settings();settings.circuit=false;settings.duration_seconds=60;settings.seed=42;settings.categories=["driving"]
	var request:int=job.begin(settings,ProjectSettings.globalize_path("user://preview-progress.memap"),true)
	var deadline:=Time.get_ticks_msec()+90000
	while results.is_empty() and Time.get_ticks_msec()<deadline:await process_frame
	check(not results.is_empty(),"generation worker completes")
	if not results.is_empty():
		var result:Dictionary=results[0][1]
		check(results[0][0]==request and result.ok,"current request succeeds")
		if result.ok:
			check(not result.data.get("preview",{}).is_empty(),"prepared preview accompanies completion")
			var store:=STORE.new()
			check(store.open_generated(result.data.document,result.data.preview)=="" and not store.prepared_track_preview.is_empty(),"document adopts prepared preview")
	var unknown:=false;var counted:=false;var preview:=false
	for row:Array in states:
		check(row[0]==request,"request identity")
		var p:Dictionary=row[1]
		unknown=unknown or p.total==null
		counted=counted or (p.total!=null and p.completed>0)
		preview=preview or str(p.stage).begins_with("preview")
	check(unknown and counted and preview,"unknown search, measured work and preview stages")
	job.cancel();panel.set_busy(false);job.queue_free();panel.queue_free();await process_frame
	print("generation_progress_validator: ","PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
