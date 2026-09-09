extends RefCounted
## One worker owns each immutable native session. No scene work on this thread.
const SNAPSHOT := preload("./project_snapshot.gd")
const PAYLOADS := preload("./authoring_files.gd")
const INDEX := preload("./preview_index.gd")
const PREVIEW_BYTES := 256 * 1024 * 1024
const OVERVIEW_BYTES := 4 * 1024 * 1024
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
	var captured := SNAPSHOT.capture(document, source)
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

func process_snapshot(staged: Dictionary, snapshot: Dictionary, operation: String, cell: Vector2i, cached: Dictionary, full: bool) -> Dictionary:
	var native: RefCounted = staged.bridge
	if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
	update("Building affected-object / cell index")
	var index := INDEX.build(native, snapshot.document, stopped)
	if not index.ok: return index
	if operation == "preview":
		var signature := INDEX.signature(snapshot.document, snapshot.hashes, index.data, cell)
		if cached.get("signature", "") == signature:
			return {"ok": true, "data": {"reused": true, "signature": signature, "cell": cell}}
		var cost := allowance(native, cell)
		if not cost.ok: return cost
		var charge := int(cost.data)
		if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
		update("Generating cell %d / %d" % [cell.x, cell.y])
		var generated: Dictionary = native.generate_chunk_packed(cell.x, cell.y)
		if generated.ok: generated = native.with_presentation(generated.data)
		if not generated.ok: return generated
		generated.data.signature = signature
		generated.data.cell = cell
		generated.data.charge = charge
		return generated
	var report: Dictionary = staged.inspection.duplicate(true)
	report.index_references = index.data.references
	update("Preparing 2D overview")
	var overview: Dictionary = JSON.parse_string(native.overview_json(OVERVIEW_BYTES))
	if not overview.ok: return overview
	report.overview = overview.data
	report.full_generation_cells = 0
	if full:
		var bounds: Dictionary = snapshot.document.bounds
		var query: Dictionary = JSON.parse_string(native.query_cells(int(bounds.min[0]), int(bounds.min[1]), int(bounds.max[0]), int(bounds.max[1]), 16384))
		if not query.ok: return query
		for target: Dictionary in query.data.geometry_cells:
			if stopped(): return failure("E_CANCELLED", "Full generation check cancelled.")
			update("Optional 3D check %d / %d" % [report.full_generation_cells + 1, report.cell_count])
			var budget := allowance(native, Vector2i(int(target.x), int(target.y)))
			if not budget.ok: return budget
			var generated: Dictionary = native.generate_chunk_packed(int(target.x), int(target.y))
			if not generated.ok: return generated
			report.full_generation_cells += 1
	if stopped(): return failure("E_CANCELLED", "Operation cancelled.")
	update("Compressing validated package")
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
	for asset: Dictionary in assets: wanted[str(asset.path)] = true
	var total := 0
	for _i in range(entries):
		var header := file.get_buffer(46)
		if header.size() != 46 or header.decode_u32(0) != 0x02014b50:
			return {"ok": false, "error": {"code": "E_ZIP", "message": "Unexpected canonical ZIP index."}}
		var name := file.get_buffer(header.decode_u16(28)).get_string_from_utf8()
		if wanted.has(name): total += header.decode_u32(20)
		file.seek(file.get_position() + header.decode_u16(30) + header.decode_u16(32))
	return {"ok": true, "data": total}

func allowance(native: RefCounted, cell: Vector2i) -> Dictionary:
	var cost: Dictionary = JSON.parse_string(native.estimate_chunk(cell.x, cell.y))
	if not cost.ok: return cost
	var charge := int(cost.data.generation_scratch_bytes) + int(cost.data.triangles) * (256 + int(cost.data.max_object_id_bytes)) + int(cost.data.objects) * 1024 + int(cost.data.presentation_bytes) * 4
	if charge > PREVIEW_BYTES: return failure("E_PREVIEW_BUDGET", "Cell estimate %d exceeds the %d-byte preview work allowance." % [charge, PREVIEW_BYTES])
	return {"ok": true, "data": charge}
