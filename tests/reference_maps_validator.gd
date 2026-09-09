extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const INDEX := preload("res://scripts/preview_index.gd")
const WORK := preload("res://scripts/package_work.gd")
var checks := 0
var evidence := {}

func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
    checks += 1
    if not value:
        push_error(message)
        quit(1)
        assert(value, message)

func run() -> void:
    var source := OS.get_environment("MAPEDITOR_REFERENCE_ROOT")
    check(not source.is_empty(), "explicit isolated reference fixture root required")
    var lock: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/reference_maps.lock.json"))
    for name: String in ["baseline", "baseline-user", "structures"]:
        var store := STORE.new()
        check(store.open_project(source.path_join(name)) == "", name + " actual Editor open")
        var before := FileAccess.get_sha256(source.path_join(name).path_join("document.json"))
        var index := INDEX.build(store.bridge, store.document)
        check(index.ok, name + " Editor index: " + str(index.get("error", "")))
        var packaged: Dictionary = JSON.parse_string(store.bridge.export_project(source.path_join(name), ProjectSettings.globalize_path("user://" + name + ".memap")))
        check(packaged.ok, name + " native export")
        for key in ["package_sha256", "world_content_hash", "package_bytes", "cell_count", "base_data_bytes", "user_asset_bytes", "expanded_bytes"]:
            check(packaged.data[key] == lock[name].inspection[key], name + " frozen " + key)
        var assets := WORK.compressed_assets("user://" + name + ".memap", store.document.assets)
        check(assets.ok and assets.data == lock[name].capacity.user_asset_compressed_bytes, name + " base/user compressed partition")
        var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
        var opened: Dictionary = JSON.parse_string(bridge.open_package(ProjectSettings.globalize_path("user://" + name + ".memap")))
        check(opened.ok, name + " exported native reopen")
        var cells: Array = [[0,0],[9,0],[0,9],[9,9],[11,11],[18,18],[19,19]] if name == "baseline" else [[0,0]]
        if name == "structures": cells = [[0,0],[1,0],[0,1],[1,1]]
        var hashes := {}
        for cell: Array in cells:
            var started := Time.get_ticks_msec()
            var generated: Dictionary = bridge.generate_chunk_packed(cell[0],cell[1])
            check(generated.ok, name + " generation " + str(cell) + ": " + str(generated.get("error", "")))
            var key := "%d/%d" % [cell[0],cell[1]]
            hashes[key] = generated.data.generated_sha256
            check(generated.data.generated_sha256 == lock[name].generated_cells[key], name + " frozen generated " + key)
            print(name, " cell ", cell, " generated in ", Time.get_ticks_msec()-started, " ms")
            await process_frame
        if name == "structures":
            for probe: Array in [[25600,10000,"ground-west",0],[25600,10000,"bridge",600],[51200,50000,"underpass",-500],[51200,80000,"tunnel",-600]]:
                var sampled: Dictionary = JSON.parse_string(bridge.surface_probe(probe[0],probe[1],probe[2]))
                check(sampled.ok and sampled.data.position_cm[1] == probe[3], "explicit structure layer " + str(probe))
        check(before == FileAccess.get_sha256(source.path_join(name).path_join("document.json")), name + " original source retained")
        evidence[name] = {"inspection":packaged.data, "index_references":index.data.references, "generated_cells":hashes}
    var report := OS.get_environment("MAPEDITOR_REFERENCE_REPORT")
    if not report.is_empty():
        var file := FileAccess.open(report,FileAccess.WRITE)
        check(file != null, "evidence destination writable")
        file.store_string(JSON.stringify(evidence,"  ")+"\n")
    print("reference_maps_validator: PASS (",checks," checks; sampled baseline / all structure cells; no driving or performance acceptance)")
    quit(0)
