extends SceneTree
const STORE := preload("res://scripts/document_store.gd")
const SIGNS := preload("res://scripts/sign_authoring.gd")
const FILES := preload("res://scripts/authoring_files.gd")
var checks := 0
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message);quit(1);assert(value,message)
func run() -> void:
	var source := OS.get_environment("WORLD_THEME_ROOT")
	var packages := {}
	for name: String in ["polar","metropolis","countryside","middle-eastern","desert","jungle","southeast-asian"]:
		var folder := source.path_join(name)
		var store := STORE.new()
		var original := FileAccess.get_sha256(folder.path_join("document.json"))
		check(store.open_project(folder)=="","open "+name)
		var saved := ProjectSettings.globalize_path("user://world-save-"+name)
		check(store.save_project(saved)=="","Save As retains all sign/common files")
		check(store.open_project(saved)=="","reopen "+name)
		var output := saved+".memap"
		var result: Dictionary = JSON.parse_string(store.bridge.export_project(saved,output))
		check(result.ok,"export "+name+": "+str(result))
		check(FileAccess.get_sha256(output)==FileAccess.get_sha256(folder+".memap"),"exact package round trip "+name)
		packages[name]=result.data
		check(FileAccess.get_sha256(folder.path_join("document.json"))==original,"original untouched")
		# Missing files are tested only in the explicitly isolated saved copy.
		var sign: Dictionary={}
		for asset: Dictionary in store.document.assets:
			if asset.id=="map-writing":sign=asset
		check(not sign.is_empty(),"map owns language variant")
		var blob: PackedByteArray=FILES.read(saved.path_join(sign.path)).bytes
		DirAccess.remove_absolute(saved.path_join(sign.path))
		check(not JSON.parse_string(store.bridge.export_project(saved,saved+"-missing.memap")).ok,"missing sign never exports blank")
		check(FILES.write_new(saved.path_join(sign.path),blob)=="","restore test-owned source")
	# Exercise the real authoring panel and the existing detached asset worker.
	var ui: Control=load("res://main.tscn").instantiate();root.add_child(ui)
	await process_frame
	check(ui.canvas.author.recipe(6,"default")=="","recipe")
	check(ui.store.save_project(ProjectSettings.globalize_path("user://sign-ui"))=="","saved UI document")
	ui.author_panel.open()
	var panel: RefCounted=ui.author_panel.sign_panel
	var controls: Dictionary=panel.controls
	controls.id.text="authored-writing"
	controls.text.text="한빛 Café"
	controls.font_path.text=OS.get_environment("WORLD_SIGN_FONTS").path_join("NotoSansCJKkr-Regular.otf")
	controls.font_source.text="Noto / https://github.com/notofonts/noto-cjk"
	controls.font_license.text="OFL-1.1"
	controls.language.text="ko,en"
	controls.font_size.value=104
	await panel._bake()
	await wait_ui(ui)
	check(ui.store.document.assets.size()==1,"one sign adopted through UI")
	var first: Dictionary=ui.store.document.assets[0].duplicate(true)
	check(first.path.ends_with(".glb"),"UV surface with embedded offline PNG")
	check(ui.store.undo()=="" and ui.store.document.assets.is_empty() and ui.store.redo()=="","single binary Undo/Redo")
	check(ui.store.save_project(ui.store.project_path)=="","persist authored text metadata")
	ui.author_panel.hide()
	ui.canvas.author.options.asset_id="authored-writing"
	ui.author_panel.open()
	panel=ui.author_panel.sign_panel;controls=panel.controls
	check(controls.text.text=="한빛 Café" and controls.font_source.text.begins_with("Noto"),"selected sign restores editable text and provenance")
	controls.id.text="imported-writing"
	controls.image_path.text=OS.get_environment("WORLD_SIGN_OUTPUT").path_join("arabic.png")
	controls.language.text="ar"
	# Restored controls still invalidate an in-flight import by revision.
	panel._import()
	controls.language.text="en";controls.language.text_changed.emit("en")
	controls.language.text="ar";controls.language.text_changed.emit("ar")
	await wait_ui(ui)
	check(ui.store.document.assets.size()==1,"stale/reverted sign controls cannot adopt")
	panel._import();await wait_ui(ui)
	check(ui.store.document.assets.size()==2,"prepared Arabic PNG imported as distinct variant")
	check(ui.store.document.assets[0]==first,"common/existing sign unaffected by new writing")
	ui.store.dirty=false;ui.queue_free();await process_frame
	var file:=FileAccess.open(OS.get_environment("WORLD_EDITOR_REPORT"),FileAccess.WRITE)
	check(file!=null,"report path")
	file.store_string(JSON.stringify({"checks":checks,"packages":packages},"  ")+"\n")
	print("world_theme_validator: PASS (",checks," checks)")
	quit(0)
func wait_ui(ui: Control) -> void:
	var deadline:=Time.get_ticks_msec()+30000
	while ui.busy and Time.get_ticks_msec()<deadline: await process_frame
	check(not ui.busy,"asset worker completes: "+ui.author_panel.feedback.text)
