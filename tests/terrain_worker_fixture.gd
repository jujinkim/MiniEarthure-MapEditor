extends SceneTree
## Pause the actual worker before raster decoding while its parent EOF watcher runs.
class PausedWorker extends "res://scripts/import_native_worker.gd":
	func progress(stage: String, completed: int, total: int) -> void:
		super.progress(stage, completed, total)
		if stage == "validate" and completed == 0:
			var release := directory.path_join("test-plan-release")
			while not FileAccess.file_exists(release): OS.delay_msec(1)
			DirAccess.remove_absolute(release)
func _initialize() -> void: root.add_child.call_deferred(PausedWorker.new())
