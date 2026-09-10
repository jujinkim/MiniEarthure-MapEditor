extends RefCounted
## Per-request loopback presence. A marker is evidence, never cleanup authority.
const MARKER := "owner.json"
const PENDING := "owner.json.part"
const MAX_METADATA := 1024
const MAX_PEERS := 4
const PEER_MS := 800
var server := TCPServer.new()
var owner := ""
var peers: Array[Dictionary] = []

static func hex32(value: Variant) -> bool:
	if value is not String or value.length() != 32: return false
	for character in value:
		if character not in "0123456789abcdef": return false
	return true

func begin(directory: String, token: String, kind: String) -> String:
	owner = Crypto.new().generate_random_bytes(16).hex_encode()
	var error := server.listen(0, "127.0.0.1")
	if error != OK: return "Cannot establish local import presence: " + error_string(error)
	var metadata := JSON.stringify({"format":"mapeditor-import-owner", "version":1,
		"request":token, "owner":owner, "kind":kind, "port":server.get_local_port(),
		"created_unix":int(Time.get_unix_time_from_system())})
	var file := FileAccess.open(directory.path_join(PENDING), FileAccess.WRITE)
	if file == null:
		close()
		return "Cannot write import ownership record."
	file.store_string(metadata)
	file.flush()
	error = file.get_error()
	file.close()
	if error == OK: error = DirAccess.rename_absolute(directory.path_join(PENDING), directory.path_join(MARKER))
	if error != OK:
		close()
		return "Cannot publish import ownership record: " + error_string(error)
	return ""

func poll(now_ms: int = -1) -> void:
	var now := Time.get_ticks_msec() if now_ms < 0 else now_ms
	# Never drain an unbounded socket backlog in one frame.
	if server.is_listening() and server.is_connection_available() and peers.size() < MAX_PEERS:
		peers.append({"socket":server.take_connection(), "bytes":PackedByteArray(), "reply":PackedByteArray(), "sent":0, "deadline":now + PEER_MS})
	for index in range(peers.size() - 1, -1, -1):
		var item := peers[index]
		var socket: StreamPeerTCP = item.socket
		socket.poll()
		var remove: bool = now >= item.deadline or socket.get_status() != StreamPeerTCP.STATUS_CONNECTED
		if not remove and item.reply.is_empty():
			var count := socket.get_available_bytes()
			if count + item.bytes.size() > 33: remove = true
			elif count > 0:
				var data := socket.get_partial_data(count)
				if data[0] != OK: remove = true
				else: item.bytes.append_array(data[1])
			if item.bytes.size() == 33:
				var nonce: String = item.bytes.slice(0, 32).get_string_from_ascii()
				if not hex32(nonce) or item.bytes[32] != 10: remove = true
				else: item.reply = (owner + ":" + nonce + "\n").to_ascii_buffer()
		if not remove and not item.reply.is_empty() and item.sent < item.reply.size():
			var sent := socket.put_partial_data(item.reply.slice(item.sent))
			item.sent += int(sent[1])
			remove = sent[0] != OK
		if remove:
			socket.disconnect_from_host()
			peers.remove_at(index)

func close() -> void:
	for item in peers: item.socket.disconnect_from_host()
	peers.clear()
	server.stop()
