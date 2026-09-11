extends RefCounted
## Editor invalidation index, never generation or physics. Native queries own cells.
const EDIT := preload("./workbench_edit.gd")
const MAX_REFERENCES := 200000

static func build(native: RefCounted, document: Dictionary, cancelled: Callable = Callable()) -> Dictionary:
	var cells := {}
	var references := 0
	for entry in EDIT.entries(document):
		if cancelled.is_valid() and cancelled.call():
			return {"ok": false, "error": {"code": "E_CANCELLED", "message": "Index build cancelled."}}
		var points := EDIT.points(entry.field, entry.record)
		var low := points[0]
		var high := low
		for point: Vector2 in points:
			low = low.min(point)
			high = high.max(point)
		# Deliberate Editor over-invalidation halo, not a generator constant.
		# Authored proxy dimensions/offsets can be larger than this halo.
		var margin := float(document.cell_size_cm)
		if entry.field == "placements":
			for asset: Dictionary in document.assets:
				if asset.id != entry.record.asset_id: continue
				for box: Dictionary in asset.collision:
					for axis in [0, 2]: margin = maxf(margin, absf(box.center[axis]) + float(box.size_cm[axis]))
				for convex: Dictionary in asset.get("convex_collision", []):
					for vertex: Array in convex.vertices:
						margin = maxf(margin, maxf(absf(vertex[0]), absf(vertex[2])))
		low -= Vector2.ONE * margin
		high += Vector2.ONE * margin
		var queried: Dictionary = JSON.parse_string(native.query_cells(int(low.x), int(low.y), int(high.x), int(high.y), 16384))
		if not queried.ok: return queried
		for cell: Dictionary in queried.data.occupancy_cells:
			var key := "%d/%d" % [cell.x, cell.y]
			if not cells.has(key): cells[key] = []
			cells[key].append(entry)
			references += 1
			if references > MAX_REFERENCES:
				return {"ok": false, "error": {"code": "E_INDEX_BUDGET", "message": "Preview index exceeds 200000 references; reduce the working map."}}
	return {"ok": true, "data": {"cells": cells, "references": references}}

static func signature(document: Dictionary, hashes: Dictionary, index: Dictionary, cell: Vector2i) -> String:
	var local: Array = index.cells.get("%d/%d" % [cell.x, cell.y], [])
	var source := {}
	for field in ["map_id", "bounds", "cell_size_cm", "seed", "recipe_version", "theme", "terrain_base_cm", "assets"]:
		source[field] = document.get(field)
	source.local = local
	source.payloads = {}
	for asset: Dictionary in document.assets: source.payloads[str(asset.path)] = hashes[str(asset.path)]
	for tile: Dictionary in document.heightmaps:
		if int(tile.cell.x) == cell.x and int(tile.cell.y) == cell.y:
			source.heightmap = tile
			source.payloads[str(tile.path)] = hashes[str(tile.path)]
	# Shared junctions, inferred sidewalks, vegetation spacing and ordered repetition
	# can depend on remote source records. Keep a conservative dependency closure.
	for entry: Dictionary in local:
		if entry.field in ["roads", "surface_areas", "zones", "repetitions"]:
			for field in ["roads", "nodes", "buildings", "surface_areas", "zones", "placements", "repetitions"]:
				source[field] = document.get(field, [])
	return JSON.stringify(source).sha256_text()
