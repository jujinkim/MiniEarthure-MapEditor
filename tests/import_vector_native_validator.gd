extends "res://tests/import_native_validator.gd"
## Run the same owned-child safety contract for a recipe-1, nonstructural layer.
func structural_case() -> bool: return false
func test_name() -> String: return "import_vector_native_validator"

func extra_faults(before: String) -> void:
	var original: Dictionary = layer.value.duplicate(true)
	var digest: String = layer.native_payload_digest
	layer.native_payload_digest = ""
	var unreviewed := JOB.new()
	check(unreviewed.start_validation(ui.store,layer,true,"test",source,token()).contains("reviewed payload"),"adoption requires reviewed payload identity before launch")
	check(unreviewed.pid == -1 and unreviewed.directory == "","unreviewed request owns no scratch")
	layer.native_payload_digest = digest
	layer.value["oversized_test_extension"] = "x".repeat(JOB.REQUEST_LIMIT)
	var oversized := JOB.new()
	check(start(oversized).contains("24 MiB"),"request budget rejects before reserving child/scratch")
	check(oversized.pid == -1 and oversized.directory == "","oversized request leaves no owned work")
	layer.value.erase("oversized_test_extension")
	# Keep source size constant to exercise the SHA check rather than length only.
	var bytes: PackedByteArray = FILES.read(source).bytes
	write(source,bytes.get_string_from_utf8().replace('"height_m":12','"height_m":13').to_utf8_buffer())
	check(FILES.read(source).bytes.size() == bytes.size() and FILES.read(source).bytes != bytes,"same-size synthetic source mutation")
	var changed := JOB.new()
	check(start(changed) == "","start same-size source check")
	await wait_job(changed)
	check(changed.result.ok and not changed.result.data.ok and changed.result.data.error.message.contains("source changed"),"same-size changed source is rejected by digest")
	write(source,bytes)
	# A shape-valid ImportLayer can still violate the native document schema.
	layer.value.patches[0].after.height_cm = -1
	var invalid := JOB.new()
	check(start(invalid) == "","start invalid native document check")
	await wait_job(invalid)
	check(invalid.result.ok and not invalid.result.data.ok,"native document failure rejects whole nonstructural candidate")
	layer.value = original.duplicate(true)
	# Completion is rejected even if edits bypass ordinary UI change signals.
	for mutation in ["document", "layer", "project", "selection"]:
		ui._start_native_import(layer,false)
		var pending: RefCounted = ui.import_job
		check(pending != null,"start stale completion " + mutation)
		var project: String = ui.store.project_path
		var theme: String = ui.store.document.theme
		match mutation:
			"document": ui.store.document.theme += " changed"
			"layer": layer.value.source.accuracy += " changed"
			"project": ui.store.project_path += "-other"
			"selection":
				ui.import_origin_x.value += 1
				ui.import_origin_x.value -= 1
				check(pending.cancelled,"same-frame changed/restored origin cancels active child")
		await wait_ui()
		check(ui.pending_import == null and ui.status_label.text.contains("STALE"),"changed snapshot cannot publish review " + mutation)
		ui.store.document.theme = theme
		ui.store.project_path = project
		layer.value = original.duplicate(true)
		check(pending.exited and not DirAccess.dir_exists_absolute(pending.directory),"stale child reaped and owned scratch retired " + mutation)
	check(state() == before,"all rejected vector candidates preserve document/history")
