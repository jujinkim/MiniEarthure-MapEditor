extends SceneTree
const SIGNS := preload("res://scripts/sign_authoring.gd")
const FILES := preload("res://scripts/authoring_files.gd")
func _initialize() -> void: run.call_deferred()
func check(value: bool, message: String) -> void:
	if not value:
		push_error(message)
		quit(1)
		assert(value,message)
func run() -> void:
	var fonts := OS.get_environment("WORLD_SIGN_FONTS")
	var output := OS.get_environment("WORLD_SIGN_OUTPUT")
	check(not fonts.is_empty() and not output.is_empty(), "explicit input/output")
	DirAccess.make_dir_recursive_absolute(output)
	var report := {}
	for entry: Array in [
		["korean", "한빛 Café", "ko", "ltr", "NotoSansCJKkr-Regular.otf", 104],
		["latin", "Café · Field Station", "en", "ltr", "NotoSans-Regular.ttf", 76],
		["arabic", "سُوق النور", "ar", "rtl", "NotoSansArabic-Regular.ttf", 100],
		["thai", "ร้านริมคลอง", "th", "ltr", "NotoSansThai-Regular.ttf", 104]]:
		var spec := {"text":entry[1],"language":entry[2],"direction":entry[3],"font_path":fonts.path_join(entry[4]),
			"font_source":"Noto / https://github.com/notofonts/" + ("noto-cjk" if entry[0]=="korean" else "noto-fonts"), "font_license":"OFL-1.1", "font_size":entry[5], "alignment":"center"}
		var result := await SIGNS.bake(root, spec)
		check(not result.has("error"), str(entry[0])+": "+str(result.get("error","")))
		if result.has("error"): return
		var rtl := 0
		for glyph: Dictionary in result.glyphs:
			if int(glyph.flags) & TextServer.GRAPHEME_IS_RTL: rtl += 1
		if entry[0]=="arabic": check(rtl>0,"Arabic shaped RTL runs")
		if entry[0] in ["thai","arabic"]: check(result.glyphs.size()>0,"combining script shaped")
		check(FILES.write_new(output.path_join(entry[0]+".png"),result.bytes)=="","immutable PNG")
		var surface := SIGNS.SURFACE.encode(result.bytes,300,110)
		check(FILES.write_new(output.path_join(entry[0]+".glb"),surface)=="","unit UV embedded PNG")
		result.metadata["glb_sha256"]=FILES.digest(surface)
		var f := FileAccess.open(output.path_join(entry[0]+".json"),FileAccess.WRITE)
		f.store_string(JSON.stringify(result.metadata,"  ")+"\n");f.close()
		report[entry[0]]={"metadata":result.metadata,"glyph_count":result.glyphs.size(),"rtl_glyphs":rtl,"bytes":result.bytes.size()}
		var bad: Dictionary = spec.duplicate(true)
		bad.text = String.chr(0x10FFFF)
		check((await SIGNS.bake(root,bad)).has("error"),"missing glyph rejected without fallback")
		bad.text = "A".repeat(128)
		check((await SIGNS.bake(root,bad)).has("error"),"overflow rejects without clipping")
		check((await SIGNS.bake(root,spec,func(): return false)).has("error"),"cancelled raster cannot adopt")
		print("sign bake: ",entry[0])
	var file := FileAccess.open(output.path_join("bake-report.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  ")+"\n");file.close()
	print("sign_bake_validator: PASS")
	quit(0)
