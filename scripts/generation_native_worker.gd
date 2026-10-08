extends RefCounted
## One owned child generates, validates and prepares a reviewable result.
const FILES := preload("./authoring_files.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const COMMAND := preload("./import_command.gd")

static func validate(request: Dictionary, directory: String, identity: String, progress: Callable) -> Dictionary:
	var output := {"ok":false,"request":identity}
	var failure := ""
	if request.get("request") != identity or request.get("generation") is not Dictionary or request.get("document") is not Dictionary or request.get("python") is not String or request.python.is_empty():
		failure = "Invalid environment generation request."
	progress.call("source",0,0)
	var modules := ["environment_generation.py","environment_profiles.py","environment_assets.py","asset_derivatives.py","reference_maps.py","special_driving_maps.py","city_assets.py","driving_school_map.py"]
	for module: String in modules:
		if failure != "": break
		failure = FILES.write_new(directory.path_join(module),FileAccess.get_file_as_string("res://scripts/"+module).to_utf8_buffer())
	if failure == "": failure = FILES.write_new(directory.path_join("kit/godot/driving_templates.json"),FileAccess.get_file_as_bytes("res://addons/mapkit/godot/driving_templates.json"))
	# Only public library sources are staged. They remain unchanged.
	for library: String in ["richer-library","arcade-library"]:
		if failure != "": break
		var base := "res://addons/mapkit/assets/"+library
		var library_text := FileAccess.get_file_as_string(base.path_join("library.json"))
		var inventory: Variant = JSON.parse_string(library_text)
		if inventory is not Dictionary:
			failure = "Missing environment asset library."
			break
		failure = FILES.write_new(directory.path_join("kit/assets/"+library+"/library.json"),library_text.to_utf8_buffer())
		for record: Dictionary in inventory.assets:
			if failure != "": break
			if not SNAPSHOT.safe_relative(record.path): failure = "Unsafe environment library asset."; break
			var read := FILES.read(base.path_join(record.path))
			failure = str(read.error) if read.has("error") else FILES.write_new(directory.path_join("kit/assets/"+library).path_join(record.path),read.bytes)
	var generated := directory.path_join("generated")
	if failure == "":
		var messages: Array = []
		var status := OS.execute(request.python,PackedStringArray(["-B",directory.path_join("environment_generation.py"),directory.path_join("request.json"),generated,"--kit",directory.path_join("kit")]),messages,true)
		if status != 0: failure = "Environment generation failed: "+str(messages).right(1800)
	var report := {}
	var candidate := {}
	var blobs := {}
	var snapshot := {}
	var prepared := {}
	var hashes := {}
	var cells: Array = []
	if failure == "":
		var raw := preload("./document_files.gd").new().read_json(generated.path_join("generation.json"))
		var source := preload("./document_files.gd").new().read_json(generated.path_join("document.json"))
		if raw.has("error") or source.has("error"): failure = "Missing generation result."
		else:
			report = raw.value
			candidate = source.value
			# Inspect bounded representative dense cells, not a whole-world bake.
			var density := {}
			for placement: Dictionary in candidate.get("placements",[]):
				var cell := Vector2i(floori((placement.position[0]-candidate.bounds.min[0])/candidate.cell_size_cm),floori((placement.position[2]-candidate.bounds.min[1])/candidate.cell_size_cm))
				density[cell] = int(density.get(cell,0))+1
			cells = density.keys()
			cells.sort_custom(func(a,b): return density[a]>density[b])
			cells.resize(mini(6,cells.size()))
			if cells.is_empty(): cells.append(Vector2i.ZERO)
	if failure == "":
		for path: String in report.payloads:
			if not SNAPSHOT.safe_relative(path): failure = "Unsafe generation payload."; break
			var read := FILES.read(generated.path_join(path))
			if read.has("error") or FILES.digest(read.bytes) != report.payloads[path]: failure = "Generation payload changed."; break
			blobs[path] = read.bytes
	if failure == "":
		progress.call("validate",0,1)
		var store := preload("./document_store.gd").new()
		store.document = request.document
		store.project_path = request.project
		var context := {"scratch":directory.path_join("candidate"),"progress":progress,"hashes":hashes}
		if request.generation.mode == "new":
			store.document = candidate
			store.project_path = generated
			failure = FILES.validate(store,candidate,blobs,cells,context)
			if failure == "":
				var captured := SNAPSHOT.capture(candidate,generated)
				failure = str(captured.error) if not captured.ok else ""
				if failure == "": snapshot = captured.data
		else:
			# Composite keys use Godot's canonical representation, exactly as the
			# store's normal history/recovery path does.
			for patch: Dictionary in report.patches:
				if patch.field in ["attributions","heightmaps"]:
					patch.id = store.record_id(patch.field,patch.after if patch.after != null else patch.before)
			if report.patches.is_empty():
				failure = FILES.validate(store,candidate,blobs,cells,context)
				progress.call("prepare",1,1)
				report.noop = true
			else:
				failure = FILES.apply(store,"Complete selected environment",report.patches,blobs,cells,true,context.merged({"prepared":prepared}))
		if failure == "" and request.generation.mode == "new":
			progress.call("prepare",0,1)
			progress.call("prepare",1,1)
	if failure == "":
		progress.call("recheck",0,0)
		for path: String in hashes:
			var source_root: String = generated if request.generation.mode == "new" else request.project
			if FileAccess.get_sha256(source_root.path_join(path)) != hashes[path]: failure = "Project changed during generation."
	if failure == "":
		# The prepared command/snapshot already carries ownership and patches.
		# Keep one copy in the bounded transfer instead of repeating authoring JSON.
		for redundant: String in ["patches","owned","metadata"]: report.erase(redundant)
		var bundle := {"request":identity,"report":report,"payloads":blobs,"snapshot":snapshot,"source_hashes":hashes}
		if not prepared.is_empty(): bundle.prepared = COMMAND.encode(prepared)
		failure = COMMAND.write_bundle(directory,bundle,output)
		output.payloads = JSON.stringify(hashes).sha256_text()
	output.ok = failure == ""
	if failure != "": output.error = {"code":"E_IMPORT_NATIVE","message":failure.left(2000)}
	return output
