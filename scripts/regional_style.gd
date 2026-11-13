extends RefCounted
## Apply changed regional art direction to automatically classified building solids.
## Source/author materials and explicit author architecture retain precedence.
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")
const OWNER := "mapeditor-regional-style-v1"

static func evidence(document: Dictionary, errors: Array = []) -> Dictionary:
	var result := {}
	for attribution: Dictionary in document.get("attributions", []):
		var parser := JSON.new()
		if parser.parse(str(attribution.get("notice", ""))) != OK or parser.data is not Dictionary: continue
		var notice: Dictionary = parser.data
		var rows: Array = []
		if notice.get("adapter") == "osm-extract-v1":
			var decoded := preload("./source_receipt.gd").rows(notice.get("coordinates",{}).get("osm_city",{}),"groups")
			if not decoded.ok: errors.append(decoded.error); return {}
			for group: Dictionary in decoded.data:
				if group.get("regional") is Dictionary: rows.append(group.regional)
		elif notice.get("adapter") == "mapeditor-regional-v1":
			var decoded := preload("./source_receipt.gd").rows(notice,"objects")
			if not decoded.ok: errors.append(decoded.error); return {}
			rows = decoded.data
		elif notice.get("adapter") == OWNER: result.merge(notice.get("evidence", {}), true)
		for row: Dictionary in rows:
			for identity: String in row.get("record_ids", []): result[identity] = row.get("evidence", {}).duplicate(true)
	return result

## The architecture's catalogue default for one building type; present fields of
## its optional `uses` entry replace the architecture's (as in MapKit and the importer).
static func use_default(architecture: String, kind: String, field: String) -> String:
	var profile: Dictionary = PROFILE.CATALOG.data.architectures[architecture]
	return str(profile.get("uses", {}).get(kind, {}).get(field, profile[field]))

static func centre(solid: Dictionary) -> Vector2:
	var point := Vector2.ZERO
	for vertex: Array in solid.footprint: point += Vector2(vertex[0],vertex[1]) / 100.0
	return point / float(solid.footprint.size())

static func patches(store: RefCounted, before: Dictionary, after: Dictionary, errors: Array = []) -> Array:
	var result: Array = []
	var facts := evidence(store.document,errors)
	if not errors.is_empty(): return []
	var changed_facts := {}
	for building: Dictionary in store.document.buildings:
		var style := str(building.get("style_id", "")).split("/")
		if not style.size() in [4,6] or style[0] != "building" or not facts.has(building.id): continue
		var source: Dictionary = facts[building.id]
		if source.get("architecture") == "author": continue
		var grouped := {}
		var solids: Array = [building] + building.get("parts", [])
		for solid: Dictionary in solids:
			var key := str(building.style_id)
			var point := centre(solid)
			var old := PROFILE.design_at(before, point)
			var next := PROFILE.design_at(after, point)
			if old.architecture != next.architecture:
				var material: String = style[3]
				if str(source.get("material", "")).begins_with("context:"): material = use_default(next.architecture, style[2], "material")
				key = "building/%s/%s/%s" % [next.architecture, style[2], material]
				if style.size() == 6:
					var roof: String = use_default(next.architecture, style[2], "roof") if str(source.get("roof_shape", "")).begins_with("context:") else style[4]
					var roof_material: String = use_default(next.architecture, style[2], "roof_material") if str(source.get("roof_material", "")).begins_with("context:") else style[5]
					# A source-qualified blue dome keeps its specific architectural
					# identity when the surrounding default changes.
					if roof_material == "blue_tile" and next.architecture != "cycladic": key = "building/%s/%s/%s" % [style[1],style[2],material]
					key += "/%s/%s" % [roof,roof_material]
			if not grouped.has(key): grouped[key] = []
			var part := {"footprint":solid.footprint.duplicate(true),"base_cm":solid.get("base_cm",building.base_cm),"height_cm":solid.get("height_cm",building.height_cm)}
			if solid.has("holes"): part.holes = solid.holes.duplicate(true)
			grouped[key].append(part)
		if grouped.size() == 1 and grouped.has(building.style_id): continue
		var first := true
		for key: String in grouped:
			var record: Dictionary = building.duplicate(true)
			record.erase("parts"); record.erase("holes")
			record.merge(grouped[key][0],true)
			if grouped[key].size() > 1: record.parts = grouped[key].slice(1)
			record.style_id = key
			if not first: record.id = "regional-style-" + (str(building.id)+"/"+key).sha256_text().left(24)
			result.append({"field":"buildings","id":record.id,"before":building if first else null,"after":record})
			changed_facts[record.id] = source.duplicate(true)
			first = false
	if not changed_facts.is_empty():
		var prior: Variant = null
		for attribution: Dictionary in store.document.attributions:
			if attribution.get("source") == OWNER: prior = attribution; break
		facts.merge(changed_facts,true)
		var record := {"source":OWNER,"license":"Authored regional profile selection","notice":JSON.stringify({"adapter":OWNER,"version":1,"evidence":facts})}
		if prior != null: result.append({"field":"attributions","id":store.record_id("attributions",prior),"before":prior,"after":null})
		result.append({"field":"attributions","id":store.record_id("attributions",record),"before":null,"after":record})
	return result
