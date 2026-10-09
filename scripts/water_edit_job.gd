extends RefCounted
## One detached snapshot and cancellation token per water request; no disk staging.
var thread := Thread.new()
var token: RefCounted = ClassDB.instantiate("MapKitWorkToken")

func start(snapshot: RefCounted, point: Vector2, remove: bool, refresh: bool) -> Error:
	return thread.start(func():
		token.enter()
		var result: Dictionary = JSON.parse_string(snapshot.water_edit(point, remove, refresh))
		token.leave()
		if token.is_cancelled(): return {"ok":false,"error":{"code":"E_CANCELLED","message":"Water edit cancelled; previous map retained."}}
		return result)

func cancel() -> void: token.cancel()
func is_alive() -> bool: return thread.is_alive()
func finish() -> Dictionary:
	var result: Dictionary = thread.wait_to_finish()
	# A completed calculation is still unpublished until the owner polls it.
	if token.is_cancelled(): return {"ok":false,"error":{"code":"E_CANCELLED","message":"Water edit cancelled; previous map retained."}}
	return result
func shutdown() -> void:
	cancel()
	if thread.is_started(): thread.wait_to_finish()
