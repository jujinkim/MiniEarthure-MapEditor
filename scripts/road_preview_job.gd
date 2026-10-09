extends RefCounted
## Nine actual 32 m cells. Source data stay immutable; publication checks epochs.
const DATA:=preload("res://addons/mapkit/godot/chunk_data.gd")
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
	var triangles: Array=[];var chunks: Array=[];var bytes:=0
	for dy in range(-1,2):
		for dx in range(-1,2):
			if token.is_cancelled():return {"error":"Preview cancelled"}
			var cell: Vector2i=request.cell+Vector2i(dx,dy)
			if request.has("only") and cell not in request.only: continue
			if cell.x<0 or cell.y<0 or cell.x*3200>=document.bounds.max[0]-document.bounds.min[0] or cell.y*3200>=document.bounds.max[1]-document.bounds.min[1]:continue
			var result: Dictionary=working.generate_packed(cell.x,cell.y,true)
			if not result.ok:return {"error":str(result.error.code)+": "+str(result.error.message)}
			bytes+=int(result.data.preview_bytes)
			if bytes>128*1024*1024:return {"error":"E_BUDGET: nearby display resources exceed allowance"}
			var cell_triangles: Array=[]
			var view: Dictionary=DATA.view(result.data.chunk)
			for i in DATA.count(view):
				if not DATA.spawnable(view,i):continue
				var values: PackedInt64Array=view.vertices_cm
				var vertices: Array=[]
				for j in 3:vertices.append(Array(values.slice(i*9+j*3,i*9+j*3+3)))
				cell_triangles.append({"object_id":DATA.object_id(view,i),"spawnable":true,"vertices":vertices})
			triangles.append_array(cell_triangles)
			if triangles.size()>40000:return {"error":"E_BUDGET: nearby picking triangle allowance exceeded"}
			chunks.append({"cell":cell,"chunk":result.data.chunk,"hash":result.data.preview_signature,"triangles":cell_triangles})
	return {"triangles":triangles,"chunks":chunks}
func cancel() -> void:token.cancel()
func is_alive() -> bool:return thread.is_alive()
func finish() -> Dictionary:return thread.wait_to_finish()
func shutdown() -> void:
	cancel()
	if thread.is_started():thread.wait_to_finish()
