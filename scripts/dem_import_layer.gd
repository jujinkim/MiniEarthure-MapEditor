extends "./heightmap_import_layer.gd"
const LICENSE := "https://copernicus-dem-30m.s3.amazonaws.com/readme.html#license"
## Hard bounds; above the former 256 cells, 4 tiles and 64 MiB per tile the
## review warns. Every cell is still sampled and checked.
const MAX_CELLS := 1024
const WARN_CELLS := 256
const STRUCTURE_FIT := preload("./dem_structure_fit.gd")
## Each tile file is bounded; decoding is bounded by the reviewed block budget.
const MAX_SOURCES := 16
const WARN_SOURCES := 4
const MAX_SOURCE_BYTES := 256 * 1024 * 1024
const WARN_SOURCE_BYTES := 64 * 1024 * 1024
const NOTICE := "produced using Copernicus WorldDEM-%d © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"

func stage_dem(terrain: RefCounted, result: Dictionary, reviewed: Dictionary, destination: String, context: Dictionary = {}) -> String:
	discard()
	if reviewed.get("options") is not Dictionary: return "Missing DEM options."
	var options: Dictionary = reviewed.options
	if options.get("coordinates") is not Dictionary or not TYPES._finite(options.get("vertical_zero_m"), -10000, 10000): return "Invalid DEM height reference."
	var frame_error: String = preload("./import_vertical.gd").frame_error(terrain.store.document, {"target_crs":"EPSG:3855 / EGM2008 metres", "vertical_zero_m":options.get("vertical_zero_m")}, options.get("coordinates", {}))
	if frame_error != "": return frame_error
	if reviewed.get("adapter") != "copernicus-dem-v1": return "Unsupported DEM adapter."
	return _stage_cells(terrain,result,reviewed,destination,context)

func summary() -> String:
	if value.is_empty(): return I18N.t("No DEM candidate.")
	var limits := LIMITS.text(limit_warnings)
	var text := (limits + "\n\n" if limits != "" else "") + I18N.t("Copernicus 2021 DSM · %d sources → %d cells\nAdopt all terrain cells atomically; one Undo restores every previous cell.\nEGM2008 height minus %s m at local zero; explicit bilinear sampling.\nSource accuracy unknown. Shared PNG quantization error ≤ %s cm.\nNo missing-data or seam repair. Save explicitly after adoption.\n") % [value.dem.receipt.sources.size(),value.heightmaps.size(),str(value.dem.sampling.vertical_zero_m),str(value.dem.sampling.max_quantization_error_cm)]
	if value.dem.has("structure_fit"):
		var fitted: Dictionary=value.dem.structure_fit
		text+=I18N.t("\nEstimated bridges/tunnels fitted to this DSM: %d roads, %d nodes; %d anchor pads levelled, %d samples cut under decks, %d filled over tunnels (largest change %d cm); %d cells re-encoded. Disclosed estimate; terrain and roads share one Undo.\n") % [fitted.changed_roads,fitted.changed_nodes,fitted.pads,fitted.clamped,fitted.filled,maxi(fitted.max_pad_cm,maxi(fitted.max_cut_cm,fitted.max_fill_cm)),fitted.fitted_cells]
	if value.dem.has("grounding"):
		text+=I18N.t("\nEstimated building bases: %d changed; %d partly outside this DEM left unchanged. Minimum sampled perimeter height; DSM includes roofs and trees. Building heights stay unchanged. Terrain and bases share one Undo.\n") % [value.dem.grounding.changes.size(),value.dem.grounding.skipped_partial]
	for index in range(value.heightmaps.size()):
		var record: Dictionary=value.heightmaps[index]
		text+=I18N.t("\nCell (%d, %d) · spacing %d cm · %s\nDerived PNG SHA-256: %s\n") % [record.cell.x,record.cell.y,record.spacing_cm,I18N.t("replaces an active tile (Undo retained)") if value.previous[index]!=null else I18N.t("new active terrain"),str(record.path).get_file().get_basename()]
	for item: Dictionary in value.dem.receipt.sources:
		text+=I18N.t("\nSource tile %s · GLO-%d%s · %d bytes\nSHA-256: %s\n%s\n%s\n") % [str(item.tile),item.resolution_m,I18N.t(" (404 fallback)") if item.fallback90 else "",item.source.bytes,item.source.sha256,item.source.name,item.notice]
	return text+I18N.t("\nLicense: ")+LICENSE


func _stage_cells(terrain: RefCounted, result: Dictionary, reviewed: Dictionary, destination: String, context: Dictionary = {}) -> String:
	if result.get("review") is not Dictionary or result.get("raster") is not Dictionary or result.get("outputs") is not Array: return "Invalid DEM mosaic result."
	var receipt: Dictionary = result.review
	var raster: Dictionary = result.raster
	if reviewed.get("sources") is not Array or reviewed.sources.is_empty() or reviewed.sources.size()>MAX_SOURCES or receipt.get("sources") is not Array or receipt.sources.size()!=reviewed.sources.size(): return "Invalid DEM mosaic sources."
	LIMITS.over(limit_warnings, "dem_sources", reviewed.sources.size(), WARN_SOURCES, "DEM source tiles")
	var contract := receipt.duplicate(true)
	contract.sources = reviewed.sources
	if JSON.stringify(contract) != JSON.stringify(reviewed) or reviewed.get("release")!="2021" or reviewed.get("license")!=LICENSE or reviewed.get("vertical_crs")!="EPSG:3855 / EGM2008 metres": return "DEM mosaic review changed."
	for index in range(reviewed.sources.size()):
		var expected: Dictionary = reviewed.sources[index]
		var captured: Dictionary = receipt.sources[index]
		var compared := captured.duplicate(true)
		compared.source = expected.source
		if compared != expected or int(expected.resolution_m) not in [30,90] or expected.notice != NOTICE % int(expected.resolution_m): return "DEM source contract changed."
		var path := destination + ".source-%d.tif" % index
		if captured.get("source") is not Dictionary or captured.source.get("captured_path")!=path or not TYPES._hex(captured.source.get("sha256"),64) or not TYPES._count(captured.source.get("bytes"),MAX_SOURCE_BYTES): return "Invalid captured DEM identity."
		for key: String in expected.source:
			if captured.source.get(key)!=expected.source[key]: return "Captured DEM differs from review."
		var file := FileAccess.open(path,FileAccess.READ)
		if file==null: return "Captured DEM is missing."
		var size := file.get_length()
		file.close()
		# The native worker already hashed this capture in the same process.
		var verified: bool = context.get("verified_files", {}).get(path, {}).get("sha256", "") == captured.source.sha256
		if size!=int(captured.source.bytes) or (not verified and FileAccess.get_sha256(path)!=captured.source.sha256): return "Captured DEM changed."
		LIMITS.over(limit_warnings, "dem_tile_bytes", size, WARN_SOURCE_BYTES, "DEM tile size in bytes")
	var options: Dictionary = reviewed.options
	var doc: Dictionary = terrain.store.document
	if options.cell_size_cm!=doc.cell_size_cm or options.map_min_cm!=doc.bounds.min or options.get("cell_count") is not Array or options.cell_count.size()!=2: return "DEM map grid changed."
	if not TYPES._count(options.cell_count[0],MAX_CELLS) or not TYPES._count(options.cell_count[1],MAX_CELLS) or options.cell_count[0]<1 or options.cell_count[1]<1: return "Invalid DEM cell count."
	if int(options.cell_count[0])*int(options.cell_count[1])>MAX_CELLS: return "DEM exceeds 1024 candidate cells."
	LIMITS.over(limit_warnings, "dem_cells", int(options.cell_count[0])*int(options.cell_count[1]), WARN_CELLS, "DEM terrain cells")
	var expected_cells: Array = []
	for y in range(int(options.cell_count[1])):
		for x in range(int(options.cell_count[0])): expected_cells.append([float(options.cell[0])+x,float(options.cell[1])+y])
	if reviewed.get("cells")!=expected_cells or result.outputs.size()!=expected_cells.size(): return "Missing or changed DEM cells."
	if raster.get("vertical_zero_m")!=options.vertical_zero_m or raster.get("resampling")!="bilinear across full-resolution COG sample centres; local rows +northing" or raster.get("source_accuracy_cm")!=null or not TYPES._finite(raster.get("offset_cm"),-1000000,1000000) or not TYPES._count(raster.get("step_cm"),100) or raster.step_cm<1: return "Invalid mosaic sampling contract."
	if raster.offset_cm!=floor(float(raster.offset_cm)) or raster.get("max_quantization_error_cm")!=0.5+float(raster.step_cm)/2: return "Invalid mosaic quantization."
	var records: Array = []
	var previous: Array = []
	var sampled: Array = []
	var sampled_blobs := {}
	for index in range(expected_cells.size()):
		var output: Dictionary = result.outputs[index]
		var path := destination+".cell-%d.png" % index
		if output.get("cell")!=expected_cells[index] or output.get("png_path")!=path or not TYPES._hex(output.get("png_sha256"),64) or not TYPES._count(output.get("png_bytes"),PNG.MAX_BYTES): return "Invalid DEM cell identity."
		var payload := FILES.read(path,PNG.MAX_BYTES)
		if payload.has("error") or payload.bytes.size()!=int(output.png_bytes) or FILES.digest(payload.bytes)!=output.png_sha256: return "Derived DEM PNG changed."
		var record := {"cell":{"x":int(expected_cells[index][0]),"y":int(expected_cells[index][1])},"path":"editor/"+output.png_sha256+".png","spacing_cm":int(options.spacing_cm),"offset_cm":int(raster.offset_cm),"step_cm":int(raster.step_cm),"source_accuracy_cm":null}
		sampled.append(record)
		sampled_blobs[record.path]=payload.bytes
	# Estimated city structures assume flat terrain; fit them before staging so
	# fitted cells, roads and building bases share one candidate and one Undo.
	var fit: Dictionary = STRUCTURE_FIT.prepare(terrain.store,sampled,sampled_blobs,options) if not doc.roads.is_empty() else {"patches":[],"fitted":{}}
	if fit.has("error"): return fit.error
	for index in range(expected_cells.size()):
		var record: Dictionary = sampled[index]
		var cell := Vector2i(record.cell.x,record.cell.y)
		var fitted: Dictionary = fit.fitted.get(cell,{})
		var bytes: PackedByteArray = fitted.get("bytes",sampled_blobs[record.path])
		var layer := preload("./heightmap_import_layer.gd").new()
		var failure: String = layer.stage(terrain,destination+".cell-%d.png" % index,cell,int(options.spacing_cm),fitted.get("offset_cm",record.offset_cm),fitted.get("step_cm",record.step_cm),0,{"source":"Copernicus 2021 mosaic","license":LICENSE},false,"",{"png_bytes":bytes})
		if failure!="":
			layer.discard();discard();return failure
		LIMITS.merge(limit_warnings, layer.limit_warnings)
		records.append(layer.value.heightmap.duplicate(true))
		previous.append(layer.value.previous)
		_patches.append(layer._patches[0].duplicate(true))
		_blobs.merge(layer._blobs)
		_cells.append_array(layer._cells)
		layer.discard()
	_patches.append_array(fit.patches)
	# The stored notice names each source file with its size and hash; local and
	# capture paths stay with the in-flight review and never enter the map.
	# Helper warnings of the review and of this run join the candidate review;
	# they never enter the stored attribution notice.
	LIMITS.merge_texts(limit_warnings, reviewed.get("limit_warnings"))
	LIMITS.merge_texts(limit_warnings, result.get("limit_warnings"))
	var stored: Dictionary = receipt.duplicate(true)
	stored.erase("limit_warnings")
	stored.options.source = str(stored.options.source).trim_suffix("/").trim_suffix("\\").get_file()
	for item: Dictionary in stored.sources:
		item.source = {"name":str(item.source.path).get_file(),"bytes":item.source.bytes,"sha256":item.source.sha256}
	value={"import_version":1,"adapter":"copernicus-dem-v1","layer_id":context.get("layer_id", Crypto.new().generate_random_bytes(16).hex_encode()),"heightmaps":records,"previous":previous,"dem":{"receipt":stored,"sampling":raster.duplicate(true)}}
	if not fit.get("receipt",{}).is_empty(): value.dem.structure_fit=fit.receipt
	if context.get("ground_buildings",false):
		var grounded:=preload("./dem_building_grounding.gd").prepare(terrain.store,records,_blobs,options)
		if grounded.has("error"): discard();return grounded.error
		LIMITS.merge(limit_warnings, grounded.get("limit_warnings"))
		_patches.append_array(grounded.patches)
		value.dem.grounding=grounded.receipt
		if not doc.buildings.is_empty() and _cells.is_empty():
			for record: Dictionary in records: _cells.append(Vector2i(record.cell.x,record.cell.y))
	var notice := {"source":"Copernicus 2021 mosaic#"+value.layer_id,"license":LICENSE,"notice":JSON.stringify(value)}
	_patches.append({"field":"attributions","id":terrain.store.record_id("attributions",notice),"before":null,"after":notice})
	_patches.append({"field":"free_roam","id":"","before":terrain.store.document.free_roam,"after":true})
	var failure := FILES.apply(terrain.store,"Adopt DEM mosaic",_patches,_blobs,_cells,true,context)
	if failure!="":
		discard();return failure
	return _retain_dependencies(terrain.store) if context.is_empty() else ""
