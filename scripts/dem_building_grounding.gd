extends RefCounted
## Explicit DSM estimate for zero-base OSM and source-based regional buildings.
const TYPES := preload("./import_layer.gd")
const PROFILE := "osm-dsm-min-perimeter-v1"
const LIMITS := preload("./limit_warnings.gd")
## Work guard; above the former one million samples grounding only warns.
const MAX_SAMPLES := 16000000
const WARN_SAMPLES := 1000000

static func layers(document: Dictionary) -> Dictionary:
	var result := {}
	var active := {}
	for field in ["nodes","buildings","placements"]:
		for record: Dictionary in document.get(field, []):
			if str(record.id).begins_with("import-"): active[str(record.id).left(40)]=true
	for attribution: Dictionary in document.attributions:
		var parser := JSON.new()
		if parser.parse(attribution.notice)!=OK or parser.data is not Dictionary: continue
		var meta: Dictionary=parser.data
		if meta.get("adapter")=="osm-extract-v1" and TYPES._hex(meta.get("layer_id"),32) and meta.get("coordinates") is Dictionary:
			var prefix: String="import-"+str(meta.layer_id)+"-"
			if active.has(prefix): result[prefix]=meta.coordinates
	return result

static func regional_sources(document: Dictionary) -> Dictionary:
	var result := {}
	for attribution: Dictionary in document.attributions:
		var parser := JSON.new()
		if parser.parse(attribution.notice)!=OK or parser.data is not Dictionary or parser.data.get("adapter")!="mapeditor-regional-v1": continue
		var decoded := preload("./source_receipt.gd").rows(parser.data,"objects")
		if not decoded.ok: return {"error":decoded.error}
		for row: Dictionary in decoded.data:
			if row.get("record_ids",[]) is not Array or row.get("source_bases_cm",[]) is not Array: return {"error":"Invalid regional source base receipt."}
			for base: Variant in row.get("source_bases_cm",[]):
				if not TYPES._finite(base,-1000000,1000000) or float(base)!=floor(float(base)): return {"error":"Invalid regional source base height."}
			for id: String in row.get("record_ids",[]):
				if id.begins_with("regional-ov-"): result[id]=row.get("source_bases_cm",[]).duplicate()
	return {"records":result}

static func prepare(store: RefCounted, records: Array, blobs: Dictionary, options: Dictionary) -> Dictionary:
	var patches: Array=[]
	var changes: Array=[]
	var sources:=layers(store.document)
	var regional:=regional_sources(store.document)
	if regional.has("error"): return regional
	var eligible: Array=[]
	var skipped:=0
	var samples:=0
	var size:=int(store.document.cell_size_cm)
	var low: Array=[store.document.bounds.min[0]+options.cell[0]*size,store.document.bounds.min[1]+options.cell[1]*size]
	var high: Array=[low[0]+options.cell_count[0]*size,low[1]+options.cell_count[1]*size]
	for building: Dictionary in store.document.buildings:
		var prefix:=str(building.id).left(40)
		var auxiliary: bool=regional.records.has(building.id)
		if not auxiliary and (not sources.has(prefix) or building.base_cm!=0): continue
		if auxiliary and sources.is_empty(): return {"error":"Regional buildings lack their imported coordinate frame."}
		var frame: Dictionary=sources.values()[0] if auxiliary else sources[prefix]
		for key in ["mode","origin","local_origin_m"]:
			if frame.get(key)!=options.coordinates.get(key): return {"error":"Projection origin conflicts with active imported height data."}
		var source_bases: Array=regional.records[building.id] if auxiliary else []
		var building_solids: Array=[building]+building.get("parts",[])
		if source_bases.is_empty():
			source_bases.resize(building_solids.size()); source_bases.fill(0)
		if source_bases.size()!=building_solids.size(): return {"error":"Regional building source bases do not match its parts."}
		var unchanged := true
		for k in building_solids.size():
			if int(building_solids[k].get("base_cm",building.base_cm))!=int(source_bases[k]): unchanged=false
		if not unchanged: continue # Preserve authored or previously grounded bases.
		# Each solid (footprint, then city building parts) is grounded on its own.
		var solids: Array=[]
		var covered:=true
		var counted:=0
		var solid_rings: Array=[[building.footprint]+building.get("holes",[])]
		for part: Dictionary in building.get("parts",[]):
			solid_rings.append([part.footprint]+part.get("holes",[]))
		for rings: Array in solid_rings:
			var points: Array=[]
			for ring: Array in rings:
				for index in range(ring.size()):
					var point: Array=ring[index]
					var next: Array=ring[(index+1)%ring.size()]
					for axis in range(2):
						if point[axis]<low[axis] or point[axis]>high[axis]: covered=false
					points.append(Vector2(point[0],point[1]))
					points.append(Vector2((point[0]+next[0])*0.5,(point[1]+next[1])*0.5))
			solids.append(points)
			counted+=points.size()
		if not covered:
			skipped+=1
			continue
		samples+=counted
		if samples>MAX_SAMPLES: return {"error":"Building grounding exceeds 16 million terrain samples."}
		eligible.append([building,solids,source_bases])
	# MapKit samples the newly reviewed DEM. The thin view excludes road grading;
	# final candidate admission still validates the full map and all selected cells.
	var native: RefCounted=store.working_snapshot().fork()
	var document: Dictionary=store.document.duplicate(true)
	for field in ["nodes","roads","buildings","zones","placements","assets","attributions","pois","surface_areas","water_bodies","gimmicks","barriers"]:
		if document.has(field): document[field]=[]
	document.erase("assembled_track")
	document.heightmaps=records
	var notes: Array = []
	var result: Dictionary=JSON.parse_string(native.set_document(JSON.stringify(document),store.project_path))
	LIMITS.native(notes, result)
	if not result.ok: return {"error":store.reason(result)}
	result=JSON.parse_string(native.provide_resources(blobs))
	LIMITS.native(notes, result)
	if not result.ok: return {"error":store.reason(result)}
	for entry: Array in eligible:
		var bases: Array=[]
		for solid_index in entry[1].size():
			var points: Array=entry[1][solid_index]
			var base:=1000001
			for point: Vector2 in points:
				result=JSON.parse_string(native.height(point))
				if not result.ok: return {"error":store.reason(result)}
				base=mini(base,int(result.data.height))
			bases.append(base+int(entry[2][solid_index]))
		var before: Dictionary=entry[0]
		var after:=before.duplicate(true)
		after.base_cm=bases[0]
		for k in range(1,bases.size()):
			if bases[k]==bases[0]: after.parts[k-1].erase("base_cm")
			else: after.parts[k-1].base_cm=bases[k]
		if after==before: continue
		var base: int=bases[0]
		patches.append({"field":"buildings","id":before.id,"before":before.duplicate(true),"after":after})
		changes.append({"id":before.id,"before_cm":before.base_cm,"after_cm":base})
	# Imported street furniture still at the flat terrain base stands on the DEM
	# at its anchor point (the same estimate, one sample each).
	var furniture := 0
	for placement: Dictionary in store.document.get("placements", []):
		var prefix:=str(placement.id).left(40)
		if not sources.has(prefix) or int(placement.position[1])!=int(store.document.get("terrain_base_cm",0)): continue
		var at := Vector2(placement.position[0],placement.position[2])
		if at.x<low[0] or at.y<low[1] or at.x>high[0] or at.y>high[1]: continue
		result=JSON.parse_string(native.height(at))
		if not result.ok: return {"error":store.reason(result)}
		var after: Dictionary=placement.duplicate(true)
		after.position[1]=int(result.data.height)
		if after==placement: continue
		patches.append({"field":"placements","id":placement.id,"before":placement.duplicate(true),"after":after})
		furniture+=1
	LIMITS.over(notes, "dem_grounding_samples", samples, WARN_SAMPLES, "Terrain samples for building grounding")
	return {"patches":patches,"receipt":{"profile":PROFILE,"estimated":true,"samples":samples,"skipped_partial":skipped,"changes":changes,"placements":furniture},"limit_warnings":notes}

static func valid_patch(patch: Dictionary, enabled: bool, regional: bool = false) -> bool:
	if enabled and patch.get("field")=="placements" and patch.get("before") is Dictionary and patch.get("after") is Dictionary:
		# Only the height of an imported placement may change.
		var moved: Dictionary=patch.after.duplicate(true)
		if moved.get("position") is not Array or moved.position.size()!=3 or not TYPES._finite(moved.position[1],-1000000,1000000): return false
		moved.position[1]=patch.before.position[1]
		return moved==patch.before and str(patch.get("id","")).begins_with("import-") and patch.before.get("id")==patch.id
	if not enabled or patch.get("field")!="buildings" or patch.get("before") is not Dictionary or patch.get("after") is not Dictionary: return false
	var before: Dictionary=patch.before
	var after: Dictionary=patch.after
	if (not regional and before.get("base_cm")!=0) or not TYPES._finite(after.get("base_cm"),-1000000,1000000): return false
	if not str(patch.get("id","")).begins_with("regional-ov-" if regional else "import-"): return false
	var expected:=before.duplicate(true)
	expected.base_cm=after.base_cm
	# City building parts: only each solid's base may change, from zero.
	if before.get("parts") is Array and after.get("parts") is Array and before.parts.size()==after.parts.size():
		for k in range(before.parts.size()):
			var part: Variant=after.parts[k]
			if part is not Dictionary or (not regional and int(before.parts[k].get("base_cm",0))!=0): return false
			if part.has("base_cm"):
				if not TYPES._finite(part.base_cm,-1000000,1000000): return false
				expected.parts[k].base_cm=part.base_cm
			else: expected.parts[k].erase("base_cm")
	return after==expected and before.get("id")==patch.id
