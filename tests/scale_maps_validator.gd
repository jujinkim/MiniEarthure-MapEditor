extends SceneTree
## Native export, actual audit limits, source samples and exact storage parity.
## Refusal is evidence of unsupported input, never a successful driving result.
var checks := 0
var report := []
func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		push_error(message)
		quit(1)
		assert(ok, message)
func run() -> void:
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("MAPEDITOR_SCALE_CASES")))
	for entry: Dictionary in cases:
		var metadata: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(entry.source.path_join("scale.json")))
		var before := FileAccess.get_sha256(entry.source.path_join("document.json"))
		check(before == metadata.source_hashes["document.json"], "exact synthetic source")
		var reader: RefCounted = ClassDB.instantiate("MapKitRegionReader")
		var opened: Dictionary = JSON.parse_string(reader.open_index(entry.path,1073741824,""))
		check(opened.ok and opened.data.verification == "index-only", "bounded native index")
		var sample := {"path":entry.path,"source_sha256":before,"opened":opened.data,"admissions":[],"generated":[]}
		var admitted := false
		for limit: int in [536870912,1073741824]:
			var started := Time.get_ticks_usec()
			var audit: Dictionary = JSON.parse_string(reader.audit(limit,reader.begin_request()))
			sample.admissions.append({"limit_bytes":limit,"elapsed_ms":(Time.get_ticks_usec()-started)/1000.0,"result":audit})
			check(audit.ok or audit.error.code == "E_MEMORY_BUDGET", "typed audit approval/refusal")
			if audit.ok:
				admitted = true
				check(audit.data.verification == "complete-audit" and audit.data.validation_peak_bytes <= limit, "full audited identity within limit")
				check(audit.data.package_sha256 == FileAccess.get_sha256(entry.path), "same file identity")
		if entry.get("export",false):
			var destination := ProjectSettings.globalize_path("user://native-scale-%d.mkregions" % report.size())
			var exported: Dictionary = JSON.parse_string(reader.export_project(entry.source,destination,int(opened.data.side_cells)))
			check(exported.ok and FileAccess.get_sha256(destination) == FileAccess.get_sha256(entry.path), "native/CLI export byte parity")
		if admitted:
			for cell: Array in entry.get("cells",[]):
				var region: Dictionary = JSON.parse_string(reader.region_for_cell(cell[0],cell[1]))
				check(region.ok, "sample belongs to a storage region")
				var ticket: int = reader.begin_request()
				var started := Time.get_ticks_usec()
				var loaded: Dictionary = reader.load_region(region.data.region,1073741824,ticket)
				check(loaded.ok, "audited representative source read")
				var bridge: RefCounted = loaded.bridge
				var data: Dictionary = bridge.generate_chunk_occupied_packed(cell[0],cell[1],200000)
				check(data.ok, "actual representative cell generation: " + str(data.get("error",{})))
				var geometry: Dictionary = preload("res://addons/mapkit/godot/chunk_data.gd").view(data.data.chunk)
				sample.generated.append({"cell":cell,"region":region.data.region,"cost":region.data.cost,
					"generated_sha256":data.data.generated_sha256,"triangles":preload("res://addons/mapkit/godot/chunk_data.gd").count(geometry),
					"elapsed_load_generate_ms":(Time.get_ticks_usec()-started)/1000.0})
				reader.cancel_request()
				var late: Dictionary = reader.load_region(region.data.region,1073741824,ticket)
				check(not late.ok and late.error.code == "E_CANCELLED", "stale candidate rejected")
				check(bridge.generate_chunk_packed(cell[0],cell[1]).data.generated_sha256 == data.data.generated_sha256, "held source survives cancelled request")
		check(FileAccess.get_sha256(entry.source.path_join("document.json")) == before, "original preserved")
		report.append(sample)
		print("L02_NATIVE ",JSON.stringify(sample))
	var file := FileAccess.open(OS.get_environment("MAPEDITOR_SCALE_REPORT"),FileAccess.WRITE)
	check(file != null,"report destination")
	file.store_string(JSON.stringify(report,"  ")+"\n")
	print("scale_maps_validator: PASS (",checks," checks; support/refusal recorded separately)")
	quit(0)
