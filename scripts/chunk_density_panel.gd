extends VBoxContainer
## Immutable worker results are published only for the current document generation.
const WORK := preload("./package_work.gd")
var store: RefCounted
var canvas: Control
var worker := Thread.new()
var task: RefCounted
var generation := 0
var running_generation := -1
var due := 0
var rows := {}
var cached := {}
var measured_delays := {}
var busy_source: Callable
var listing: ItemList
var details: Label

func configure(document_store: RefCounted, map_canvas: Control) -> void:
	store = document_store
	canvas = map_canvas
	listing = ItemList.new()
	listing.custom_minimum_size.y = 48
	add_child(listing)
	details = Label.new()
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(details)
	listing.item_selected.connect(_select)
	store.changed.connect(invalidate)
	invalidate()

func invalidate() -> void:
	cancel()
	due = Time.get_ticks_msec() + 350
	details.text = "Chunk cost analysis pending"

func cancel() -> void:
	generation += 1
	due = 0
	if task != null: task.cancel()
	rows.clear()
	measured_delays.clear()
	if is_instance_valid(listing): listing.clear()
	if is_instance_valid(canvas):
		canvas.density_cells.clear()
		canvas.queue_redraw()

func _process(_delta: float) -> void:
	if worker.is_started():
		if worker.is_alive(): return
		var result: Dictionary = worker.wait_to_finish()
		var stale: bool = running_generation != generation or task.stopped()
		task = null
		if not stale:
			if result.ok:
				rows = result.data.chunk_costs
				cached = rows.duplicate(true)
				_show_rows()
			else: details.text = "Chunk analysis: " + str(result.error.message)
	if due == 0 or Time.get_ticks_msec() < due or store.has_gesture() or (busy_source.is_valid() and busy_source.call()): return
	due = 0
	task = WORK.new()
	running_generation = generation
	var document: Dictionary = store.document.duplicate(true)
	var source: String = store.project_path
	var previous := cached.duplicate(true)
	var job := task
	var error := worker.start(func(): return job.run(document,source,"density",Vector2i.ZERO,previous,false))
	if error != OK:
		task = null
		details.text = "Chunk analysis could not start: " + error_string(error)

func _show_rows() -> void:
	listing.clear()
	canvas.density_cells.clear()
	var keys: Array = rows.keys()
	keys.sort_custom(func(a: String,b: String): return int(rows[a].work_bytes) > int(rows[b].work_bytes))
	for key: String in keys:
		var row: Dictionary = rows[key]
		listing.add_item("%s · %.1f MiB estimated · %s" % [key,float(row.work_bytes)/1048576.0,row.warning])
		listing.set_item_metadata(listing.item_count - 1,key)
		if not row.warning.is_empty(): canvas.density_cells.append(row.cell)
	details.text = "Estimated work memory: warning at 192 MiB; limit 256 MiB. Warnings do not block Save or Export."
	canvas.queue_redraw()

func _select(index: int) -> void:
	var row: Dictionary = rows[listing.get_item_metadata(index)]
	var bounds: Dictionary = store.document.bounds
	var size_cm := float(store.document.cell_size_cm)
	var center := [bounds.min[0]+(row.cell.x+0.5)*size_cm,bounds.min[1]+(row.cell.y+0.5)*size_cm]
	canvas.pan += canvas.size * 0.5 - canvas.screen(center)
	canvas.queue_redraw()
	details.text = "Cell %s · objects %d · triangles %d · building prisms %d · asset convexes %d · display %.1f MiB · work %.1f MiB (estimates)" % [listing.get_item_metadata(index),row.objects,row.triangles,row.building_prisms,row.asset_convexes,float(row.presentation_bytes)/1048576.0,float(row.work_bytes)/1048576.0]
	var key: String = listing.get_item_metadata(index)
	if measured_delays.has(key): details.text += " · measured preview preparation %.2f seconds" % measured_delays[key].seconds

func record_preview(cell: Vector2i, signature: String, seconds: float) -> void:
	measured_delays.erase("%d/%d" % [cell.x,cell.y])
	if seconds <= 5.0:
		details.text = "Preview ready: cell %s took %.2f seconds (measured preparation and attachment)." % [cell,seconds]
		return
	measured_delays["%d/%d" % [cell.x,cell.y]] = {"signature":signature,"seconds":seconds}
	details.text = "Slow preview: cell %s took %.2f seconds (measured preparation and attachment, separate from memory estimates)." % [cell,seconds]

func _exit_tree() -> void:
	if task != null: task.cancel()
	if worker.is_started(): worker.wait_to_finish()
