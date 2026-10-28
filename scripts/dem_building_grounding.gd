extends RefCounted
## Explicit DSM estimate for zero-base OSM buildings. Never structural roads.
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

static func prepare(store: RefCounted, records: Array, blobs: Dictionary, options: Dictionary) -> Dictionary:
	var patches: Array=[]
	var changes: Array=[]
	var sources:=layers(store.document)
	var eligible: Array=[]
	var skipped:=0
	var samples:=0
	var size:=int(store.document.cell_size_cm)
	var low: Array=[store.document.bounds.min[0]+options.cell[0]*size,store.document.bounds.min[1]+options.cell[1]*size]
	var high: Array=[low[0]+options.cell_count[0]*size,low[1]+options.cell_count[1]*size]
	for building: Dictionary in store.document.buildings:
		var prefix:=str(building.id).left(40)
		if not sources.has(prefix) or building.base_cm!=0: continue
		for key in ["mode","origin","local_origin_m"]:
			if sources[prefix].get(key)!=options.coordinates.get(key): return {"error":"Projection origin conflicts with active imported height data."}
		# Each solid (footprint, then city building parts) is grounded on its own.
		var solids: Array=[]
		var covered:=true
		var counted:=0
		var solid_rings: Array=[[building.footprint]+building.get("holes",[])]
		for part: Dictionary in building.get("parts",[]):
			if int(part.get("base_cm",0))!=0: covered=false
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
		eligible.append([building,solids])
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
		for points: Array in entry[1]:
			var base:=1000001
			for point: Vector2 in points:
				result=JSON.parse_string(native.height(point))
				if not result.ok: return {"error":store.reason(result)}
				base=mini(base,int(result.data.height))
			bases.append(base)
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

static func valid_patch(patch: Dictionary, enabled: bool) -> bool:
	if enabled and patch.get("field")=="placements" and patch.get("before") is Dictionary and patch.get("after") is Dictionary:
		# Only the height of an imported placement may change.
		var moved: Dictionary=patch.after.duplicate(true)
		if moved.get("position") is not Array or moved.position.size()!=3 or not TYPES._finite(moved.position[1],-1000000,1000000): return false
		moved.position[1]=patch.before.position[1]
		return moved==patch.before and str(patch.get("id","")).begins_with("import-") and patch.before.get("id")==patch.id
	if not enabled or patch.get("field")!="buildings" or patch.get("before") is not Dictionary or patch.get("after") is not Dictionary: return false
	var before: Dictionary=patch.before
	var after: Dictionary=patch.after
	if before.get("base_cm")!=0 or not TYPES._finite(after.get("base_cm"),-1000000,1000000) or not str(patch.get("id","")).begins_with("import-"): return false
	var expected:=before.duplicate(true)
	expected.base_cm=after.base_cm
	# City building parts: only each solid's base may change, from zero.
	if before.get("parts") is Array and after.get("parts") is Array and before.parts.size()==after.parts.size():
		for k in range(before.parts.size()):
			var part: Variant=after.parts[k]
			if part is not Dictionary or int(before.parts[k].get("base_cm",0))!=0: return false
			if part.has("base_cm"):
				if not TYPES._finite(part.base_cm,-1000000,1000000): return false
				expected.parts[k].base_cm=part.base_cm
	return after==expected and before.get("id")==patch.id
