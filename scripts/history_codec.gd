extends RefCounted
## Private in-memory history. Bound both retained bytes and decompression work.
const RETAINED_LIMIT := 16 * 1024 * 1024
const TEXT_LIMIT := 48 * 1024 * 1024
const THRESHOLD := 1024 * 1024

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func retain(command: Dictionary, text: String, binary: Dictionary = {}) -> Dictionary:
	var raw := text.to_utf8_buffer()
	if raw.size() > TEXT_LIMIT: return {"error":"Command exceeds the 48 MiB expanded Undo budget."}
	var result := command.duplicate(true)
	var size := raw.size()
	if size >= THRESHOLD:
		var packed := raw.compress(FileAccess.COMPRESSION_ZSTD)
		if not packed.is_empty() and packed.size() < size:
			result = {"label":command.label,"packed_patches":packed,"expanded_bytes":raw.size(),"digest":digest(raw)}
			size = packed.size()+128+str(command.label).to_utf8_buffer().size()
	for blob: PackedByteArray in binary.values(): size += blob.size()
	if size > RETAINED_LIMIT: return {"error":"Command exceeds the 16 MiB undo budget; split this operation."}
	result.bytes = size
	if not binary.is_empty(): result.binary_mementos = binary.duplicate()
	return result

static func unpack(command: Dictionary) -> Dictionary:
	if not command.has("packed_patches"): return {"patches":command.get("patches",[])}
	if command.packed_patches is not PackedByteArray or command.packed_patches.size() > RETAINED_LIMIT or not command.get("expanded_bytes") is int or command.expanded_bytes < 1 or command.expanded_bytes > TEXT_LIMIT:
		return {"error":"Invalid compressed Undo size."}
	var raw: PackedByteArray = command.packed_patches.decompress(command.expanded_bytes,FileAccess.COMPRESSION_ZSTD)
	if raw.size() != command.expanded_bytes or digest(raw) != command.get("digest"): return {"error":"Compressed Undo content changed."}
	var value: Variant = JSON.parse_string(raw.get_string_from_utf8())
	if value is not Dictionary or value.get("label") != command.get("label") or value.get("patches") is not Array: return {"error":"Invalid compressed Undo command."}
	return {"patches":value.patches}
