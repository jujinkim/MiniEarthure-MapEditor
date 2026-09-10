extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const FILES := preload("res://scripts/document_files.gd")

class InterruptedFiles extends FILES:
	var phase := ""
	func crash(destination: String) -> void:
		var marker := FileAccess.open(destination.get_base_dir().path_join("crash-phase.txt"), FileAccess.WRITE)
		marker.store_string(phase)
		marker.close()
		OS.kill(OS.get_process_id())
	func _publish(source: String, destination: String) -> Error:
		if phase == "before_backup" and destination.ends_with(".previous"):
			crash(destination)
		if phase == "before_primary" and destination.ends_with("document.json"):
			crash(destination)
		var error := super._publish(source, destination)
		if phase == "after_primary" and destination.ends_with("document.json"):
			crash(destination)
		return error

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		quit(2)
		return
	var store := STORE.new()
	if store.open_project(args[0]) != "":
		quit(3)
		return
	var adapter := InterruptedFiles.new()
	adapter.phase = args[1]
	store.files = adapter
	if store.apply_command("Crash fixture", [{"field": "seed", "before": store.document.seed, "after": 777}]) != "":
		quit(4)
		return
	store.save_project(args[0])
	# Reaching here means the requested interruption never happened.
	quit(5)
