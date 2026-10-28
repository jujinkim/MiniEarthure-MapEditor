extends RefCounted
## Private, hash-bound owned-worker transfer, never a public import format.
const FILES := preload("./authoring_files.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const TYPES := preload("./import_layer.gd")
const LIMITS := preload("./limit_warnings.gd")
## Memory guards of the owned-child transfer; the former 24/96 MiB only warn.
const BUNDLE_LIMIT := 512 * 1024 * 1024
const WARN_BUNDLE_BYTES := 24 * 1024 * 1024
const HISTORY_LIMIT := 16 * 1024 * 1024
const HISTORY := preload("./history_codec.gd")
const EXPANDED_BUNDLE_LIMIT := 1024 * 1024 * 1024
const WARN_EXPANDED_BYTES := 96 * 1024 * 1024
## v1 package document size (MapKit MAX_DOCUMENT_BYTES); the game refuses larger maps.
const DOCUMENT_LIMIT := 32 * 1024 * 1024

static func encode(prepared: Dictionary) -> Dictionary:
	# A command released from Undo no longer holds its payloads; callers then
	# pass them as prepared.retained so the transfer still carries every blob.
	return {"version":1, "canonical":prepared.canonical, "command_json":prepared.command_json,
		"signature":prepared.signature, "retained":prepared.command.get("binary_mementos", prepared.get("retained", {}))}

static func decode(value: Variant, allow_assets: bool = false, allow_generation: bool = false) -> Dictionary:
	if value is not Dictionary or value.get("version") != 1 or value.get("canonical") is not String or value.get("command_json") is not String or value.get("retained") is not Dictionary or not TYPES._hex(value.get("signature"), 64):
		return {"error":"Invalid prepared import command transfer."}
	# Charge the actual text and bytes, never a size asserted by the result.
	var size: int = value.command_json.to_utf8_buffer().size()
	if size > HISTORY.TEXT_LIMIT:
		return {"error":"Prepared command exceeds its text budget."}
	var notes: Array = []
	LIMITS.over(notes, "document_bytes", value.canonical.to_utf8_buffer().size(), DOCUMENT_LIMIT, "Map document size in bytes", true)
	# A command above the Undo budget is still installed; the store then
	# releases earlier history (history_codec marks it) and warns.
	for path: Variant in value.retained:
		if path is not String or not SNAPSHOT.safe_relative(path) or value.retained[path] is not PackedByteArray:
			return {"error":"Invalid prepared binary memento."}
	var document_parser := JSON.new()
	var command_parser := JSON.new()
	if document_parser.parse(value.canonical) != OK or command_parser.parse(value.command_json) != OK:
		return {"error":"Malformed prepared command JSON."}
	var candidate: Variant = document_parser.data
	var command: Variant = command_parser.data
	if candidate is not Dictionary or candidate.get("provenance") is not Dictionary or candidate.get("map_id") is not String or command is not Dictionary or command.size() != 2 or command.get("label") is not String or command.get("patches") is not Array or command.patches.is_empty():
		return {"error":"Invalid prepared canonical document or history command."}
	# Defensive transfer shape checks; the owned child remains responsible for
	# native semantics. Do not repeat coordinate/attribution canonicalization here.
	for field in ["nodes", "roads", "buildings", "zones", "assets", "placements", "heightmaps", "attributions"]:
		if candidate.get(field) is not Array: return {"error":"Missing prepared document records."}
		for record: Variant in candidate[field]:
			if record is not Dictionary: return {"error":"Invalid prepared document record."}
	var fields: Array = ["pois","nodes","roads","buildings","zones","heightmaps","attributions","placements","surface_areas","water_bodies","gimmicks","assets","barriers"] if allow_generation else ["assets", "attributions"] if allow_assets else ["pois", "nodes", "roads", "buildings", "zones", "surface_areas", "heightmaps", "attributions", "barriers", "water_bodies"]
	for patch: Variant in command.patches:
		if not allow_assets and patch is Dictionary and patch.get("field") == "bounds":
			if patch.get("id") != "" or patch.get("before") is not Dictionary or patch.get("after") is not Dictionary or patch.get("after") != candidate.get("bounds"):
				return {"error":"Invalid imported map extent."}
			for extent: Dictionary in [patch.before,patch.after]:
				for key in ["min","max"]:
					if extent.get(key) is not Array or extent[key].size() != 2: return {"error":"Invalid imported map extent."}
					for coordinate: Variant in extent[key]:
						if (coordinate is not int and coordinate is not float) or not is_finite(coordinate) or coordinate != round(coordinate): return {"error":"Invalid imported map extent."}
			continue
		if not allow_assets and patch is Dictionary and patch.get("field") == "assembled_track":
			# Only the native composition transition of an existing standalone
			# assembly is transferable. Adapter patches cannot name this field.
			var before: Variant = patch.get("before")
			var after: Variant = patch.get("after")
			if patch.get("id") != "" or before is not Dictionary:
				return {"error":"Invalid imported track composition."}
			var source: Variant = before.get("authoring") if before.get("authoring") is Dictionary else before.get("seed_source")
			if source is not Dictionary or source.get("terrain_integration",false):
				return {"error":"Invalid imported track composition."}
			var expected: Dictionary = before.duplicate(true)
			expected.authoring = source.duplicate(true)
			expected.authoring.terrain_integration = true
			expected.seed_source = null
			if after != expected and not (after == null and before.get("pieces",[]).is_empty() and source.get("structures",[]).is_empty() and source.get("grind_lines",[]).is_empty()):
				return {"error":"Import cannot rewrite assembled geometry."}
			continue
		if not allow_assets and patch is Dictionary and patch.get("field") == "ground_surface":
			# A city import paves the unpainted ground of a map without a surface.
			if patch.get("id") != "" or patch.get("before") != null or patch.get("after") != TYPES.CITY_GROUND_SURFACE or candidate.get("ground_surface") != patch.after:
				return {"error":"Invalid imported ground surface."}
			continue
		if not allow_assets and patch is Dictionary and patch.get("field") == "play_area":
			# A city import's crop window becomes the drivable area of a map without one.
			if patch.get("id") != "" or patch.get("before") != null or patch.get("after") is not Array or patch.after.is_empty() or candidate.get("play_area") != patch.after:
				return {"error":"Invalid imported play area."}
			continue
		if not allow_assets and patch is Dictionary and patch.get("field") == "free_roam":
			if patch.get("id") != "" or patch.get("before") is not bool or patch.get("after") != true or candidate.get("free_roam") != true:
				return {"error":"Invalid imported map free-roam policy."}
			continue
		if patch is not Dictionary or not patch.has_all(["field", "id", "before", "after"]) or patch.field not in fields or patch.id is not String or patch.id.is_empty() or (patch.after is not Dictionary and not (allow_generation and patch.after == null)) or (patch.before != null and patch.before is not Dictionary):
			return {"error":"Invalid prepared command memento."}
	var patches: Array = command.patches
	command = HISTORY.retain(command,value.command_json,value.retained)
	if command.has("error"): return command
	# Patches and binary payloads stay available even when Undo was released.
	return {"candidate":candidate, "command":command, "signature":value.signature, "patches":patches, "retained":value.retained, "limit_warnings":notes}

static func write_bundle(directory: String, bundle: Dictionary, output: Dictionary) -> String:
	var bytes := var_to_bytes(bundle)
	if bytes.size() > EXPANDED_BUNDLE_LIMIT: return "Prepared import transfer exceeds 1 GiB expanded."
	if not output.has("limit_warnings"): output.limit_warnings = []
	LIMITS.over(output.limit_warnings, "transfer_expanded_bytes", bytes.size(), WARN_EXPANDED_BYTES, "Prepared change size in bytes")
	bytes = var_to_bytes({"expanded":bytes.size(),"packed":bytes.compress(FileAccess.COMPRESSION_ZSTD)})
	if bytes.size() > BUNDLE_LIMIT: return "Prepared import transfer exceeds 512 MiB."
	LIMITS.over(output.limit_warnings, "transfer_bytes", bytes.size(), WARN_BUNDLE_BYTES, "Compressed prepared change size in bytes")
	var failure := FILES.write_new(directory.path_join("bundle.bin"), bytes)
	if failure == "": output.merge({"bundle_bytes":bytes.size(), "bundle_sha256":FILES.digest(bytes)})
	return failure

static func read_bundle(directory: String, output: Dictionary) -> Dictionary:
	var read := FILES.read(directory.path_join("bundle.bin"), BUNDLE_LIMIT)
	if read.has("error") or not TYPES._count(output.get("bundle_bytes"), BUNDLE_LIMIT) or read.bytes.size() != int(output.bundle_bytes) or FILES.digest(read.bytes) != output.get("bundle_sha256"):
		return {"error":"Prepared import transfer changed or exceeded its budget."}
	# Object deserialization is deliberately disabled.
	var decoded: Variant = bytes_to_var(read.bytes)
	if decoded is not Dictionary or decoded.get("expanded") is not int or decoded.expanded < 1 or decoded.expanded > EXPANDED_BUNDLE_LIMIT or decoded.get("packed") is not PackedByteArray: return {"error":"Invalid compressed import transfer."}
	var expanded: PackedByteArray = decoded.packed.decompress(decoded.expanded,FileAccess.COMPRESSION_ZSTD)
	if expanded.size() != decoded.expanded: return {"error":"Invalid expanded import transfer."}
	decoded = bytes_to_var(expanded)
	if decoded is not Dictionary: return {"error":"Invalid prepared import transfer."}
	return decoded
