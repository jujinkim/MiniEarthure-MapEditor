extends SceneTree
## Deterministic preparation barrier around the actual product worker. The
## production EOF watcher remains live, so cancel/deadline/parent loss can kill it.
class PausedWorker extends "res://scripts/import_native_worker.gd":
	func progress(stage: String, completed: int, total: int) -> void:
		super.progress(stage, completed, total)
		if stage == "prepare" and completed == 0:
			var release := directory.path_join("test-prepare-release")
			while not FileAccess.file_exists(release): OS.delay_msec(1)
			DirAccess.remove_absolute(release)

func _initialize() -> void: root.add_child.call_deferred(PausedWorker.new())
