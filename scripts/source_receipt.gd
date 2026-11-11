extends RefCounted
## Optional lossless storage for repeated authoring evidence inside v1 notices.
## Coordinate frames, source hashes and license credits stay directly readable.
const MAX_BYTES := 32 * 1024 * 1024
const MIN_BYTES := 64 * 1024

static func pack(record: Dictionary, key: String) -> void:
	if record.get(key) is not Array: return
	var bytes := JSON.stringify(record[key]).to_utf8_buffer()
	if bytes.size() < MIN_BYTES or bytes.size() > MAX_BYTES: return
	var blob := bytes.compress(FileAccess.COMPRESSION_GZIP)
	if blob.is_empty(): return
	record[key+"_blob"] = {"codec":"gzip-base64","bytes":bytes.size(),"data":Marshalls.raw_to_base64(blob)}
	# Hash the exact JSON bytes, without relying on a text/float round trip.
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256); hash.update(bytes)
	record[key+"_blob"].sha256 = hash.finish().hex_encode()
	record.erase(key)

static func rows(record: Dictionary, key: String) -> Dictionary:
	if not record.has(key+"_blob"):
		return {"ok":true,"data":record.get(key,[])} if record.get(key,[]) is Array else {"ok":false,"error":"Invalid source evidence rows."}
	var blob: Variant = record[key+"_blob"]
	if record.has(key) or blob is not Dictionary or blob.get("codec") != "gzip-base64" or blob.get("data") is not String or blob.get("sha256") is not String:
		return {"ok":false,"error":"Invalid packed source evidence."}
	var size: Variant = blob.get("bytes")
	if not (size is int or size is float) or size != floor(float(size)) or size <= 0 or size > MAX_BYTES or blob.data.length() > MAX_BYTES*2:
		return {"ok":false,"error":"Packed source evidence exceeds its budget."}
	var bytes := Marshalls.base64_to_raw(blob.data).decompress(int(size),FileAccess.COMPRESSION_GZIP)
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256); hash.update(bytes)
	if bytes.size() != size or hash.finish().hex_encode() != blob.sha256:
		return {"ok":false,"error":"Packed source evidence hash mismatch."}
	var parser := JSON.new()
	if parser.parse(bytes.get_string_from_utf8()) != OK or parser.data is not Array:
		return {"ok":false,"error":"Invalid packed source evidence JSON."}
	return {"ok":true,"data":parser.data}
