extends "./heightmap_import_layer.gd"
const LICENSE := "https://copernicus-dem-30m.s3.amazonaws.com/readme.html#license"
const NOTICE := "produced using Copernicus WorldDEM-%d © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"

func stage_dem(terrain: RefCounted, result: Dictionary, reviewed: Dictionary, destination: String, context: Dictionary = {}) -> String:
	discard()
	if reviewed.get("options") is not Dictionary: return "Missing DEM options."
	var options: Dictionary = reviewed.options
	if options.get("coordinates") is not Dictionary or not TYPES._finite(options.get("vertical_zero_m"), -10000, 10000): return "Invalid DEM height reference."
	var frame_error: String = preload("./import_vertical.gd").frame_error(terrain.store.document, {"target_crs":"EPSG:3855 / EGM2008 metres", "vertical_zero_m":options.get("vertical_zero_m")}, options.get("coordinates", {}))
	if frame_error != "": return frame_error
	if reviewed.get("adapter") == "copernicus-dem-v2": return _stage_mosaic(terrain,result,reviewed,destination,context)
	if result.get("review") is not Dictionary or result.get("raster") is not Dictionary: return "Invalid DEM result."
	var receipt: Dictionary = result.review
	var raster: Dictionary = result.raster
	var contract := receipt.duplicate(true)
	contract.source = reviewed.get("source")
	for key: String in reviewed:
		if contract.get(key) != reviewed[key]: return "DEM review field changed: " + key + " expected " + JSON.stringify(reviewed[key]) + " actual " + JSON.stringify(contract.get(key))
	if contract.size() != reviewed.size() or receipt.get("adapter") != "copernicus-dem-v1" or receipt.get("release") != "2021" or receipt.get("license") != LICENSE or not TYPES._count(receipt.get("resolution_m"),90) or int(receipt.resolution_m) not in [30,90]: return "DEM review contract changed."
	if receipt.get("notice") != NOTICE % int(receipt.resolution_m) or receipt.get("vertical_crs") != "EPSG:3855 / EGM2008 metres": return "Invalid DEM source/vertical contract."
	if receipt.get("source") is not Dictionary or receipt.source.get("captured_path") != destination or not TYPES._hex(receipt.source.get("sha256"),64) or not TYPES._count(receipt.source.get("bytes"),64*1024*1024): return "Invalid captured DEM identity."
	for key: String in reviewed.source:
		if receipt.source.get(key) != reviewed.source[key]: return "Captured DEM differs from reviewed source: " + key
	var source_file := FileAccess.open(destination,FileAccess.READ)
	if source_file == null: return "Captured DEM is missing."
	var source_size := source_file.get_length()
	source_file.close()
	if source_size != int(receipt.source.bytes) or FileAccess.get_sha256(destination) != receipt.source.sha256: return "Captured DEM changed."
	if result.get("png_path") != destination + ".png" or not TYPES._hex(result.get("png_sha256"),64) or not TYPES._count(result.get("png_bytes"),PNG.MAX_BYTES): return "Invalid DEM PNG identity."
	var payload := FILES.read(result.png_path,PNG.MAX_BYTES)
	if payload.has("error") or payload.bytes.size() != int(result.png_bytes) or FILES.digest(payload.bytes) != result.png_sha256: return "Derived DEM PNG changed."
	if raster.get("vertical_zero_m") != options.vertical_zero_m or raster.get("resampling") != "bilinear at full-resolution COG sample centres; local rows +northing" or raster.get("source_accuracy_cm") != null or not TYPES._finite(raster.get("offset_cm"),-1000000,1000000) or not TYPES._finite(raster.get("step_cm"),1,100): return "Invalid DEM sampling contract."
	if float(raster.offset_cm) != floor(float(raster.offset_cm)) or not TYPES._count(raster.step_cm,100): return "DEM height offset/step must be integer cm."
	var doc: Dictionary = terrain.store.document
	if options.cell_size_cm != doc.cell_size_cm or options.map_min_cm != doc.bounds.min: return "DEM map grid changed."
	var failure := stage(terrain,result.png_path,Vector2i(options.cell[0],options.cell[1]),int(options.spacing_cm),int(raster.offset_cm),int(raster.step_cm),0,{"source":"Copernicus 2021 GLO-%d" % int(receipt.resolution_m),"license":LICENSE,"notice":receipt.notice},false,str(context.get("layer_id", "")))
	if failure != "": return failure
	value.adapter = "copernicus-dem-v1"
	value.resampled = true
	value.dem = {"receipt":receipt.duplicate(true),"sampling":raster.duplicate(true)}
	_patches.back().after.notice = JSON.stringify(value)
	_patches.back().id = terrain.store.record_id("attributions",_patches.back().after)
	failure = FILES.apply(terrain.store,"Adopt DEM heightmap layer",_patches,_blobs,_cells,true,context)
	if failure != "":
		discard()
		return failure
	return _retain_dependencies(terrain.store) if context.is_empty() else ""

func summary() -> String:
	if value.is_empty(): return "No DEM candidate."
	if value.get("adapter") == "copernicus-dem-v2":
		var text := "Copernicus 2021 DSM · %d sources → %d cells\nAdopt all terrain cells atomically; one Undo restores every previous cell.\nEGM2008 height minus %s m at local zero; explicit bilinear sampling.\nSource accuracy unknown. Shared PNG quantization error ≤ %s cm.\nNo missing-data or seam repair. Save explicitly after adoption.\n" % [value.dem.receipt.sources.size(),value.heightmaps.size(),str(value.dem.sampling.vertical_zero_m),str(value.dem.sampling.max_quantization_error_cm)]
		for index in range(value.heightmaps.size()):
			var record: Dictionary=value.heightmaps[index]
			text+="\nCell (%d, %d) · spacing %d cm · %s\nDerived PNG SHA-256: %s\n" % [record.cell.x,record.cell.y,record.spacing_cm,"replaces an active tile (Undo retained)" if value.previous[index]!=null else "new active terrain",str(record.path).get_file().get_basename()]
		for item: Dictionary in value.dem.receipt.sources:
			text+="\nSource tile %s · GLO-%d%s · %d bytes\nSHA-256: %s\n%s\n%s\n" % [str(item.tile),item.resolution_m," (404 fallback)" if item.fallback90 else "",item.source.bytes,item.source.sha256,item.source.get("path",item.source.get("url","")),item.notice]
		return text+"\nLicense: "+LICENSE
	var receipt: Dictionary = value.dem.receipt
	var sampling: Dictionary = value.dem.sampling
	var introduction := "Copernicus 2021 GLO-%d · DSM, including buildings and vegetation\nOriginal COG: %d bytes · SHA-256: %s\nHeight: EGM2008 metres − %s m at local zero\nExplicit bilinear sampling; source accuracy unknown. PNG quantization error ≤ %s cm.\n\n" % [int(receipt.resolution_m),int(receipt.source.bytes),receipt.source.sha256,str(sampling.vertical_zero_m),str(sampling.max_quantization_error_cm)]
	return introduction + super.summary().replace(value.source.name,"Derived PNG").replace("no resampling", "explicit bilinear resampling") + "\n\nDEM source / processing:\n" + JSON.stringify(value.dem, "  ")


func _stage_mosaic(terrain: RefCounted, result: Dictionary, reviewed: Dictionary, destination: String, context: Dictionary = {}) -> String:
	if result.get("review") is not Dictionary or result.get("raster") is not Dictionary or result.get("outputs") is not Array: return "Invalid DEM mosaic result."
	var receipt: Dictionary = result.review
	var raster: Dictionary = result.raster
	if reviewed.get("sources") is not Array or reviewed.sources.is_empty() or reviewed.sources.size()>4 or receipt.get("sources") is not Array or receipt.sources.size()!=reviewed.sources.size(): return "Invalid DEM mosaic sources."
	var contract := receipt.duplicate(true)
	contract.sources = reviewed.sources
	if JSON.stringify(contract) != JSON.stringify(reviewed) or reviewed.get("release")!="2021" or reviewed.get("license")!=LICENSE or reviewed.get("vertical_crs")!="EPSG:3855 / EGM2008 metres": return "DEM mosaic review changed."
	var total := 0
	for index in range(reviewed.sources.size()):
		var expected: Dictionary = reviewed.sources[index]
		var captured: Dictionary = receipt.sources[index]
		var compared := captured.duplicate(true)
		compared.source = expected.source
		if compared != expected or int(expected.resolution_m) not in [30,90] or expected.notice != NOTICE % int(expected.resolution_m): return "DEM source contract changed."
		var path := destination + ".source-%d.tif" % index
		if captured.get("source") is not Dictionary or captured.source.get("captured_path")!=path or not TYPES._hex(captured.source.get("sha256"),64) or not TYPES._count(captured.source.get("bytes"),64*1024*1024): return "Invalid captured DEM identity."
		for key: String in expected.source:
			if captured.source.get(key)!=expected.source[key]: return "Captured DEM differs from review."
		var file := FileAccess.open(path,FileAccess.READ)
		if file==null: return "Captured DEM is missing."
		var size := file.get_length()
		file.close()
		if size!=int(captured.source.bytes) or FileAccess.get_sha256(path)!=captured.source.sha256: return "Captured DEM changed."
		total+=size
	if total>64*1024*1024: return "Combined DEM source budget exceeded."
	var options: Dictionary = reviewed.options
	var doc: Dictionary = terrain.store.document
	if options.cell_size_cm!=doc.cell_size_cm or options.map_min_cm!=doc.bounds.min or options.get("cell_count") is not Array or options.cell_count.size()!=2: return "DEM map grid changed."
	if not TYPES._count(options.cell_count[0],4) or not TYPES._count(options.cell_count[1],4) or options.cell_count[0]<1 or options.cell_count[1]<1: return "Invalid DEM cell count."
	var expected_cells: Array = []
	for y in range(int(options.cell_count[1])):
		for x in range(int(options.cell_count[0])): expected_cells.append([float(options.cell[0])+x,float(options.cell[1])+y])
	if reviewed.get("cells")!=expected_cells or result.outputs.size()!=expected_cells.size(): return "Missing or changed DEM cells."
	if raster.get("vertical_zero_m")!=options.vertical_zero_m or raster.get("resampling")!="bilinear across full-resolution COG sample centres; local rows +northing" or raster.get("source_accuracy_cm")!=null or not TYPES._finite(raster.get("offset_cm"),-1000000,1000000) or not TYPES._count(raster.get("step_cm"),100) or raster.step_cm<1: return "Invalid mosaic sampling contract."
	if raster.offset_cm!=floor(float(raster.offset_cm)) or raster.get("max_quantization_error_cm")!=0.5+float(raster.step_cm)/2: return "Invalid mosaic quantization."
	var records: Array = []
	var previous: Array = []
	for index in range(expected_cells.size()):
		var output: Dictionary = result.outputs[index]
		var path := destination+".cell-%d.png" % index
		if output.get("cell")!=expected_cells[index] or output.get("png_path")!=path or not TYPES._hex(output.get("png_sha256"),64) or not TYPES._count(output.get("png_bytes"),PNG.MAX_BYTES): return "Invalid DEM cell identity."
		var payload := FILES.read(path,PNG.MAX_BYTES)
		if payload.has("error") or payload.bytes.size()!=int(output.png_bytes) or FILES.digest(payload.bytes)!=output.png_sha256: return "Derived DEM PNG changed."
		var layer := preload("./heightmap_import_layer.gd").new()
		var cell := Vector2i(expected_cells[index][0],expected_cells[index][1])
		var failure: String = layer.stage(terrain,path,cell,int(options.spacing_cm),int(raster.offset_cm),int(raster.step_cm),0,{"source":"Copernicus 2021 mosaic","license":LICENSE},false)
		if failure!="":
			layer.discard();discard();return failure
		records.append(layer.value.heightmap.duplicate(true))
		previous.append(layer.value.previous)
		_patches.append(layer._patches[0].duplicate(true))
		_blobs.merge(layer._blobs)
		_cells.append_array(layer._cells)
		layer.discard()
	value={"import_version":1,"adapter":"copernicus-dem-v2","layer_id":context.get("layer_id", Crypto.new().generate_random_bytes(16).hex_encode()),"heightmaps":records,"previous":previous,"dem":{"receipt":receipt.duplicate(true),"sampling":raster.duplicate(true)}}
	var notice := {"source":"Copernicus 2021 mosaic#"+value.layer_id,"license":LICENSE,"notice":JSON.stringify(value)}
	_patches.append({"field":"attributions","id":terrain.store.record_id("attributions",notice),"before":null,"after":notice})
	var failure := FILES.apply(terrain.store,"Adopt DEM mosaic",_patches,_blobs,_cells,true,context)
	if failure!="":
		discard();return failure
	return _retain_dependencies(terrain.store) if context.is_empty() else ""
