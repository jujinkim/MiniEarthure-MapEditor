extends RefCounted
## A validator's own user:// scratch folder: every run starts empty and the
## validator removes it on exit (MainLoop._finalize), so a rerun never meets an
## earlier run's project, capture or package. Only paths under ROOT are removed.
const ROOT := "user://validator-scratch"

static func fresh(name: String) -> String:
	var path := ProjectSettings.globalize_path(ROOT).path_join(name)
	remove(path)
	DirAccess.make_dir_recursive_absolute(path)
	return path

static func remove(path: String) -> void:
	var base := ProjectSettings.globalize_path(ROOT) + "/"
	if path == "" or not path.begins_with(base) or path.contains("/../"): return
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.include_hidden = true
	for name in dir.get_directories(): remove(path.path_join(name))
	for name in dir.get_files(): DirAccess.remove_absolute(path.path_join(name))
	DirAccess.remove_absolute(path)
