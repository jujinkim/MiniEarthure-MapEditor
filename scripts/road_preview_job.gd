extends RefCounted
## Nine actual 32 m cells. Source data stay immutable; publication checks epochs.
const DATA:=preload("res://addons/mapkit/godot/chunk_data.gd")
const LIMITS:=preload("./limit_warnings.gd")
# Display allowance and picking cap: above them cells are still shown, with a
# warning, and cells past the picking cap cannot be picked.
const DISPLAY_BYTES:=128*1024*1024
const PICK_TRIANGLES:=40000
var thread:=Thread.new()
var token: RefCounted=ClassDB.instantiate("MapKitWorkToken")
var request: Dictionary
var working: RefCounted
func start(store: RefCounted,value: Dictionary) -> Error:
	request=value.duplicate(true)
	working=store.working_snapshot().fork()
	return thread.start(_run.bind(store.document.duplicate(true),store.project_path))
func _run(document: Dictionary,path: String) -> Dictionary:
	token.enter()
	var result:=_prepare(document,path)
	token.leave()
	return result
func _prepare(document: Dictionary,path: String) -> Dictionary:
	var triangles: Array=[];var chunks: Array=[];var bytes:=0;var warnings: Array=[]
	for dy in range(-1,2):
		for dx in range(-1,2):
			if token.is_cancelled():return {"error":"Preview cancelled"}
			var cell: Vector2i=request.cell+Vector2i(dx,dy)
			if request.has("only") and cell not in request.only: continue
			if cell.x<0 or cell.y<0 or cell.x*3200>=document.bounds.max[0]-document.bounds.min[0] or cell.y*3200>=document.bounds.max[1]-document.bounds.min[1]:continue
			var result: Dictionary=working.generate_packed(cell.x,cell.y,true)
			if not result.ok:return {"error":str(result.error.code)+": "+str(result.error.message)}
			bytes+=int(result.data.preview_bytes)
			if bytes>DISPLAY_BYTES:LIMITS.note(warnings,"nearby_display",bytes,DISPLAY_BYTES,"Nearby display resources are very large")
			var cell_triangles: Array=[]
			var view: Dictionary=DATA.view(result.data.chunk)
			var pickable:=triangles.size()+DATA.count(view)<=PICK_TRIANGLES
			if not pickable:LIMITS.note(warnings,"nearby_picking",triangles.size()+DATA.count(view),PICK_TRIANGLES,"Too many nearby triangles; some cells cannot be picked")
			for i in (DATA.count(view) if pickable else 0):
				var values: PackedInt64Array=view.vertices_cm
				var vertices: Array=[]
				for j in 3:vertices.append(Array(values.slice(i*9+j*3,i*9+j*3+3)))
				cell_triangles.append({"object_id":DATA.object_id(view,i),"spawnable":DATA.spawnable(view,i),"vertices":vertices})
			triangles.append_array(cell_triangles)
			chunks.append({"cell":cell,"chunk":result.data.chunk,"hash":result.data.preview_signature,"triangles":cell_triangles})
	return {"triangles":triangles,"chunks":chunks,"limit_warnings":warnings}
func cancel() -> void:token.cancel()
func is_alive() -> bool:return thread.is_alive()
func finish() -> Dictionary:return thread.wait_to_finish()
func shutdown() -> void:
	cancel()
	if thread.is_started():thread.wait_to_finish()
