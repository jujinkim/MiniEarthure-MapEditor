extends RefCounted
## Verify provider attribution through the actual paged UI, not a full summary dump.
static func source_readable(ui: Control, metadata: String, collection: String = "feature_sources") -> bool:
	ui._open_import_details()
	var browser: AcceptDialog = ui.import_details
	var result: bool = browser.visible
	for key in ["coordinates", metadata, collection, 0, "sources", 0, "dataset"]:
		var index: int = browser.page_keys.find(key)
		if index < 0:
			result = false
			break
		browser.descend(index)
	result = result and JSON.parse_string(browser.content.text) == "synthetic fixture"
	browser.clear()
	return result
