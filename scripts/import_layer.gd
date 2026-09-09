extends RefCounted
## Untrusted adapter output can only add a fresh, explicitly adopted vector layer.
const MAX_BYTES := 12 * 1024 * 1024
const FIELDS := ["nodes", "roads", "buildings", "zones"]
var value: Dictionary = {}

static func _hex(text: Variant, length: int) -> bool:
	if text is not String or text.length() != length: return false
	for c in text:
		if c not in "0123456789abcdef": return false
	return true

static func _text(value: Variant) -> bool:
	if value is not String or value.strip_edges().is_empty() or value.length() > 512: return false
	for c in value:
		if c.unicode_at(0) < 32: return false
	return true

static func _count(value: Variant, maximum: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value)) and value >= 0 and value <= maximum

func load_value(raw: Variant, expected_id: String) -> String:
	value = {}
	if raw is not Dictionary or JSON.stringify(raw).to_utf8_buffer().size() > MAX_BYTES: return "Invalid or oversized ImportLayer."
	if raw.get("import_version") != 1 or raw.get("adapter") != "geojson-local-v1": return "Unsupported ImportLayer version/adapter."
	if not _hex(raw.get("layer_id"), 32) or raw.layer_id != expected_id: return "Stale or invalid import identity."
	var source: Variant = raw.get("source")
	if source is not Dictionary or not _text(source.get("name")) or not _text(source.get("license")) or not _text(source.get("accuracy")) or not _hex(source.get("sha256"), 64) or not _count(source.get("bytes"), 32 * 1024 * 1024): return "Invalid import source metadata."
	if raw.get("coordinates") is not Dictionary or raw.coordinates.get("mode") != "local-metres" or raw.coordinates.get("quantization_cm") != 1: return "Unsupported import coordinates."
	for key in ["feature_count", "point_count", "warning_count"]:
		if not _count(raw.get(key), 200000): return "Invalid import counts."
	if raw.get("warnings") is not Array or raw.warnings.size() > 50 or raw.warning_count < raw.warnings.size(): return "Invalid import warnings."
	for warning in raw.warnings:
		if not _text(warning): return "Invalid import warning."
	if raw.get("estimates") is not Dictionary or raw.estimates.size() > 32: return "Invalid estimates."
	for key in raw.estimates:
		if not _text(key) or not _count(raw.estimates[key], 200000): return "Invalid estimated-field count."
	if raw.get("extent_cm") is not Array or raw.extent_cm.size() != 4: return "Invalid import extent."
	for n in raw.extent_cm:
		if not _count(n + 10000000 if n is int or n is float else null, 20000000): return "Invalid import extent coordinate."
	if raw.extent_cm[0] > raw.extent_cm[2] or raw.extent_cm[1] > raw.extent_cm[3]: return "Invalid import extent ordering."
	if raw.get("patches") is not Array or raw.patches.is_empty() or raw.patches.size() > 60000: return "Invalid import records."
	var ids := {}
	var nodes := {}
	var prefix := "import-" + expected_id + "-"
	for patch in raw.patches:
		if patch is not Dictionary or not patch.has_all(["field", "id", "before", "after"]): return "Invalid import patch."
		if patch.field not in FIELDS or patch.before != null or patch.after is not Dictionary: return "Import may only add supported records."
		if patch.id is not String or not patch.id.begins_with(prefix) or patch.id.length() > 128 or patch.after.get("id") != patch.id or ids.has(patch.id): return "Invalid/duplicate import record identity."
		ids[patch.id] = true
		if patch.field == "nodes": nodes[patch.id] = true
	for patch in raw.patches:
		if patch.field == "roads" and (not nodes.has(patch.after.get("from")) or not nodes.has(patch.after.get("to"))): return "Imported roads must reference their own layer nodes."
	value = raw.duplicate(true)
	return ""

func patches(store: RefCounted) -> Array:
	var result: Array = value.patches.duplicate(true)
	var metadata := value.duplicate(true)
	metadata.erase("patches")
	var attribution := {"source": value.source.name + "#" + value.layer_id, "license": value.source.license, "notice": JSON.stringify(metadata)}
	result.append({"field": "attributions", "id": store.record_id("attributions", attribution), "before": null, "after": attribution})
	return result

func validate_for(store: RefCounted) -> String:
	if value.is_empty(): return "No import candidate."
	var candidate: Dictionary = store.document.duplicate(true)
	var failure: String = store._apply(candidate, patches(store), false)
	if failure != "": return failure
	var result: Dictionary = store._validate(candidate)
	return "" if result.ok else store.reason(result)

func adopt(store: RefCounted) -> String:
	var failure := validate_for(store)
	return failure if failure != "" else store.apply_command("Adopt import " + str(value.source.name), patches(store))

func summary() -> String:
	return "%s · %d bytes\nLicense: %s · source accuracy: %s\n%d features / %d records · local extent (cm): %s\nEstimated fields (counts): %s\nWarnings: %d (showing %d)\n%s\n\nAdopt adds a new layer as one Undo command. Existing objects and source files remain unchanged." % [value.source.name, value.source.bytes, value.source.license, value.source.accuracy, value.feature_count, value.patches.size(), str(value.extent_cm), JSON.stringify(value.estimates), value.warning_count, value.warnings.size(), "\n".join(value.warnings)]
