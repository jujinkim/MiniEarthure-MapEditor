extends RefCounted
## Lossless bounded PNG16 adapter for authoring. MapKit remains the acceptance gate.
const MAX_SIDE := 513
const MAX_BYTES := 4 * 1024 * 1024
const SIGNATURE := [137, 80, 78, 71, 13, 10, 26, 10]

static func u32(bytes: PackedByteArray, at: int) -> int:
	return (int(bytes[at]) << 24) | (int(bytes[at + 1]) << 16) | (int(bytes[at + 2]) << 8) | bytes[at + 3]

static func be32(value: int) -> PackedByteArray:
	return PackedByteArray([(value >> 24) & 255, (value >> 16) & 255, (value >> 8) & 255, value & 255])

static func crc(bytes: PackedByteArray) -> int:
	var value := 0xffffffff
	for byte in bytes:
		value ^= byte
		for _bit in range(8): value = (value >> 1) ^ (0xedb88320 if value & 1 else 0)
	return value ^ 0xffffffff

static func chunk(kind: String, bytes: PackedByteArray) -> PackedByteArray:
	var content := kind.to_ascii_buffer() + bytes
	return be32(bytes.size()) + content + be32(crc(content))

static func encode(heights: PackedInt64Array, side: int) -> Dictionary:
	if side < 2 or side > MAX_SIDE or heights.size() != side * side:
		return {"error": "Heightmap grid exceeds authoring limits."}
	var low := heights[0]
	var high := low
	for h in heights:
		low = mini(low, h)
		high = maxi(high, h)
	if high - low > 65535 or absi(low) > 1000000:
		return {"error": "Brush requires a lossless 1 cm height range within 655.35 m; split or rescale the source explicitly."}
	var raw := PackedByteArray()
	raw.resize(side * (1 + side * 2))
	for y in range(side):
		for x in range(side):
			var value := int(heights[y * side + x]) - low
			var at := y * (1 + side * 2) + 1 + x * 2
			raw[at] = value >> 8
			raw[at + 1] = value & 255
	var ihdr := be32(side) + be32(side) + PackedByteArray([16, 0, 0, 0, 0])
	return {"bytes": PackedByteArray(SIGNATURE) + chunk("IHDR", ihdr) + chunk("IDAT", raw.compress(FileAccess.COMPRESSION_DEFLATE)) + chunk("IEND", PackedByteArray()), "offset_cm": low, "step_cm": 1}

static func decode(bytes: PackedByteArray, side: int, offset: int, step: int) -> Dictionary:
	if side < 2 or side > MAX_SIDE or bytes.size() > MAX_BYTES or bytes.size() < 33 or bytes.slice(0, 8) != PackedByteArray(SIGNATURE):
		return {"error": "Expected a bounded unsigned 16-bit grayscale PNG."}
	var at := 8
	var compressed := PackedByteArray()
	var header := false
	var ended := false
	while at + 12 <= bytes.size():
		var length := u32(bytes, at)
		if length > MAX_BYTES or at + length + 12 > bytes.size(): return {"error": "Truncated PNG chunk."}
		var kind := bytes.slice(at + 4, at + 8).get_string_from_ascii()
		var content := bytes.slice(at + 8, at + 8 + length)
		if crc(bytes.slice(at + 4, at + 8 + length)) != u32(bytes, at + 8 + length): return {"error": "PNG checksum mismatch."}
		if not header and kind != "IHDR": return {"error": "PNG header must be first."}
		if kind == "IHDR":
			if header or length != 13 or u32(content, 0) != side or u32(content, 4) != side or content.slice(8) != PackedByteArray([16, 0, 0, 0, 0]):
				return {"error": "PNG must be non-interlaced grayscale16 with the exact full cell grid dimensions."}
			header = true
		elif kind == "IDAT": compressed.append_array(content)
		elif kind == "IEND":
			ended = length == 0 and at + 12 == bytes.size()
			break
		elif kind.to_upper() == kind and kind != "PLTE": return {"error": "Unsupported critical PNG chunk."}
		at += length + 12
	if not ended or compressed.is_empty(): return {"error": "Incomplete PNG."}
	var stride := side * 2
	var raw := compressed.decompress(side * (stride + 1), FileAccess.COMPRESSION_DEFLATE)
	if raw.size() != side * (stride + 1): return {"error": "PNG decoded size mismatch."}
	var previous := PackedByteArray()
	previous.resize(stride)
	var heights := PackedInt64Array()
	heights.resize(side * side)
	for y in range(side):
		var filter := int(raw[y * (stride + 1)])
		if filter > 4: return {"error": "Invalid PNG row filter."}
		var row := raw.slice(y * (stride + 1) + 1, (y + 1) * (stride + 1))
		for x in range(stride):
			var a := int(row[x - 2]) if x >= 2 else 0
			var b := int(previous[x])
			var c := int(previous[x - 2]) if x >= 2 else 0
			var predictor := 0
			match filter:
				1: predictor = a
				2: predictor = b
				3: predictor = (a + b) / 2
				4:
					var p := a + b - c
					predictor = a if absi(p - a) <= absi(p - b) and absi(p - a) <= absi(p - c) else (b if absi(p - b) <= absi(p - c) else c)
			row[x] = (int(row[x]) + predictor) & 255
		for x in range(side): heights[y * side + x] = offset + ((int(row[x * 2]) << 8) | row[x * 2 + 1]) * step
		previous = row
	return {"heights": heights}
