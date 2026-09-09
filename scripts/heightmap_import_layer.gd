extends RefCounted
## Editor-local raster candidate. No vector interchange or package schema changes.
const FILES := preload("./authoring_files.gd")
const PNG := preload("./terrain_png.gd")
const TYPES := preload("./import_layer.gd")
var value: Dictionary = {}
var _patches: Array = []
var _blobs: Dictionary = {}
var _cells: Array = []
var _dependencies := {}
var _store: RefCounted
var _signature := ""
var _project := ""
var _stale := false

func discard() -> void:
	if _store != null and _store.changed.is_connected(_changed): _store.changed.disconnect(_changed)
	_store = null
	value.clear()
	_patches.clear()
	_blobs.clear()
	_cells.clear()
	_dependencies.clear()

func _changed() -> void:
	_stale = true

func stage(terrain: RefCounted, path: String, cell: Vector2i, spacing: int, offset: int, step: int, accuracy: int, attribution: Dictionary) -> String:
	discard()
	var store: RefCounted = terrain.store
	if store.has_gesture() or store.project_path.is_empty(): return "Save the project and finish the active gesture before staging."
	if terrain.canvas != null and not terrain.canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true): return "Show and unlock terrain before staging."
	for key in ["source", "license"]:
		if not TYPES._text(attribution.get(key)): return "Provide bounded source attribution and license."
	if attribution.get("notice", "") is not String or str(attribution.get("notice", "")).length() > 2048: return "Source notice exceeds the import limit."
	if spacing < 200 or int(store.document.cell_size_cm) % spacing != 0 or step < 1 or step > 100 or absi(offset) > 1000000 or accuracy < 0 or accuracy > 1000000: return "Invalid heightmap spacing/offset/step/accuracy."
	var source := FILES.read(path, PNG.MAX_BYTES)
	if source.has("error"): return source.error
	var side := int(store.document.cell_size_cm) / spacing + 1
	var decoded := PNG.decode(source.bytes, side, offset, step)
	if decoded.has("error"): return decoded.error
	var low: int = decoded.heights[0]
	var high := low
	for height: int in decoded.heights:
		low = mini(low, height)
		high = maxi(high, height)
	var sha := FILES.digest(source.bytes)
	var before: Dictionary = terrain.descriptor(cell).duplicate(true)
	var record := {"cell":{"x":cell.x,"y":cell.y},"path":"editor/" + sha + ".png","spacing_cm":spacing,"offset_cm":offset,"step_cm":step,"source_accuracy_cm":accuracy if accuracy > 0 else null}
	value = {"import_version":1,"adapter":"heightmap-local-v1","layer_id":Crypto.new().generate_random_bytes(16).hex_encode(),"source":{"name":attribution.source,"license":attribution.license,"notice":attribution.get("notice", ""),"sha256":sha,"bytes":source.bytes.size()},"heightmap":record.duplicate(true),"previous":null if before.is_empty() else before.duplicate(true),"sample_side":side,"height_range_cm":[low,high],"axes":"PNG columns +local x, rows +local y","resampled":false}
	var notice := {"source":str(attribution.source) + "#" + value.layer_id,"license":attribution.license,"notice":JSON.stringify(value)}
	_patches = [{"field":"heightmaps","id":store.record_id("heightmaps",record),"before":null if before.is_empty() else before,"after":record},{"field":"attributions","id":store.record_id("attributions",notice),"before":null,"after":notice}]
	_blobs = {record.path:source.bytes}
	_cells = [cell] if not store.document.roads.is_empty() else []
	var failure := FILES.apply(store, "Adopt heightmap layer", _patches, _blobs, _cells, true)
	if failure != "":
		discard()
		return failure
	var retained_size := 0
	for field in ["heightmaps", "assets"]:
		for existing: Dictionary in store.document[field]:
			if _dependencies.has(existing.path): continue
			var payload := FILES.read(store.project_path.path_join(existing.path), FILES.MAX_PAYLOAD_BYTES - retained_size)
			if payload.has("error"):
				discard()
				return payload.error
			retained_size += payload.bytes.size()
			_dependencies[existing.path] = {"size":payload.bytes.size(),"sha256":FILES.digest(payload.bytes)}
	_store = store
	_project = store.project_path
	_signature = store._signature(store.document)
	_stale = false
	store.changed.connect(_changed)
	return ""

func adopt(terrain: RefCounted) -> String:
	if value.is_empty() or _store == null: return "No staged heightmap."
	if terrain.store != _store or _stale or _project != _store.project_path or _signature != _store._signature(_store.document):
		discard()
		return "Stale heightmap candidate; stage the source again."
	if terrain.canvas != null and not terrain.canvas.available({"field":"heightmaps", "record":{"id":"terrain"}}, true): return "Show and unlock terrain before adoption."
	for path: String in _dependencies:
		var payload := FILES.read(_project.path_join(path), _dependencies[path].size)
		if payload.has("error") or FILES.digest(payload.bytes) != _dependencies[path].sha256:
			discard()
			return "Project payload changed during review; stage again."
	# Native seam/file/budget checks run again against current payloads.
	var failure := FILES.apply(_store, "Adopt heightmap layer", _patches, _blobs, _cells)
	if failure == "": discard()
	return failure

func summary() -> String:
	if value.is_empty(): return "No staged heightmap."
	return "%s · %d bytes\nLicense: %s\nSHA-256: %s\nNew source layer: %s\nCell: %s · %d × %d samples\nSpacing / offset / step (cm): %d / %d / %d\nSource accuracy (cm; null unknown): %s\nRestored height range (cm): %s\n%s · no resampling\nPrevious active tile: %s\n\nAdopt explicitly activates this tile and retains its source notice. Previous file references and bytes remain available to Undo/Redo. Source changes after staging do not change this captured candidate." % [value.source.name,value.source.bytes,value.source.license,value.source.sha256,value.layer_id,str(value.heightmap.cell),value.sample_side,value.sample_side,value.heightmap.spacing_cm,value.heightmap.offset_cm,value.heightmap.step_cm,str(value.heightmap.source_accuracy_cm),str(value.height_range_cm),value.axes,str(value.previous)]
