extends SceneTree
const EDITOR := preload("res://scripts/editor_main.gd")
const STORE := preload("res://scripts/document_store.gd")
const STYLE := preload("res://scripts/workbench_style.gd")
const I18N := preload("res://scripts/locale_text.gd")
const PRESETS := ["straight_extra_wide", "gentle90_extra_wide", "gentle90_extra_wide_left", "right90_extra_wide", "right90_extra_wide_left"]
var failures: Array[String] = []
func _initialize() -> void: run.call_deferred()
func check(value: bool, label: String) -> void:
	if not value: failures.append(label); push_error(label)
func settle(ui: Control) -> void:
	var deadline := Time.get_ticks_msec()+10000
	while ui.store.track_edit_busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.store.track_edit_busy, "bounded extra-wide edit completion")
func run() -> void:
	var ui := EDITOR.new(); root.add_child(ui); await process_frame
	var bench: Node = ui.track_workbench
	var icon_hashes := {}
	for preset in PRESETS:
		var label: String = bench.piece_name(preset)
		for code in ["en", "ko", "ja"]:
			TranslationServer.set_locale(code)
			var messages: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://translations/%s.json" % code)).messages
			check(messages.has(label) and I18N.t(label) == messages.get(label), "translated label " + code + " " + preset)
			ui.commands._filter(I18N.t(label))
			check(ui.commands.results.item_count > 0, "translated search " + code + " " + preset)
			bench.palette_tools._filter(I18N.t(label))
			check(bench.palette_tools.tiles.any(func(t): return t.id == "track.piece."+preset and t.button.visible), "palette search " + code + " " + preset)
		TranslationServer.set_locale("en")
		ui.commands._filter("track.piece."+preset)
		check(ui.commands.results.item_count > 0, "stable ID search " + preset)
		var icon := STYLE.icon("piece_"+preset)
		check(icon != null and not icon.get_image().is_invisible(), "visible SVG " + preset)
		var digest := icon.get_image().get_data().hex_encode().sha256_text()
		check(not icon_hashes.has(digest), "distinct SVG " + preset); icon_hashes[digest] = true
		check(digest != STYLE.icon("piece_"+preset.replace("_extra_wide", "")).get_image().get_data().hex_encode().sha256_text(), "extra-wide icon differs from ordinary " + preset)
		var before: Dictionary = ui.store.document.duplicate(true)
		var history: Array = ui.store.undo_stack.duplicate(true)
		bench.add_piece(preset)
		check(bench.placement.width_cm == 1200, "12m initial preview " + preset)
		check(bench.placement.preview_at(Vector3(200*PRESETS.find(preset),0,0)), "preview " + preset)
		var serial: int = bench.placement.serial
		bench.cancel_interaction()
		check(not bench.placement.commit(serial) and ui.store.document == before and ui.store.undo_stack == history, "cancel keeps document/history " + preset)
		bench.add_piece(preset)
		check(bench.placement.preview_at(Vector3(200*PRESETS.find(preset),0,0)) and bench.placement.commit(), "placement " + preset)
		await settle(ui)
		bench.placement.cancel(); bench.select_piece(bench.source.instances.size()-1); bench._properties()
		check(bench.width.item_count == 1 and bench.width.get_selected_id() == 1200, "fixed body width control " + preset)
		check(bench.port_widths.all(func(s): return s.min_value == 2 and s.max_value == 12 and s.value == 12), "12m default ports and 2–12m range " + preset)
		var after: Dictionary = ui.store.document.duplicate(true)
		ui._history(false); await settle(ui); check(ui.store.document == before, "Undo " + preset)
		ui._history(true); await settle(ui); check(ui.store.document == after, "Redo " + preset)
		# Ordinary continuation snaps to the wide exit and tapers back to 4m.
		var end: Vector3 = bench.PREVIEW.point(ui.store.document.assembled_track.pieces.back().path.back().position_cm)
		bench.add_piece("straight")
		check(bench.placement.width_cm == 400, "ordinary default preserved")
		check(bench.placement.preview_at(end) and bench.placement.candidate.snap >= 0 and bench.placement.commit(), "connected ordinary continuation " + preset)
		await settle(ui); bench.placement.cancel()
		var connected: Dictionary = bench.source.instances.back()
		check(connected.entry_width_cm == 1200 and connected.exit_width_cm == 400, "connected width transition " + preset)
	var path := ProjectSettings.globalize_path("user://extra-wide-project")
	check(ui.store.save_project(path) == "", "save five extra-wide presets")
	var reopened := STORE.new()
	check(reopened.open_project(path) == "", "reopen five extra-wide presets")
	check(reopened.document.assembled_track == JSON.parse_string(JSON.stringify(ui.store.document.assembled_track)), "reopen preserves source, graph and geometry")
	ui.store.dirty = false; ui.queue_free(); await process_frame; await process_frame
	print("extra_wide_track_validator: ", "PASS" if failures.is_empty() else failures)
	quit(0 if failures.is_empty() else 1)
