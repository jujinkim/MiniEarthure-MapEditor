extends RefCounted
## One worker owns each immutable native session. No scene work on this thread.
const SNAPSHOT := preload("./project_snapshot.gd")
const PAYLOADS := preload("./authoring_files.gd")
const INDEX := preload("./preview_index.gd")
const LIMITS := preload("./limit_warnings.gd")
# Preview work allowance: above it a cell is still shown or checked, with a warning.
const PREVIEW_BYTES := 256 * 1024 * 1024
# Export-report overview: warn above OVERVIEW_WARN_BYTES, omit it above OVERVIEW_BYTES.
const OVERVIEW_BYTES := 64 * 1024 * 1024
const OVERVIEW_WARN_BYTES := 4 * 1024 * 1024
# Native whole-map queries accept at most 16384 cells; larger maps are queried in windows.
const QUERY_CELLS := 16384
const QUERY_WINDOW_CELLS := 96
# Memory allowance for restoring and auditing the user's own package.
const REOPEN_MIN_BYTES := 1024 * 1024 * 1024
const REOPEN_MAX_BYTES := 8 * 1024 * 1024 * 1024
## MapKit core per-cell generation budgets (mapkit-core generation, roads,
## occupancy, courtyards, water). The game generates cells with the same core
## and refuses these cells; any other E_BUDGET is an Editor-side check budget.
const RUNTIME_CELL_BUDGETS := ["chunk triangle budget", "occupancy limit", "occupied solid budget", "road local ", "road sampling limit", "road subdivision work", "road paint exceeds", "sidewalk fragments", "courtyard topology", "water shoreline work"]
var regional_side_cells := 0
var working: RefCounted
var mutex := Mutex.new()
var cancelled := false
var progress := "Preparing snapshot"

func cancel() -> void:
	mutex.lock()
	cancelled = true
	mutex.unlock()

func stopped() -> bool:
	mutex.lock()
	var value := cancelled
	mutex.unlock()
	return value

func update(value: String) -> void:
	mutex.lock()
	progress = value
	mutex.unlock()

func status() -> String:
	mutex.lock()
	var value := progress
	mutex.unlock()
	return value

func failure(code: String, message: String) -> Dictionary:
	return {"ok": false, "error": {"code": code, "message": message}}

func run(document: Dictionary, source: String, operation: String, cell: Vector2i, cached: Dictionary, full: bool) -> Dictionary:
	var start := Time.get_ticks_usec()
	if working == null:
		working = ClassDB.instantiate("MapKitWorkingSnapshot")
		var configured: Dictionary = JSON.parse_string(working.configure(JSON.stringify(document), source))
		if not configured.ok: return configured
	if operation != "export": return _memory_preview(document, operation, cell, full, start, cached)
	var captured := SNAPSHOT.capture_working(working, source)
	if not captured.ok: return captured
	if stopped(): return failure("E_CANCELLED", "Operation cancelled; previous preview and files retained.")
	update("Validating files, seams and package inventory")
	var staged := SNAPSHOT.stage(captured.data)
	if not staged.ok: return staged
	var result := process_snapshot(staged.data, captured.data, operation, cell, cached, full)
	if result.ok and operation == "export":
		result.data.scratch = staged.data.path
	else:
		PAYLOADS.remove_scratch(staged.data.path)
	if result.ok: result.data.seconds = (Time.get_ticks_usec() - start) / 1000000.0
	return result

func _memory_preview(document: Dictionary, operation: String, cell: Vector2i, full: bool, started: int, cached: Dictionary) -> Dictionary:
	var checked: Dictionary = JSON.parse_string(working.validate_memory())
	if not checked.ok: return checked
	if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
	if operation == "preview":
		var result: Dictionary = working.generate_packed(cell.x, cell.y, false)
		if not result.ok: return result
		if cached.get("signature", "") == result.data.preview_signature:
			return {"ok":true,"data":{"reused":true,"signature":result.data.preview_signature,"cell":cell}}
		result.data.signature = result.data.preview_signature
		result.data.cell = cell
		var cost: Dictionary = JSON.parse_string(working.estimate(cell.x,cell.y))
		if not cost.ok: return cost
		# Native generation has already enforced its separate work/triangle limit.
		# Reserve the materialized output, rather than every possible road cut in
		# the conservative pre-generation estimate, before creating scene resources.
		var measured := materialized_preview_cost(cost.data, result.data)
		if measured.is_empty(): return failure("E_PREVIEW_BUDGET", "Generated counts exceed the admitted preview estimate.")
		result.data.charge = work_bytes(measured) + result.data.preview_bytes
		if result.data.charge > PREVIEW_BYTES:
			result.data.limit_warnings = []
			LIMITS.note(result.data.limit_warnings, "preview_work", int(result.data.charge), PREVIEW_BYTES, "Cell preview needs more work memory than the preview allowance")
		result.data.generation_seconds = (Time.get_ticks_usec()-started)/1000000.0
		result.data.seconds = result.data.generation_seconds
		return result
	var rows := {}
	var bounds: Dictionary = document.bounds
	var nx := ceili(float(bounds.max[0]-bounds.min[0])/document.cell_size_cm)
	var ny := ceili(float(bounds.max[1]-bounds.min[1])/document.cell_size_cm)
	for y in ny:
		for x in nx:
			if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
			var cost: Dictionary = JSON.parse_string(working.estimate(x,y))
			if not cost.ok: return cost
			var row: Dictionary = cost.data
			row.cell = Vector2i(x,y)
			row.signature = str([x,y])
			row.work_bytes = work_bytes(row)
			row.warning = "over limit" if row.work_bytes > PREVIEW_BYTES else ("high" if row.work_bytes >= PREVIEW_BYTES*3/4 else "")
			rows["%d/%d" % [x,y]] = row
			if full:
				var generated: Dictionary = working.generate_packed(x,y,false)
				if not generated.ok: return generated
	checked.data.chunk_costs = rows
	checked.data.seconds = (Time.get_ticks_usec()-started)/1000000.0
	checked.data.full_generation_cells = nx*ny if full else 0
	return checked

func process_snapshot(staged: Dictionary, snapshot: Dictionary, operation: String, cell: Vector2i, cached: Dictionary, full: bool) -> Dictionary:
	var native: RefCounted = staged.bridge
	if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
	# Export owns an immutable snapshot and never reuses preview-cache entries.
	# Native staging/package validation already checks the spatial index.
	var index := {"data": {}}
	if operation != "export":
		update("Building affected-object / cell index")
		index = INDEX.build(native, snapshot.document, stopped)
		if not index.ok: return index
	var warnings: Array = index.data.get("limit_warnings", []).duplicate(true)
	if operation == "preview":
		var signature := INDEX.signature(snapshot.document, snapshot.hashes, index.data, cell)
		if cached.get("signature", "") == signature:
			return {"ok": true, "data": {"reused": true, "signature": signature, "cell": cell}}
		var cost := allowance(native, cell, warnings)
		if not cost.ok: return cost
		var charge := int(cost.data)
		if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
		update("Generating cell %d / %d" % [cell.x, cell.y])
		var generation_started := Time.get_ticks_usec()
		var generated: Dictionary = native.generate_chunk_packed(cell.x, cell.y)
		if generated.ok: generated = native.with_presentation(generated.data)
		if not generated.ok: return generated
		generated.data.signature = signature
		generated.data.cell = cell
		generated.data.charge = charge
		if not warnings.is_empty(): generated.data.limit_warnings = warnings
		generated.data.generation_seconds = (Time.get_ticks_usec() - generation_started) / 1000000.0
		return generated
	var report: Dictionary = staged.inspection.duplicate(true)
	report.limit_warnings = snapshot.get("limit_warnings", []).duplicate(true) + warnings
	var density := density_report(native, snapshot, index.data, cached, operation != "export")
	if not density.ok: return density
	report.chunk_costs = density.data
	if operation == "density": return {"ok":true,"data":report}
	update("Preparing 2D overview")
	var overview_text: String = native.overview_json(OVERVIEW_BYTES)
	var overview: Dictionary = JSON.parse_string(overview_text)
	if not overview.ok and str(overview.error.code) != "E_MEMORY_BUDGET": return overview
	if overview.ok:
		report.overview = overview.data
		if overview_text.length() > OVERVIEW_WARN_BYTES: LIMITS.note(report.limit_warnings, "overview_bytes", overview_text.length(), OVERVIEW_WARN_BYTES, "2D overview is very large")
	else: LIMITS.note(report.limit_warnings, "overview_bytes", OVERVIEW_BYTES + 1, OVERVIEW_BYTES, "2D overview is too large and was omitted from the report")
	report.full_generation_cells = 0
	if full:
		var query := whole_map_cells(native, snapshot.document)
		if not query.ok: return query
		var over_cells := 0
		var other_budget_cells := 0
		for target: Dictionary in query.data:
			if stopped(): return failure("E_CANCELLED", "Full generation check cancelled.")
			update("Optional 3D check %d / %d" % [report.full_generation_cells + 1, report.cell_count])
			var budget := allowance(native, Vector2i(int(target.x), int(target.y)), report.limit_warnings)
			if not budget.ok: return budget
			var generated: Dictionary = native.generate_chunk_packed(int(target.x), int(target.y))
			# MapKit's per-cell generation budgets are the game's own: it refuses
			# such a cell at play time. Report the count of cells; other native
			# budget errors are plain warnings, every other error stays fatal.
			if not generated.ok and str(generated.error.code) == "E_BUDGET":
				if runtime_cell_budget(str(generated.error.get("message", ""))):
					over_cells += 1
					LIMITS.note(report.limit_warnings, "runtime_cell_generation", over_cells, 0, "Number of cells over the game's per-cell generation budget", true)
				else:
					other_budget_cells += 1
					LIMITS.note(report.limit_warnings, "cell_generation_budget", other_budget_cells, 0, "Number of cells over an Editor generation check budget")
			elif not generated.ok: return generated
			report.full_generation_cells += 1
	if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
	update("Compressing validated package")
	if regional_side_cells > 0:
		var regional: RefCounted = ClassDB.instantiate("MapKitRegionReader")
		var regional_path: String = staged.path.path_join("result.mkregions")
		var packed: Dictionary = JSON.parse_string(regional.export_project(staged.path,regional_path,regional_side_cells))
		if not packed.ok: return packed
		var budget := reopen_budget(regional_path)
		var opened: Dictionary = JSON.parse_string(regional.open_index(regional_path,budget,""))
		if not opened.ok: return opened
		var audited: Dictionary = JSON.parse_string(regional.audit(budget,regional.begin_request()))
		if not audited.ok: return audited
		report.merge(audited.data,true)
		report.erase("overview_json")
		report.erase("overview_cost")
		report.base_package_bytes = int(report.package_bytes)
		report.base_target_bytes = 50000000
		report.base_target_met = report.package_bytes <= report.base_target_bytes
		report.path = regional_path
		return {"ok":true,"data":report}
	var package_path: String = staged.path.path_join("result.memap")
	var packed: Dictionary = JSON.parse_string(native.export_project(staged.path, package_path))
	if not packed.ok: return packed
	var compressed := compressed_assets(package_path, snapshot.document.assets)
	if not compressed.ok: return compressed
	report.user_asset_compressed_bytes = compressed.data
	# ZIP headers/manifest stay in the base; subtract only compressed asset payloads.
	report.base_package_bytes = int(report.package_bytes) - int(compressed.data)
	report.base_target_bytes = 50000000
	report.base_target_met = report.base_package_bytes <= report.base_target_bytes
	report.path = package_path
	return {"ok": true, "data": report}

static func compressed_assets(path: String, assets: Array) -> Dictionary:
	# Read the bounded central directory of our own canonical (non-ZIP64) export.
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return {"ok": false, "error": {"code": "E_IO", "message": "Cannot inspect exported ZIP."}}
	file.seek(file.get_length() - 22)
	if file.get_32() != 0x06054b50: return {"ok": false, "error": {"code": "E_ZIP", "message": "Unexpected canonical ZIP footer."}}
	file.seek(file.get_length() - 12)
	var entries := file.get_16()
	file.get_32()
	var offset := file.get_32()
	file.seek(offset)
	var wanted := {}
	for asset: Dictionary in assets:
		for payload_path: String in PAYLOADS.paths(asset): wanted[payload_path] = true
	var total := 0
	for _i in range(entries):
		var header := file.get_buffer(46)
		if header.size() != 46 or header.decode_u32(0) != 0x02014b50:
			return {"ok": false, "error": {"code": "E_ZIP", "message": "Unexpected canonical ZIP index."}}
		var name := file.get_buffer(header.decode_u16(28)).get_string_from_utf8()
		if wanted.has(name): total += header.decode_u32(20)
		file.seek(file.get_position() + header.decode_u16(30) + header.decode_u16(32))
	return {"ok": true, "data": total}

# Over the preview allowance the cell is still generated; the caller gets a warning.
func allowance(native: RefCounted, cell: Vector2i, warnings: Array = []) -> Dictionary:
	var cost: Dictionary = JSON.parse_string(native.estimate_chunk(cell.x, cell.y))
	if not cost.ok: return cost
	var charge := work_bytes(cost.data)
	if charge > PREVIEW_BYTES: LIMITS.note(warnings, "preview_work", charge, PREVIEW_BYTES, "Cell preview needs more work memory than the preview allowance")
	return {"ok": true, "data": charge}

# Native queries cap one request at 16384 cells (including a small halo), so
# larger regional maps are queried in aligned windows and merged in row order.
func whole_map_cells(native: RefCounted, document: Dictionary) -> Dictionary:
	var bounds: Dictionary = document.bounds
	var size := int(document.cell_size_cm)
	var step := size * QUERY_WINDOW_CELLS
	var seen := {}
	var cells: Array = []
	var y := int(bounds.min[1])
	while y <= int(bounds.max[1]):
		var x := int(bounds.min[0])
		while x <= int(bounds.max[0]):
			if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
			var query: Dictionary = JSON.parse_string(native.query_cells(x, y, mini(x + step, int(bounds.max[0])), mini(y + step, int(bounds.max[1])), QUERY_CELLS))
			if not query.ok: return query
			for target: Dictionary in query.data.geometry_cells:
				var key := "%d/%d" % [int(target.x), int(target.y)]
				if seen.has(key): continue
				seen[key] = true
				cells.append(target)
			x += step
		y += step
	cells.sort_custom(func(a: Dictionary, b: Dictionary): return int(a.y) < int(b.y) or (int(a.y) == int(b.y) and int(a.x) < int(b.x)))
	return {"ok": true, "data": cells}

static func work_bytes(cost: Dictionary) -> int:
	return int(cost.get("gimmick_bytes",0)) + int(cost.generation_scratch_bytes) + int(cost.triangles) * (256 + int(cost.max_object_id_bytes)) + int(cost.objects) * 1024 + int(cost.presentation_bytes) * 4

static func materialized_preview_cost(cost: Dictionary, data: Dictionary) -> Dictionary:
	var counts: Dictionary = data.get("generated_counts", {})
	var refined := cost.duplicate()
	for key in ["triangles", "objects", "building_prisms", "asset_convexes"]:
		var value: Variant = counts.get(key)
		if not (value is int or value is float) or not is_finite(float(value)) or value < 0 or float(value) != floor(float(value)) or value > cost.get(key, 0): return {}
		refined[key] = int(value)
	# Keep source/environment allowances; only replace the per-triangle bound.
	# Source assets and styles remain fully charged even when geometry is sparse.
	var source_bytes := maxi(int(cost.presentation_bytes) - int(cost.triangles) * 256, int(data.get("preview_bytes", 0)))
	var styles: Dictionary = data.get("chunk", {}).get("presentation", {}).get("road_styles", {})
	refined.presentation_bytes = source_bytes + int(refined.triangles) * 256 + styles.size() * 16384
	return refined

func density_report(native: RefCounted, snapshot: Dictionary, index: Dictionary, cached: Dictionary, use_cache: bool = true) -> Dictionary:
	var query := whole_map_cells(native, snapshot.document)
	if not query.ok: return query
	var rows := {}
	for target: Dictionary in query.data:
		if stopped(): return failure("E_CANCELLED", "Density analysis cancelled.")
		var cell := Vector2i(int(target.x), int(target.y))
		var key := "%d/%d" % [cell.x,cell.y]
		var signature := INDEX.signature(snapshot.document,snapshot.hashes,index,cell) if use_cache else ""
		if use_cache and cached.get(key,{}).get("signature","") == signature:
			rows[key] = cached[key]
			continue
		var estimated: Dictionary = JSON.parse_string(native.estimate_chunk(cell.x,cell.y))
		if not estimated.ok: return estimated
		var row: Dictionary = estimated.data.duplicate(true)
		row.cell = cell
		row.signature = signature
		row.work_bytes = work_bytes(row)
		row.warning = "over limit" if row.work_bytes > PREVIEW_BYTES else ("high" if row.work_bytes >= PREVIEW_BYTES * 3 / 4 else "")
		rows[key] = row
	return {"ok":true,"data":rows}

func reopen_package(path: String, destination: String) -> Dictionary:
	if stopped(): return failure("E_CANCELLED", "Reopen cancelled.")
	if path.get_extension().to_lower() == "memap":
		update("Validating package before restoring a new project directory")
		var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
		var validated: Dictionary = JSON.parse_string(bridge.open_package_budgeted(path, reopen_budget(path)))
		if not validated.ok: return validated
		if stopped(): return failure("E_CANCELLED", "Reopen cancelled.")
		return JSON.parse_string(bridge.unpack_source(destination))
	if path.get_extension().to_lower() != "mkregions":
		return failure("E_FORMAT", "Choose a .memap or .mkregions package.")
	var native: RefCounted = ClassDB.instantiate("MapKitRegionReader")
	var budget := reopen_budget(path)
	var opened: Dictionary = JSON.parse_string(native.open_index(path,budget,""))
	if not opened.ok: return opened
	update("Auditing regional source and restoring a new project directory")
	var result: Dictionary = JSON.parse_string(native.unpack_source(destination,budget,native.begin_request()))
	return result

# The user's own package: size the memory allowance from the file and the machine,
# never below the previous 1 GiB. Runtime readers keep their own defaults.
static func reopen_budget(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	var length := file.get_length() if file != null else 0
	if file != null: file.close()
	var physical := int(OS.get_memory_info().get("physical", 0))
	var ceiling := REOPEN_MAX_BYTES if physical <= 0 else clampi(physical / 2, REOPEN_MIN_BYTES, REOPEN_MAX_BYTES)
	return clampi(length * 8, REOPEN_MIN_BYTES, ceiling)


static func runtime_cell_budget(message: String) -> bool:
	for prefix: String in RUNTIME_CELL_BUDGETS:
		if message.contains(prefix): return true
	return false
