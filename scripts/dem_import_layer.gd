extends "./heightmap_import_layer.gd"
const LICENSE := "https://copernicus-dem-30m.s3.amazonaws.com/readme.html#license"
const NOTICE := "produced using Copernicus WorldDEM-%d © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"

func stage_dem(terrain: RefCounted, result: Dictionary, reviewed: Dictionary, destination: String) -> String:
	discard()
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
	var options: Dictionary = reviewed.options
	if raster.get("vertical_zero_m") != options.vertical_zero_m or raster.get("resampling") != "bilinear at full-resolution COG sample centres; local rows +northing" or raster.get("source_accuracy_cm") != null or not TYPES._finite(raster.get("offset_cm"),-1000000,1000000) or not TYPES._finite(raster.get("step_cm"),1,100): return "Invalid DEM sampling contract."
	if float(raster.offset_cm) != floor(float(raster.offset_cm)) or not TYPES._count(raster.step_cm,100): return "DEM height offset/step must be integer cm."
	var doc: Dictionary = terrain.store.document
	if options.cell_size_cm != doc.cell_size_cm or options.map_min_cm != doc.bounds.min: return "DEM map grid changed."
	var failure := stage(terrain,result.png_path,Vector2i(options.cell[0],options.cell[1]),int(options.spacing_cm),int(raster.offset_cm),int(raster.step_cm),0,{"source":"Copernicus 2021 GLO-%d" % int(receipt.resolution_m),"license":LICENSE,"notice":receipt.notice})
	if failure != "": return failure
	value.adapter = "copernicus-dem-v1"
	value.resampled = true
	value.dem = {"receipt":receipt.duplicate(true),"sampling":raster.duplicate(true)}
	_patches.back().after.notice = JSON.stringify(value)
	_patches.back().id = terrain.store.record_id("attributions",_patches.back().after)
	failure = FILES.apply(terrain.store,"Adopt DEM heightmap layer",_patches,_blobs,_cells,true)
	if failure != "": discard()
	return failure

func summary() -> String:
	if value.is_empty(): return "No DEM candidate."
	var receipt: Dictionary = value.dem.receipt
	var sampling: Dictionary = value.dem.sampling
	var introduction := "Copernicus 2021 GLO-%d · DSM, including buildings and vegetation\nOriginal COG: %d bytes · SHA-256: %s\nHeight: EGM2008 metres − %s m at local zero\nExplicit bilinear sampling; source accuracy unknown. PNG quantization error ≤ %s cm.\n\n" % [int(receipt.resolution_m),int(receipt.source.bytes),receipt.source.sha256,str(sampling.vertical_zero_m),str(sampling.max_quantization_error_cm)]
	return introduction + super.summary().replace(value.source.name,"Derived PNG").replace("no resampling", "explicit bilinear resampling") + "\n\nDEM source / processing:\n" + JSON.stringify(value.dem, "  ")
