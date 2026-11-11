extends SceneTree
const RECEIPT := preload("res://scripts/source_receipt.gd")
const SCRATCH := preload("res://tests/validator_scratch.gd")
var scratch: String = SCRATCH.fresh("source_receipt_validator")
var failed := false
func _finalize() -> void: SCRATCH.remove(scratch)
func check(ok: bool, message: String) -> void:
	if not ok: failed = true; push_error(message)
func _initialize() -> void:
	var python := OS.get_environment("MINIEARTHURE_PYTHON")
	var fixture := ProjectSettings.globalize_path("res://tests/source_receipt_fixture.py")
	var path := scratch.path_join("receipt.json")
	var output: Array = []
	check(OS.execute(python,[fixture,"write",path],output,true)==0,"write Python receipt: "+str(output))
	if failed: quit(1); return
	var value: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var decoded := RECEIPT.rows(value.packed,"objects")
	check(decoded.ok and decoded.data==value.expected,"Python gzip receipt retains Unicode and every source fact")
	var first: Dictionary = {"objects":value.expected.duplicate(true)}
	var second: Dictionary = first.duplicate(true)
	RECEIPT.pack(first,"objects"); RECEIPT.pack(second,"objects")
	check(first==second and first.has("objects_blob"),"GDScript compression is deterministic")
	var file := FileAccess.open(path,FileAccess.WRITE)
	file.store_string(JSON.stringify({"expected":value.expected,"packed":first})); file.close()
	check(OS.execute(python,[fixture,"verify",path],output,true)==0,"Python reads GDScript compressed receipt: "+str(output))
	var damaged := first.duplicate(true)
	damaged.objects_blob.sha256 = "0".repeat(64)
	check(not RECEIPT.rows(damaged,"objects").ok,"corrupt hash refuses evidence")
	damaged = first.duplicate(true); damaged.objects_blob.bytes = RECEIPT.MAX_BYTES+1
	check(not RECEIPT.rows(damaged,"objects").ok,"oversized expansion refused before allocation")
	damaged = first.duplicate(true); damaged.objects = []
	check(not RECEIPT.rows(damaged,"objects").ok,"ambiguous plain and compressed evidence refused")
	print("source_receipt_validator: ","FAIL" if failed else "PASS")
	quit(1 if failed else 0)
