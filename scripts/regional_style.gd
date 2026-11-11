extends RefCounted
## Apply changed regional art direction to automatically classified building solids.
## Source/author materials and explicit author architecture retain precedence.
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")
const OWNER := "mapeditor-regional-style-v1"

static func evidence(document: Dictionary) -> Dictionary:
	var result := {}
	for attribution: Dictionary in document.get("attributions", []):
		var parser := JSON.new()
		if parser.parse(str(attribution.get("notice", ""))) != OK or parser.data is not Dictionary: continue
		var notice: Dictionary = parser.data
		var rows: Array = []
		if notice.get("adapter") == "osm-extract-v1":
			for group: Dictionary in notice.get("coordinates", {}).get("osm_city", {}).get("groups", []):
				if group.get("regional") is Dictionary: rows.append(group.regional)
		elif notice.get("adapter") == "mapeditor-regional-v1": rows = notice.get("objects", [])
		elif notice.get("adapter") == OWNER: result.merge(notice.get("evidence", {}), true)
		for row: Dictionary in rows:
			for identity: String in row.get("record_ids", []): result[identity] = row.get("evidence", {}).duplicate(true)
	return result

static func centre(solid: Dictionary) -> Vector2:
	var point := Vector2.ZERO
	for vertex: Array in solid.footprint: point += Vector2(vertex[0],vertex[1]) / 100.0
	return point / float(solid.footprint.size())

static func patches(store: RefCounted, before: Dictionary, after: Dictionary) -> Array:
	var result: Array = []
	var facts := evidence(store.document)
	var changed_facts := {}
	for building: Dictionary in store.document.buildings:
		var style := str(building.get("style_id", "")).split("/")
		if style.size() != 4 or style[0] != "building" or not facts.has(building.id): continue
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
				if str(source.get("material", "")).begins_with("context:"): material = PROFILE.CATALOG.data.architectures[next.architecture].material
				key = "building/%s/%s/%s" % [next.architecture, style[2], material]
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
