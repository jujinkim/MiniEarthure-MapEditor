extends RefCounted
## Bounded, read-only discovery. No path from this report can adopt or delete work.
const PRESENCE := preload("./import_presence.gd")
const MAX_ENTRIES := 256
const MAX_ROWS := 64
const ENTRIES_PER_FRAME := 8
const MAX_PROBES := 4
const SCAN_MS := 5000
var rows: Array[Dictionary] = []
var probes: Array[Dictionary] = []
var root := ""
var entries := 0
var partial := false
var done := true
var message := ""
var listing: DirAccess
var deadline := 0

func start() -> void:
	cancel()
	rows.clear()
	entries = 0
	partial = false
	message = ""
	root = ProjectSettings.globalize_path("user://import-jobs")
	var parent := DirAccess.open(root.get_base_dir())
	if parent == null or parent.is_link(root.get_file()):
		message = "Import work folder is unavailable or linked; it was not inspected."
		return
	if not DirAccess.dir_exists_absolute(root):
		if FileAccess.file_exists(root): message = "Import work folder is occupied by a file; it was preserved."
		return
	listing = DirAccess.open(root)
	if listing == null or listing.list_dir_begin() != OK:
		listing = null
		message = "Import work folder could not be read; all files were preserved."
		return
	done = false
	deadline = Time.get_ticks_msec() + SCAN_MS

func cancel() -> void:
	if listing != null: listing.list_dir_end()
	listing = null
	for probe in probes: probe.socket.disconnect_from_host()
	probes.clear()
	done = true

func _end_listing() -> void:
	if listing != null: listing.list_dir_end()
	listing = null

func _metadata(name: String) -> Dictionary:
	var directory := DirAccess.open(root.path_join(name))
	if directory == null or directory.is_link(PRESENCE.MARKER): return {}
	var file := FileAccess.open(root.path_join(name).path_join(PRESENCE.MARKER), FileAccess.READ)
	if file == null: return {}
	if file.get_length() <= 0 or file.get_length() > PRESENCE.MAX_METADATA:
		file.close()
		return {}
	var bytes := file.get_buffer(PRESENCE.MAX_METADATA + 1)
	file.close()
	if bytes.size() > PRESENCE.MAX_METADATA: return {}
	var parser := JSON.new()
	if parser.parse(bytes.get_string_from_utf8()) != OK: return {}
	var data: Variant = parser.data
	if data is not Dictionary or data.size() != 7: return {}
	if data.get("format") != "mapeditor-import-owner" or data.get("version") != 1 or data.get("request") != name or not PRESENCE.hex32(data.get("owner")): return {}
	if data.get("kind") not in ["vector", "dem-plan", "dem"]: return {}
	if not _integer(data.get("port"), 1, 65535) or not _integer(data.get("created_unix"), 0, 9999999999): return {}
	return data

static func _integer(value: Variant, minimum: int, maximum: int) -> bool:
	return (value is int or value is float) and is_finite(value) and value == floor(value) and value >= minimum and value <= maximum

func _inspect(name: String, now: int) -> void:
	var row := {"name":name.validate_filename().left(80), "kind":"unknown", "state":"unknown"}
	rows.append(row)
	if listing.is_link(name) or not listing.current_is_dir() or not PRESENCE.hex32(name): return
	var metadata := _metadata(name)
	if metadata.is_empty(): return
	row.kind = metadata.kind
	row.state = "checking"
	var socket := StreamPeerTCP.new()
	var nonce := Crypto.new().generate_random_bytes(16).hex_encode()
	if socket.connect_to_host("127.0.0.1", int(metadata.port)) != OK:
		row.state = "unconfirmed"
		return
	probes.append({"socket":socket, "row":row, "nonce":nonce, "owner":metadata.owner,
		"bytes":PackedByteArray(), "sent":0, "deadline":now + PRESENCE.PEER_MS})

func poll(now_ms: int = -1) -> void:
	if done: return
	var now := Time.get_ticks_msec() if now_ms < 0 else now_ms
	for index in range(probes.size() - 1, -1, -1):
		var probe := probes[index]
		var socket: StreamPeerTCP = probe.socket
		socket.poll()
		var remove: bool = now >= probe.deadline
		if not remove and socket.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			var request: PackedByteArray = (probe.nonce + "\n").to_ascii_buffer()
			if probe.sent < request.size():
				var sent := socket.put_partial_data(request.slice(probe.sent))
				probe.sent += int(sent[1])
				remove = sent[0] != OK
			var count := socket.get_available_bytes()
			if count + probe.bytes.size() > 66: remove = true
			elif count > 0:
				var received := socket.get_partial_data(count)
				if received[0] != OK: remove = true
				else: probe.bytes.append_array(received[1])
			if probe.bytes.size() == 66:
				if probe.bytes == (probe.owner + ":" + probe.nonce + "\n").to_ascii_buffer(): probe.row.state = "active"
				remove = true
		elif socket.get_status() != StreamPeerTCP.STATUS_CONNECTING: remove = true
		if remove:
			if probe.row.state != "active": probe.row.state = "unconfirmed"
			socket.disconnect_from_host()
			probes.remove_at(index)
	if now >= deadline:
		partial = true
		_end_listing()
		for probe in probes: probe.row.state = "unconfirmed"
		cancel()
		return
	for _index in ENTRIES_PER_FRAME:
		if listing == null or probes.size() >= MAX_PROBES: break
		if entries >= MAX_ENTRIES or rows.size() >= MAX_ROWS:
			partial = true
			_end_listing()
			break
		var name := listing.get_next()
		if name == "":
			_end_listing()
			break
		entries += 1
		_inspect(name, now)
	done = listing == null and probes.is_empty()
