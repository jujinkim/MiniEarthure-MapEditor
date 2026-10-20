extends RefCounted
## Private in-memory history. Bound both retained bytes and decompression work.
## A command larger than the retained budget is still applied, without Undo:
## the store then releases the earlier history and warns (never refuses).
const RETAINED_LIMIT := 16 * 1024 * 1024
const TEXT_LIMIT := 512 * 1024 * 1024
const THRESHOLD := 1024 * 1024

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func retain(command: Dictionary, text: String, binary: Dictionary = {}) -> Dictionary:
	var raw := text.to_utf8_buffer()
	var size := raw.size()
	var binary_size := 0
	for blob: PackedByteArray in binary.values(): binary_size += blob.size()
	var result := {}
	# Skip copying and compressing a command that can never be retained.
	if binary_size <= RETAINED_LIMIT and size <= TEXT_LIMIT:
		result = command.duplicate(true)
		if size >= THRESHOLD:
			var packed := raw.compress(FileAccess.COMPRESSION_ZSTD)
			if not packed.is_empty() and packed.size() < size:
				result = {"label":command.label,"packed_patches":packed,"expanded_bytes":raw.size(),"digest":digest(raw)}
				size = packed.size()+128+str(command.label).to_utf8_buffer().size()
	size += binary_size
	# Same comparison as the store's trimming: exactly RETAINED_LIMIT still fits.
	if size > RETAINED_LIMIT:
		return {"label":command.label,"bytes":size,"history_released":true}
	result.bytes = size
	if not binary.is_empty(): result.binary_mementos = binary.duplicate()
	return result

static func unpack(command: Dictionary) -> Dictionary:
	if command.get("history_released", false): return {"error":"Undo history for this change was released."}
	if not command.has("packed_patches"): return {"patches":command.get("patches",[])}
	if command.packed_patches is not PackedByteArray or command.packed_patches.size() > RETAINED_LIMIT or not command.get("expanded_bytes") is int or command.expanded_bytes < 1 or command.expanded_bytes > TEXT_LIMIT:
		return {"error":"Invalid compressed Undo size."}
	var raw: PackedByteArray = command.packed_patches.decompress(command.expanded_bytes,FileAccess.COMPRESSION_ZSTD)
	if raw.size() != command.expanded_bytes or digest(raw) != command.get("digest"): return {"error":"Compressed Undo content changed."}
	var value: Variant = JSON.parse_string(raw.get_string_from_utf8())
	if value is not Dictionary or value.get("label") != command.get("label") or value.get("patches") is not Array: return {"error":"Invalid compressed Undo command."}
	return {"patches":value.patches}
