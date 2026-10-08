extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/authoring_files.gd")
const SNAPSHOT := preload("res://scripts/project_snapshot.gd")
const INDEX := preload("res://scripts/preview_index.gd")
const FAR := preload("res://addons/mapkit/godot/distant_renderer.gd")
class Lease extends RefCounted:
	var owned: Array = []
	func track(value: Variant) -> void: owned.append(value)
var failed := false
func check(ok: bool, message: String) -> void:
	if not ok: failed = true; push_error(message)
func _initialize() -> void: run.call_deferred()
func integer_json(value: Variant) -> Variant:
	if value is Dictionary:
		for key: String in value: value[key]=integer_json(value[key])
	elif value is Array:
		for index in value.size(): value[index]=integer_json(value[index])
	elif value is float and value==floor(value): return int(value)
	return value
func small_fixture(source: PackedByteArray) -> PackedByteArray:
	var length := source.decode_u32(12)
	var document: Dictionary=JSON.parse_string(source.slice(20,20+length).get_string_from_utf8())
	for node: Dictionary in document.nodes:
		node.erase("matrix")
		node.scale=[.1,.1,.1]
	var encoded := JSON.stringify(integer_json(document)).to_utf8_buffer()
	while encoded.size()%4!=0: encoded.append(32)
	var bytes:=source.slice(0,20)
	bytes.encode_u32(8,source.size()-length+encoded.size())
	bytes.encode_u32(12,encoded.size())
	bytes.append_array(encoded);bytes.append_array(source.slice(20+length))
	return bytes
func run() -> void:
	var store := STORE.new(); store.new_document()
	var project := ProjectSettings.globalize_path("user://lod-source")
	check(store.save_project(project) == "", "new isolated project")
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://addons/mapkit/examples/assets/document.json"))
	var record: Dictionary = fixture.assets[0].duplicate(true)
	var bytes := small_fixture(FileAccess.get_file_as_bytes("res://addons/mapkit/examples/assets/tetra.glb"))
	var near := "editor/" + FILES.digest(bytes) + ".glb"
	# Different immutable paths are legitimate even if these synthetic bytes match.
	check(FILES.write_new(project.path_join("far.glb"), bytes) == "", "stage distant source")
	record.path = near; record.distant_path = "far.glb"
	var patches := [{"field":"assets","id":record.id,"before":null,"after":record}]
	var applied: String=FILES.apply(store, "LOD pair", patches, {near:bytes})
	check(applied == "", "candidate includes both files: "+applied)
	if applied!="": quit(1);return
	check(store.undo_stack.back().binary_mementos.has("far.glb"), "Undo charges distant payload")
	check(store.undo() == "" and store.redo() == "", "LOD pair Undo/Redo")
	var snapshot := SNAPSHOT.capture(store.document, project, store.undo_stack)
	check(snapshot.ok and snapshot.data.blobs.has("far.glb"), "detached snapshot retains distant payload")
	var signature := INDEX.signature(store.document,snapshot.data.hashes,{"cells":{}},Vector2i.ZERO)
	var changed: Dictionary = snapshot.data.hashes.duplicate();changed["far.glb"] = "different"
	check(signature != INDEX.signature(store.document,changed,{"cells":{}},Vector2i.ZERO), "far content invalidates preview")
	var copy := ProjectSettings.globalize_path("user://lod-copy")
	check(store.save_project(copy) == "", "Save As copies distant and history payloads")
	check(FileAccess.get_sha256(copy.path_join("far.glb")) == FILES.digest(bytes), "Save As exact bytes")
	var reopened := STORE.new();check(reopened.open_project(copy) == "", "reopen LOD pair")
	var placement := {"id":"placed-tetra","asset_id":record.id,"position":[3000,0,3000],"quarter_turns":1,"yaw_offset_mdeg":17000}
	check(reopened.apply_command("Place",[{"field":"placements","id":"placed-tetra","before":null,"after":placement}]) == "", "placement")
	check(reopened.save_project(copy) == "", "save placement")
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	check(JSON.parse_string(bridge.open_project(copy)).ok, "load display fixture")
	var result: Dictionary = bridge.generate_far_chunk(0,0)
	check(result.get("ok",false), "native silhouette view")
	if result.get("ok",false):
		var lease := Lease.new()
		var parent := Node3D.new();root.add_child(parent)
		var owner: WeakRef = weakref(result.data.geometry)
		var job := FAR.begin(result.data,parent,lease)
		while not FAR.advance(job): pass
		check(job.done and job.root.get_child_count()>0, "bounded shared display batches")
		var small_count := 0
		for node: MeshInstance3D in job.root.get_children():
			if node.get_meta("mapkit_decoration",false):
				small_count+=1
				check(node.visibility_range_end==112.0,"small far props use current quality distance")
		check(small_count>0,"small authored silhouette is classified for culling")
		preload("res://addons/mapkit/godot/display_quality.gd").apply(root,preload("res://addons/mapkit/godot/display_quality.gd").profile(0))
		for node: MeshInstance3D in job.root.get_children():
			if node.get_meta("mapkit_decoration",false): check(node.visibility_range_end==64.0,"live quality updates far culling")
		FAR.cancel(job);result.clear();job.clear();lease.owned.clear();parent.queue_free()
		await process_frame;await process_frame
		check(owner.get_ref()==null, "cancel/release retires native far geometry")
	check(FILES.validate(reopened,reopened.document)=="", "retained source validates")
	DirAccess.remove_absolute(copy.path_join("far.glb"))
	check(not SNAPSHOT.capture(reopened.document,copy).ok, "missing distant file rejects publication")
	print("distant_asset_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
