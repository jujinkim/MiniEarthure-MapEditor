extends RefCounted
## Private, hash-bound owned-worker transfer, never a public import format.
const FILES := preload("./authoring_files.gd")
const SNAPSHOT := preload("./project_snapshot.gd")
const TYPES := preload("./import_layer.gd")
const BUNDLE_LIMIT := 24 * 1024 * 1024
const HISTORY_LIMIT := 16 * 1024 * 1024

static func encode(prepared: Dictionary) -> Dictionary:
	return {"version":1, "canonical":prepared.canonical, "command_json":prepared.command_json,
		"signature":prepared.signature, "retained":prepared.command.get("binary_mementos", {})}

static func decode(value: Variant) -> Dictionary:
	if value is not Dictionary or value.get("version") != 1 or value.get("canonical") is not String or value.get("command_json") is not String or value.get("retained") is not Dictionary or not TYPES._hex(value.get("signature"), 64):
		return {"error":"Invalid prepared import command transfer."}
	# Charge the actual text and bytes, never a size asserted by the result.
	var size: int = value.command_json.to_utf8_buffer().size()
	if value.canonical.to_utf8_buffer().size() > BUNDLE_LIMIT or size > HISTORY_LIMIT:
		return {"error":"Prepared command exceeds its text budget."}
	for path: Variant in value.retained:
		if path is not String or not SNAPSHOT.safe_relative(path) or value.retained[path] is not PackedByteArray:
			return {"error":"Invalid prepared binary memento."}
		size += value.retained[path].size()
		if size > HISTORY_LIMIT: return {"error":"Prepared command exceeds the 16 MiB Undo budget."}
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
	for patch: Variant in command.patches:
		if patch is not Dictionary or not patch.has_all(["field", "id", "before", "after"]) or patch.field not in ["nodes", "roads", "buildings", "zones", "heightmaps", "attributions"] or patch.id is not String or patch.id.is_empty() or patch.after is not Dictionary or (patch.before != null and patch.before is not Dictionary):
			return {"error":"Invalid prepared command memento."}
	command.bytes = size
	if not value.retained.is_empty(): command.binary_mementos = value.retained
	return {"candidate":candidate, "command":command, "signature":value.signature}

static func write_bundle(directory: String, bundle: Dictionary, output: Dictionary) -> String:
	var bytes := var_to_bytes(bundle)
	if bytes.size() > BUNDLE_LIMIT: return "Prepared import transfer exceeds 24 MiB."
	var failure := FILES.write_new(directory.path_join("bundle.bin"), bytes)
	if failure == "": output.merge({"bundle_bytes":bytes.size(), "bundle_sha256":FILES.digest(bytes)})
	return failure

static func read_bundle(directory: String, output: Dictionary) -> Dictionary:
	var read := FILES.read(directory.path_join("bundle.bin"), BUNDLE_LIMIT)
	if read.has("error") or not TYPES._count(output.get("bundle_bytes"), BUNDLE_LIMIT) or read.bytes.size() != int(output.bundle_bytes) or FILES.digest(read.bytes) != output.get("bundle_sha256"):
		return {"error":"Prepared import transfer changed or exceeded its budget."}
	# Object deserialization is deliberately disabled.
	var decoded: Variant = bytes_to_var(read.bytes)
	if decoded is not Dictionary: return {"error":"Invalid prepared import transfer."}
	return decoded
