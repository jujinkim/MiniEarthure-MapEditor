extends Node
## Route the private worker before constructing any Editor UI or user session.
func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var scene := "res://scripts/import_native_worker.tscn" if not args.is_empty() and args[0] == "--native-import-validation" else "res://main.tscn"
	add_child(load(scene).instantiate())
