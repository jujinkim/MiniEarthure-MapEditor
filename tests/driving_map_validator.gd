extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
    checks += 1
    if not value:
        push_error(message)
        quit(1)
        assert(value, message)
func run() -> void:
    var source := OS.get_environment("MAPEDITOR_DRIVING_ROOT")
    check(not source.is_empty(), "explicit new synthetic project required")
    var store := STORE.new()
    check(store.open_project(source) == "", "actual Editor open")
    var lock: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/driving_map.lock.json"))
    var before := FileAccess.get_sha256(source.path_join("document.json"))
    check(before == lock.source_sha256, "frozen original source")
    var saved := ProjectSettings.globalize_path("user://saved")
    check(store.save_project(saved) == "", "Editor Save As")
    check(store.open_project(saved) == "", "Editor saved project reopen")
    var output := source + ".memap"
    check(not FileAccess.file_exists(output), "preserve existing package")
    var packed: Dictionary = JSON.parse_string(store.bridge.export_project(saved, output))
    check(packed.ok, "native package export: " + str(packed))
    for key in ["package_sha256", "world_content_hash", "package_bytes"]:
        check(packed.data[key] == lock.inspection[key], "frozen package " + key)
    var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
    check(JSON.parse_string(bridge.open_package(output)).ok, "package reopen")
    var hashes := {}
    for x in range(2):
        for y in range(2):
            var generated: Dictionary = bridge.generate_chunk_packed(x,y)
            check(generated.ok, "all four cells: " + str(generated.get("error", "")))
            hashes["%d/%d" % [x,y]] = generated.data.generated_sha256
            check(hashes["%d/%d" % [x,y]] == lock.generated_cells["%d/%d" % [x,y]], "frozen generated cell")
            await process_frame
    for probe: Array in [[14000,16000,"straight",0],[51200,16000,"straight",0],[51200,78000,"tunnel",-600],[4000,51200,"west-bridge",600],[30000,52000,"bumps",140],[32000,52000,"bumps",100],[50000,36000,"surface-lane",0]]:
        var result: Dictionary = JSON.parse_string(bridge.surface_probe(probe[0],probe[1],probe[2]))
        check(result.ok and result.data.position_cm[1] == probe[3], "exact route surface " + str(probe) + ": " + str(result))
    check(FileAccess.get_sha256(source.path_join("document.json")) == before, "original project retained")
    var report := FileAccess.open(OS.get_environment("MAPEDITOR_DRIVING_REPORT"),FileAccess.WRITE)
    check(report != null, "report path")
    report.store_string(JSON.stringify({"inspection":packed.data,"generated_cells":hashes,"source_sha256":before},"  ")+"\n")
    print("driving_map_validator: PASS (",checks," checks)")
    quit(0)
